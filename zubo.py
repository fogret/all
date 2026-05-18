# coding: utf-8

from threading import Thread
import os
import time
import datetime
import glob
import requests
import configparser
import aiohttp
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== Scan Speed Optimize Config =====================

ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"
CONFIG_INI = "config.ini"

# Speed Test Optimize Params
SPEED_CONCURRENCY = 80
SPEED_TIMEOUT = 2.2
BANDWIDTH_TEST_DURATION = 1.2
MIN_VALID_BYTES = 1024 * 128
DROP_SLOW_DELAY = 1.5

# UDProxy Node Weight Grade
LIVE_TOP_WEIGHT = 4
LIVE_GOOD_WEIGHT = 3
NORMAL_WEIGHT = 2
TEMP_WEIGHT = 1
INVALID_WEIGHT = 0

# Fast Scan Core Params
IP_CHECK_TIMEOUT = 1.0
SINGLE_SCAN_TIMEOUT = 180
SCAN_WORKER_ODD = 380
SCAN_WORKER_EVEN = 160

# ===================== Load Ini Config =====================
def load_ini_config():
    cfg = configparser.ConfigParser()
    epg_url = ""
    logo_domain = ""
    default_logo = ""
    if os.path.exists(CONFIG_INI):
        cfg.read(CONFIG_INI, encoding="utf-8")
        if "EPG" in cfg:
            epg_url = cfg["EPG"].get("epg_url", "").strip()
        if "LOGO" in cfg:
            logo_domain = cfg["LOGO"].get("logo_domain", "").strip()
            default_logo = cfg["LOGO"].get("default_logo", "").strip()
    return epg_url, logo_domain, default_logo

# ===================== Load Alias Map =====================
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

# ===================== Load Demo Category Order =====================
def load_demo_order():
    cate_list = []
    cate_chan = {}
    now_cate = ""
    if os.path.exists(DEMO_FILE):
        with open(DEMO_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.endswith(",#genre#"):
                    now_cate = line.replace(",#genre#","")
                    cate_list.append(now_cate)
                    cate_chan[now_cate] = []
                elif now_cate:
                    cate_chan[now_cate].append(line)
    return cate_list, cate_chan

# ===================== Read Province Config =====================
def read_config(config_file):
    print(f"Read config file: {config_file}")
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
                    print(f"Line {line_num}: http://{ip}:{port}{url_end} added to scan list")
        return ip_configs
    except Exception as e:
        print(f"Read config error: {e}")
        return []

# ===================== Generate IP Range List =====================
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

# ===================== Single IP Port Check =====================
def check_ip_port(ip_port, url_end):
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=IP_CHECK_TIMEOUT)
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            return ip_port
    except:
        return None

# ===================== Core High Concurrent Scan =====================
def scan_ip_port(ip, port, option, url_end):
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    total = len(ip_ports)
    checked = 0

    work_num = SCAN_WORKER_ODD if option % 2 == 1 else SCAN_WORKER_EVEN

    with ThreadPoolExecutor(max_workers=work_num) as executor:
        futures = {executor.submit(check_ip_port, ip_port, url_end): ip_port for ip_port in ip_ports}

        for future in as_completed(futures):
            res = future.result()
            if res:
                valid_ip_ports.append(res)
            checked += 1

            if checked % 2000 == 0 or checked == total:
                print(f"Scanned: {checked}/{total} | Valid IP: {len(valid_ip_ports)}")

    return valid_ip_ports

# ===================== Recheck Old Archive IP =====================
def check_old_single_ip(ip_port):
    res1 = check_ip_port(ip_port, "/stat")
    if res1:
        return ip_port
    res2 = check_ip_port(ip_port, "/status")
    if res2:
        return ip_port
    return None

