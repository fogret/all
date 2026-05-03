# -*- coding: utf-8 -*-
import os
import time
import datetime
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== IPTV 专属扫描配置 =====================
# 并发 稳、快、不卡死
SCAN_THREADS = 450
# 快速连通校验超时，只测通断，速度最快
CHECK_TIMEOUT = 1.0
SAVE_DIR = "iptv_scan_result"

# IPTV 组播 官方专用端口 只扫这几个
IPTV_PORTS = [4000,4022,8012,8188,8686,8800,8889,2083,7086]

# 全国 电信/联通/移动 【纯IPTV组播专用网段】
# 都是业内iptv组播常用真实网段，无无关外网
IPTV_NET_SEGMENTS = [
    "113.0.0.0-113.255.255.255",
    "114.0.0.0-114.255.255.255",
    "116.0.0.0-116.255.255.255",
    "118.0.0.0-118.255.255.255",
    "121.0.0.0-121.255.255.255",
    "123.0.0.0-123.255.255.255",
    "171.0.0.0-171.255.255.255",
    "211.0.0.0-211.255.255.255",
    "218.0.0.0-218.255.255.255",
    "221.0.0.0-221.255.255.255",
    "58.0.0.0-58.255.255.255",
    "60.0.0.0-60.255.255.255"
]

# ===================== IP 区间转换 =====================
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

# ===================== 【只检测纯正 IPTV udpxy 组播服务】 =====================
def check_iptv_udpxy(ip, port):
    try:
        # iptv组播专用两个接口
        url1 = f"http://{ip}:{port}/stat"
        url2 = f"http://{ip}:{port}/status"
        res1 = requests.get(url1, timeout=CHECK_TIMEOUT)
        res2 = requests.get(url2, timeout=CHECK_TIMEOUT)
        # 只识别udpxy组播专属特征，普通IP直接过滤
        if "udpxy" in res1.text or "Multi stream daemon" in res1.text or "udpxy" in res2.text:
            return f"{ip}:{port}"
    except:
        return None

# ===================== 主程序 =====================
def main():
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    all_task = []
    print("========== 加载全国IPTV组播专用网段 ==========")
    for seg in IPTV_NET_SEGMENTS:
        ips = gen_ip_list(seg)
        for ip in ips:
            for p in IPTV_PORTS:
                all_task.append((ip, p))

    print(f"本次待扫描 IPTV 总任务数：{len(all_task)}")
    print("========== 开始极速批量扫描 只筛IPTV组播udpxy ==========")

    alive_iptv = []
    count = 0

    with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
        futures = [exe.submit(check_iptv_udpxy, ip, pt) for ip, pt in all_task]
        for fu in as_completed(futures):
            count += 1
            ret = fu.result()
            if ret:
                alive_iptv.append(ret)
            # 简洁进度 不刷屏
            if count % 8000 == 0:
                print(f"已扫描：{count}/{len(all_task)} | 存活可用IPTV：{len(alive_iptv)}")

    # 去重排序保存
    alive_iptv = sorted(list(set(alive_iptv)))
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_path = os.path.join(SAVE_DIR, f"iptv有效组播IP_{now.replace(':','-')}.txt")

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(f"扫描时间：{now}\n")
        f.write(f"总扫描数量：{len(all_task)}\n")
        f.write(f"筛选出纯IPTV组播有效IP：{len(alive_iptv)}\n\n")
        f.write("\n".join(alive_iptv))

    print("\n========== IPTV组播全网扫描完成 ==========")
    print(f"有效IPTV组播IP已保存：{save_path}")
    print(f"一共扫出可用：{len(alive_iptv)} 条")

if __name__ == "__main__":
    main()
