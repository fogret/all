# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import datetime
import glob
import requests
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed
import aiohttp
import asyncio

# ==================== 配置 ====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"
CONCURRENCY = 60

# ==================== 读取 config.ini ====================
def load_config():
    cfg = configparser.ConfigParser()
    cfg.read("config.ini", encoding="utf-8")
    epg_url = cfg.get("EPG", "epg_url", fallback="")
    logo_base = cfg.get("LOGO", "logo_base_url", fallback="")
    return epg_url, logo_base

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

# ==================== 读取分类顺序 ====================
def load_category_map():
    category_map = {}
    cat_order = []
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
                    cat_order.append(current_cat)
                else:
                    if current_cat:
                        category_map[current_cat].append(line.strip())
    return category_map, cat_order

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
                    a,b,c,d = ip_part.split('.')
                    option = int(parts[1])
                    url_end = "/status" if option >=10 else "/stat"
                    ip = f"{a}.{b}.{c}.1" if option%2 ==0 else f"{a}.{b}.1.1"
                    ip_configs.append((ip, port, option, url_end))
                    print(f"第{line_num}行：http://{ip}:{port}{url_end} 添加到扫描列表")
        return ip_configs
    except Exception as e:
        print(f"读取文件错误: {e}")
        return []

def generate_ip_ports(ip, port, option):
    a,b,c,d = ip.split('.')
    if option ==2 or option ==12:
        c_parts = c.split('-')
        c_start = int(c_parts[0])
        c_end = int(c_parts[-1])+1 if '-' in c else int(c)+8
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(c_start,c_end) for y in range(1,256)]
    elif option ==0 or option ==10:
        return [f"{a}.{b}.{c}.{y}:{port}" for y in range(1,256)]
    else:
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(256) for y in range(1,256)]

def check_ip_port(ip_port, url_end):
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=2)
        if "udpxy" in resp.text or "Multi stream" in resp.text:
            return ip_port
    except:
        return None

def scan_ip_port(ip, port, option, url_end):
    ip_ports = generate_ip_ports(ip, port, option)
    valid = []
    checked = [0]
    def progress():
        while checked[0]<len(ip_ports):
            print(f"扫描进度：{checked[0]}/{len(ip_ports)}  有效：{len(valid)}")
            time.sleep(15)
    Thread(target=progress, daemon=True).start()
    with ThreadPoolExecutor(300 if option%2 else 100) as pool:
        fs = {pool.submit(check_ip_port, ipp, url_end): ipp for ipp in ip_ports}
        for f in as_completed(fs):
            res = f.result()
            if res:
                valid.append(res)
            checked[0] +=1
    return valid

def multicast_province(config_file):
    fname = os.path.basename(config_file)
    province = fname.split('_')[0]
    print(f"\n========== {province} 扫描开始 ==========")
    cfgs = read_config(config_file)
    all_ip = []
    for ip,port,opt,ue in cfgs:
        all_ip += scan_ip_port(ip,port,opt,ue)
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
            for idx, ip in enumerate(all_ip,1):
                out.append(f"{province}-组播{idx},#genre#")
                out.append(tmp.replace("ipipip", ip))
            with open(f"组播_{province}.txt", 'w', encoding='utf-8') as f:
                f.write('\n'.join(out))

# ==================== 核心：生成带 tvg-logo、tvg-epg 的 m3u ====================
def txt_to_m3u_with_meta(txt_path, m3u_path, update_str, epg_url, logo_base):
    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    with open(m3u_path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        if epg_url:
            f.write(f"#EXTM3U url-tvg=\"{epg_url}\"\n")
        f.write(f"# 更新时间：{update_str.replace(',#genre#','')}\n\n")

        current_group = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ",#genre#" in line:
                current_group = line.split(',')[0].strip()
                continue
            if "," in line:
                name, url = line.split(',', 1)
                logo = f"{logo_base}{name}.png" if logo_base else ""
                ext = f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" group-title="{current_group}",{name}'
                f.write(ext + "\n")
                f.write(url + "\n\n")

# ==================== 异步测速 ====================
async def test_speed(session, name, url):
    try:
        t0 = time.time()
        async with session.get(url, timeout=8) as r:
            await r.read(2048)
        return name, url, time.time()-t0
    except:
        return name, url, 999

async def async_speed_sort(channels):
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_speed(session, n, u) for n,u in channels]
        results = await asyncio.gather(*tasks)
    results.sort(key=lambda x:x[2])
    return [(n,u) for n,u,t in results]

# ==================== 主函数 ====================
def main():
    epg_url, logo_base = load_config()
    print("===== 加载配置 =====")
    print("EPG地址:", epg_url)
    print("台标地址:", logo_base)

    # 扫描
    for cfg in glob.glob("ip/*_config.txt"):
        multicast_province(cfg)

    # 收集频道
    alias_map = load_alias_map()
    all_channels = []
    for f in glob.glob("组播_*.txt"):
        g = None
        with open(f, 'r', encoding='utf-8') as fobj:
            for line in fobj:
                line = line.strip()
                if ",#genre#" in line:
                    g = line.split(',')[0]
                elif "," in line:
                    n,u = line.split(',',1)
                    n_std = alias_map.get(n.strip(), n.strip())
                    all_channels.append((n_std, u.strip()))

    # 去重
    unique = list(dict.fromkeys(all_channels))
    print(f"\n测速总数：{len(unique)} 并发：{CONCURRENCY}")
    unique = asyncio.run(async_speed_sort(unique))

    # 按 demo 排序
    cat_map, cat_order = load_category_map()
    cat_channels = {c:[] for c in cat_order}
    used = set()

    for cat in cat_order:
        names = cat_map[cat]
        for dn in names:
            for ch in unique:
                if ch[0] == dn and ch not in used:
                    cat_channels[cat].append(ch)
                    used.add(ch)
    uncat = [ch for ch in unique if ch not in used]

    # 北京时间
    tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz)
    update_str = now.strftime("%Y/%m/%d %H:%M") + " 更新,#genre#"

    # 写 txt
    out_lines = [update_str]
    for cat in cat_order:
        out_lines.append(f"{cat},#genre#")
        out_lines += [f"{n},{u}" for n,u in cat_channels[cat]]
    if uncat:
        out_lines.append("其他频道,#genre#")
        out_lines += [f"{n},{u}" for n,u in uncat]

    with open("zubo_all.txt", 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))

    # 写带台标、EPG的 m3u
    txt_to_m3u_with_meta(
        "zubo_all.txt",
        "zubo_all.m3u",
        update_str,
        epg_url,
        logo_base
    )

    print("\n✅ 完成：zubo_all.txt + zubo_all.m3u")
    print("✅ 已自动加入 tvg-logo & tvg-epg")

if __name__ == "__main__":
    main()
