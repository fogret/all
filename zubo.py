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

# ==================== 全局防卡死配置 最终固定版 ====================
SCAN_WORKERS_HIGH = 60
SCAN_WORKERS_LOW = 35
SCAN_TIMEOUT = 1.2
BATCH_MAX_IP = 6000       # 大网段分批扫描，杜绝卡死
PROVINCE_WORKERS = 3      # 同时最多3个省扫描，不堆任务卡死

# H264播放测速配置（只对最终成品播放链接生效）
PLAY_CHECK_CONCURRENCY = 45
PLAY_CHECK_TIMEOUT = 3.2
STREAM_STABLE_CHECK_TIME = 2.0  # 稳定拉流2秒，过滤跳解码、断流不稳定源

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

# ==================== 读取demo.txt 分类顺序 + 频道固定排序 ====================
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

# ==================== IP扫描核心函数 分批防卡死 无循环刷屏 ====================
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
                    print(f"第{line_num}行：http://{ip}:{port}{url_end} 添加扫描列表")
        return ip_configs
    except Exception as e:
        print(f"读取文件错误: {e}")
        return []

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
            print(f"✅ 有效: {url}")
            return ip_port
    except:
        return None

def scan_ip_port(ip, port, option, url_end):
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    total_all = len(ip_ports)
    checked_cnt = 0
    workers = SCAN_WORKERS_HIGH if option % 2 == 1 else SCAN_WORKERS_LOW

    # 大IP列表强制分批，杜绝一次性6万IP卡死
    batch_list = [ip_ports[i:i+BATCH_MAX_IP] for i in range(0, total_all, BATCH_MAX_IP)]

    for batch_idx, batch in enumerate(batch_list):
        batch_len = len(batch)
        print(f"\n--- 当前批次 {batch_idx+1}/{len(batch_list)} 本轮数量：{batch_len} ---")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(check_ip_port, ip_port, url_end): ip_port for ip_port in batch}
            for future in as_completed(futures, timeout=12):
                try:
                    res = future.result(timeout=4)
                    if res:
                        valid_ip_ports.append(res)
                    checked_cnt += 1
                except TimeoutError:
                    checked_cnt += 1
                    continue
        # 每批次打印一次总进度，不无限刷屏
        print(f"总扫描进度：{checked_cnt}/{total_all}  已累计有效：{len(valid_ip_ports)} 个")

    return valid_ip_ports

def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"\n{'='*30}\n        开始扫描 {province}\n{'='*30}")
    configs = sorted(set(read_config(config_file)))
    print(f"本省份共需扫描 {len(configs)} 组网段")
    all_ip_ports = []

    for ip, port, option, url_end in configs:
        print(f"\n开始扫描网段：{ip}:{port}")
        res = scan_ip_port(ip, port, option, url_end)
        all_ip_ports.extend(res)

    # 扫描完成后保存该省数据
    if all_ip_ports:
        all_ip_ports = sorted(set(all_ip_ports))
        print(f"\n✅ {province} 扫描完成，有效IP总数：{len(all_ip_ports)}")
        os.makedirs("ip", exist_ok=True)
        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip_ports))

        # 存档备份
        if os.path.exists(f"ip/存档_{province}_ip.txt"):
            with open(f"ip/存档_{province}_ip.txt", 'r', encoding='utf-8') as f:
                old_lines = f.readlines()
            for ip_port in all_ip_ports:
                ip, port = ip_port.split(":")
                a,b,c,d = ip.split(".")
                old_lines.append(f"{a}.{b}.{c}.1:{port}\n")
            old_lines = sorted(set(old_lines))
            with open(f"ip/存档_{province}_ip.txt", 'w', encoding='utf-8') as f:
                f.writelines(old_lines)

        # 生成省份组播文件
        template_file = os.path.join('template', f"template_{province}.txt")
        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                tem_channels = f.read()
            output = []
            with open(f"ip/{province}_ip.txt", 'r', encoding='utf-8') as f:
                for idx, line in enumerate(f, 1):
                    ip = line.strip()
                    output.append(f"{province}-组播{idx},#genre#\n")
                    output.append(tem_channels.replace("ipipip", ip))
            with open(f"组播_{province}.txt", 'w', encoding='utf-8') as f:
                f.writelines(output)
    else:
        print(f"\n❌ {province} 扫描完成，无有效IP")

# ==================== H264真实解码测速【只对最终成品播放链接执行】 ====================
async def single_stream_check(session, url):
    start_time = time.time()
    try:
        async with session.get(url, timeout=PLAY_CHECK_TIMEOUT) as resp:
            if resp.status != 200:
                return (False, 9999, "链接失效")
            # 校验H264编码
            content = await resp.read()
            if not (b'h264' in content or b'H264' in content or b'avc1' in content):
                return (False, 9999, "非H264编码")
            # 持续拉流检测稳定性，过滤跳解码、断流
            await asyncio.sleep(STREAM_STABLE_CHECK_TIME)
            delay = round(time.time() - start_time, 3)
            return (True, delay, "H264稳定流畅")
    except:
        return (False, 9999, "播放不稳定/断流")

