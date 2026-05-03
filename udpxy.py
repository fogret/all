# -*- coding: utf-8 -*-
import os
import requests
from concurrent.futures import ThreadPoolExecutor

# ==================== 配置 ====================
SCAN_THREADS = 120
CHECK_TIMEOUT = 0.7
# 新建单独文件夹 output 存放结果，完全不碰你原本的ip文件夹
SAVE_DIR = "output"
BATCH_STEP = 256

UDPXY_API_LIST = ["/stat", "/status"]
SCAN_PORTS = [4000,4022,8012,8188,8686,8800,8888,8899]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ==================== IP 进制转换 ====================
def ip_to_int(ip):
    a,b,c,d = map(int, ip.split('.'))
    return (a << 24) | (b << 16) | (c << 8) | d

def int_to_ip(num):
    return f"{(num>>24)&0xff}.{(num>>16)&0xff}.{(num>>8)&0xff}.{num&0xff}"

# ==================== 自动查询 国家/省份/运营商 ====================
def get_ip_info(ip):
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}?lang=zh-CN", timeout=1.3)
        data = res.json()
        if data.get("country") != "中国":
            return None, None
        
        province = data.get("regionName", "").strip()
        isp = data.get("isp", "").strip()

        if "电信" in isp:
            op = "电信"
        elif "联通" in isp or "网通" in isp:
            op = "联通"
        elif "移动" in isp or "铁通" in isp:
            op = "移动"
        else:
            return None, None
        
        return province, op
    except:
        return None, None

# ==================== 快速存活检测 只测通不通 ====================
def check_alive(ip, port):
    try:
        for api in UDPXY_API_LIST:
            url = f"http://{ip}:{port}{api}"
            r = requests.get(url, timeout=CHECK_TIMEOUT, headers=HEADERS)
            if "udpxy" in r.text.lower() or "multi stream daemon" in r.text:
                return f"{ip}:{port}"
    except:
        pass
    return None

# ==================== 全国全IP遍历扫描 ====================
def scan_all_country_ip():
    all_result = {}
    start_ip = ip_to_int("0.0.0.1")
    end_ip = ip_to_int("255.255.255.255")
    current = start_ip

    print("✅ 开始全国全IP遍历扫描", flush=True)
    print("✅ 结果全部存入 output 文件夹，不改动你原有任何文件", flush=True)

    while current <= end_ip:
        batch_end = min(current + BATCH_STEP - 1, end_ip)
        ip_list = [int_to_ip(n) for n in range(current, batch_end + 1)]

        print(f"\n📡 扫描区间：{int_to_ip(current)} ~ {int_to_ip(batch_end)}", flush=True)

        tasks = []
        for ip in ip_list:
            for p in SCAN_PORTS:
                tasks.append((ip, p))

        with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
            res_list = list(exe.map(lambda x: check_alive(*x), tasks))

        valid_data = [i for i in res_list if i]
        for item in valid_data:
            ip_addr = item.split(":")[0]
            province, op = get_ip_info(ip_addr)
            if not province or not op:
                continue

            file_key = f"{province}{op}"
            if file_key not in all_result:
                all_result[file_key] = []
            all_result[file_key].append(item)

        print(f"✅ 本段扫描完成 有效存活：{len(valid_data)} 条", flush=True)
        current = batch_end + 1

    for k in all_result:
        all_result[k] = sorted(list(set(all_result[k])))
    return all_result

# ==================== 保存到 output 文件夹 格式完全一致 ====================
def save_file(data):
    # 自动新建output文件夹，和原ip文件夹完全分开
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    for name, ip_list in data.items():
        file_path = os.path.join(SAVE_DIR, f"{name}_config.txt")
        write_lines = [line + ",12" for line in ip_list]

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(write_lines))

        print(f"\n📁 已生成：output/{name}_config.txt  数量：{len(write_lines)}")

# ==================== 主程序 ====================
def main():
    res = scan_all_country_ip()
    save_file(res)
    print("\n======================================")
    print("🎉 全国省份扫描全部结束，文件全部保存在output文件夹")
    print("======================================")

if __name__ == "__main__":
    main()
