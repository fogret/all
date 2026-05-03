# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed

# 基础配置 跟你原代码保持一致
SCAN_WORKERS = 60
SCAN_TIMEOUT = 1.2
SAVE_DIR = "output"
SCAN_PORTS = ["4000","4022","8188","8800","8888","8899","2083","6000"]

# 固定写入 北京 贵州 湖南 精准网段
SCAN_DATA = [
    ("北京","电信",[
        "114.252.0.0/12","115.42.0.0/16","116.247.0.0/16"
    ]),
    ("北京","联通",[
        "61.135.96.0/19","123.126.0.0/14","202.96.0.0/12"
    ]),
    ("北京","移动",[
        "211.136.0.0/13","221.176.0.0/12"
    ]),

    ("贵州","电信",[
        "113.110.0.0/14","114.139.0.0/16","219.151.0.0/16"
    ]),
    ("贵州","联通",[
        "111.85.0.0/16","221.13.0.0/16"
    ]),
    ("贵州","移动",[
        "58.42.0.0/15","221.192.0.0/12"
    ]),

    ("湖南","电信",[
        "113.240.0.0/13","175.10.0.0/15"
    ]),
    ("湖南","联通",[
        "112.92.0.0/14","61.150.160.0/24"
    ]),
    ("湖南","移动",[
        "59.51.0.0/16","115.208.0.0/13"
    ]),
]

# 网段转IP 最简稳定写法 不卡死
def get_ip_list(cidr):
    try:
        return [str(ip) for ip in ipaddress.IPv4Network(cidr, strict=False)]
    except:
        return []

# 原版udpxy存活检测 完全照搬你原代码逻辑
def check_alive(ip, port):
    try:
        url = f"http://{ip}:{port}/stat"
        res = requests.get(url, timeout=SCAN_TIMEOUT)
        if "udpxy" in res.text:
            return f"{ip}:{port}"
    except:
        pass
    try:
        url = f"http://{ip}:{port}/status"
        res = requests.get(url, timeout=SCAN_TIMEOUT)
        if "udpxy" in res.text:
            return f"{ip}:{port}"
    except:
        pass
    return None

# 单省份单运营商扫描 日志清晰不刷屏
def start_scan(prov, isp, cidr_list):
    all_ips = []
    for cidr in cidr_list:
        ips = get_ip_list(cidr)
        all_ips.extend(ips)
        print(f"读取网段 {cidr}  IP数量：{len(ips)}")
    
    all_ips = list(set(all_ips))
    total = len(all_ips)
    print(f"\n【开始扫描 {prov}{isp}】 总计待扫IP：{total}")

    ok_list = []
    count = 0

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as t:
        task = []
        for ip in all_ips:
            for p in SCAN_PORTS:
                task.append((ip,p))
        
        for res in t.map(lambda x: check_alive(*x), task):
            count += 1
            if count % 300 == 0:
                print(f"{prov}{isp} 已扫描：{count} | 有效数量：{len(ok_list)}")
            if res:
                ok_list.append(res)
    
    ok_list = list(set(ok_list))
    print(f"✅ {prov}{isp} 扫描完成，有效IP：{len(ok_list)}\n")
    return ok_list

def main():
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)
    print("========== 开始扫描 北京 / 贵州 / 湖南 ==========")

    for prov,isp,cidr_arr in SCAN_DATA:
        res = start_scan(prov,isp,cidr_arr)
        # 输出格式 ip:端口,12 和你原文件完全一致
        with open(f"{SAVE_DIR}/{prov}{isp}_config.txt","w",encoding="utf-8") as f:
            for line in res:
                f.write(line + ",12\n")
    
    print("========== 全部扫描完成 ==========")

if __name__ == "__main__":
    import requests
    main()