# ===================== Province Scan & Merge Old/New IP =====================
def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"\n{'='*30}\nProcess: {province}\n{'='*30}")

    configs = sorted(set(read_config(config_file)))
    new_valid_ips = []

    for idx, (ip, port, option, url_end) in enumerate(configs, 1):
        try:
            print(f"\nScan segment {idx}: {ip}:{port}")
            res = scan_ip_port(ip, port, option, url_end)
            new_valid_ips.extend(res)
        except Exception as e:
            print(f"Segment {idx} scan error, skip: {e}")
            continue

    archive_path = f"ip/archive_{province}_ip.txt"
    old_survive_ips = []
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            old_ip_list = [line.strip() for line in f if line.strip()]
        print(f"\nLoad old archive IP: {len(old_ip_list)}, recheck alive")
        with ThreadPoolExecutor(max_workers=60) as exe:
            out = exe.map(check_old_single_ip, old_ip_list)
            old_survive_ips = [x for x in out if x]

    all_final_ips = sorted(list(set(new_valid_ips + old_survive_ips)))

    print(f"\n{province} Summary:")
    print(f"New valid IP: {len(new_valid_ips)}")
    print(f"Old alive IP: {len(old_survive_ips)}")
    print(f"Final save total: {len(all_final_ips)}")

    with open(f"ip/{province}_ip.txt", "w", encoding="utf-8") as f:
        if all_final_ips:
            f.write("\n".join(all_final_ips))

    if not os.path.exists("ip"):
        os.mkdir("ip")

    full_archive_ips = sorted(list(set(all_final_ips)))
    with open(archive_path, "w", encoding="utf-8") as f:
        for ipa in full_archive_ips:
            f.write(ipa + "\n")

    template_file = os.path.join('template', f"template_{province}.txt")
    if os.path.exists(template_file):
        with open(template_file, "r", encoding="utf-8") as f:
            tem_channels = f.read()
        output = []
        for idx, single_ip in enumerate(all_final_ips, 1):
            ip = single_ip.strip()
            output.append(f"{province}-Multicast{idx},#genre#\n")
            output.append(tem_channels.replace("ipipip", ip))
        with open(f"multicast_{province}.txt", "w", encoding="utf-8") as f:
            f.writelines(output)
        print(f"✅ {province} multicast file generated")
    else:
        print(f"❌ template_{province}.txt not found")

# ===================== Async Node Stability Judge =====================
async def check_node_type(session, ip_port):
    check_url1 = f"http://{ip_port}/stat"
    check_url2 = f"http://{ip_port}/status"
    stable_score = 0
    retry_times = 2

    for _ in range(retry_times):
        try:
            async with session.get(check_url1, timeout=1.2) as r:
                text = await r.text()
                txt_len = len(text)
                if txt_len > 1200 and "stream" in text and "client" in text:
                    stable_score += 3
                elif txt_len > 700:
                    stable_score += 2
                elif txt_len > 300:
                    stable_score += 1
        except:
            pass
        await asyncio.sleep(0.1)

    for _ in range(retry_times):
        try:
            async with session.get(check_url2, timeout=1.2) as r:
                text = await r.text()
                txt_len = len(text)
                if txt_len > 1200 and "stream" in text and "client" in text:
                    stable_score += 3
                elif txt_len > 700:
                    stable_score += 2
                elif txt_len > 300:
                    stable_score += 1
        except:
            pass
        await asyncio.sleep(0.1)

    if stable_score >= 10:
        return ip_port, LIVE_TOP_WEIGHT
    elif stable_score >= 6:
        return ip_port, LIVE_GOOD_WEIGHT
    elif stable_score >= 3:
        return ip_port, NORMAL_WEIGHT
    elif stable_score >= 1:
        return ip_port, TEMP_WEIGHT
    else:
        return ip_port, INVALID_WEIGHT

# ===================== Bandwidth Speed Test =====================
async def test_single_url(session, url):
    try:
        start = time.time()
        total_bytes = 0
        async with session.get(url, timeout=SPEED_TIMEOUT) as r:
            while time.time() - start < BANDWIDTH_TEST_DURATION:
                chunk = await r.content.read(1024 * 32)
                if not chunk:
                    break
                total_bytes += len(chunk)
            await r.read()
        cost = round(time.time() - start, 3)
        if total_bytes < MIN_VALID_BYTES:
            return url, cost, 0.0
        bandwidth = round((total_bytes * 8) / 1024 / 1024 / BANDWIDTH_TEST_DURATION, 2)
        return url, cost, bandwidth
    except Exception:
        return url, 999.9, 0.0

