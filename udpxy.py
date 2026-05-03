# -*- coding: utf-8 -*-
import os
import time
import datetime
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 稳定适配GitHub 配置 =====================
SCAN_THREADS = 100
CHECK_TIMEOUT = 1.2
SAVE_DIR = "iptv_scan_result"
# IPTV专属通用端口
IPTV_PORTS = [4000,4022,8012,8188,8686,8800,2083,7086]

# 请求头 加入标准UA
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 按运营商 单独分类拆分网段 分批扫描
IPTV_SEG_CLASS = {
    "电信IPTV": [
        "113.0.0.0-113.255.255.255",
        "114.0.0.0-114.255.255.255",
        "211.0.0.0-211.255.255.255"
    ],
    "联通IPTV": [
        "121.0.0.0-121.255.255.255",
        "123.0.0.0-123.255.255.255",
        "60.0.0.0-60.255.255.255"
    ],
    "移动IPTV": [
        "171.0.0.0-171.255.255.255",
        "221.0.0.0-221.255.255.255",
        "58.0.0.0-58.255.255.255"
    ]
}

# ===================== IP格式转换工具 =====================
def ip_str_to_int(ip):
    a,b,c,d = map(int, ip.split('.'))
    return a << 24 | b << 16 | c << 8 | d

def int_to_ip_str(num):
    return f"{(num>>24)&0xff}.{(num>>16)&0xff}.{(num>>8)&0xff}.{num&0xff}"

# 生成单段IP列表
def gen_ip_list(ip_range):
    start, end = ip_range.split('-')
    start_num = ip_str_to_int(start)
    end_num = ip_str_to_int(end)
    ip_list = []
    for n in range(start_num, end_num + 1):
        ip_list.append(int_to_ip_str(n))
    return ip_list

# ===================== 纯IPTV udpxy存活检测 带UA请求头 =====================
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

# ===================== 单类网段扫描函数 =====================
def scan_one_class(class_name, seg_list):
    all_task = []
    print(f"\n========================================")
    print(f"【开始扫描 {class_name}】")
    print("========================================")

    for seg in seg_list:
        ips = gen_ip_list(seg)
        for ip in ips:
            for p in IPTV_PORTS:
                all_task.append((ip, p))

    total = len(all_task)
    print(f"{class_name} 本轮总扫描任务：{total}")

    alive = []
    count = 0

    with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
        futures = [exe.submit(check_iptv_udpxy, ip, pt) for ip, pt in all_task]
        for fu in as_completed(futures):
            count += 1
            ret = fu.result()
            if ret:
                alive.append(ret)
            # 进度日志 不刷屏
            if count % 5000 == 0:
                print(f"{class_name} 已扫描：{count}/{total} | 本轮存活IP：{len(alive)}")

    alive = sorted(list(set(alive)))
    print(f"\n✅ {class_name} 扫描完成，本轮有效IP：{len(alive)} 条")
    return alive

# ===================== 主程序 顺序分批执行 =====================
def main():
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    all_total_alive = []

    # 按顺序：电信 → 联通 →移动 逐个分批扫描
    for class_name, seg_list in IPTV_SEG_CLASS.items():
        res = scan_one_class(class_name, seg_list)
        all_total_alive.extend(res)

    # 全部扫完 统一去重合并
    all_total_alive = sorted(list(set(all_total_alive)))
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_path = os.path.join(SAVE_DIR, f"IPTV分类扫描全部有效IP_{now.replace(':','-')}.txt")

    # 写入最终合并结果
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(f"扫描完成时间：{now}\n")
        f.write(f"电信+联通+移动 分类分批合并扫描\n")
        f.write(f"全局去重后总有效IPTV：{len(all_total_alive)} 条\n\n")
        f.write("\n".join(all_total_alive))

    # 最终收尾日志
    print("\n========================================")
    print("      三大运营商 全部扫描完毕")
    print("========================================")
    print(f"合并去重总可用IPTV：{len(all_total_alive)} 条")
    print(f"结果保存文件夹：iptv_scan_result")
    print("========================================")

if __name__ == "__main__":
    main()
