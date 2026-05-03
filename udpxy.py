# -*- coding: utf-8 -*-
import os
import time
import datetime
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 配置 可控分批生成IP 防卡死 =====================
SCAN_THREADS = 80
CHECK_TIMEOUT = 1.2
SAVE_DIR = "ip"
IPTV_PORTS = [4000,4022,8012,8188,8686,8800,2083,7086]

# 关键：每一批最多生成扫描 2000 个IP，严格控制，不爆内存不卡死
BATCH_IP_LIMIT = 2000

# 浏览器UA请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 全国运营商大网段
OP_SEG_MAP = [
    ("电信", ["113.0.0.0/8", "114.0.0.0/8", "211.0.0.0/8"]),
    ("联通", ["121.0.0.0/8", "123.0.0.0/8", "60.0.0.0/8"]),
    ("移动", ["171.0.0.0/8", "221.0.0.0/8", "58.0.0.0/8"])
]

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

# 分段生成IP：按批次限量生成，不一次性全部输出
def gen_ip_batch(ip_range, start_offset, batch_size):
    start, end = ip_range.split('-')
    start_num = ip_str_to_int(start)
    end_num = ip_str_to_int(end)

    current_start = start_num + start_offset
    if current_start > end_num:
        return [], 0

    current_end = min(current_start + batch_size - 1, end_num)
    batch_ips = []
    for n in range(current_start, current_end + 1):
        batch_ips.append(int_to_ip_str(n))

    next_offset = start_offset + batch_size
    return batch_ips, next_offset

# 判断IP运营商
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

# ===================== 单网段 循环分批扫描 =====================
def scan_seg_by_batch(seg):
    all_alive = []
    offset = 0
    print(f"\n========================================")
    print(f"开始分段扫描网段：{seg}")
    print("========================================")

    while True:
        # 每次只生成限量一批IP
        batch_ips, offset = gen_ip_batch(seg, offset, BATCH_IP_LIMIT)
        if not batch_ips:
            break

        task_list = []
        for ip in batch_ips:
            for p in IPTV_PORTS:
                task_list.append((ip, p))

        if not task_list:
            continue

        print(f"本批次生成IP任务：{len(task_list)} 个")
        batch_alive = []

        with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
            futures = [exe.submit(check_iptv_udpxy, ip, pt) for ip, pt in task_list]
            for fu in as_completed(futures):
                res = fu.result()
                if res:
                    batch_alive.append(res)

        batch_alive = list(set(batch_alive))
        all_alive.extend(batch_alive)
        print(f"本批次扫描完成，本轮有效IP：{len(batch_alive)} | 累计当前网段有效：{len(all_alive)}")

    all_alive = sorted(list(set(all_alive)))
    print(f"\n✅ 网段 {seg} 全部分批扫描完毕，总有效IP：{len(all_alive)}")
    return all_alive

# ===================== 自动归类生成对应文件 =====================
def auto_save_to_file(alive_list):
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    op_dict = {}
    for item in alive_list:
        ip = item.split(":")[0]
        op = get_ip_operator(ip)
        if op not in op_dict:
            op_dict[op] = []
        op_dict[op].append(item)

    for op, ip_list in op_dict.items():
        file_name = f"{op}_config.txt"
        save_path = os.path.join(SAVE_DIR, file_name)
        lines = sorted(list(set([x + ",12" for x in ip_list])))
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"📁 自动生成文件：ip/{file_name} | 有效数量：{len(lines)}")

# ===================== 主程序 =====================
def main():
    print("========== 启动IPTV分批限量扫描 严格控制IP生成数量 ==========")
    total_all_alive = []

    for seg in SCAN_ALL_SEGS:
        res = scan_seg_by_batch(seg)
        total_all_alive.extend(res)

    total_all_alive = sorted(list(set(total_all_alive)))
    auto_save_to_file(total_all_alive)

    print("\n========================================")
    print("        所有网段分批扫描全部完成")
    print("========================================")
    print(f"全局去重总有效组播IP：{len(total_all_alive)} 条")
    print("========================================")

if __name__ == "__main__":
    main()
