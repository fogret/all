from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 映射配置 =====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"

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

# ===================== 原版扫描基础函数 完全不变 =====================
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
        
def check_ip_port(ip_port, url_end):    
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=2)
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
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

# 单独检测旧存档IP双端口
def check_old_single_ip(ip_port):
    res1 = check_ip_port(ip_port, "/stat")
    if res1:
        return ip_port
    res2 = check_ip_port(ip_port, "/status")
    if res2:
        return ip_port
    return None

# ===================== 核心 完整写入生效版 =====================
def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"\n{'='*30}\n开始处理：{province}\n{'='*30}")

    # 1.扫描本次新IP段
    configs = sorted(set(read_config(config_file)))
    new_valid_ips = []
    for ip, port, option, url_end in configs:
        print(f"\n扫描新网段：{ip}:{port}")
        new_valid_ips.extend(scan_ip_port(ip, port, option, url_end))

    # 2.读取历史存档IP 重新扫描校验
    archive_path = f"ip/存档_{province}_ip.txt"
    old_survive_ips = []
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            old_ip_list = [line.strip() for line in f if line.strip()]
        print(f"\n加载历史存档IP：{len(old_ip_list)} 个，开始重扫校验")
        # 批量扫描旧IP
        with ThreadPoolExecutor(max_workers=120) as exe:
            out = exe.map(check_old_single_ip, old_ip_list)
            old_survive_ips = [x for x in out if x]

    # 3.新有效 + 旧存活 合并去重
    all_final_ips = sorted(list(set(new_valid_ips + old_survive_ips)))

    # 4.【关键！强制写入正式IP文件 真正生效】
    if len(all_final_ips) > 0:
        print(f"\n{province} 汇总结果：")
        print(f"新扫描有效IP：{len(new_valid_ips)} 个")
        print(f"旧存档重扫存活：{len(old_survive_ips)} 个")
        print(f"本次最终写入总数：{len(all_final_ips)} 个")

        # 写入ip/省份_ip.txt 覆盖旧内容 正式生效
        with open(f"ip/{province}_ip.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(all_final_ips))

        # 保留原代码：新IP追加进存档备份 不变
        if os.path.exists(archive_path):
            with open(archive_path, "r", encoding="utf-8") as f:
                old_lines = f.readlines()
            for ip_port in new_valid_ips:
                ip, port = ip_port.split(":")
                a,b,c,d = ip.split(".")
                old_lines.append(f"{a}.{b}.{c}.1:{port}\n")
            old_lines = sorted(set(old_lines))
            with open(archive_path, "w", encoding="utf-8") as f:
                f.writelines(old_lines)

        # 正常生成单省组播文件
        template_file = os.path.join('template', f"template_{province}.txt")
        if os.path.exists(template_file):
            with open(template_file, "r", encoding="utf-8") as f:
                tem_channels = f.read()
            output = []
            with open(f"ip/{province}_ip.txt", "r", encoding="utf-8") as f:
                for idx, line in enumerate(f, 1):
                    ip = line.strip()
                    output.append(f"{province}-组播{idx},#genre#\n")
                    output.append(tem_channels.replace("ipipip", ip))
            with open(f"组播_{province}.txt", "w", encoding="utf-8") as f:
                f.writelines(output)
    else:
        print(f"\n{province} 无任何有效IP，不写入")

# 原版m3u转换
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

# 频道改名+分类重排
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

# 主函数 原版完整合并
def main():
    # 逐省扫描+写入
    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    # 原版合并所有省份组播文件
    file_contents = []
    for file_path in glob.glob('组播_*电信.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            file_contents.append(f.read())
    for file_path in glob.glob('组播_*联通.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            file_contents.append(f.read())
    
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")
    origin_total = f"{current_time}更新,#genre#\n"
    origin_total += f"浙江卫视,http://ali-m-l.cztv.com/channels/lantian/channel001/1080p.m3u8\n"
    origin_total += '\n'.join(file_contents)

    final_total = reorder_channel_content(origin_total)

    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(final_total)

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print("\n===== 全部执行完成 所有IP已正常写入 =====")

if __name__ == "__main__":
    main()
