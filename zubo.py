# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 配置 ====================
ALIAS_FILE = "alias.txt"
DEMO_FILE  = "demo.txt"

# ==================== 频道别名映射 ====================
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

# ==================== 读取分类结构 ====================
def load_categories():
    categories = []
    current = None
    if os.path.exists(DEMO_FILE):
        with open(DEMO_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if ',#genre#' in line:
                    current = line.split(',')[0].strip()
                    categories.append((current, None))
                else:
                    if current is not None:
                        categories.append((current, line))
    return categories

# ==================== 你原有代码完全不动 ====================
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
    return all_ip_ports

# ==================== 输出：只加分类 + 别名，URL完全不变 ====================
def generate_final(alias_map, categories):
    all_ips = []
    for fn in glob.glob("ip/*.txt"):
        if "存档" in fn:
            continue
        with open(fn, 'r', encoding='utf-8') as f:
            all_ips += [l.strip() for l in f if l.strip()]
    all_ips = sorted(set(all_ips))
    if not all_ips:
        print("无可用IP")
        return

    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    update_str = now.strftime("%Y/%m/%d %H:%M") + "更新,#genre#"

    lines = [update_str]
    idx = 0

    for cat, chn in categories:
        if chn is None:
            lines.append(f"{cat},#genre#")
        else:
            name = alias_map.get(chn, chn)
            if idx < len(all_ips):
                ip_port = all_ips[idx]
                url = f"http://{ip_port}/rtp/239.16.0.0:10000"
            else:
                url = ""
            lines.append(f"{name},{url}")
            idx += 1

    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open("zubo_all.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        g = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ",#genre#" in line:
                g = line.split(",")[0].strip()
            else:
                if "," in line:
                    n, u = line.split(",", 1)
                    f.write(f'#EXTINF:-1 group-title="{g}",{n}\n{u}\n')

def main():
    alias_map = load_alias_map()
    categories = load_categories()

    for cfg in glob.glob("ip/*_config.txt"):
        multicast_province(cfg)

    generate_final(alias_map, categories)
    print("生成完成：zubo_all.txt / zubo_all.m3u")

if __name__ == "__main__":
    main()
