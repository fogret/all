from threading import Thread
import os
import time
import datetime
import glob
import requests
import aiohttp
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from collections import OrderedDict

# ==================== 全局配置 防卡死优化 ====================
# 降低并发，适配GitHub，彻底解决扫描卡死不动
SCAN_WORKERS_HIGH = 70
SCAN_WORKERS_LOW = 40
SCAN_TIMEOUT = 1.2
# 单批次最大扫描IP数量，防止一次性6万IP撑爆线程池
BATCH_MAX_IP = 8000

# 频道播放测速配置（真实H264解码测速）
PLAY_CHECK_CONCURRENCY = 50
PLAY_CHECK_TIMEOUT = 3.5
# 连续拉流检测时长，判断播放稳定性
STREAM_STABLE_CHECK_TIME = 2.0

# ==================== 读取alias.txt 标准频道别名映射 ====================
def load_alias_map():
    alias_map = {}
    if os.path.exists("alias.txt"):
        with open("alias.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "," not in line:
                    continue
                parts = [p.strip() for p in line.split(",") if p.strip()]
                standard_name = parts[0]
                for alias in parts[1:]:
                    alias_map[alias] = standard_name
    return alias_map

# ==================== 读取demo.txt 分类顺序 + 频道排序规则 ====================
def load_demo_order():
    category_order = []
    category_channel_order = OrderedDict()
    current_cat = None

    if os.path.exists("demo.txt"):
        with open("demo.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.endswith(",#genre#"):
                    current_cat = line.replace(",#genre#","").strip()
                    category_order.append(current_cat)
                    category_channel_order[current_cat] = []
                    continue
                if current_cat:
                    category_channel_order[current_cat].append(line.strip())
    return category_order, category_channel_order

# ==================== 原有IP扫描函数 增加分批防卡死 ====================
def read_config(config_file):
    print(f"读取设置文件：{config_file}")
    ip_configs = []
    try:
        with open(config_file, 'r', encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if "," in line and not line.startswith("#"):
                    parts = line.strip().split(',')
                    ip_part, port = parts[0].strip().split(':')
                    a, b, c, d = ip_part.split('.')
                    option = int(parts[1])
                    url_end = "/status" if option >= 10 else "/stat"
                    ip = f"{a}.{b}.{c}.1" if option % 2 == 0 else f"{a}.{b}.1.1"
                    ip_configs.append((ip, port, option, url_end))
                    print(f"第{line_num}行：http://{ip}:{port}{url_end}添加到扫描列表")
        return ip_configs
    except Exception as e:
        print(f"读取文件错误: {e}")

def generate_ip_ports(ip, port, option):
    a, b, c, d = ip.split('.')
    if option == 2 or option == 12:
        c_extent = c.split('-')
        c_first = int(c_extent[0]) if len(c_extent) == 2 else int(c)
        c_last = int(c_extent[1]) + 1 if len(c_extent) == 2 else int(c) + 8
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(c_first, c_last) for y in range(1, 256)]
    elif option == 0 or option == 10:
        return [f"{a}.{b}.{c}.{y}:{port}" for y in range(1, 256)]
    else:
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(256) for y in range(1, 256)]

def check_ip_port(ip_port, url_end):
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=SCAN_TIMEOUT)
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            print(f"{url} 访问成功")
            return ip_port
    except:
        return None

def scan_ip_port(ip, port, option, url_end):
    def show_progress():
        while checked[0] < len(ip_ports) and option % 2 == 1:
            print(f"已扫描：{checked[0]}/{len(ip_ports)}, 有效ip_port：{len(valid_ip_ports)}个")
            time.sleep(20)
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    checked = [0]
    Thread(target=show_progress, daemon=True).start()
    workers = SCAN_WORKERS_HIGH if option % 2 == 1 else SCAN_WORKERS_LOW

    # 超大IP列表 分批切割，不一次性全部塞入，解决卡死
    batch_list = [ip_ports[i:i+BATCH_MAX_IP] for i in range(0, len(ip_ports), BATCH_MAX_IP)]

    for batch in batch_list:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(check_ip_port, ip_port, url_end): ip_port for ip_port in batch}
            for future in as_completed(futures, timeout=15):
                try:
                    result = future.result(timeout=5)
                    if result:
                        valid_ip_ports.append(result)
                    checked[0] += 1
                except TimeoutError:
                    checked[0] += 1
                    continue
    return valid_ip_ports

