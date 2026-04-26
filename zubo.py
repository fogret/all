# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 读取频道别名映射 alias.txt ====================
def load_alias_map():
    alias_map = {}
    if os.path.exists(ALIAS_FILE):
        with open(ALIAS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or ',' not in line:
                    continue
                parts = [p.strip() for p in line.split(',') if p.strip()]
                if len(parts) < 2:
                    continue
                standard = parts[0]
                for alias in parts[1:]:
                    alias_map[alias] = standard
    return alias_map

# ==================== 读取分类与频道 demo.txt ====================
def load_demo_category():
    category_channels = []
    current_genre = None
    if os.path.exists(DEMO_FILE):
        with open(DEMO_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if ',#genre#' in line:
                    current_genre = line.split(',')[0].strip()
                    category_channels.append((current_genre, None))
                else:
                    if current_genre is not None:
                        category_channels.append((current_genre, line))
    return category_channels

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
                    print(f"第{line_num}行：http://{ip}:{port}{url_end}添加到扫描列表")
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

# 发送get请求检测url是否可访问
def check_ip_port(ip_port, url_end):
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=2)
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            print(f"✅ {url} 访问成功")
            return ip_port
    except Exception as e:
        print(f"❌ {url} 失败")
    return None

# 多线程检测url，获取有效ip_port
def scan_ip_port(ip, port, option, url_end):
    def show_progress():
        while checked[0] < len(ip_ports) and option % 2 == 1:
            print(f"已扫描：{checked[0]}/{len(ip_ports)}, 有效ip_port：{len(valid_ip_ports)}个")
            time.sleep(30)
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    checked = [0]
    Thread(target=show_progress, daemon=True).start()
    with ThreadPoolExecutor(max_workers=300 if option % 2 == 1 else 100) as executor:
        futures = {executor.submit(check_ip_port, ip_port, url_end): ip_port for ip_port in ip_ports}
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid_ip_ports.append(result)
            checked[0] += 1
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
        print(f"\n{province} 扫描完成，获取有效ip_port共：{len(all_ip_ports)}个")
        os.makedirs("ip", exist_ok=True)
        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip_ports))

        archive_file = f"ip/存档_{province}_ip.txt"
        if os.path.exists(archive_file):
            with open(archive_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        else:
            lines = []
        for ip_port in all_ip_ports:
            ip, port = ip_port.split(":")
            a, b, c, d = ip.split(".")
            lines.append(f"{a}.{b}.{c}.1:{port}\n")
        lines = sorted(set(lines))
        with open(archive_file, 'w', encoding='utf-8') as f:
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
    return all_ip_ports

def txt_to_m3u(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        genre = ''
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ",#genre#" in line:
                genre = line.split(',')[0].strip()
            else:
                if ',' in line:
                    channel_name, channel_url = line.split(',', 1)
                    f.write(f'#EXTINF:-1 group-title="{genre}",{channel_name}\n')
                    f.write(f'{channel_url}\n')

def main():
    # 配置文件名
    global ALIAS_FILE, DEMO_FILE
    ALIAS_FILE = "alias.txt"
    DEMO_FILE = "demo.txt"

    # 加载映射
    alias_map = load_alias_map()
    category_channels = load_demo_category()

    # 扫描所有省份
    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    # 收集所有有效IP
    all_ips = []
    for fn in glob.glob("ip/*.txt"):
        if "存档" in fn or not fn.endswith("_ip.txt"):
            continue
        with open(fn, 'r', encoding='utf-8') as f:
            all_ips += [l.strip() for l in f if l.strip()]
    all_ips = sorted(set(all_ips))

    # 生成带分类的最终文件
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")
    output_lines = [f"{current_time}更新,#genre#"]

    ip_idx = 0
    for genre, chn in category_channels:
        if chn is None:
            output_lines.append(f"{genre},#genre#")
        else:
            std_name = alias_map.get(chn, chn)
            if all_ips:
                use_ip = all_ips[ip_idx % len(all_ips)]
                url = f"http://{use_ip}/rtp/239.16.0.0:10000"
            else:
                url = ""
            output_lines.append(f"{std_name},{url}")
            ip_idx += 1

    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write('\n'.join(output_lines))

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print(f"\n组播地址获取完成，已生成分类频道列表")

if __name__ == "__main__":
    main()
