# -*- coding: utf-8 -*-
import os
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 保存目录 单独新建 不改动你原文件
SAVE_DIR = "output"
# 扫描并发、超时 稳定不卡死
SCAN_THREADS = 80
SCAN_TIMEOUT = 1.5

# 端口 沿用你原版常用端口
SCAN_PORTS = [
    "4000","4022","7086","8188","8800","8888",
    "8899","2083","6000","8077","8686"
]

# ===================== 只写入 北京 / 贵州 / 湖南 精准专用IP网段 =====================
PROVINCE_SEG_LIST = [
    # 北京
    {"prov":"北京","isp":"电信","seg_list":[
        "114.252.0.0/12","115.42.0.0/16","116.247.0.0/16","120.204.0.0/14"
    ]},
    {"prov":"北京","isp":"联通","seg_list":[
        "61.135.96.0/19","61.149.60.0/23","123.126.0.0/14","202.96.0.0/12"
    ]},
    {"prov":"北京","isp":"移动","seg_list":[
        "211.136.0.0/13","221.176.0.0/12","222.128.0.0/12"
    ]},

    # 贵州
    {"prov":"贵州","isp":"电信","seg_list":[
        "113.110.0.0/14","114.139.0.0/16","183.224.0.0/12","219.151.0.0/16"
    ]},
    {"prov":"贵州","isp":"联通","seg_list":[
        "111.85.0.0/16","219.138.0.0/15","221.13.0.0/16"
    ]},
    {"prov":"贵州","isp":"移动","seg_list":[
        "58.42.0.0/15","120.192.0.0/12","221.192.0.0/12"
    ]},

    # 湖南
    {"prov":"湖南","isp":"电信","seg_list":[
        "113.240.0.0/13","175.10.0.0/15","220.168.128.0/17"
    ]},
    {"prov":"湖南","isp":"联通","seg_list":[
        "112.92.0.0/14","61.150.160.0/24","222.246.128.0/17"
    ]},
    {"prov":"湖南","isp":"移动","seg_list":[
        "59.51.0.0/16","115.208.0.0/13","221.208.0.0/13"
    ]},
]

# CIDR网段 转全部IP列表
def cidr_to_ip_list(cidr):
    import ipaddress
    ip_list = []
    try:
        net = ipaddress.IPv4Network(cidr, strict=False)
        for ip in net:
            ip_list.append(str(ip))
    except:
        pass
    return ip_list

# 单个IP+端口 存活检测 沿用你原版逻辑
def check_ip_alive(ip, port):
    try:
        url1 = f"http://{ip}:{port}/stat"
        url2 = f"http://{ip}:{port}/status"
        res = os.popen(f"curl -s -m {SCAN_TIMEOUT} {url1} {url2}").read()
        if "udpxy" in res.lower() or "rtp" in res:
            return f"{ip}:{port}"
    except:
        pass
    return None

# 批量扫描当前省份运营商所有网段
def scan_one_prov_isp(prov, isp, seg_list):
    all_ip_pool = []
    for seg in seg_list:
        all_ip_pool.extend(cidr_to_ip_list(seg))
    all_ip_pool = list(set(all_ip_pool))
    print(f"【开始扫描 {prov}{isp}】 共计待扫描IP：{len(all_ip_pool)} 个")

    alive_result = []
    with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
        task_list = []
        for ip in all_ip_pool:
            for port in SCAN_PORTS:
                task_list.append(exe.submit(check_ip_alive, ip, port))
        
        finish_num = 0
        for task in as_completed(task_list):
            finish_num += 1
            if finish_num % 200 == 0:
                print(f"{prov}{isp} 已扫描：{finish_num}/{len(task_list)} | 已累计有效：{len(alive_result)}")
            ret = task.result()
            if ret:
                alive_result.append(ret)
    
    alive_result = list(set(alive_result))
    print(f"【{prov}{isp} 扫描完成】 有效可用IP：{len(alive_result)} 条\n")
    return alive_result

# 主程序入口
def main():
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)
    print("===== 开始扫描 北京 / 贵州 / 湖南 三省IPTV专用网段 =====")
    print("===== 结果全部保存到 output 文件夹 =====")

    for item in PROVINCE_SEG_LIST:
        prov_name = item["prov"]
        isp_name = item["isp"]
        seg_arr = item["seg_list"]

        # 扫描当前省份运营商
        alive_data = scan_one_prov_isp(prov_name, isp_name, seg_arr)
        # 写入对应文件 格式 ip:端口,12
        file_name = f"{prov_name}{isp_name}_config.txt"
        file_path = os.path.join(SAVE_DIR, file_name)

        with open(file_path, "w", encoding="utf-8") as f:
            for line in alive_data:
                f.write(line + ",12\n")
    
    print("==================== 全部省份扫描完毕 ====================")
    print(f"所有文件已全部生成完毕，存放目录：./{SAVE_DIR}")

if __name__ == "__main__":
    main()
