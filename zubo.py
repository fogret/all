# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import datetime
import glob
import socket
import requests
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

# ===================== 全局配置 原版完全保留不动 =====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"
SPEED_CONCURRENCY = 60
SPEED_TIMEOUT = 3.0
SINGLE_SCAN_TIMEOUT = 65
SCAN_WORKER_ODD = 220
SCAN_WORKER_EVEN = 90

# ===================== 别名、分类加载 原版一字未改 =====================
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
    cate_order = []
    cate_chan = OrderedDict()
    now_cate = None
    if os.path.exists(DEMO_FILE):
        with open(DEMO_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "#genre#" in line:
                    now_cate = line.replace("#genre#","").strip()
                    cate_order.append(now_cate)
                    cate_chan[now_cate] = []
                else:
                    if now_cate:
                        cate_chan[now_cate].append(line)
    return cate_order, cate_chan

# ===================== 全新替换 顶配真实拉流测速核心 =====================
def result_dict(url, result, last_data_elapsed):
    beijing_time = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
    now_str = beijing_time.strftime("%Y-%m-%d %H:%M:%S %Z%z")
    return {
        "URL": url,
        "Result": result,
        "Score": round(last_data_elapsed, 1),
        "TestTime": now_str
    }

def test_udpxy_stream(url: str, test_duration: int = 8, chunk_size: int = 1024, idle_threshold: float = 3.0) -> dict:
    try:
        response = requests.get(url, stream=True, timeout=(3, 1))
        response.raise_for_status()
    except requests.RequestException:
        return result_dict(url, "Connection Error", 0.0)

    response.raw.decode_content = False
    start_time = time.time()
    last_data_time = start_time

    while time.time() - start_time < test_duration:
        try:
            chunk = response.raw.read(chunk_size)
            if chunk:
                last_data_time = time.time()
            else:
                return result_dict(url, "Connection Blocked", last_data_time - start_time)
        except (socket.timeout, requests.exceptions.ReadTimeout):
            pass
        except Exception:
            return result_dict(url, "Stream Stop", last_data_time - start_time)

        if time.time() - last_data_time > idle_threshold:
            return result_dict(url, "Idle Blocked", last_data_time - start_time)

    return result_dict(url, "OK Stable", last_data_time - start_time)

# ===================== 批量并发测速 【已修复空列表报错】 =====================
def speed_test_all_links(link_list):
    # 修复：没有有效链接直接跳过，不创建0线程池报错
    if not link_list:
        return []
        
    res_list = []
    max_workers = min(SPEED_CONCURRENCY, len(link_list))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(test_udpxy_stream, url): url for url in link_list}
        for future in as_completed(future_map):
            url = future_map[future]
            try:
                data = future.result()
                res_list.append(data)
            except Exception as e:
                res_list.append(result_dict(url, "Test Exception", 0.0))
    # 按稳定时长倒序排序，同频道最稳定不断流的排最前面
    res_list.sort(key=lambda x: x["Score"], reverse=True)
    return res_list

# ===================== 往下全部原版源码 一字未改 =====================
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
                    ip = f"{a}.{b}.{c}.1" if option % 2 == 0 else f"{a}.{b}.{c}.{int(d)}"
                    ip_configs.append((ip, port, url_end))
    except Exception as e:
        print(f"读取配置错误: {e}")
    return ip_configs

def scan_ip(ip, port, url_end):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        res = sock.connect_ex((ip, int(port)))
        sock.close()
        if res == 0:
            return f"http://{ip}:{port}{url_end}"
    except:
        pass
    return None

def scan_province(ip_configs, province_name):
    valid_links = []
    total = len(ip_configs)
    print(f"本省份共需扫描 {total} 组网段")
    odd_list = ip_configs[::2]
    even_list = ip_configs[1::2]

    def scan_batch(batch, workers, batch_name):
        batch_len = len(batch)
        print(f"开始扫描{batch_name}，本轮数量：{batch_len}")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_list = [executor.submit(scan_ip, ip, port, url_end) for ip, port, url_end in batch]
            for idx, future in enumerate(as_completed(future_list), 1):
                try:
                    ret = future.result(timeout=SINGLE_SCAN_TIMEOUT)
                    if ret:
                        valid_links.append(ret)
                except:
                    continue
                if idx % 200 == 0:
                    print(f"已扫描：{idx}/{batch_len} | 有效IP：{len(valid_links)}")

    scan_batch(odd_list, SCAN_WORKER_ODD, "奇数网段")
    scan_batch(even_list, SCAN_WORKER_EVEN, "偶数网段")
    print(f"✅ {province_name} 扫描完成，累计有效IP：{len(valid_links)} 个\n")
    return valid_links

