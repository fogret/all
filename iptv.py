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
CONCURRENCY = 60    # 异步测速并发数

# 全局配置缓存
EPG_URL = ""
LOGO_DOMAIN = ""
SCAN_TIMEOUT = 2
SPEED_TIMEOUT = 6

# ==================== 读取全局配置 ====================
def load_config_ini():
    global EPG_URL, LOGO_DOMAIN, SCAN_TIMEOUT, SPEED_TIMEOUT
    cfg = configparser.ConfigParser()
    if os.path.exists(CONFIG_INI):
        cfg.read(CONFIG_INI, encoding="utf-8")
        EPG_URL = cfg.get("EPG", "epg_url", fallback=EPG_URL)
        LOGO_DOMAIN = cfg.get("LOGO", "logo_domain", fallback=LOGO_DOMAIN)
        SCAN_TIMEOUT = cfg.getint("TIMEOUT", "scan_timeout", fallback=SCAN_TIMEOUT)
        SPEED_TIMEOUT = cfg.getint("TIMEOUT", "speed_timeout", fallback=SPEED_TIMEOUT)
    print("[配置] 已加载 config.ini")

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

# ==================== 原有扫描逻辑【完全保留】 ====================
def read_config(config_file):
    print(f"[扫描] 读取设置文件：{config_file}")
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
                    ip = f"{a}.{b}.1.1" if option % 2 else f"{a}.{b}.{c}.1"
                    ip_configs.append((ip, port, option, url_end))
                    print(f"[扫描] 第{line_num}行：http://{ip}:{port}{url_end} 添加到扫描列表")
        return ip_configs
    except Exception as e:
        print(f"[错误] 读取文件失败: {e}")
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
    except Exception:
        pass
    return None

def scan_ip_port(ip, port, option, url_end):
    ip_ports = generate_ip_ports(ip, port, option)
    valid = []
    checked = [0]

    def progress():
        while checked[0] < len(ip_ports):
            print(f"[进度] 扫描：{checked[0]}/{len(ip_ports)} | 有效IP：{len(valid)}")
            time.sleep(15)
    Thread(target=progress, daemon=True).start()

    worker = 300 if option % 2 else 100
    with ThreadPoolExecutor(worker) as pool:
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
    print(f"[结果] {province} 有效IP：{len(all_ip)}")

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

# ==================== 生成M3U（读取配置，不写死） ====================
def txt_to_m3u(txt, m3u):
    with open(txt, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    update_str = now.strftime("%Y-%m-%d %H:%M:%S")

    with open(m3u, 'w', encoding='utf-8') as f:
        f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
        f.write(f'#EXTINF:-1 tvg-id="CCTV-1" tvg-name="CCTV-1" tvg-logo="{LOGO_DOMAIN}CCTV-1.png" group-title="🕘️更新时间",{update_str}\n')
        g = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ",#genre#" in line:
                g = line.split(',')[0]
            else:
                if ',' in line:
                    n, u = line.split(',', 1)
                    f.write(f'#EXTINF:-1 group-title="{g}",{n}\n{u}\n')

# ==================== 异步测速【修复None报错 + 增强兼容】 ====================
async def test_speed(session, sem, name, url):
    try:
        async with sem:
            t0 = time.perf_counter()
            async with session.get(url, timeout=SPEED_TIMEOUT) as r:
                await r.content.read(16384)
            cost = time.perf_counter() - t0
            # 限制最大延迟，彻底杜绝None参与比较
            return name, url, min(cost, 99.8)
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
        # 全部有数值，无None，彻底修复报错
        groups[n].append((t, u))

    sorted_channels = []
    for name in groups:
        groups[name].sort(key=lambda x: x[0])
        for t, u in groups[name]:
            sorted_channels.append((name, u))
    return sorted_channels

# ==================== 主流程 ====================
async def main():
    # 步骤1：加载全局配置
    load_config_ini()

    # 步骤2：原样执行IP扫描
    for cfg in glob.glob("ip/*_config.txt"):
        multicast_province(cfg)

    # 步骤3：收集所有频道 + 别名标准化
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

    # 步骤4：去重
    unique = list(dict.fromkeys(all_channels))

    # 步骤5：异步测速排序
    print(f"\n[测速] 开始测速，共 {len(unique)} 条，并发 {CONCURRENCY}")
    sorted_channels = await async_speed_sort(unique)

    # 步骤6：严格按demo.txt分类排序
    cat_map = load_category_map()
    out_lines = []

    for cat, names in cat_map.items():
        out_lines.append(f"{cat},#genre#")
        for name in names:
            for (n, u) in sorted_channels:
                if n == name:
                    out_lines.append(f"{n},{u}")

    # 未匹配频道
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

    # 写入汇总txt
    with open("zubo_all.txt", 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))

    # 生成最终m3u
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")

    print("\n========== 全部完成 ==========")
    print("[优化] 已修复测速None报错")
    print("[优化] EPG/台标已接入config.ini")
    print("[优化] 日志标准化，无冗余刷屏")
    print("[保留] 分类顺序、测速排序、原有扫描逻辑全部不变")

if __name__ == "__main__":
    asyncio.run(main())
