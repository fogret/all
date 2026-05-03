# -*- coding: utf-8 -*-
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= 基础配置 =================
SAVE_DIR = "output"
SCAN_THREADS = 50
TIMEOUT = 1.5
SCAN_PORTS = ["4000","4022","8188","8800","8888","8899","2083"]

# 北京 贵州 湖南 网段 全部写死在这里
SCAN_LIST = [
    ("北京","电信",
    ["114.252.0.0/16","115.42.0.0/16","116.247.0.0/16"]),
    ("北京","联通",
    ["61.135.0.0/16","123.126.0.0/16","202.96.0.0/16"]),
    ("北京","移动",
    ["211.136.0.0/16","221.176.0.0/16"]),

    ("贵州","电信",
    ["113.110.0.0/16","114.139.0.0/16","219.151.0.0/16"]),
    ("贵州","联通",
    ["111.85.0.0/16","221.13.0.0/16"]),
    ("贵州","移动",
    ["58.42.0.0/16","221.192.0.0/16"]),

    ("湖南","电信",
    ["113.240.0.0/16","175.10.0.0/16"]),
    ("湖南","联通",
    ["112.92.0.0/16","61.150.160.0/16"]),
    ("湖南","移动",
    ["59.51.0.0/16","115.208.0.0/16"]),
]

# 简单单IP检测 不搞复杂逻辑
def check_ip(ip, port):
    try:
        r = requests.get(f"http://{ip}:{port}/stat", timeout=TIMEOUT)
        if "udpxy" in r.text:
            return f"{ip}:{port}"
    except:
        pass
    try:
        r = requests.get(f"http://{ip}:{port}/status", timeout=TIMEOUT)
        if "udpxy" in r.text:
            return f"{ip}:{port}"
    except:
        pass
    return None

# 生成ip 简单不卡死
def gen_ips(net):
    ips = []
    a,b,c,d = net.split('.')
    base = f"{a}.{b}.{c}"
    for i in range(1,255):
        ips.append(f"{base}.{i}")
    return ips

def main():
    # 第一步直接打印 开局就有日志
    print("==== 程序开始运行 正常启动 ====")
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    for prov,isp,nets in SCAN_LIST:
        print(f"\n======== 开始扫描 {prov}{isp} ========")
        all_ips = []
        for net in nets:
            ip_arr = gen_ips(net)
            all_ips.extend(ip_arr)
            print(f"加载网段 {net}  数量：{len(ip_arr)}")
        
        task_all = []
        for ip in all_ips:
            for p in SCAN_PORTS:
                task_all.append((ip,p))
        
        res_list = []
        num = 0
        with ThreadPoolExecutor(max_workers=SCAN_THREADS) as tp:
            for ret in tp.map(lambda x: check_ip(*x), task_all):
                num += 1
                if num % 400 == 0:
                    print(f"已扫描 {num} / 总{len(task_all)}  有效：{len(res_list)}")
                if ret:
                    res_list.append(ret)
        
        # 去重写入 文件格式 ip:端口,12
        res_list = list(set(res_list))
        print(f"{prov}{isp} 扫描完成 有效IP：{len(res_list)}")

        with open(f"{SAVE_DIR}/{prov}{isp}_config.txt","w",encoding="utf-8") as f:
            for line in res_list:
                f.write(line + ",12\n")

    print("\n==== 全部省份扫描完毕 ====")

if __name__ == "__main__":
    main()
