# -*- coding: utf-8 -*-
import os
import requests
from concurrent.futures import ThreadPoolExecutor

# ==================== 配置 不用随便改 稳+快 不漏扫 ====================
SCAN_THREADS = 120
CHECK_TIMEOUT = 0.7
SAVE_DIR = "ip"
BATCH_STEP = 256

# 只做基础连通检测 不做深度测速 后期你自己测
UDPXY_API_LIST = ["/stat", "/status"]
# 国内IPTV通用全量端口
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

# ==================== 自动查询：国家+省份+运营商 ====================
def get_ip_info(ip):
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}?lang=zh-CN", timeout=1.3)
        data = res.json()
        # 不是中国 直接丢弃
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

# ==================== 快速检测udpxy是否存活 只看通不通 ====================
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

# ==================== 全IP遍历 全国挨个扫 自动分省分运营商 ====================
def scan_all_country_ip():
    # 字典：key=省份+运营商  value=有效ip列表
    all_result = {}

    # 全网公网完整范围 0.0.0.1 ~ 255.255.255.255
    start_ip = ip_to_int("0.0.0.1")
    end_ip = ip_to_int("255.255.255.255")
    current = start_ip

    print("✅ 开始全国全IP遍历扫描", flush=True)
    print("✅ 自动分省、分电信联通移动、国外自动过滤", flush=True)

    while current <= end_ip:
        batch_end = min(current + BATCH_STEP - 1, end_ip)
        ip_list = [int_to_ip(n) for n in range(current, batch_end + 1)]

        print(f"\n📡 扫描区间：{int_to_ip(current)} ~ {int_to_ip(batch_end)}", flush=True)

        # 组装所有扫描任务
        tasks = []
        for ip in ip_list:
            for p in SCAN_PORTS:
                tasks.append((ip, p))

        # 多线程批量扫描
        with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
            res_list = list(exe.map(lambda x: check_alive(*x), tasks))

        # 过滤有效结果 归类省份+运营商
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

    # 所有结果去重
    for k in all_result:
        all_result[k] = sorted(list(set(all_result[k])))
    return all_result

# ==================== 生成文件 和你现有文件名、格式完全一致 ====================
def save_file(data):
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    for name, ip_list in data.items():
        # 文件名：广东电信_config.txt 完全跟你现有的一模一样
        file_path = os.path.join(SAVE_DIR, f"{name}_config.txt")
        # 每行格式：ip:端口,12 完全对齐你原版
        write_lines = [line + ",12" for line in ip_list]

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(write_lines))

        print(f"\n📁 已生成：{name}_config.txt  数量：{len(write_lines)}")

# ==================== 主程序 ====================
def main():
    res = scan_all_country_ip()
    save_file(res)
    print("\n======================================")
    print("🎉 全国所有省份扫描全部结束 全部保存完成")
    print("======================================")

if __name__ == "__main__":
    main()
