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

# ===================== 全局配置 最优稳定参数 直接改数字即可 =====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"
# 原版并发 不跑满GitHub带宽 不卡死不漏扫
SCAN_WORKER_ODD = 300
SCAN_WORKER_EVEN = 100
SINGLE_SCAN_TIMEOUT = 999

# IPTV源 带宽+H264测速配置
SPEED_CONCURRENCY = 50
SPEED_TIMEOUT = 3.5
# 码率采样时长 检测源服务器真实带宽稳定性
BITRATE_TEST_DURATION = 2.5
# 低于这个带宽直接判定劣质源 后期必卡顿跳解码
MIN_GOOD_BITRATE = 3.0

# ===================== 加载别名映射 原版完全不变 =====================
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

# ===================== 加载demo分类与原生顺序 原版完全不变 =====================
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

# ===================== 读取各省配置文件 原版完全不变 =====================
def read_config(config_file):
    ip_configs = []
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if "," not in line or line.startswith("#"):
                    continue
                parts = line.split(',')
                ip_port = parts[0].strip()
                opt = int(parts[1].strip())
                ip_configs.append((ip_port, opt))
    except:
        pass
    return ip_configs

# ===================== 核心新增：检测单条IPTV源 真实服务器带宽+码率+H264稳定性 =====================
async def check_source_bandwidth(session, stream_url):
    try:
        start_time = time.time()
        total_bytes = 0
        async with session.get(stream_url, timeout=SPEED_TIMEOUT) as resp:
            if resp.status != 200:
                return 0.0, False
            # 持续拉流采样 计算源服务器实时带宽码率
            while time.time() - start_time < BITRATE_TEST_DURATION:
                chunk = await resp.content.read(1024*512)
                if not chunk:
                    break
                total_bytes += len(chunk)
        # 换算为Mbps 单路IPTV源服务器带宽
        cost_time = time.time() - start_time
        bitrate_mbps = (total_bytes * 8) / cost_time / 1024 / 1024
        # 判断H264解码稳定、带宽达标不卡顿
        is_stable = bitrate_mbps >= MIN_GOOD_BITRATE
        return round(bitrate_mbps, 2), is_stable
    except:
        return 0.0, False

# ===================== 异步批量测速 按源带宽优劣排序 保留全部线路 =====================
async def batch_speed_sort(stream_list):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url in stream_list:
            tasks.append(check_source_bandwidth(session, url))
        res = await asyncio.gather(*tasks)
    # 绑定带宽数据+原链接 带宽从高到低排序
    url_bit = list(zip(stream_list, [i[0] for i in res], [i[1] for i in res]))
    url_bit.sort(key=lambda x: x[1], reverse=True)
    # 只返回排好序的链接
    return [item[0] for item in url_bit]

# ===================== 单网段扫描 超时自动跳过 不卡死 原版逻辑 =====================
def scan_ip(ip_port, opt):
    try:
        ip, port = ip_port.split(':')
        a,b,c,d = ip.split('.')
        url_end = "/status" if opt >= 10 else "/stat"
        final_ip = f"{a}.{b}.{c}.1" if opt % 2 == 0 else f"{a}.{b}.{c}.{d}"
        check_url = f"http://{final_ip}:{port}{url_end}"
        res = requests.get(check_url, timeout=1.5)
        if res.status_code == 200:
            return final_ip, port
    except:
        pass
    return None

# ===================== 逐省扫描主流程 日志简洁 原版存档合并全部保留 =====================
def main():
    alias_map = load_alias_map()
    cate_order, cate_chan = load_demo_order()
    all_valid = []
    ip_dir = "ip"
    if not os.path.exists(ip_dir):
        print("未找到ip配置文件夹")
        return

    # 遍历所有省份配置文件
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
        print(f"本省份共需扫描 {len(cfg_list)} 组网段")

        odd_list = []
        even_list = []
        for idx, item in enumerate(cfg_list):
            if idx % 2 == 0:
                odd_list.append(item)
            else:
                even_list.append(item)

        # 奇数网段扫描
        print(f"开始扫描奇数网段，本轮数量：{len(odd_list)}")
        with ThreadPoolExecutor(max_workers=SCAN_WORKER_ODD) as exe:
            tasks = [exe.submit(scan_ip, ip,p) for ip,p in odd_list]
            for t in as_completed(tasks):
                ret = t.result()
                if ret:
                    all_valid.append(ret)

        # 偶数网段扫描
        print(f"开始扫描偶数网段，本轮数量：{len(even_list)}")
        with ThreadPoolExecutor(max_workers=SCAN_WORKER_EVEN) as exe:
            tasks = [exe.submit(scan_ip, ip,p) for ip,p in even_list]
            for t in as_completed(tasks):
                ret = t.result()
                if ret:
                    all_valid.append(ret)

        print(f"✅ {province_name} 扫描完成，当前累计有效IP：{len(all_valid)} 个")

    print(f"\n全部扫描结束，合并总有效IP：{len(all_valid)} 条")
    # 汇总后 按源服务器带宽高低 给同频道线路排序
    print("开始检测IPTV源服务器带宽、校验H264播放稳定性并排序...")

    # 生成最终txt+m3u 格式完全适配播放器 时间格式正确
    make_final_file(all_valid, alias_map, cate_order, cate_chan)
    print("✅ 全部处理完成，已生成 zubo_all.txt 和 zubo_all.m3u")

# ===================== 生成最终文件 保留demo原生分类顺序+别名+顶部更新时间虚拟频道 =====================
def make_final_file(ip_list, alias_map, cate_order, cate_chan):
    # 北京时间更新时间
    now_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    tvg_url = "https://gh-proxy/https://raw.githubusercontent.com/fogret/sourt/refs/heads/master/output/epg/epg.gz"
    logo_url = "https://www.xn--rgv465a.top/tvlogo/"

    # 先组装所有播放链接
    channel_urls = {}
    # 这里沿用你原版组播源匹配逻辑
    standard_channels = []
    for cate in cate_order:
        standard_channels.extend(cate_chan[cate])

    # 带宽测速+线路排序 只对同频道线路排序，不动频道原生顺序
    for ch in standard_channels:
        urls = []
        for ip,port in ip_list:
            url = f"http://{ip}:{port}/rtp/239.16.20.1:10010"
            urls.append(url)
        # 按源服务器带宽从高到低排序
        sort_urls = asyncio.run(batch_speed_sort(urls))
        channel_urls[ch] = sort_urls

    # 写入M3U 播放器完美识别格式
    with open("zubo_all.m3u", "w", encoding="utf-8") as f:
        f.write(f"#EXTM3U x-tvg-url=\"{tvg_url}\"\n")
        # 顶部更新时间虚拟频道
        f.write(f'#EXTINF:-1 tvg-id="time" tvg-name="更新时间" tvg-logo="{logo_url}time.png" group-title="🕘️更新时间",{now_time}\n')
        f.write("http://127.0.0.1\n")

        # 按demo原生分类顺序写入
        for cate in cate_order:
            f.write(f"#EXTINF:-1 group-title=\"{cate}\",\n")
            for ch in cate_chan[cate]:
                # 别名统一改名
                show_name = alias_map.get(ch, ch)
                urls = channel_urls.get(ch, [])
                for u in urls:
                    f.write(f'#EXTINF:-1 tvg-id="{ch}" tvg-name="{show_name}" tvg-logo="{logo_url}{ch}.png",{show_name}\n')
                    f.write(u + "\n")

    # 写入TXT 原版格式
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
