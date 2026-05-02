from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 映射配置 完全保留 =====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"

# 加载频道别名映射 统一标准名
def load_alias_map():
    alias_map = {}
    if os.path.exists(ALIAS_FILE):
        with open(ALIAS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "," not in line:
                    continue
                sp = [p.strip() for p in line.split(",")]
                std = sp[0]
                for old_name in sp[1:]:
                    alias_map[old_name] = std
    return alias_map

# 加载demo分类顺序
def load_demo_order():
    cate_list = []
    cate_chan = {}
    now_cate = ""
    if os.path.exists(DEMO_FILE):
        with open(DEMO_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.endswith(",#genre#"):
                    now_cate = line.replace(",#genre#","")
                    cate_list.append(now_cate)
                    cate_chan[now_cate] = []
                elif now_cate:
                    cate_chan[now_cate].append(line)
    return cate_list, cate_chan

# ===================== 原版基础函数 全部原样不动 =====================
def read_config(config_file):
    print(f"读取设置文件：{config_file}")
    ip_configs = []
    try:
        with open(config_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if "," in line and not line.startswith("#"):
                    parts = line.strip().split(',')
                    ip_part, port = parts[0].strip().split(':')
                    a, b, c, d = ip_part.split('.')
                    option = int(parts[1]) 
                    url_end = "/status" if option >= 10 else "/stat"
                    ip = f"{a}.{b}.{c}.1" if option % 2 == 0 else f"{a}.{b}.1.1"
                    ip_configs.append((ip, port, option, url_end))
                    print(f"第{line_num}行：http://{ip}:{port}{url_end} 添加到扫描列表")
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

# 单独检测单个ip_port是否有效
def check_ip_port(ip_port, url_end):    
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=2)
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            print(f"{url} 访问成功")
            return ip_port
    except:
        return None

# 批量多线程扫描IP段
def scan_ip_port(ip, port, option, url_end):
    def show_progress():
        while checked[0] < len(ip_ports) and option % 2 == 1:
            print(f"已扫描：{checked[0]}/{len(ip_ports)}, 有效ip_port：{len(valid_ip_ports)}个")
            time.sleep(30)
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    checked = [0]
    Thread(target=show_progress, daemon=True).start()
    with ThreadPoolExecutor(max_workers = 300 if option % 2 == 1 else 100) as executor:
        futures = {executor.submit(check_ip_port, ip_port, url_end): ip_port for ip_port in ip_ports}
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid_ip_ports.append(result)
            checked[0] += 1
    return valid_ip_ports

# 单独扫描检测 历史存档旧IP
def scan_old_archive_ip(ip_port):
    # 自动适配两种后缀 兼容旧存档所有格式
    url_end_list = ["/stat", "/status"]
    for end in url_end_list:
        res = check_ip_port(ip_port, end)
        if res:
            return res
    return None

# ===================== 核心重写：单省扫描逻辑 新旧IP一起参与扫描 =====================
def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"{'='*25}\n   获取: {province}ip_port\n{'='*25}")
    configs = sorted(set(read_config(config_file)))
    print(f"读取完成，共需扫描【新配置】{len(configs)}组")

    # 1. 先扫描本次配置里的新IP段
    new_scan_ips = []
    for ip, port, option, url_end in configs:
        print(f"\n开始扫描新网段  http://{ip}:{port}{url_end}")
        new_scan_ips.extend(scan_ip_port(ip, port, option, url_end))

    # 2. 读取历史存档旧IP，全部加入扫描队列 重新校验存活
    archive_old_ips = []
    archive_path = f"ip/存档_{province}_ip.txt"
    if os.path.exists(archive_path):
        with open(archive_path, 'r', encoding='utf-8') as f:
            archive_old_ips = [line.strip() for line in f.readlines() if line.strip()]
        print(f"\n读取历史存档旧IP：{len(archive_old_ips)} 个，开始逐个重新扫描校验")

    # 3. 多线程批量扫描所有存档旧IP，只保留现在还能用的
    old_valid_ips = []
    if archive_old_ips:
        with ThreadPoolExecutor(max_workers=150) as executor:
            futures = {executor.submit(scan_old_archive_ip, ip): ip for ip in archive_old_ips}
            for future in as_completed(futures):
                ret = future.result()
                if ret:
                    old_valid_ips.append(ret)

    # 4. 新扫描有效IP + 旧存档扫描存活IP 合并去重
    all_valid_ips = sorted(list(set(new_scan_ips + old_valid_ips)))

    if len(all_valid_ips) != 0:
        print(f"\n{province} 本次新扫描有效：{len(new_scan_ips)} 个 | 旧存档重扫存活：{len(old_valid_ips)} 个")
        print(f"{province} 合并全部当下可用有效IP总数：{len(all_valid_ips)} 个\n")

        # 覆盖写入本省ip.txt 供后续生成组播文件使用
        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_valid_ips))

        # 保留原代码原版逻辑：新IP继续追加写入存档 永久累加备份
        if os.path.exists(archive_path):
            with open(archive_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for ip_port in new_scan_ips:
                    ip, port = ip_port.split(":")
                    a, b, c, d = ip.split(".")
                    lines.append(f"{a}.{b}.{c}.1:{port}\n")
                lines = sorted(set(lines))
            with open(archive_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)    

        # 套用模板 生成单省组播文件 原版逻辑不变
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
        print(f"\n{province} 新扫描无有效IP、旧存档重扫无存活IP")

# 原版原生m3u转换函数 完全不变 播放器完美识别
def txt_to_m3u(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, 'w', encoding='utf-8') as f:
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

# 原版合并后 统一频道名+demo分类重排
def reorder_channel_content(origin_merge_text):
    alias_map = load_alias_map()
    cate_order, cate_chan_dict = load_demo_order()

    all_channel_data = []
    lines = origin_merge_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.endswith(",#genre#"):
            continue
        if "," in line:
            name, url = line.split(",", 1)
            new_name = alias_map.get(name.strip(), name.strip())
            all_channel_data.append( (new_name, url.strip()) )

    res = []
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    time_str = now.strftime("%Y/%m/%d %H:%M")
    res.append("更新时间,#genre#\n")
    res.append(f"{time_str},http://127.0.0.1\n\n")

    for cate in cate_order:
        res.append(f"{cate},#genre#\n")
        for std_chan in cate_chan_dict[cate]:
            for chan_name, chan_url in all_channel_data:
                if chan_name == std_chan:
                    res.append(f"{chan_name},{chan_url}\n")
        res.append("\n")

    return "".join(res)

# ===================== 主函数 完整原版流程 一步没改 =====================
def main():
    # 1.逐省扫描：新IP段扫描 + 旧存档IP重扫校验存活
    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    # 2.恢复原版 所有省份组播文件合并逻辑
    file_contents = []
    for file_path in glob.glob('组播_*电信.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            content = f.read()
            file_contents.append(content)
    for file_path in glob.glob('组播_*联通.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            content = f.read()
            file_contents.append(content)
    
    # 3.生成原版标准格式合并文本
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")
    origin_total = f"{current_time}更新,#genre#\n"
    origin_total += f"浙江卫视,http://ali-m-l.cztv.com/channels/lantian/channel001/1080p.m3u8\n"
    origin_total += '\n'.join(file_contents)

    # 4.合并完成后 统一频道名+按demo分类排序
    final_total = reorder_channel_content(origin_total)

    # 5.写入最终汇总txt
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(final_total)

    # 6.原版函数转m3u 格式标准 播放器正常识别
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print("="*40)
    print("全部执行完成：")
    print("1.新IP段扫描完成  2.历史存档旧IP重扫校验存活")
    print("3.新旧有效IP合并复用  4.原版写入存档、合并、改名分类、m3u生成全部正常")
    print("="*40)

if __name__ == "__main__":
    main()
