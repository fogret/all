from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================
# 读取 alias.txt（频道名映射）
# ============================
def load_alias():
    alias_map = {}
    if os.path.exists("alias.txt"):
        with open("alias.txt", "r", encoding="utf-8") as f:
            for line in f:
                if "," in line:
                    std, bad = line.strip().split(",", 1)
                    alias_map[bad] = std
    return alias_map

# ============================
# 读取 demo.txt（分类顺序）
# ============================
def load_demo():
    demo_list = []
    if os.path.exists("demo.txt"):
        with open("demo.txt", "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if name:
                    demo_list.append(name)
    return demo_list

# ============================
# 读取设置文件
# ============================
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

# ============================
# 生成 IP 列表
# ============================
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

# ============================
# 新增测速功能
# ============================
def check_ip_port(ip_port, url_end):
    url = f"http://{ip_port}{url_end}"
    try:
        start = time.time()
        resp = requests.get(url, timeout=2)
        resp.raise_for_status()
        cost = int((time.time() - start) * 1000)  # 毫秒
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            print(f"{url} 访问成功 {cost}ms")
            return (ip_port, cost)
    except:
        return None

# ============================
# 多线程扫描
# ============================
def scan_ip_port(ip, port, option, url_end):
    def show_progress():
        while checked[0] < len(ip_ports) and option % 2 == 1:
            print(f"已扫描：{checked[0]}/{len(ip_ports)}, 有效：{len(valid)}个")
            time.sleep(30)

    valid = []
    ip_ports = generate_ip_ports(ip, port, option)
    checked = [0]

    Thread(target=show_progress, daemon=True).start()

    with ThreadPoolExecutor(max_workers=300 if option % 2 == 1 else 100) as executor:
        futures = {executor.submit(check_ip_port, ip_port, url_end): ip_port for ip_port in ip_ports}
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid.append(result)
            checked[0] += 1

    return valid  # 返回 (ip_port, speed)

# ============================
# 扫描省份
# ============================
def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"{'='*25}\n   获取: {province} ip_port\n{'='*25}")

    configs = sorted(set(read_config(config_file)))
    print(f"读取完成，共需扫描 {len(configs)} 组")

    all_valid = []

    for ip, port, option, url_end in configs:
        print(f"\n开始扫描 http://{ip}:{port}{url_end}")
        all_valid.extend(scan_ip_port(ip, port, option, url_end))

    if len(all_valid) == 0:
        print(f"\n{province} 扫描完成，未扫描到有效 ip_port")
        return

    # 去重 + 按速度排序
    all_valid = list({v[0]: v for v in all_valid}.values())
    all_valid.sort(key=lambda x: x[1])

    # 写入 ip 文件
    with open(f"ip/{province}_ip.txt", "w", encoding="utf-8") as f:
        for ip_port, speed in all_valid:
            f.write(f"{ip_port},{speed}\n")

    print(f"\n{province} 扫描完成，共 {len(all_valid)} 个有效地址")

# ============================
# 汇总 + alias + 分类 + 排序
# ============================
def process_all():
    alias_map = load_alias()
    demo_list = load_demo()

    # 读取所有组播文件
    file_contents = []
    for file_path in glob.glob("组播_*电信.txt") + glob.glob("组播_*联通.txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            file_contents.extend(f.readlines())

    # 解析频道
    channels = []  # (name, url)
    for line in file_contents:
        line = line.strip()
        if "," in line and not line.endswith("#genre#"):
            name, url = line.split(",", 1)
            # alias 替换
            if name in alias_map:
                name = alias_map[name]
            channels.append((name, url))

    # 按频道名分组
    grouped = {}
    for name, url in channels:
        grouped.setdefault(name, []).append(url)

    # 分类输出
    output_lines = []
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    update_time = now.strftime('%Y/%m/%d %H:%M')

    # 写入更新时间
    output_lines.append(f"{update_time}更新,#genre#\n")
    output_lines.append("浙江卫视,http://ali-m-l.cztv.com/channels/lantian/channel001/1080p.m3u8\n")

    for cate in demo_list:
        output_lines.append(f"{cate},#genre#\n")
        cate_channels = [name for name in grouped if cate in name]
        cate_channels.sort()

        for name in cate_channels:
            for url in grouped[name]:
                output_lines.append(f"{name},{url}\n")

    # 写入 zubo_all.txt
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.writelines(output_lines)

    # 转 m3u（含更新时间虚拟频道）
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u", update_time)

    print("组播地址获取完成")

# ============================
# txt → m3u（含更新时间虚拟频道）
# ============================
def txt_to_m3u(input_file, output_file, update_time):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    with open(output_file, 'w', encoding='utf-8') as f:

        # 写入更新时间虚拟频道
        f.write(f'#EXTINF:-1 group-title="更新信息",更新时间：{update_time}\n')
        f.write('http://127.0.0.1/update\n\n')

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

# ============================
# 主程序
# ============================
def main():
    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    process_all()

if __name__ == "__main__":
    main()
