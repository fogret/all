from threading import Thread
import os
import time
import datetime
import glob
import requests
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 配置文件 不动 =====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"

# ===================== 加载别名映射 不动 =====================
def load_alias_map():
    alias_map = {}
    if os.path.exists(ALIAS_FILE):
        with open(ALIAS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "," not in line:
                    continue
                parts = [p.strip() for p in line.split(",") if p.strip()]
                standard_name = parts[0]
                for alias in parts[1:]:
                    alias_map[alias] = standard_name
    return alias_map

# ===================== 加载demo分类+顺序 不动 =====================
def load_demo_category():
    category_order = []
    category_channel_list = OrderedDict()
    now_category = None
    if os.path.exists(DEMO_FILE):
        with open(DEMO_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.endswith(",#genre#"):
                    now_category = line.replace(",#genre#", "").strip()
                    category_order.append(now_category)
                    category_channel_list[now_category] = []
                elif now_category:
                    category_channel_list[now_category].append(line)
    return category_order, category_channel_list

# ===================== 以下所有原有代码 完全原封不动 无任何修改 =====================
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

# ===================== 全新重写 汇总逻辑 只改这里 =====================
def merge_all_channel():
    alias_map = load_alias_map()
    cate_order, cate_std_list = load_demo_category()

    # 收集所有纯频道 剔除原有省份分组
    raw_channel_dict = {}
    for file in glob.glob("组播_*.txt"):
        with open(file, "r", encoding="utf-8") as f:
            for line in f.readlines():
                line = line.strip()
                if not line:
                    continue
                if "," in line and not line.endswith("#genre#"):
                    name, url = line.split(",", 1)
                    # 统一标准频道名
                    std_name = alias_map.get(name.strip(), name.strip())
                    raw_channel_dict[std_name] = url.strip()

    # 按demo分类顺序 归类分组
    final_out = []
    # 1.顶部虚拟更新时间分类
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    time_str = now.strftime("%Y/%m/%d %H:%M")
    final_out.append("更新时间,#genre#\n")
    final_out.append(f"{time_str},http://127.0.0.1\n\n")

    # 2.按你demo所有分类依次排版
    for cate_name in cate_order:
        final_out.append(f"{cate_name},#genre#\n")
        # 该分类下按demo内部频道顺序排列
        for chan in cate_std_list[cate_name]:
            if chan in raw_channel_dict:
                final_out.append(f"{chan},{raw_channel_dict[chan]}\n")
        final_out.append("\n")

    return ''.join(final_out)

# ===================== 主函数 只改汇总部分 其余不动 =====================
def main():
    # 原有扫描逻辑 完全不动
    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    # 执行新汇总规则
    total_content = merge_all_channel()

    # 写入最终txt
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(total_content)

    # 转m3u 原有函数不变
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print(f"组播扫描完成，已按标准分类+统一频道名汇总完毕")

if __name__ == "__main__":
    main()
