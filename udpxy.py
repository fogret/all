# -*- coding: utf-8 -*-
import os
import time
import datetime
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 基础配置 =====================
SCAN_THREADS = 100
CHECK_TIMEOUT = 1.2
SAVE_DIR = "ip"
IPTV_PORTS = [4000,4022,8012,8188,8686,8800,2083,7086]

# 浏览器UA请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 全国 运营商大网段 自动匹配规则
OP_SEG_MAP = [
    ("电信", ["113.0.0.0/8", "114.0.0.0/8", "211.0.0.0/8"]),
    ("联通", ["121.0.0.0/8", "123.0.0.0/8", "60.0.0.0/8"]),
    ("移动", ["171.0.0.0/8", "221.0.0.0/8", "58.0.0.0/8"])
]

# 批量遍历扫描的总大网段池
SCAN_ALL_SEGS = [
    "113.0.0.0-113.255.255.255",
    "114.0.0.0-114.255.255.255",
    "211.0.0.0-211.255.255.255",
    "121.0.0.0-121.255.255.255",
    "123.0.0.0-123.255.255.255",
    "60.0.0.0-60.255.255.255",
    "171.0.0.0-171.255.255.255",
    "221.0.0.0-221.255.255.255",
    "58.0.0.0-58.255.255.255"
]

# ===================== IP工具函数 =====================
def ip_str_to_int(ip):
    a,b,c,d = map(int, ip.split('.'))
    return a << 24 | b << 16 | c << 8 | d

def int_to_ip_str(num):
    return f"{(num>>24)&0xff}.{(num>>16)&0xff}.{(num>>8)&0xff}.{num&0xff}"

def gen_ip_list(ip_range):
    start, end = ip_range.split('-')
    start_num = ip_str_to_int(start)
    end_num = ip_str_to_int(end)
    ip_list = []
    for n in range(start_num, end_num + 1):
        ip_list.append(int_to_ip_str(n))
    return ip_list

# 判断IP属于哪个运营商
def get_ip_operator(ip):
    ip_num = ip_str_to_int(ip)
    for op, cidr_list in OP_SEG_MAP:
        for cidr in cidr_list:
            ip_seg, mask = cidr.split('/')
            mask = int(mask)
            seg_num = ip_str_to_int(ip_seg)
            if (ip_num >> (32 - mask)) == (seg_num >> (32 - mask)):
                return op
    return "未知运营商"

# ===================== IPTV udpxy 检测 带UA =====================
def check_iptv_udpxy(ip, port):
    try:
        url1 = f"http://{ip}:{port}/stat"
        url2 = f"http://{ip}:{port}/status"
        res1 = requests.get(url1, timeout=CHECK_TIMEOUT, headers=HEADERS)
        res2 = requests.get(url2, timeout=CHECK_TIMEOUT, headers=HEADERS)
        if "udpxy" in res1.text or "Multi stream daemon" in res1.text or "udpxy" in res2.text:
            return f"{ip}:{port}"
    except:
        return None

# ===================== 按单段网段分批扫描 =====================
def scan_single_segment(seg):
    all_task = []
    print(f"\n========================================")
    print(f"开始扫描网段：{seg}")
    print("========================================")

    ips = gen_ip_list(seg)
    for ip in ips:
        for p in IPTV_PORTS:
            all_task.append((ip, p))

    total = len(all_task)
    print(f"本段待扫描总数：{total}")

    temp_alive = []
    count = 0

    with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
        futures = [exe.submit(check_iptv_udpxy, ip, pt) for ip, pt in all_task]
        for fu in as_completed(futures):
            count += 1
            ret = fu.result()
            if ret:
                temp_alive.append(ret)
            if count % 5000 == 0:
                print(f"已扫描：{count}/{total} | 当前存活：{len(temp_alive)}")

    temp_alive = sorted(list(set(temp_alive)))
    print(f"\n✅ 本段扫描完成，有效IP：{len(temp_alive)} 条")
    return temp_alive

# ===================== 自动归类、自动生成对应文件 =====================
def auto_save_to_file(alive_list):
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    # 按运营商分类存放
    op_dict = {}
    for item in alive_list:
        ip = item.split(":")[0]
        op = get_ip_operator(ip)
        if op not in op_dict:
            op_dict[op] = []
        op_dict[op].append(item)

    # 自动生成 运营商_config.txt 文件，格式和你现有完全一致
    for op, ip_list in op_dict.items():
        # 文件名自动生成：运营商_config.txt
        file_name = f"{op}_config.txt"
        save_path = os.path.join(SAVE_DIR, file_name)
        # 自动拼接 ,12 格式
        lines = sorted(list(set([x + ",12" for x in ip_list])))
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"📁 已自动生成文件：ip/{file_name}  有效条数：{len(lines)}")

# ===================== 主程序 =====================
def main():
    print("========== 启动全自动IPTV组播扫描 自动匹配运营商生成文件 ==========")
    total_all_alive = []

    # 逐个网段分批扫描，不一次性加载巨量IP
    for seg in SCAN_ALL_SEGS:
        res = scan_single_segment(seg)
        total_all_alive.extend(res)

    # 全局去重 + 自动分类存文件
    total_all_alive = sorted(list(set(total_all_alive)))
    auto_save_to_file(total_all_alive)

    print("\n========================================")
    print("          全部网段扫描结束")
    print("========================================")
    print(f"全局去重总有效组播IP：{len(total_all_alive)} 条")
    print(f"所有文件已自动分类保存至 ip 文件夹")
    print("========================================")

if __name__ == "__main__":
    main()
