# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import datetime
from datetime import datetime, timezone, timedelta
import glob
import socket
import requests
import aiohttp
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 全局稳定配置 直接改数字即可 =====================
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"
SPEED_CONCURRENCY = 60
SPEED_TIMEOUT = 3.0
# 单个网段最大扫描超时，杜绝卡死停滞
SINGLE_SCAN_TIMEOUT = 65
# 扫描并发 均衡速度+稳定 不卡不崩
SCAN_WORKER_ODD = 220
SCAN_WORKER_EVEN = 90

# ===================== 别名分类加载 完全原版不动 =====================
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

# ===================== 读取配置 原版完全不变 =====================
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

# ===================== IP网段生成 原版逻辑一字不改 =====================
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

# ===================== 单个IP检测 原版不变 =====================
def check_ip_port(ip_port, url_end):    
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=2)
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            return ip_port
    except:
        return None

# ===================== 【稳定防卡死核心版扫描函数】 =====================
def scan_ip_port(ip, port, option, url_end):
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    total = len(ip_ports)
    checked = 0
    start_scan_time = time.time()

    # 合理分配并发，稳又快
    work_num = SCAN_WORKER_ODD if option % 2 == 1 else SCAN_WORKER_EVEN

    with ThreadPoolExecutor(max_workers=work_num) as executor:
        futures = {executor.submit(check_ip_port, ip_port, url_end): ip_port for ip_port in ip_ports}

        for future in as_completed(futures):
            # 超时直接终止，防止卡死阻塞后续所有扫描
            if time.time() - start_scan_time > SINGLE_SCAN_TIMEOUT:
                print(f"⚠️ 当前网段扫描超时，强制结束，避免卡死")
                executor.shutdown(wait=False, cancel_futures=True)
                break

            res = future.result()
            if res:
                valid_ip_ports.append(res)
            checked += 1

            # 全部网段 统一打印进度，不分奇偶，全程看得见
            if checked % 2000 == 0 or checked == total:
                print(f"已扫描：{checked}/{total} | 有效IP：{len(valid_ip_ports)}个")

    # 扫描完毕 彻底释放线程资源
    executor.shutdown(wait=True)
    return valid_ip_ports

# ===================== 旧存档IP重扫 原版不变 =====================
def check_old_single_ip(ip_port):
    res1 = check_ip_port(ip_port, "/stat")
    if res1:
        return ip_port
    res2 = check_ip_port(ip_port, "/status")
    if res2:
        return ip_port
    return None

# ===================== 逐省扫描 加异常捕获 绝不跳过网段 =====================
def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"\n{'='*30}\n开始处理：{province}\n{'='*30}")

    configs = sorted(set(read_config(config_file)))
    new_valid_ips = []

    # 循环加异常捕获，单个网段报错不中断、不跳过下一个
    for idx, (ip, port, option, url_end) in enumerate(configs, 1):
        try:
            print(f"\n开始扫描第{idx}个网段：{ip}:{port}")
            res = scan_ip_port(ip, port, option, url_end)
            new_valid_ips.extend(res)
        except Exception as e:
            print(f"❌ 第{idx}个网段扫描异常，自动跳过本网段，继续执行下一个：{e}")
            continue

    # 下面所有写入、存档、生成文件逻辑 全部原版不动
    archive_path = f"ip/存档_{province}_ip.txt"
    old_survive_ips = []
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            old_ip_list = [line.strip() for line in f if line.strip()]
        print(f"\n加载历史存档IP：{len(old_ip_list)} 个，开始重扫校验")
        with ThreadPoolExecutor(max_workers=120) as exe:
            out = exe.map(check_old_single_ip, old_ip_list)
            old_survive_ips = [x for x in out if x]

    all_final_ips = sorted(list(set(new_valid_ips + old_survive_ips)))

    print(f"\n{province} 汇总结果：")
    print(f"新扫描有效IP：{len(new_valid_ips)} 个")
    print(f"旧存档重扫存活：{len(old_survive_ips)} 个")
    print(f"本次最终写入总数：{len(all_final_ips)} 个")

    with open(f"ip/{province}_ip.txt", "w", encoding="utf-8") as f:
        if all_final_ips:
            f.write("\n".join(all_final_ips))

    if not os.path.exists("ip"):
        os.mkdir("ip")
    old_lines = []
    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            old_lines = f.readlines()
    for ip_port in new_valid_ips:
        old_lines.append(ip_port + "\n")
    old_lines = sorted(set(old_lines))
    with open(archive_path, "w", encoding="utf-8") as f:
        f.writelines(old_lines)

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

