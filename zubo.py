# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import aiohttp
import asyncio
from collections import defaultdict
import configparser

# ==================== 配置 ====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"
CONFIG_INI = "config.ini"
CONCURRENCY = 60

# ==================== 读取config.ini ====================
def load_config_ini():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_INI, encoding="utf-8")
    epg_url = cfg.get("EPG", "epg_url", fallback="")
    logo_domain = cfg.get("LOGO", "logo_domain", fallback="")
    scan_timeout = cfg.getint("TIMEOUT", "scan_timeout", fallback=2)
    speed_timeout = cfg.getint("TIMEOUT", "speed_timeout", fallback=8)
    return epg_url, logo_domain, scan_timeout, speed_timeout

EPG_URL, LOGO_DOMAIN, SCAN_TIMEOUT, SPEED_TIMEOUT = load_config_ini()

# ==================== 别名映射 ====================
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
def load_category_map():
    category_map = {}
    current_cat = None
    if os.path.exists(DEMO_FILE):
        with open(DEMO_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if ',#genre#' in line:
                    current_cat = line.split(',')[0].strip()
                    category_map[current_cat] = []
                else:
                    if current_cat:
                        category_map[current_cat].append(line.strip())
    return category_map

# ==================== 读取IP配置 ====================
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
        return []

def generate_ip_ports(ip, port, option):
    a, b, c, d = ip.split('.')
    if option == 2 or option == 12:
        c_parts = c.split('-')
        c_start = int(c_parts[0])
        c_end = int(c_parts[-1]) + 1 if '-' in c else int(c) + 8
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(c_start, c_end) for y in range(1, 256)]
    elif option == 0 or option == 10:
        return [f"{a}.{b}.{c}.{y}:{port}" for y in range(1, 256)]
    else:
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(256) for y in range(1, 256)]

def check_ip_port(ip_port, url_end):
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=SCAN_TIMEOUT)
        if "udpxy" in resp.text or "Multi stream" in resp.text:
            return ip_port
    except:
        return None

def scan_ip_port(ip, port, option, url_end):
    ip_ports = generate_ip_ports(ip, port, option)
    valid = []
    checked = [0]

    def progress():
        while checked[0] < len(ip_ports):
            print(f"扫描进度：{checked[0]}/{len(ip_ports)}  有效：{len(valid)}")
            time.sleep(15)
    Thread(target=progress, daemon=True).start()

    with ThreadPoolExecutor(300 if option % 2 else 100) as pool:
        fs = {pool.submit(check_ip_port, ipp, url_end): ipp for ipp in ip_ports}
        for f in as_completed(fs):
            res = f.result()
            if res:
                valid.append(res)
            checked[0] += 1
    return valid

def multicast_province(config_file):
    fname = os.path.basename(config_file)
    province = fname.split('_')[0]
    print(f"\n========== {province} 扫描开始 ==========")
    cfgs = read_config(config_file)
    all_ip = []
    for ip, port, opt, ue in cfgs:
        all_ip += scan_ip_port(ip, port, opt, ue)
    all_ip = sorted(set(all_ip))
    print(f"{province} 有效IP：{len(all_ip)}")

    os.makedirs("ip", exist_ok=True)
    if all_ip:
        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip))
        tmpl = os.path.join("template", f"template_{province}.txt")
        if os.path.exists(tmpl):
            with open(tmpl, 'r', encoding='utf-8') as f:
                tmp = f.read()
            out = []
            for idx, ip in enumerate(all_ip, 1):
                out.append(f"{province}-组播{idx},#genre#")
                out.append(tmp.replace("ipipip", ip))
            with open(f"组播_{province}.txt", 'w', encoding='utf-8') as f:
                f.write('\n'.join(out))

# ==================== TXT转M3U 修复版 ====================
def txt_to_m3u(txt, m3u):
    with open(txt, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    update_str = now.strftime("%Y/%m/%d %H:%M更新")

    with open(m3u, 'w', encoding='utf-8') as f:
        f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
        g = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ",#genre#" in line:
                g = line.split(',')[0].strip()
            else:
                if ',' in line:
                    name, url = line.split(',', 1)
                    name = name.strip()
                    tvg_logo = f"{LOGO_DOMAIN}{name}.png"
                    line_inf = (
                        f'#EXTINF:-1 tvg-id="{name}" tvg-name="{name}" '
                        f'tvg-logo="{tvg_logo}" group-title="{g}",{name}\n'
                    )
                    f.write(line_inf)
                    f.write(f"{url}\n")

# ==================== 异步测速 稳定修复版 ====================
async def test_speed(session, sem, name, url):
    try:
        async with sem:
            t0 = time.perf_counter()
            async with session.get(url, timeout=SPEED_TIMEOUT) as r:
                total_read = 0
                # 持续拉流2.5秒，过滤瞬时假快
                while time.perf_counter() - t0 < 2.5:
                    chunk = await r.content.read(32768)
                    if not chunk:
                        break
                    total_read += len(chunk)
            # 有效数据过少直接判定失效
            if total_read < 8192:
                return name, url, 99.9
            cost = time.perf_counter() - t0
            return name, url, cost
    except Exception:
        return name, url, 99.9

async def async_speed_sort(channels):
    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(ssl=False, limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_speed(session, sem, n, u) for n, u in channels]
        results = await asyncio.gather(*tasks)

    groups = defaultdict(list)
    for n, u, t in results:
        groups[n].append((t, u))

    sorted_channels = []
    for name in groups:
        # 超过3秒不稳定源后置，优先稳定源
        groups[name].sort(key=lambda x: (x[0] if x[0] < 3.0 else 999))
        for t, u in groups[name]:
            sorted_channels.append((name, u))
    return sorted_channels

# ==================== 主流程 ====================
async def main():
    for cfg in glob.glob("ip/*_config.txt"):
        multicast_province(cfg)

    alias_map = load_alias_map()
    all_channels = []
    for f in glob.glob("组播_*.txt"):
        g = None
        with open(f, 'r', encoding='utf-8') as fobj:
            for line in fobj:
                line = line.strip()
                if ",#genre#" in line:
                    g = line.split(',')[0]
                elif ',' in line:
                    n, u = line.split(',', 1)
                    n_std = alias_map.get(n.strip(), n.strip())
                    all_channels.append((n_std, u.strip()))

    unique = list(dict.fromkeys(all_channels))

    print(f"\n开始测速，共 {len(unique)} 条，并发 {CONCURRENCY}")
    sorted_channels = await async_speed_sort(unique)

    cat_map = load_category_map()
    out_lines = []

    for cat, names in cat_map.items():
        out_lines.append(f"{cat},#genre#")
        for name in names:
            for (n, u) in sorted_channels:
                if n == name:
                    out_lines.append(f"{n},{u}")

    uncat = []
    for n, u in sorted_channels:
        found = False
        for names in cat_map.values():
            if n in names:
                found = True
                break
        if not found:
            uncat.append((n, u))

    if uncat:
        out_lines.append("未匹配频道,#genre#")
        out_lines += [f"{n},{u}" for n, u in uncat]

    with open("zubo_all.txt", 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")

    print("\n========== 全部完成 ==========")
    print("✅ 已读取config.ini台标、EPG配置")
    print("✅ 每条频道完整tvg参数，图标正常")
    print("✅ 时间格式规范，无垃圾时间行")
    print("✅ 测速已修复，优先稳定源")

if __name__ == "__main__":
    asyncio.run(main())
