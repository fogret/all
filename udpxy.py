# -*- coding: utf-8 -*-
import os
import requests
from concurrent.futures import ThreadPoolExecutor
import sys

# ===================== 全局配置 =====================
SCAN_THREADS = 60
CHECK_TIMEOUT = 1.2
SAVE_DIR = "ip"
BATCH_STEP = 512

# 全部 udpxy 完整检测接口
UDPXY_API_PATHS = [
    "/stat",
    "/status",
    "/udp/status",
    "/udp/stat",
    "/get_status",
    "/info",
    "/udp/info"
]

# 全覆盖 IPTV 常用组播端口
IPTV_PORTS = [
    3456,4000,4022,6000,7086,8012,8077,
    8188,8686,8800,8888,8899,9000
]

# 浏览器UA
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 三大运营商 完整官方大网段
ALL_FULL_NET_SEG = {
    "电信": [
        ("113.0.0.0", "113.255.255.255"),
        ("114.0.0.0", "114.255.255.255"),
        ("211.0.0.0", "211.255.255.255")
    ],
    "联通": [
        ("121.0.0.0", "121.255.255.255"),
        ("123.0.0.0", "123.255.255.255"),
        ("60.0.0.0", "60.255.255.255")
    ],
    "移动": [
        ("171.0.0.0", "171.255.255.255"),
        ("221.0.0.0", "221.255.255.255"),
        ("58.0.0.0", "58.255.255.255")
    ]
}

# ===================== IP进制转换 =====================
def ip_to_num(ip):
    a, b, c, d = map(int, ip.split('.'))
    return (a << 24) | (b << 16) | (c << 8) | d

def num_to_ip(num):
    return f"{(num>>24)&0xff}.{(num>>16)&0xff}.{(num>>8)&0xff}.{num&0xff}"

# 识别真实运营商，非当前运营商网段直接跳过
def get_ip_real_operator(ip):
    ip_num = ip_to_num(ip)
    for op, seg_list in ALL_FULL_NET_SEG.items():
        for (start_ip, end_ip) in seg_list:
            s = ip_to_num(start_ip)
            e = ip_to_num(end_ip)
            if s <= ip_num <= e:
                return op
    return ""

# ===================== udpxy 全接口存活检测 =====================
def check_udpxy_alive(ip, port):
    try:
        # 循环遍历所有udpxy接口，任意一个能通就算有效
        for api in UDPXY_API_PATHS:
            url = f"http://{ip}:{port}{api}"
            r = requests.get(url, timeout=CHECK_TIMEOUT, headers=HEADERS)
            if "udpxy" in r.text.lower() or "multi stream daemon" in r.text:
                return f"{ip}:{port}"
    except:
        pass
    return None

# ===================== 单运营商 全网段分批扫描 =====================
def scan_operator_full_net(op_name):
    op_all_valid = []
    print(f"\n========================================", flush=True)
    print(f"【开始全量扫描 {op_name} 完整全网段】", flush=True)
    print("========================================", flush=True)
    sys.stdout.flush()

    for (start_ip, end_ip) in ALL_FULL_NET_SEG[op_name]:
        start_num = ip_to_num(start_ip)
        end_num = ip_to_num(end_ip)
        current = start_num

        while current <= end_num:
            batch_end = min(current + BATCH_STEP - 1, end_num)
            batch_ip_list = []

            for n in range(current, batch_end + 1):
                ip = num_to_ip(n)
                real_op = get_ip_real_operator(ip)
                # 不是对应运营商网段 直接跳过
                if real_op != op_name:
                    continue
                batch_ip_list.append(ip)

            print(f"\n📡 扫描区间: {num_to_ip(current)} ~ {num_to_ip(batch_end)} | 待扫IP: {len(batch_ip_list)}", flush=True)
            sys.stdout.flush()

            task_list = []
            for ip in batch_ip_list:
                for port in IPTV_PORTS:
                    task_list.append((ip, port))

            if task_list:
                with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
                    res = list(exe.map(lambda x: check_udpxy_alive(*x), task_list))
                valid = [item for item in res if item]
                op_all_valid.extend(valid)
                print(f"✅ 本段完成，本段有效udpxy: {len(valid)} 条", flush=True)

            current = batch_end + 1

    op_all_valid = sorted(list(set(op_all_valid)))
    print(f"\n✅ {op_name} 全网扫描完毕 | 真实有效udpxy总数: {len(op_all_valid)} 条", flush=True)
    sys.stdout.flush()
    return op_all_valid

# ===================== 主程序 =====================
def main():
    print("✅ 启动 全网段扫描 + 全量udpxy接口检测 + 自动运营商匹配", flush=True)
    sys.stdout.flush()

    final_result = {}
    # 按顺序 电信→联通→移动 依次扫描
    for op in ["电信","联通","移动"]:
        final_result[op] = scan_operator_full_net(op)

    # 自动分类生成文件 格式 ip:端口,12
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    for op, data_list in final_result.items():
        file_name = f"{op}_config.txt"
        save_path = os.path.join(SAVE_DIR, file_name)
        write_lines = [line + ",12" for line in data_list]
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("\n".join(write_lines))
        print(f"\n📁 已保存: ip/{file_name} | 有效条数: {len(write_lines)}", flush=True)

    total_all = sum(len(v) for v in final_result.values())
    print("\n========================================", flush=True)
    print(f"🎉 全部扫描结束 | 全网真实有效udpxy总和: {total_all} 条", flush=True)
    print("========================================", flush=True)

if __name__ == "__main__":
    main()