# ===================== 【全新替换：真实拉流H264稳流测速】只改这里 其他不动 =====================
def test_real_stream_speed(url):
    test_duration = 8
    idle_threshold = 3.0
    try:
        response = requests.get(url, stream=True, timeout=(3, 1))
        response.raise_for_status()
    except requests.RequestException:
        return url, 0.0

    response.raw.decode_content = False
    start_time = time.time()
    last_data_time = start_time

    while time.time() - start_time < test_duration:
        try:
            chunk = response.raw.read(1024)
            if chunk:
                last_data_time = time.time()
            else:
                return url, round(last_data_time - start_time, 1)
        except (socket.timeout, requests.exceptions.ReadTimeout):
            pass
        except Exception:
            return url, round(last_data_time - start_time, 1)

        if time.time() - last_data_time > idle_threshold:
            return url, round(last_data_time - start_time, 1)

    return url, 8.0

def speed_sort_all_channels(channel_list):
    if not channel_list:
        return []
    print("开始真实拉流测速检测，判断播放稳定性...")

    # 多线程并发拉流测速
    res_data = []
    with ThreadPoolExecutor(max_workers=SPEED_CONCURRENCY) as exe:
        futures = [exe.submit(test_real_stream_speed, url) for _, url in channel_list]
        for fu in as_completed(futures):
            res_data.append(fu.result())

    # 按频道分组，同频道 稳定分数越高 排越前面
    group = {}
    for name, url in channel_list:
        if name not in group:
            group[name] = []
    for url, score in res_data:
        for n, u in channel_list:
            if u == url:
                group[n].append( (u, score) )
                break

    final_list = []
    for name, url_score_list in group.items():
        # 稳定度倒序排序，最稳不断流排第一
        url_score_list.sort(key=lambda x: x[1], reverse=True)
        for u, _ in url_score_list:
            final_list.append( (name, u) )

    print("真实拉流测速排序完成，所有线路完整保留")
    return final_list

# ===================== TXT转M3U 原版不变 =====================
def txt_to_m3u(input_file, output_file):
    if not os.path.exists(input_file):
        return
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, 'w', encoding="utf-8") as f:
        genre = ''
        for line in lines:
            line = line.strip()
            if "," in line:
                channel_name, channel_url = line.split(',', 1)
                if channel_url == '#genre#':
                    genre = channel_name
                else:
                    f.write(f'#EXTINF:-1 group-title="{genre}",{channel_name}\n')
                    f.write(f'{channel_url}\n')

# ===================== 分类改名 原版不变 =====================
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
            all_channel_data.append( (new_name, url.strip()) )

    # 调用新的真实拉流测速排序
    all_channel_data = speed_sort_all_channels(all_channel_data)

    res = []
    # 【已修复报错的时间代码】
    now = datetime.now(timezone.utc) + timedelta(hours=8)
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

# ===================== 主函数 流程不变 =====================
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
    
    now = datetime.now(timezone.utc) + timedelta(hours=8)
    current_time = now.strftime("%Y/%m/%d %H:%M")
    origin_total = f"{current_time}更新,#genre#\n"
    origin_total += f"浙江卫视,http://ali-m-l.cztv.com/channels/lantian/channel001/1080p.m3u8\n"
    origin_total += '\n'.join(file_contents)

    final_total = reorder_channel_content(origin_total)

    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(final_total)

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print("\n===== 全部执行完成 真实拉流测速排序完毕，所有线路完整保留 =====")

if __name__ == "__main__":
    main()