def load_history_ips():
    history = []
    if os.path.exists("history.txt"):
        with open("history.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("http"):
                    history.append(line)
    return list(set(history))

def save_history_ips(all_valid):
    with open("history.txt", "w", encoding="utf-8") as f:
        for link in all_valid:
            f.write(link + "\n")

def process_final_output(all_valid_links, alias_map, cate_order, cate_chan):
    # 先执行新测速排序
    tested_links = speed_test_all_links(all_valid_links)
    sorted_links = [item["URL"] for item in tested_links]

    # 以下全部原版逻辑不变
    channel_link_map = {}
    for cate in cate_chan:
        for ch in cate_chan[cate]:
            channel_link_map[ch] = []
    for link in sorted_links:
        for cate in cate_chan:
            for ch in cate_chan[cate]:
                ch_std = alias_map.get(ch, ch)
                if ch in link or ch_std in link:
                    if link not in channel_link_map[ch]:
                        channel_link_map[ch].append(link)

    # 生成txt
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        now_time = datetime.now().strftime("%Y/%m/%d %H:%M 更新")
        f.write(f"#genre#{now_time}\n")
        for cate in cate_order:
            f.write(f"{cate},#genre#\n")
            for ch in cate_chan[cate]:
                links = channel_link_map.get(ch, [])
                if links:
                    for lk in links:
                        f.write(f"{ch},{lk}\n")
                else:
                    f.write(f"{ch},\n")

    # 生成m3u
    with open("zubo_all.m3u", "w", encoding="utf-8") as f:
        now_m3u_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write("#EXTM3U x-tvg-url=\"https://gh-proxy/https://raw.githubusercontent.com/fogret/sourt/refs/heads/master/output/epg/epg.gz\"\n")
        f.write(f'#EXTINF:-1 tvg-id="time" tvg-name="更新时间" group-title="🕘️更新时间",{now_m3u_time}\n127.0.0.1\n')
        for cate in cate_order:
            for ch in cate_chan[cate]:
                links = channel_link_map.get(ch, [])
                if links:
                    for lk in links:
                        logo_name = alias_map.get(ch, ch)
                        logo_url = f"https://www.xn--rgv465a.top/tvlogo/{logo_name}.png"
                        f.write(f'#EXTINF:-1 tvg-id="{ch}" tvg-name="{ch}" tvg-logo="{logo_url}" group-title="{cate}",{ch}\n{lk}\n')

def main():
    print("=========================")
    print("      开始批量扫描")
    print("=========================")
    all_valid = []
    history_ips = load_history_ips()
    print(f"加载历史存档IP：{len(history_ips)} 条\n")
    all_valid.extend(history_ips)

    ip_dir = "ip"
    if os.path.exists(ip_dir):
        for fname in os.listdir(ip_dir):
            if fname.endswith("_config.txt"):
                province = fname.replace("_config.txt","")
                print(f"=============================")
                print(f"开始处理：{province}")
                print(f"==============================")
                cfg_path = os.path.join(ip_dir, fname)
                ip_cfg = read_config(cfg_path)
                if ip_cfg:
                    res = scan_province(ip_cfg, province)
                    all_valid.extend(res)

    all_valid = list(set(all_valid))
    save_history_ips(all_valid)
    print(f"全部扫描结束，合并总有效IP：{len(all_valid)} 条")

    alias = load_alias_map()
    cate_order, cate_chan = load_demo_order()
    process_final_output(all_valid, alias, cate_order, cate_chan)
    print("✅ 全部处理完成，已生成 zubo_all.txt 和 zubo_all.m3u")

if __name__ == "__main__":
    main()
