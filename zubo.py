from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

# ==================== 测速配置（原shell提取逻辑，无改动） ====================
SAVE_TOP_NUM = 10       # 每个频道保留最快前10条
CURL_CONNECT_TIMEOUT = 5
CURL_MAX_TIMEOUT = 40

# ==================== 新增：读取alias.txt 标准频道别名映射 ====================
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
                # 别名全部映射为标准名
                for alias in parts[1:]:
                    alias_map[alias] = standard_name
    return alias_map

# ==================== 新增：读取demo.txt 分类顺序 + 频道排序规则 ====================
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

# ==================== 原有全部函数 完全原样保留不动 ====================
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
    # 开头加标准#EXTM3U头部，解决播放器解析乱码
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # 写入m3u强制标准格式、无多余空格、utf-8编码
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
                    # 严格标准格式 无多余空格
                    f.write(f'#EXTINF:-1 group-title="{genre}",{channel_name}\n')
                    f.write(f'{channel_url}\n')

# ==================== 原生shell提取 测速核心函数（纯原逻辑，适配汇总后使用） ====================
def speed_test_all_channels(channel_list):
    # channel_list 格式：[(频道名, 播放链接), ...]
    chan_speed_data = {}
    # 先按频道分组
    for ch_name, ch_url in channel_list:
        if ch_name not in chan_speed_data:
            chan_speed_data[ch_name] = []
        chan_speed_data[ch_name].append(ch_url)

    # 逐个频道测速
    result_final = []
    for ch_name, url_list in chan_speed_data.items():
        print(f"\n开始测速：{ch_name}  共{len(url_list)}条链接")
        one_chan_res = []
        for url in url_list:
            try:
                # 完全沿用你shell里curl拉流测速原逻辑
                res = requests.get(url, timeout=CURL_MAX_TIMEOUT,
                                   allow_redirects=True, stream=True)
                speed_kb = round(len(res.content) / 1024, 2)
                one_chan_res.append( {"url":url, "speed":speed_kb} )
            except:
                one_chan_res.append( {"url":url, "speed":0.0} )

        # 同频道按速度 从快到慢 排序
        one_chan_res.sort(key=lambda x: x["speed"], reverse=True)
        # 只保留最快前10条
        top_res = one_chan_res[:SAVE_TOP_NUM]
        # 重新存入最终列表
        for item in top_res:
            result_final.append( (ch_name, item["url"]) )
        print(f"{ch_name} 测速完成，保留最优{len(top_res)}条")
    return result_final

# ==================== 主函数 ====================
def main():
    # 1. 原有：逐省扫描全部不变
    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    # 2. 原有：汇总所有省份组播文件不变
    file_contents = []
    for file_path in glob.glob('组播_*电信.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            content = f.read()
            file_contents.append(content)
    for file_path in glob.glob('组播_*联通.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            content = f.read()
            file_contents.append(content)

    # ========== 原有：统一别名 + 按demo分类排序 完全不变 ==========
    print("\n=== 开始统一频道别名 + 按demo.txt分类排序 ===")
    alias_map = load_alias_map()
    cat_order, cat_channel_order = load_demo_order()

    raw_all_channels = []
    temp_group = ""
    all_group_data = {}

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
            # 别名替换为标准频道名
            if c_name in alias_map:
                c_name = alias_map[c_name]
            if temp_group:
                all_group_data[temp_group].append( (c_name, c_url) )

    # 按demo.txt严格分类、顺序重排
    final_sort_data = OrderedDict()
    for c in cat_order:
        final_sort_data[c] = []

    for cat_name, ch_list in cat_channel_order.items():
        for std_ch in ch_list:
            for g_name, items in all_group_data.items():
                for n,u in items:
                    if n == std_ch:
                        final_sort_data[cat_name].append( (n,u) )

    # ==================== 【重点：全部汇总排序完成后，再执行测速】 ====================
    print("\n===== 全部汇总、分类、别名处理完毕，开始全局拉流测速 =====")
    # 取出所有频道+链接 进行测速
    test_input_list = []
    for cat_key, item_list in final_sort_data.items():
        for ch_n, ch_u in item_list:
            test_input_list.append( (ch_n, ch_u) )

    # 执行原生提取的测速代码
    after_speed_list = speed_test_all_channels(test_input_list)

    # 测速完成后，重新按demo分类顺序整理回去
    speed_final_group = OrderedDict()
    for c in cat_order:
        speed_final_group[c] = []
    for ch_n, ch_u in after_speed_list:
        for cat_name, ch_list in cat_channel_order.items():
            if ch_n in ch_list:
                speed_final_group[cat_name].append(f"{ch_n},{ch_u}")

    # 拼装最终输出文本
    new_content_lines = []
    for cat in speed_final_group:
        if speed_final_group[cat]:
            new_content_lines.append(f"{cat},#genre#")
            new_content_lines.extend(speed_final_group[cat])
    # ================================================

    # 北京时间 格式：2026/04/30 15:23更新
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")
    
    # 生成zubo_all.txt
    with open("zubo_all.txt", "w", encoding="utf-8", newline='') as f:
        f.write(f"{current_time}更新,#genre#\n")
        f.write(f"更新时间展示,http://127.0.0.1/null\n")
        f.write('\n'.join(new_content_lines))

    # 转m3u
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print(f"\n全部完成：扫描汇总+别名统一+demo排序+全局拉流测速+保留各频道前10最优线路")

if __name__ == "__main__":
    main()
