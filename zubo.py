# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import datetime
import glob
import requests
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 配置 ====================
CONCURRENCY = 60
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"

# ==================== 读取频道别名映射 ====================
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

# ==================== 读取分类与频道 ====================
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

# ==================== 异步测速单个地址 ====================
async def test_speed(session, url):
    try:
        start = time.time()
        async with session.head(url, timeout=3) as resp:
            cost = int((time.time() - start) * 1000)
            return (url, cost)
    except:
        try:
            async with session.get(url, timeout=3) as resp:
                cost = int((time.time() - start) * 1000)
                return (url, cost)
        except:
            return (url, 9999)

# ==================== 异步并发测速批量地址 ====================
async def batch_test_speed(url_list):
    connector = aiohttp.TCPConnector(ssl=False, limit=CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [test_speed(session, url) for url in url_list]
        results = await asyncio.gather(*tasks)
    return results

# ==================== 原有扫描逻辑不动 ====================
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
            print(f"✅ {url} 有效")
            return ip_port
    except:
        print(f"❌ {url} 无效")
    return None

def scan_ip_port(ip, port, option, url_end):
    def show_progress():
        while checked[0] < len(ip_ports) and option % 2 == 1:
            print(f"已扫描：{checked[0]}/{len(ip_ports)}, 有效：{len(valid_ip_ports)}")
            time.sleep(20)
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    checked = [0]
    Thread(target=show_progress, daemon=True).start()
    with ThreadPoolExecutor(max_workers=300 if option % 2 == 1 else 100) as executor:
        futures = {executor.submit(check_ip_port, p, url_end): p for p in ip_ports}
        for future in as_completed(futures):
            res = future.result()
            if res:
                valid_ip_ports.append(res)
            checked[0] += 1
    return valid_ip_ports

def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"{'='*25}\n获取: {province} IP\n{'='*25}")
    configs = sorted(set(read_config(config_file)))
    all_ip_ports = []
    for ip, port, option, url_end in configs:
        print(f"扫描: {ip}:{port}")
        all_ip_ports.extend(scan_ip_port(ip, port, option, url_end))
    if all_ip_ports:
        all_ip_ports = sorted(set(all_ip_ports))
        os.makedirs("ip", exist_ok=True)
        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip_ports))
    return all_ip_ports

def txt_to_m3u(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        genre = ''
        for line in lines:
            line = line.strip()
            if not line: continue
            if ",#genre#" in line:
                genre = line.split(',')[0].strip()
            else:
                if ',' in line:
                    name, url = line.split(',',1)
                    f.write(f'#EXTINF:-1 group-title="{genre}",{name}\n{url}\n')

# ==================== 主函数（新增异步测速排序） ====================
def main():
    alias_map = load_alias_map()
    category_channels = load_demo_category()

    # 扫描IP
    for cfg in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(cfg)

    # 收集IP
    all_ips = []
    for fn in glob.glob("ip/*.txt"):
        if "存档" in fn: continue
        with open(fn, 'r', encoding='utf-8') as f:
            all_ips += [l.strip() for l in f if l.strip()]
    all_ips = sorted(set(all_ips))
    if not all_ips:
        print("无可用IP")
        return

    # 生成待测速地址
    temp_items = []
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    update_time = now.strftime("%Y/%m/%d %H:%M")

    ip_idx = 0
    for genre, chn in category_channels:
        if chn is None:
            continue
        std_name = alias_map.get(chn, chn)
        use_ip = all_ips[ip_idx % len(all_ips)]
        url = f"http://{use_ip}/rtp/239.16.0.0:10000"
        temp_items.append((std_name, url))
        ip_idx += 1

    # 异步并发测速
    print("开始异步并发测速播放地址...")
    urls = [u for n, u in temp_items]
    results = asyncio.run(batch_test_speed(urls))

    # 绑定名称 & 按耗时升序排序
    named = []
    res_dict = {u: t for u, t in results}
    for name, url in temp_items:
        named.append((name, url, res_dict.get(url, 9999)))
    named.sort(key=lambda x: x[2])

    # 写入最终文件
    output_lines = [f"{update_time}更新,#genre#"]
    current_gen = None
    for g, c in category_channels:
        if c is None:
            current_gen = g
            output_lines.append(f"{g},#genre#")
        else:
            for item in named:
                iname, iurl, itime = item
                if iname == alias_map.get(c, c):
                    output_lines.append(f"{iname},{iurl}")
                    break

    with open("zubo_all.txt", 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print("全部完成：已异步测速并按速度排序")

if __name__ == "__main__":
    main()