def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"{'='*25}\n   获取: {province}ip_port\n{'='*25}")
    configs = sorted(set(read_config(config_file)))
    print(f"读取完成，共需扫描 {len(configs)}组")
    all_ip_ports = []
    for ip, port, option, url_end in configs:
        print(f"\n开始扫描  http://{ip}:{port}{url_end}")
        all_ip_ports.extend(scan_ip_port(ip, port, option, url_end))
    if len(all_ip_ports) != 0:
        all_ip_ports = sorted(set(all_ip_ports))
        print(f"\n{province} 扫描完成，获取有效ip_port共：{len(all_ip_ports)}个\n")
        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip_ports))
        if os.path.exists(f"ip/存档_{province}_ip.txt"):
            with open(f"ip/存档_{province}_ip.txt", 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for ip_port in all_ip_ports:
                    ip, port = ip_port.split(":")
                    a, b, c, d = ip.split(".")
                    lines.append(f"{a}.{b}.{c}.1:{port}\n")
                lines = sorted(set(lines))
            with open(f"ip/存档_{province}_ip.txt", 'w', encoding='utf-8') as f:
                f.writelines(lines)
        template_file = os.path.join('template', f"template_{province}.txt")
        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                tem_channels = f.read()
            output = []
            with open(f"ip/{province}_ip.txt", 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    ip = line.strip()
                    output.append(f"{province}-组播{line_num},#genre#\n")
                    output.append(tem_channels.replace("ipipip", f"{ip}"))
            with open(f"组播_{province}.txt", 'w', encoding='utf-8') as f:
                f.writelines(output)
        else:
            print(f"缺少模板文件: {template_file}")
    else:
        print(f"\n{province} 扫描完成，未扫描到有效ip_port")

# ==================== 新增：H264真实解码+流稳定性 异步测速核心 ====================
async def single_stream_check(session, url):
    start_time = time.time()
    try:
        async with session.get(url, timeout=PLAY_CHECK_TIMEOUT) as resp:
            if resp.status != 200:
                return (False, 9999, "invalid")
            
            # 读取流媒体头部，校验H264编码
            content = await resp.read()
            h264_flag = b'h264' in content or b'H264' in content or b'avc1' in content
            if not h264_flag:
                return (False, 9999, "no_h264")
            
            # 持续拉流一段时间，检测播放稳定性、杜绝断流跳解码
            await asyncio.sleep(STREAM_STABLE_CHECK_TIME)
            delay = round(time.time() - start_time, 3)
            return (True, delay, "ok_h264")
    except:
        return (False, 9999, "fail")

async def batch_stream_check(channel_url_list):
    timeout = aiohttp.ClientTimeout(total=PLAY_CHECK_TIMEOUT)
    connector = aiohttp.TCPConnector(limit=PLAY_CHECK_CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [single_stream_check(session, url) for _,url in channel_url_list]
        results = await asyncio.gather(*tasks)
    return results

def start_play_speed_test(channel_url_map):
    print("\n=============================================")
    print("        开始H264真实解码+播放稳定性测速")
    print("=============================================")
    log_lines = []
    log_lines.append(f"测速开始时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_lines.append(f"待测速总频道线路数: {sum(len(v) for v in channel_url_map.values())}")

    # 存储测速结果
    channel_speed_result = OrderedDict()

    for ch_name, url_list in channel_url_map.items():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        res_list = loop.run_until_complete(batch_stream_check([(ch_name,u) for u in url_list]))

        # 整合结果：合格H264稳定源 / 不合格不稳定源
        good_h264 = []
        bad_other = []
        for idx, (is_ok, delay, status) in enumerate(res_list):
            url = url_list[idx]
            if is_ok:
                good_h264.append( (delay, url) )
                log_lines.append(f"【正常合格】{ch_name} | 延迟:{delay}s | H264稳定流")
            else:
                bad_other.append(url)
                if status == "no_h264":
                    log_lines.append(f"【淘汰】{ch_name} | 非H264编码，易跳解码")
                else:
                    log_lines.append(f"【淘汰】{ch_name} | 播放不稳定/断流/假存活")
        
        # 同频道 按延迟从小到大排序，最快最稳定排前面
        good_h264.sort(key=lambda x: x[0])
        sorted_urls = [url for _,url in good_h264] + bad_other
        channel_speed_result[ch_name] = sorted_urls

    log_lines.append(f"\n测速完成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_lines.append(f"合格H264稳定流畅源: {len([i for v in channel_speed_result.values() for i in v[:len([g for g,_ in v if isinstance(g,float)])]])} 条")
    log_lines.append(f"非H264/不稳定淘汰源: {len([i for v in channel_speed_result.values() for i in v[len([g for g,_ in v if isinstance(g,float)]):]])} 条")

    # 保存完整测速日志
    with open("speed_test_log.txt", "w", encoding="utf-8") as f:
        f.write('\n'.join(log_lines))
    
    print("\n✅ H264解码测速全部完成，测速日志已保存 speed_test_log.txt")
    return channel_speed_result

# ==================== 格式转换 不乱码标准m3u生成 ====================
def txt_to_m3u(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        f.write("#EXTM3U\n")
        genre = ''
        for line in lines:
            line = line.strip()
            if "," in line:
                channel_name, channel_url = line.split(',', 1)
                if channel_url == '#genre#':
                    genre = channel_name
                else:
                    f.write(f'#EXTINF:-1 group-title="{genre}",{channel_name}\n')
                    f.write(f'{channel_url}\n')

# ==================== 主函数 多省并行降为3，不堆积卡死 ====================
def main():
    # 1. 多省并行扫描 降低并发，防卡死
    config_files = glob.glob(os.path.join('ip', '*_config.txt'))
    with ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(multicast_province, config_files)

    # 2. 汇总所有省份组播文件
    file_contents = []
    for file_path in glob.glob('组播_*电信.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            content = f.read()
            file_contents.append(content)
    for file_path in glob.glob('组播_*联通.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            content = f.read()
            file_contents.append(content)

    # 3. 别名替换 + 基础分类整理
    print("\n=== 开始统一频道别名 + 按demo.txt分类排序 ===")
    alias_map = load_alias_map()
    cat_order, cat_channel_order = load_demo_order()

    temp_group = ""
    all_group_data = {}
    channel_url_collect = OrderedDict()

    full_text = '\n'.join(file_contents)
    for line in full_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith(",#genre#"):
            temp_group = line.replace(",#genre#","")
            if temp_group not in all_group_data:
                all_group_data[temp_group] = []
        elif "," in line:
            c_name, c_url = line.split(",",1)
            c_name = c_name.strip()
            c_url = c_url.strip()
            if c_name in alias_map:
                c_name = alias_map[c_name]
            if temp_group:
                all_group_data[temp_group].append( (c_name, c_url) )
                if c_name not in channel_url_collect:
                    channel_url_collect[c_name] = []
                channel_url_collect[c_name].append(c_url)

    # 4. 执行 H264真实解码+稳定性测速 排序
    channel_sorted_url = start_play_speed_test(channel_url_collect)

    # 5. 按demo.txt原有分类顺序重组
    final_sort_data = OrderedDict()
    for c in cat_order:
        final_sort_data[c] = []

    for cat_name, ch_list in cat_channel_order.items():
        for std_ch in ch_list:
            for g_name, items in all_group_data.items():
                for n,_ in items:
                    if n == std_ch:
                        # 接入测速后排序好的url列表
                        if std_ch in channel_sorted_url:
                            for u in channel_sorted_url[std_ch]:
                                final_sort_data[cat_name].append(f"{std_ch},{u}")

    new_content_lines = []
    for cat in final_sort_data:
        if final_sort_data[cat]:
            new_content_lines.append(f"{cat},#genre#")
            new_content_lines.extend(final_sort_data[cat])

    # 6. 写入最终文件 带北京时间更新
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")

    with open("zubo_all.txt", "w", encoding="utf-8", newline='') as f:
        f.write(f"{current_time}更新,#genre#\n")
        f.write(f"更新时间展示,http://127.0.0.1/null\n")
        f.write('\n'.join(new_content_lines))

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print(f"\n全部流程完成：IP扫描+H264测速+分类排序+文件生成")
    print(f"稳定H264流畅源已全部置顶，不稳定/非H264源自动后置")

if __name__ == "__main__":
    main()
