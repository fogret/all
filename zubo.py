# -*- coding: utf-8 -*-
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

# ===================== 【扫描专项提速优化配置】=====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"
CONFIG_INI = "config.ini"

# 仅修改测速稳定参数，根治播放断续跳解码
SPEED_CONCURRENCY = 50
SPEED_TIMEOUT = 2.8
BANDWIDTH_TEST_DURATION = 1.8
MIN_VALID_BYTES = 1024 * 512
DROP_SLOW_DELAY = 1.8

# udpxy节点权重上调，稳定节点优先级拉满
LIVE_TOP_WEIGHT = 6
LIVE_GOOD_WEIGHT = 4
NORMAL_WEIGHT = 2
TEMP_WEIGHT = 1
INVALID_WEIGHT = 0

# 【扫描提速关键参数】完全原样未改动
IP_CHECK_TIMEOUT = 1.0
SINGLE_SCAN_TIMEOUT = 180
SCAN_WORKER_ODD = 380
SCAN_WORKER_EVEN = 160

# ===================== 读取config.ini配置 不变 =====================
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

# ===================== 别名分类加载 不变 =====================
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

# ===================== 读取配置 不变 =====================
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

# ===================== IP网段生成 不变 =====================
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

# ===================== 【优化】单个IP检测 超时缩短，拒绝无效等待 =====================
def check_ip_port(ip_port, url_end):
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=IP_CHECK_TIMEOUT)
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            return ip_port
    except:
        return None

# ===================== 【优化】扫描核心 高并发+高效进度打印 =====================
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
                print(f"已扫描：{checked}/{total} | 有效IP：{len(valid_ip_ports)}个")

    return valid_ip_ports

# ===================== 旧存档IP重扫 不变 =====================
def check_old_single_ip(ip_port):
    res1 = check_ip_port(ip_port, "/stat")
    if res1:
        return ip_port
    res2 = check_ip_port(ip_port, "/status")
    if res2:
        return ip_port
    return None

# ===================== 逐省扫描 新旧IP合并 不变 =====================
def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"\n{'='*30}\n开始处理：{province}\n{'='*30}")

    configs = sorted(set(read_config(config_file)))
    new_valid_ips = []

    for idx, (ip, port, option, url_end) in enumerate(configs, 1):
        try:
            print(f"\n开始扫描第{idx}个网段：{ip}:{port}")
            res = scan_ip_port(ip, port, option, url_end)
            new_valid_ips.extend(res)
        except Exception as e:
            print(f"❌ 第{idx}个网段扫描异常，自动跳过本网段，继续执行下一个：{e}")
            continue

    archive_path = f"ip/存档_{province}_ip.txt"
    old_survive_ips = []
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            old_ip_list = [line.strip() for line in f if line.strip()]
        print(f"\n加载历史存档IP：{len(old_ip_list)} 个，开始重扫校验")
        with ThreadPoolExecutor(max_workers=60) as exe:
            out = exe.map(check_old_single_ip, old_ip_list)
            old_survive_ips = [x for x in out if x]

    # 新IP+旧存活IP 去重合并
    all_final_ips = sorted(list(set(new_valid_ips + old_survive_ips)))

    print(f"\n{province} 汇总结果：")
    print(f"新扫描有效IP：{len(new_valid_ips)} 个")
    print(f"旧存档重扫存活：{len(old_survive_ips)} 个")
    print(f"本次最终写入总数：{len(all_final_ips)} 个")

    # 写入当前省份IP文件
    with open(f"ip/{province}_ip.txt", "w", encoding="utf-8") as f:
        if all_final_ips:
            f.write("\n".join(all_final_ips))

    if not os.path.exists("ip"):
        os.mkdir("ip")

    # 同步更新存档文件
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
            output.append(f"{province}-组播{idx},#genre#\n")
            output.append(tem_channels.replace("ipipip", ip))
        with open(f"组播_{province}.txt", "w", encoding="utf-8") as f:
            f.writelines(output)
        print(f"✅ {province} 组播文件生成完成")
    else:
        print(f"❌ 未找到 template_{province}.txt")

