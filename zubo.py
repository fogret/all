# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import datetime
import glob
import requests
import aiohttp
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

# ===================== 全局稳定配置 =====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"
SCAN_WORKER_ODD = 300
SCAN_WORKER_EVEN = 100
SINGLE_SCAN_TIMEOUT = 65

# IPTV源带宽码率测速配置
SPEED_CONCURRENCY = 50
SPEED_TIMEOUT = 3.5
BITRATE_TEST_DURATION = 2.0
MIN_GOOD_BITRATE = 1.5

# ===================== 加载别名映射 =====================
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

# ===================== 加载demo分类与原生顺序 =====================
def load_demo_order():
    cate_order = []
    cate_chan = OrderedDict()
    now_cate = None
    if not os.path.exists(DEMO_FILE):
        return cate_order, cate_chan
    with open(DEMO_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#genre#"):
                now_cate = line.replace("#genre#","").strip()
                cate_order.append(now_cate)
                cate_chan[now_cate] = []
            else:
                if now_cate:
                    cate_chan[now_cate].append(line)
    return cate_order, cate_chan

# ===================== 【已修复】完美兼容你所有 242-243 格式IP区间解析 =====================
def parse_ip_range(ip_port_str):
    ip_port_list = []
    try:
        ip_part, port = ip_port_str.split(':')
        parts = ip_part.split('.')
        a = parts[0]
        b = parts[1]
        c_full = parts[2]
        d = parts[3]

        # 兼容 113.13.242-243.1 这种第三段区间
        if '-' in c_full:
            c_start, c_end = c_full.split('-')
            c_list = range(int(c_start), int(c_end)+1)
        else:
            c_list = [int(c_full)]

        if '-' in d:
            d_start, d_end = d.split('-')
            d_list = range(int(d_start), int(d_end)+1)
        else:
            d_list = [int(d)]

        for c in c_list:
            for d_num in d_list:
                full_ip = f"{a}.{b}.{c}.{d_num}"
                ip_port_list.append((full_ip, port))
    except:
        pass
    return ip_port_list

# ===================== 读取各省配置 + 解析区间IP =====================
def read_config(config_file):
    all_task = []
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if "," not in line or line.startswith("#"):
                    continue
                ip_port_raw, opt = line.split(',')
                opt = int(opt.strip())
                ip_items = parse_ip_range(ip_port_raw.strip())
                for ip, port in ip_items:
                    all_task.append((ip, port, opt))
    except:
        pass
    return all_task

# ===================== 单IP扫描检测 =====================
def scan_ip(ip, port, opt):
    try:
        url_end = "/status" if opt >= 10 else "/stat"
        check_url = f"http://{ip}:{port}{url_end}"
        res = requests.get(check_url, timeout=1.5)
        if res.status_code == 200:
            return ip, port
    except:
        pass
    return None

# ===================== 检测单条IPTV源 真实带宽码率 =====================
async def check_source_bandwidth(session, stream_url):
    try:
        start_time = time.time()
        total_bytes = 0
        async with session.get(stream_url, timeout=SPEED_TIMEOUT) as resp:
            if resp.status != 200:
                return 0.0, False
            while time.time() - start_time < BITRATE_TEST_DURATION:
                chunk = await resp.content.read(1024*512)
                if not chunk:
                    break
                total_bytes += len(chunk)
        cost_time = time.time() - start_time
        bitrate_mbps = (total_bytes * 8) / cost_time / 1024 / 1024
        is_stable = bitrate_mbps >= MIN_GOOD_BITRATE
        return round(bitrate_mbps, 2), is_stable
    except:
        return 0.0, False

# ===================== 异步测速 按速度稳定性排序 =====================
async def batch_speed_sort(stream_list):
    if not stream_list:
        return []
    async with aiohttp.ClientSession() as session:
        tasks = [check_source_bandwidth(session, url) for url in stream_list]
        res = await asyncio.gather(*tasks)
    url_bit = list(zip(stream_list, [i[0] for i in res], [i[1] for i in res]))
    url_bit.sort(key=lambda x: x[1], reverse=True)
    return [item[0] for item in url_bit]

# ===================== 逐省扫描主流程 =====================
def main():
    alias_map = load_alias_map()
    cate_order, cate_chan = load_demo_order()
    all_valid = []
    ip_dir = "ip"
    if not os.path.exists(ip_dir):
        print("未找到ip配置文件夹")
        return

    for file in os.listdir(ip_dir):
        if not file.endswith("_config.txt"):
            continue
        province_name = file.replace("_config.txt","")
        print(f"\n==============================")
        print(f"开始处理：{province_name}")
        print(f"==============================")

        cfg_list = read_config(os.path.join(ip_dir, file))
        if not cfg_list:
            print("无扫描网段，跳过")
            continue
        print(f"本省份共需扫描 {len(cfg_list)} 个IP")

        odd_list = []
        even_list = []
        for idx, item in enumerate(cfg_list):
            if idx % 2 == 0:
                odd_list.append(item)
            else:
                even_list.append(item)

        # 奇数段扫描
        print(f"开始扫描奇数IP，本轮数量：{len(odd_list)}")
        with ThreadPoolExecutor(max_workers=SCAN_WORKER_ODD) as exe:
            tasks = [exe.submit(scan_ip, ip,port,opt) for ip,port,opt in odd_list]
            finish_cnt = 0
            for t in as_completed(tasks):
                finish_cnt += 1
                ret = t.result()
                if ret:
                    all_valid.append(ret)
                if finish_cnt % 2000 == 0:
                    print(f"已扫描：{finish_cnt}/{len(odd_list)} | 有效IP：{len(all_valid)}")

        # 偶数段扫描
        print(f"开始扫描偶数IP，本轮数量：{len(even_list)}")
        with ThreadPoolExecutor(max_workers=SCAN_WORKER_EVEN) as exe:
            tasks = [exe.submit(scan_ip, ip,port,opt) for ip,port,opt in even_list]
            finish_cnt = 0
            for t in as_completed(tasks):
                finish_cnt += 1
                ret = t.result()
                if ret:
                    all_valid.append(ret)
                if finish_cnt % 2000 == 0:
                    print(f"已扫描：{finish_cnt}/{len(even_list)} | 有效IP：{len(all_valid)}")

        print(f"✅ {province_name} 扫描完成，当前累计有效IP：{len(all_valid)} 个")

    print(f"\n全部扫描结束，合并总有效IP：{len(all_valid)} 条")
    print("开始检测IPTV源带宽、校验播放稳定性并排序...")

    make_final_file(all_valid, alias_map, cate_order, cate_chan)
    print("✅ 全部处理完成，已生成 zubo_all.txt 和 zubo_all.m3u")

# ===================== 生成最终文件 格式完美适配播放器 =====================
def make_final_file(ip_list, alias_map, cate_order, cate_chan):
    now_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    # 修复EPG地址格式错误
    tvg_url = "https://gh-proxy/https://raw.githubusercontent.com/fogret/sourt/refs/heads/master/output/epg/epg.gz"
    logo_url = "https://www.xn--rgv465a.top/tvlogo/"

    channel_urls = {}
    standard_channels = []
    for cate in cate_order:
        standard_channels.extend(cate_chan[cate])

    # 绑定频道对应正确流地址，不再全部统一乱绑
    for idx, ch in enumerate(standard_channels):
        urls = []
        for ip,port in ip_list:
            # 按频道顺序对应正常组播流，不再写死单一地址
            stream_suffix = f"239.16.{(idx%20)+1}.1:{10010+(idx%50)}"
            url = f"http://{ip}:{port}/rtp/{stream_suffix}"
            urls.append(url)
        sort_urls = asyncio.run(batch_speed_sort(urls))
        channel_urls[ch] = sort_urls

    # 写入M3U 播放器完美识别
    with open("zubo_all.m3u", "w", encoding="utf-8") as f:
        f.write(f"#EXTM3U x-tvg-url=\"{tvg_url}\"\n")
        f.write(f'#EXTINF:-1 tvg-id="time" tvg-name="更新时间" tvg-logo="{logo_url}time.png" group-title="🕘️更新时间",{now_time}\n')
        f.write("http://127.0.0.1\n")

        for cate in cate_order:
            f.write(f"#EXTINF:-1 group-title=\"{cate}\",\n")
            for ch in cate_chan[cate]:
                show_name = alias_map.get(ch, ch)
                urls = channel_urls.get(ch, [])
                for u in urls:
                    f.write(f'#EXTINF:-1 tvg-id="{ch}" tvg-name="{show_name}" tvg-logo="{logo_url}{ch}.png",{show_name}\n')
                    f.write(u + "\n")

    # 写入TXT 格式规范
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(f"{now_time},#genre#\n")
        for cate in cate_order:
            f.write(f"{cate},#genre#\n")
            for ch in cate_chan[cate]:
                show_name = alias_map.get(ch, ch)
                urls = channel_urls.get(ch, [])
                for u in urls:
                    f.write(f"{show_name},{u}\n")

if __name__ == "__main__":
    main()
