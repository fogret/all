from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

# ==================== 统一频道名 alias.txt ====================
def load_alias_map():
    alias_map = {}
    if os.path.exists("alias.txt"):
        with open("alias.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "," not in line:
                    continue
                parts = [p.strip() for p in line.split(",") if p.strip()]
                standard = parts[0]
                for alias in parts[1:]:
                    alias_map[alias] = standard
    return alias_map

# ==================== 分类 demo.txt ====================
def load_demo_order():
    category_order = []
    category_channels = OrderedDict()
    current_cat = None

    if os.path.exists("demo.txt"):
        with open("demo.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.endswith(",#genre#"):
                    current_cat = line.replace(",#genre#", "")
                    category_order.append(current_cat)
                    category_channels[current_cat] = []
                else:
                    if current_cat:
                        category_channels[current_cat].append(line)
    return category_order, category_channels

# ==================== 测速排序 ====================
def test_speed(url):
    try:
        start = time.time()
        requests.get(url, timeout=1)
        return time.time() - start
    except:
        return 9999

# ==================== 原始扫描逻辑（完全不动） ====================
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
            print(f"{url} 访问成功")
            return ip_port
    except:
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
        print(f"\n{province} 扫描完成，获取有效ip_port共：{len(all_ip_ports)}个\n{all_ip_ports}\n")

        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip_ports))

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

# ==================== TXT → M3U ====================
def txt_to_m3u(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        genre = ''
        for line in lines:
            line = line.strip()
            if "," in line:
                name, url = line.split(",", 1)
                if url == "#genre#":
                    genre = name
                else:
                    f.write(f'#EXTINF:-1 group-title="{genre}",{name}\n')
                    f.write(f'{url}\n')

# ==================== 主流程 ====================
def main():
    # 扫描
    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    # 读取所有组播文件
    file_contents = []
    for file_path in glob.glob('组播_*电信.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            file_contents.append(f.read())
    for file_path in glob.glob('组播_*联通.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            file_contents.append(f.read())

    # 加载 alias 和 demo
    alias_map = load_alias_map()
    cat_order, cat_channels = load_demo_order()

    # 解析所有频道
    all_channels = []
    for content in file_contents:
        for line in content.splitlines():
            line = line.strip()
            if "," in line and "http" in line:
                name, url = line.split(",", 1)
                name = alias_map.get(name, name)
                all_channels.append((name, url))

    # 分类 + 排序
    final_output = []

    for cat in cat_order:
        final_output.append(f"{cat},#genre#")
        for ch in cat_channels[cat]:
            lines = [(n, u) for (n, u) in all_channels if n == ch]
            if lines:
                sorted_lines = sorted(lines, key=lambda x: test_speed(x[1]))
                for n, u in sorted_lines:
                    final_output.append(f"{n},{u}")

    # 写入最终文件
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")

    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(f"{current_time}更新,#genre#\n")
        f.write("\n".join(final_output))

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print("组播地址获取完成（分类 + 统一频道名 + 排序）")

if __name__ == "__main__":
    main()