# ===================== 重写节点判定：双接口稳态计分，过滤瞬时假好节点 =====================
async def check_node_type(session, ip_port):
    stable_score = 0
    try:
        async with session.get(f"http://{ip_port}/stat", timeout=1.4) as r:
            text = await r.text()
            txt_len = len(text)
            if txt_len > 1300 and "stream" in text and "client" in text:
                stable_score += 3
            elif txt_len > 800:
                stable_score += 2
            elif txt_len > 400:
                stable_score += 1
    except:
        pass

    try:
        async with session.get(f"http://{ip_port}/status", timeout=1.4) as r:
            text = await r.text()
            txt_len = len(text)
            if txt_len > 1300 and "stream" in text and "client" in text:
                stable_score += 3
            elif txt_len > 800:
                stable_score += 2
            elif txt_len > 400:
                stable_score += 1
    except:
        pass

    if stable_score >= 6:
        return ip_port, LIVE_TOP_WEIGHT
    elif stable_score >= 4:
        return ip_port, LIVE_GOOD_WEIGHT
    elif stable_score >= 2:
        return ip_port, NORMAL_WEIGHT
    elif stable_score >= 1:
        return ip_port, TEMP_WEIGHT
    else:
        return ip_port, INVALID_WEIGHT

# ===================== 重写测速：大分片真实码率、低流量直接判劣源 =====================
async def test_single_url(session, url):
    try:
        start = time.time()
        total_bytes = 0
        async with session.get(url, timeout=SPEED_TIMEOUT) as r:
            while time.time() - start < BANDWIDTH_TEST_DURATION:
                chunk = await r.content.read(1024 * 64)
                if not chunk:
                    break
                total_bytes += len(chunk)
        cost = round(time.time() - start, 3)
        # 流量不达标判定无效低带宽
        if total_bytes < MIN_VALID_BYTES:
            return url, cost, 0.0
        bandwidth = round((total_bytes * 8) / 1024 / 1024 / BANDWIDTH_TEST_DURATION, 2)
        return url, cost, bandwidth
    except:
        return url, 999.9, 0.0

# ===================== 新版排序：带宽越快越靠前，延迟次之，全部线路保留不删除 =====================
async def speed_sort_all_channels(channel_list):
    name_url_origin = channel_list.copy()
    tasks = []
    type_tasks = []
    conn = aiohttp.TCPConnector(limit=SPEED_CONCURRENCY, ttl_dns_cache=600)

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

    speed_dict = {url:(cost,bw) for url,cost,bw in speed_res}
    group = {}
    for name, url in name_url_origin:
        if name not in group:
            group[name] = []
        cost, bw = speed_dict.get(url, (999.9, 0.0))
        node_w = node_type_dict.get(url_ip_map.get(url,""), TEMP_WEIGHT)
        
        # 权重：带宽 >> 延迟 >> 稳定
        score = bw * 100 - cost * 15 + node_w * 3
        group[name].append((url, cost, bw, node_w, score))

    final_list = []
    for name, url_info_list in group.items():
        url_info_list.sort(key=lambda x: (-x[2], x[1], -x[3]))
        for u, _, _, _, _ in url_info_list:
            final_list.append((name, u))

    return final_list

# ===================== TXT转M3U 不变 =====================
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

# ===================== 频道别名统一+分类排序 不变 =====================
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

    print("\n========== 节点带宽测速排序，全部线路完整保留 ==========")
    all_channel_data = asyncio.run(speed_sort_all_channels(all_channel_data))
    print("========== 网速最快线路置顶，依次从快到慢排序完成 ==========\n")

    res = []
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    time_str = now.strftime("%Y/%m/%d %H:%M")
    res.append("更新时间,#genre#\n")
    res.append(f"{time_str},http://127.0.0.1\n\n")

    for cate in cate_order:
        res.append(f"{cate},#genre#\n")
        for std_chan in cate_chan_dict[cate]:
            for chan_name, chan_url in all_channel_data:
                if chan_name == std_chan:
                    res.append(f"{chan_name},{chan_url}\n")
        res.append("\n")

    return "".join(res)

# ===================== 主函数 不变 =====================
def main():
    if not os.path.exists("ip"):
        os.mkdir("ip")

    for config_file in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(config_file)

    file_contents = []
    for file_path in glob.glob('组播_*.txt'):
        with open(file_path, 'r', encoding="utf-8") as f:
            content = f.read()
            if content.strip():
                file_contents.append(content)

    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")
    origin_total = f"{current_time}更新,#genre#\n"
    origin_total += f"浙江卫视,http://ali-m-l.cztv.com/channels/lantian/channel001/1080p.m3u8\n"
    origin_total += '\n'.join(file_contents)

    final_total = reorder_channel_content(origin_total)

    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(final_total)

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print("\n===== 全部执行完成 网速最快优先排序，所有线路完整保留 =====")

if __name__ == "__main__":
    main()
