from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# 加载频道别名映射：标准名在前，杂乱名在后
def load_alias():
    alias_map = {}
    alias_path = "alias.txt"
    if not os.path.exists(alias_path):
        print("警告：根目录不存在 alias.txt，不执行频道名替换")
        return alias_map
    try:
        with open(alias_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",", 1)
                if len(parts) == 2:
                    standard_name, raw_name = parts[0].strip(), parts[1].strip()
                    alias_map[raw_name] = standard_name
    except Exception as e:
        print(f"读取alias.txt失败：{e}")
    return alias_map

# 加载demo排序&分类规则
def load_demo_rule():
    demo_path = "demo.txt"
    genre_order = []
    channel_order = []
    current_genre = ""
    if not os.path.exists(demo_path):
        print("警告：根目录不存在 demo.txt，不执行分类排序")
        return genre_order, channel_order
    try:
        with open(demo_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.endswith(",#genre#"):
                    current_genre = line.replace(",#genre#", "")
                    genre_order.append(current_genre)
                else:
                    channel_order.append((current_genre, line))
    except Exception as e:
        print(f"读取demo.txt失败：{e}")
    return genre_order, channel_order

# 频道名别名替换
def replace_channel_name(name, alias_map):
    return alias_map.get(name, name)

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
    with ThreadPoolExecutor(max_workers = 300 if option % 2 == 1 else 100) as executor:
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

# 合并+别名替换+demo分类排序核心逻辑
def merge_and_sort(alias_map, genre_order, channel_order):
    raw_lines = []
    # 读取所有组播文件
    for file_path in glob.glob('组播_*.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            raw_lines.extend(f.readlines())
    # 解析原始频道数据
    raw_channel_data = {}
    current_g = ""
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        if line.endswith(",#genre#"):
            current_g = line.replace(",#genre#", "")
            continue
        if "," in line:
            c_name, c_url = line.split(",", 1)
            std_name = replace_channel_name(c_name.strip(), alias_map)
            if current_g not in raw_channel_data:
                raw_channel_data[current_g] = {}
            raw_channel_data[current_g][std_name] = c_url.strip()
    # 按demo规则重组
    final_lines = []
    # 先写入固定头部更新时间行
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")
    final_lines.append(f"{current_time},#genre#\n")
    final_lines.append(f"浙江卫视,http://ali-m-l.cztv.com/channels/lantian/channel001/1080p.m3u8\n")
    # 按demo分类顺序遍历
    used_channel = set()
    for target_g in genre_order:
        final_lines.append(f"{target_g},#genre#\n")
        # 该分类下按demo频道顺序输出
        for g, c_name in channel_order:
            if g == target_g and c_name in raw_channel_data.get(g, {}):
                final_lines.append(f"{c_name},{raw_channel_data[g][c_name]}\n")
                used_channel.add((g, c_name))
    # 追加demo中未定义的剩余频道
    for g_name, c_dict in raw_channel_data.items():
        if g_name not in genre_order:
            final_lines.append(f"{g_name},#genre#\n")
            for c_name, c_url in c_dict.items():
                if (g_name, c_name) not in used_channel:
                    final_lines.append(f"{c_name},{c_url}\n")
    return final_lines

def main():
    # 加载别名&排序规则
    alias_map = load_alias()
    genre_order, channel_order = load_demo_rule()
    # 原有各省扫描逻辑不变
    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)
    # 合并+别名替换+分类排序
    sorted_content = merge_and_sort(alias_map, genre_order, channel_order)
    # 写入汇总txt
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.writelines(sorted_content)
    # 转m3u
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print(f"组播地址获取完成，已按alias统一频道名、demo.txt分类排序")

if __name__ == "__main__":
    main()
