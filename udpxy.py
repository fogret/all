# -*- coding: utf-8 -*-
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor
import sys

# ===================== 极速稳定核心配置 =====================
SCAN_THREADS = 150
CHECK_TIMEOUT = 0.7
SAVE_DIR = "ip"
BATCH_STEP = 256

# 最简快速连通校验，只测通不通，速度最快
UDPXY_CHECK = ["/stat", "/status"]
# IPTV通用全量常用端口
IPTV_PORTS = [3456,4000,4022,6000,7086,8012,8188,8686,8800,8888,8899]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ===================== IP转换工具 =====================
def ip2num(ip):
    a, b, c, d = map(int, ip.split('.'))
    return (a << 24) | (b << 16) | (c << 8) | d

def num2ip(num):
    return f"{(num>>24)&0xff}.{(num>>16)&0xff}.{(num>>8)&0xff}.{num&0xff}"

# ===================== 公网IP 国内/国外 + 运营商自动识别 =====================
def get_ip_location(ip):
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}?lang=zh-CN", timeout=1.5)
        data = res.json()
        if data.get("country") != "中国":
            return "国外"
        isp = data.get("isp","")
        if "电信" in isp:
            return "电信"
        elif "联通" in isp or "网通" in isp:
            return "联通"
        elif "移动" in isp or "铁通" in isp:
            return "移动"
        else:
            return "国内其他"
    except:
        return "未知"

# ===================== 极速udpxy连通检测 只测通断 =====================
def fast_check(ip, port):
    try:
        for api in UDPXY_CHECK:
            url = f"http://{ip}:{port}{api}"
            r = requests.get(url, timeout=CHECK_TIMEOUT, headers=HEADERS)
            if "udpxy" in r.text.lower() or "multi stream daemon" in r.text:
                return f"{ip}:{port}"
    except:
        pass
    return None

# ===================== 全网完整无死角遍历扫描 不写死任何网段 =====================
def scan_all_world_ip():
    # 分类容器
    res_dict = {
        "电信": [],
        "联通": [],
        "移动": []
    }

    print("✅ 开始全网全IP无限制扫描 | 全覆盖所有IPTV源", flush=True)
    print("✅ 不限制网段、不提前划定范围、全球全IP逐个遍历", flush=True)

    # 全网完整范围：0.0.0.1 ~ 255.255.255.255
    start_all = ip2num("0.0.0.1")
    end_all = ip2num("255.255.255.255")
    current = start_all

    while current <= end_all:
        batch_end = min(current + BATCH_STEP - 1, end_all)
        batch_ips = []

        # 逐IP生成，一个不漏、不跳、不缺
        for n in range(current, batch_end + 1):
            ip = num2ip(n)
            batch_ips.append(ip)

        print(f"\n📡 扫描区间：{num2ip(current)} ~ {num2ip(batch_end)}", flush=True)

        # 批量组装扫描任务
        tasks = []
        for ip in batch_ips:
            for p in IPTV_PORTS:
                tasks.append((ip, p))

        # 多线程极速扫描
        if tasks:
            with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
                raw_result = list(exe.map(lambda x: fast_check(*x), tasks))

            # 过滤有效udpxy，再自动归类国内三大运营商
            valid_list = [i for i in raw_result if i]
            for item in valid_list:
                ip_only = item.split(":")[0]
                tag = get_ip_location(ip_only)
                if tag in res_dict:
                    res_dict[tag].append(item)

            print(f"✅ 本段扫描完成，本段存活udpxy总数：{len(valid_list)}", flush=True)

        current = batch_end + 1

    # 全部去重排序
    for k in res_dict:
        res_dict[k] = sorted(list(set(res_dict[k])))
    return res_dict

# ===================== 主程序 输出文件 =====================
def main():
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    # 全网扫描
    all_data = scan_all_world_ip()

    # 分别保存 电信/联通/移动 配置文件
    for op, data_list in all_data.items():
        save_path = os.path.join(SAVE_DIR, f"{op}_config.txt")
        write_lines = [line + ",12" for line in data_list]
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("\n".join(write_lines))
        print(f"\n📁 已导出 {op}_config.txt  有效总量：{len(write_lines)}", flush=True)

    total_sum = sum(len(v) for v in all_data.values())
    print("\n========================================", flush=True)
    print(f"🎉 全网扫描全部结束！国内有效IPTV udpxy 总数：{total_sum}")
    print("========================================", flush=True)

if __name__ == "__main__":
    main()
