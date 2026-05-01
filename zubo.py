from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

# ==================== 读取 alias.txt（修改版逻辑） ====================
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

# ==================== 读取 demo.txt（修改版逻辑） ====================
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
                    current_cat = line.replace(",#genre#", "").strip()
                    category_order.append(current_cat)
                    category_channel_order[current_cat] = []
                    continue
                if current_cat:
                    category_channel_order[current_cat].append(line.strip())
    return category_order, category_channel_order

# ==================== 原代码：读取 config（保持原逻辑） ====================
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

# ==================== 原代码：生成扫描 IP（保持原逻辑） ====================
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

# ==================== 原代码：检测 URL（保持原逻辑） ====================
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

# ==================== 原代码：多线程扫描（保持原逻辑） ====================
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

# ==================== 原代码：每省扫描（保持原逻辑） ====================
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

        # 原代码：写入当前扫描结果
        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip_ports))

        # 原代码：存档逻辑（保持原样）
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

        # 原代码：模板生成（保持原样）
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

# ==================== TXT 转 M3U（保持原逻辑） ====================
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

# ==================== 主函数（修改版汇总 + 更新时间分类） ====================
def main():
    # 原代码：扫描所有省份
    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    # 原代码：读取所有组播文件
    file_contents = []
    for file_path in glob.glob('组播_*电信.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            file_contents.append(f.read())

    for file_path in glob.glob('组播_*联通.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            file_contents.append(f.read())

    # 修改版：alias + demo 分类排序
    alias_map = load_alias_map()
    cat_order, cat_channel_order = load_demo_order()

    all_group_data = {}
    temp_group = ""

    full_text = '\n'.join(file_contents)
    for line in full_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith(",#genre#"):
            temp_group = line.replace(",#genre#", "")
            if temp_group not in all_group_data:
                all_group_data[temp_group] = []
        elif "," in line:
            c_name, c_url = line.split(",", 1)
            c_name = alias_map.get(c_name.strip(), c_name.strip())
            if temp_group:
                all_group_data[temp_group].append((c_name, c_url.strip()))

    final_sort_data = OrderedDict()
    for c in cat_order:
        final_sort_data[c] = []

    for cat_name, ch_list in cat_channel_order.items():
        for std_ch in ch_list:
            for g_name, items in all_group_data.items():
                for n, u in items:
                    if n == std_ch:
                        final_sort_data[cat_name].append(f"{n},{u}")

    new_content_lines = []
    for cat in final_sort_data:
        if final_sort_data[cat]:
            new_content_lines.append(f"{cat},#genre#")
            new_content_lines.extend(final_sort_data[cat])

    # ==================== 修改点 1：加入“更新时间分类” ====================
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    date_part = now.strftime("%m月%d日")
    time_part = now.strftime("%H:%M")

    # ==================== 修改点 2：最终输出格式 ====================
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write("更新时间,#genre#\n")
        f.write(f"{date_part} {time_part},http://127.0.0.1/null\n")
        f.write('\n'.join(new_content_lines))

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print("组播地址获取完成")

if __name__ == "__main__":
    main()