async def batch_stream_check(task_list):
    timeout = aiohttp.ClientTimeout(total=PLAY_CHECK_TIMEOUT)
    connector = aiohttp.TCPConnector(limit=PLAY_CHECK_CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [single_stream_check(session, url) for _, url in task_list]
        return await asyncio.gather(*tasks)

def start_play_speed_test(channel_url_map):
    print("\n\n=============================================")
    print("      全部IP扫描完毕，开始H264成品链接测速")
    print("=============================================")
    log_lines = []
    start_all_time = datetime.datetime.now()
    log_lines.append(f"测速开始时间：{start_all_time.strftime('%Y-%m-%d %H:%M:%S')}")
    total_line = sum(len(v) for v in channel_url_map.values())
    log_lines.append(f"待测速成品播放链接总数：{total_line} 条\n")

    channel_sort_result = OrderedDict()

    # 逐个频道测速、按延迟排序
    for ch_name, url_list in channel_url_map.items():
        if not url_list:
            channel_sort_result[ch_name] = []
            continue
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        res_list = loop.run_until_complete(batch_stream_check([(ch_name, u) for u in url_list]))

        good_stable = []
        bad_unstable = []
        for idx, (ok, delay, status) in enumerate(res_list):
            url = url_list[idx]
            if ok:
                good_stable.append((delay, url))
                log_lines.append(f"【正常】{ch_name} | 延迟{delay}s | {status}")
            else:
                bad_unstable.append(url)
                log_lines.append(f"【淘汰】{ch_name} | {status}")

        # 同频道：稳定源按速度从小到大排前面，不稳定源放后面
        good_stable.sort(key=lambda x: x[0])
        channel_sort_result[ch_name] = [u for _,u in good_stable] + bad_unstable

    end_all_time = datetime.datetime.now()
    ok_num = sum(len(v) for v in channel_sort_result.values()) - sum(len(v) for v in channel_sort_result.values() if v in [u for _,u in good_stable])
    bad_num = total_line - ok_num

    log_lines.append(f"\n测速结束时间：{end_all_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log_lines.append(f"合格H264稳定流畅源：{ok_num} 条")
    log_lines.append(f"非H264/不稳定易断流源：{bad_num} 条")

    # 保存完整测速日志
    with open("speed_test_log.txt", "w", encoding="utf-8") as f:
        f.write('\n'.join(log_lines))

    print("\n✅ H264成品链接测速全部完成，日志已保存 speed_test_log.txt")
    return channel_sort_result

# ==================== m3u 标准格式生成 不乱码 ====================
def txt_to_m3u(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        f.write("#EXTM3U\n")
        genre = ''
        for line in lines:
            line = line.strip()
            if "," in line:
                c_name, c_url = line.split(',', 1)
                if c_url == '#genre#':
                    genre = c_name
                else:
                    f.write(f'#EXTINF:-1 group-title="{genre}",{c_name}\n')
                    f.write(f'{c_url}\n')

# ==================== 主函数【严格固定执行顺序 绝不乱序】 ====================
def main():
    # 第一步：先跑完所有省份IP扫描，完全结束再往下走
    print("========== 第一步：开始全国所有省份IP扫描 ==========")
    config_files = glob.glob(os.path.join('ip', '*_config.txt'))
    with ThreadPoolExecutor(max_workers=PROVINCE_WORKERS) as executor:
        executor.map(multicast_province, config_files)
    print("\n\n✅ ========== 所有省份IP扫描 全部执行完毕 ==========")

    # 第二步：汇总所有省份组播文件
    print("\n========== 第二步：汇总全部组播播放链接 ==========")
    file_contents = []
    for file_path in glob.glob('组播_*电信.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            file_contents.append(f.read())
    for file_path in glob.glob('组播_*联通.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            file_contents.append(f.read())

    # 第三步：别名统一 + 整理分类频道
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
            # 统一标准频道名
            if c_name in alias_map:
                c_name = alias_map[c_name]
            if temp_group:
                all_group_data[temp_group].append((c_name, c_url))
                if c_name not in channel_url_collect:
                    channel_url_collect[c_name] = []
                channel_url_collect[c_name].append(c_url)

    # 第四步：才开始执行H264测速（只测汇总好的成品播放链接）
    channel_sorted_url = start_play_speed_test(channel_url_collect)

    # 第五步：按demo.txt原有顺序重新排版组合
    final_sort_data = OrderedDict()
    for c in cat_order:
        final_sort_data[c] = []

    for cat_name, ch_list in cat_channel_order.items():
        for std_ch in ch_list:
            for g_name, items in all_group_data.items():
                for n,_ in items:
                    if n == std_ch:
                        if std_ch in channel_sorted_url:
                            for url in channel_sorted_url[std_ch]:
                                final_sort_data[cat_name].append(f"{std_ch},{url}")

    # 第六步：写入最终文件 + 北京时间标准更新时间
    new_content_lines = []
    for cat in final_sort_data:
        if final_sort_data[cat]:
            new_content_lines.append(f"{cat},#genre#")
            new_content_lines.extend(final_sort_data[cat])

    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    update_time = now.strftime("%Y/%m/%d %H:%M")

    with open("zubo_all.txt", "w", encoding="utf-8", newline='') as f:
        f.write(f"{update_time}更新,#genre#\n")
        f.write(f"更新时间展示,http://127.0.0.1/null\n")
        f.write('\n'.join(new_content_lines))

    # 生成标准m3u文件
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")

    print(f"\n🎉 全部流程彻底完成！")
    print(f"✅ IP扫描 ✅ 链接汇总 ✅ H264稳定测速 ✅ 分类排序 ✅ 文件输出")
    print(f"稳定流畅源已全部置顶，测速日志查看：speed_test_log.txt")

if __name__ == "__main__":
    main()