# ===================== Weight Sort All Channels Keep All Lines =====================
async def speed_sort_all_channels(channel_list):
    name_url_origin = channel_list.copy()
    tasks = []
    type_tasks = []
    conn = aiohttp.TCPConnector(limit=SPEED_CONCURRENCY, ttl_dns_cache=300, force_close=True)

    ip_set = set()
    url_ip_map = {}
    for name, url in name_url_origin:
        ip_port = url.split('/rtp/')[0].replace('http://','')
        ip_set.add(ip_port)
        url_ip_map[url] = ip_port

    async with aiohttp.ClientSession(connector=conn) as session:
        for ip in ip_set:
            type_tasks.append(check_node_type(session, ip))
        type_res = await asyncio.gather(*type_tasks)
        node_type_dict = {ip:w for ip,w in type_res}

        for _, url in name_url_origin:
            tasks.append(test_single_url(session, url))
        speed_res = await asyncio.gather(*tasks)

        group = {}
        for name, url in name_url_origin:
            if name not in group:
                group[name] = []
            for url, cost, bw in speed_res:
                for n, u in name_url_origin:
                    if u == url:
                        node_w = node_type_dict.get(url_ip_map[url], TEMP_WEIGHT)
                        score = node_w * 45 + bw * 45 - cost * 10
                        group[n].append((u, cost, bw, node_w, score))
                        break

        final_list = []
        for name, url_info_list in group.items():
            url_info_list.sort(key=lambda x: (-x[4], -x[2], x[1]))
            for u, _, _, _, _ in url_info_list:
                final_list.append((name, u))

    return final_list

# ===================== Txt To M3U =====================
def txt_to_m3u(input_file, output_file):
    if not os.path.exists(input_file):
        return
    epg_url, logo_domain, default_logo = load_ini_config()
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, "w", encoding="utf-8") as f:
        if epg_url:
            f.write(f'#EXTM3U x-tvg-url="{epg_url}"\n')
        else:
            f.write("#EXTM3U\n")
        genre = ''
        for line in lines:
            line = line.strip()
            if "," in line:
                channel_name, channel_url = line.split(',', 1)
                if channel_url == '#genre#':
                    genre = channel_name
                else:
                    logo_url = f"{logo_domain}{channel_name}.png" if logo_domain else default_logo
                    f.write(f'#EXTINF:-1 tvg-id="{channel_name}" tvg-name="{channel_name}" tvg-logo="{logo_url}" group-title="{genre}",{channel_name}\n')
                    f.write(f'{channel_url}\n')

# ===================== Rename & Sort Channels =====================
def reorder_channel_content(origin_merge_text):
    alias_map = load_alias_map()
    cate_order, cate_chan_dict = load_demo_order()

    all_channel_data = []
    lines = origin_merge_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.endswith(",#genre#"):
            continue
        if "," in line:
            name, url = line.split(",", 1)
            new_name = alias_map.get(name.strip(), name.strip())
            all_channel_data.append((new_name, url.strip()))

    print("\n========== Node Detect + Async Speed Sort, All Lines Reserved ==========")
    all_channel_data = asyncio.run(speed_sort_all_channels(all_channel_data))
    print("========== High Quality Source Sorted Finish ==========\n")

    res = []
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    time_str = now.strftime("%Y/%m/%d %H:%M")
    res.append("Update Time,#genre#\n")
    res.append(f"{time_str},http://127.0.0.1\n\n")

    for cate in cate_order:
        res.append(f"{cate},#genre#\n")
        for std_chan in cate_chan_dict[cate]:
            for chan_name, chan_url in all_channel_data:
                if chan_name == std_chan:
                    res.append(f"{chan_name},{chan_url}\n")
        res.append("\n")

    return "".join(res)

# ===================== Main Entry =====================
def main():
    if not os.path.exists("ip"):
        os.mkdir("ip")

    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    file_contents = []
    for file_path in glob.glob('multicast_*.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            content = f.read()
            if content.strip():
                file_contents.append(content)

    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")
    origin_total = f"{current_time} Update,#genre#\n"
    origin_total += f"ZJTV,http://ali-m-l.cztv.com/channels/lantian/channel001/1080p.m3u8\n"
    origin_total += '\n'.join(file_contents)

    final_total = reorder_channel_content(origin_total)

    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(final_total)

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print("\n===== All Task Done, Full Lines Saved & Optimized Sort =====")

if __name__ == "__main__":
    main()
