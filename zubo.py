from threading import Thread
import os
import time
import datetime
import glob
import requests
import aiohttp
import asyncio
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 配置 ====================
CONCURRENCY = 60
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"

# ==================== 读取别名映射 ====================
def load_alias_map():
    alias_map = {}
    if os.path.exists(ALIAS_FILE):
        with open(ALIAS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or ',' not in line:
                    continue
                parts = [p.strip() for p in line.split(',') if p.strip()]
                if len(parts) < 1:
                    continue
                standard = parts[0]
                for alias in parts[1:]:
                    alias_map[alias] = standard
    return alias_map

# ==================== 读取分类结构 ====================
def load_categories():
    categories = []
    current_cat = None
    if os.path.exists(DEMO_FILE):
        with open(DEMO_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if ',#genre#' in line:
                    current_cat = line.replace(',#genre#', '').strip()
                    categories.append((current_cat, []))
                elif current_cat is not None:
                    ch = line.strip()
                    categories[-1][1].append(ch)
    return categories

# ==================== 标准化频道名 ====================
def standardize_name(name, alias_map):
    return alias_map.get(name, name)

# ==================== 异步测速 ====================
async def async_test_speed(session, url, timeout=3):
    try:
        start = time.time()
        async with session.get(url, timeout=timeout) as resp:
            if resp.status in (200, 206):
                chunk = await resp.content.read(1024 * 128)
                cost = time.time() - start
                speed = len(chunk) / cost / 1024 / 1024 if cost > 0 else 0
                return url, speed, cost * 1000
    except:
        pass
    return url, 0.0, 9999

async def run_speed_test(items):
    connector = aiohttp.TCPConnector(ssl=False)
    timeout = aiohttp.ClientTimeout(total=3)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        for name, url in items:
            tasks.append(async_test_speed(session, url))
        results = await asyncio.gather(*tasks)
    speed_map = {url: (speed, delay) for url, speed, delay in results}
    return speed_map

# ==================== 原有扫描逻辑 ====================
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
        if '-' in c:
            cs = c.split('-')
            c_start = int(cs[0])
            c_end = int(cs[1]) + 1
        else:
            c_start = int(c)
            c_end = int(c) + 8
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(c_start, c_end) for y in range(1, 256)]
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
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    checked = [0]

    def progress():
        while checked[0] < len(ip_ports) and option % 2 == 1:
            print(f"已扫描：{checked[0]}/{len(ip_ports)}, 有效：{len(valid_ip_ports)}")
            time.sleep(30)
    Thread(target=progress, daemon=True).start()

    with ThreadPoolExecutor(max_workers=300 if option%2==1 else 100) as executor:
        fs = {executor.submit(check_ip_port, p, url_end): p for p in ip_ports}
        for f in as_completed(fs):
            res = f.result()
            if res:
                valid_ip_ports.append(res)
            checked[0] += 1
    return valid_ip_ports

def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"{'='*25}\n   获取: {province} ip_port\n{'='*25}")
    configs = sorted(set(read_config(config_file)))
    print(f"读取完成，共 {len(configs)} 组")
    all_ips = []
    for ip, port, opt, end in configs:
        print(f"\n扫描：http://{ip}:{port}{end}")
        all_ips.extend(scan_ip_port(ip, port, opt, end))
    if not all_ips:
        print(f"\n{province} 未扫描到有效ip")
        return
    all_ips = sorted(set(all_ips))
    os.makedirs("ip", exist_ok=True)
    with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_ips))
    archive = f"ip/存档_{province}_ip.txt"
    if os.path.exists(archive):
        with open(archive, encoding='utf-8') as f:
            lines = f.readlines()
        for ip_port in all_ips:
            ip, port = ip_port.split(':')
            a,b,c,d = ip.split('.')
            lines.append(f"{a}.{b}.{c}.1:{port}\n")
        lines = sorted(set(lines))
        with open(archive, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    tpl = os.path.join('template', f"template_{province}.txt")
    if os.path.exists(tpl):
        with open(tpl, encoding='utf-8') as f:
            tpl_content = f.read()
        out = []
        with open(f"ip/{province}_ip.txt", encoding='utf-8') as f:
            for idx, line in enumerate(f, 1):
                ip = line.strip()
                out.append(f"{province}-组播{idx},#genre#\n")
                out.append(tpl_content.replace("ipipip", ip))
        with open(f"组播_{province}.txt", 'w', encoding='utf-8') as f:
            f.writelines(out)
    else:
        print(f"无模板：{tpl}")

def txt_to_m3u(input_file, output_file):
    with open(input_file, encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for line in lines:
            line = line.strip()
            if not line or ',#genre#' in line:
                continue
            if ',' in line:
                name, url = line.split(',', 1)
                f.write(f"#EXTINF:-1,{name}\n{url}\n")

# ==================== 主函数（已整合全部新功能） ====================
def main():
    # 1. 原有扫描
    for cfg in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(cfg)

    # 2. 收集所有频道
    raw_channels = []
    for fp in glob.glob('组播_*.txt'):
        with open(fp, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or ',#genre#' in line:
                    continue
                if ',' in line:
                    parts = line.split(',', 1)
                    if len(parts) == 2:
                        n, u = parts
                        raw_channels.append((n.strip(), u.strip()))

    if not raw_channels:
        print("无频道可处理")
        return

    # 3. 加载别名 & 标准化名称
    alias_map = load_alias_map()
    std_channels = [(standardize_name(n, alias_map), u) for n, u in raw_channels]

    # 4. 异步测速
    print(f"\n开始测速，并发 {CONCURRENCY}...")
    try:
        loop = asyncio.get_event_loop()
    except:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    speed_map = loop.run_until_complete(run_speed_test(std_channels))

    # 5. 按速度从高到低排序
    std_channels.sort(key=lambda x: speed_map[x[1]][0], reverse=True)

    # 6. 按 demo 分类
    categories = load_categories()
    cat_map = defaultdict(list)
    uncat = []
    for n, u in std_channels:
        found = False
        for cat_name, ch_list in categories:
            if n in ch_list:
                cat_map[cat_name].append((n, u))
                found = True
                break
        if not found:
            uncat.append((n, u))

    # 7. 输出最终文件
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")
    output_lines = [f"{current_time}更新,#genre#"]

    for cat_name, _ in categories:
        ch_list = cat_map.get(cat_name, [])
        if ch_list:
            output_lines.append(f"{cat_name},#genre#")
            output_lines.extend([f"{n},{u}" for n, u in ch_list])

    if uncat:
        output_lines.append("未分类频道,#genre#")
        output_lines.extend([f"{n},{u}" for n, u in uncat])

    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write('\n'.join(output_lines) + '\n')

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print("\n✅ 全部完成：测速排序 + 标准名 + 分类")
    print("✅ 输出：zubo_all.txt / zubo_all.m3u")

if __name__ == "__main__":
    main()
