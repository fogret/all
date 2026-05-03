# -*- coding: utf-8 -*-
import os
import requests
from concurrent.futures import ThreadPoolExecutor

# ================= 基础配置 =================
THREAD_NUM = 65
TIMEOUT = 1.8
# 独立新文件夹，不和你原文件冲突
SAVE_FOLDER = "ip_scan"
SCAN_PORTS = ["4000","4022","8188","8800","8888","8899","2083","6000"]

# ================= 完全照搬你给的全国省份网段 =================
PROVINCE_IP_SEG = [
    ("北京", "219.142"),
    ("天津", "60.28"),
    ("河北", "60.6"),
    ("山西", "59.49"),
    ("内蒙古", "1.24"),
    ("辽宁", "61.133"),
    ("吉林", "58.154"),
    ("黑龙江", "112.100"),
    ("上海", "116.228"),
    ("江苏", "58.192"),
    ("浙江", "60.12"),
    ("安徽", "60.166"),
    ("福建", "218.85"),
    ("江西", "59.52"),
    ("山东", "58.56"),
    ("河南", "61.158"),
    ("湖北", "58.48"),
    ("湖南", "36.111"),
    ("广东", "113.96"),
    ("广西", "116.252"),
    ("海南", "218.77"),
    ("重庆", "61.128"),
    ("四川", "61.139"),
    ("贵州", "61.159"),
    ("云南", "222.172"),
    ("西藏", "59.151"),
    ("陕西", "113.140"),
    ("甘肃", "42.90"),
    ("青海", "36.255"),
    ("宁夏", "59.110"),
    ("新疆", "124.88"),
]

# 生成 A.B.x.x 全部IP
def generate_all_ip(ab_seg):
    ip_list = []
    for c in range(0, 256):
        for d in range(1, 255):
            ip_list.append(f"{ab_seg}.{c}.{d}")
    return ip_list

# 检测udpxy存活
def check_udpxy(ip, port):
    try:
        res = requests.get(f"http://{ip}:{port}/stat", timeout=TIMEOUT)
        if "udpxy" in res.text.lower():
            return f"{ip}:{port}"
    except:
        pass
    try:
        res = requests.get(f"http://{ip}:{port}/status", timeout=TIMEOUT)
        if "udpxy" in res.text.lower():
            return f"{ip}:{port}"
    except:
        pass
    return None

# 单省扫描+完整日志输出
def scan_one_prov(prov_name, ab_seg):
    print(f"\n==============================")
    print(f"开始扫描：{prov_name} | 网段 {ab_seg}.x.x")
    print(f"==============================")

    ip_pool = generate_all_ip(ab_seg)
    total_ip = len(ip_pool)
    print(f"待扫描IP总量：{total_ip} 个")

    task_list = []
    for ip in ip_pool:
        for p in SCAN_PORTS:
            task_list.append((ip, p))

    alive_list = []
    finish = 0

    with ThreadPoolExecutor(max_workers=THREAD_NUM) as pool:
        for ret in pool.map(lambda x: check_udpxy(*x), task_list):
            finish += 1
            # 每800条打印一次进度，日志不刷屏
            if finish % 800 == 0:
                print(f"已扫描：{finish}/{len(task_list)} | 有效累计：{len(alive_list)}")
            if ret:
                alive_list.append(ret)

    alive_list = list(set(alive_list))
    print(f"\n✅ {prov_name} 扫描完成 | 有效IP：{len(alive_list)} 条")
    return alive_list

def main():
    # 新建独立文件夹，不碰你原有任何文件
    if not os.path.exists(SAVE_FOLDER):
        os.mkdir(SAVE_FOLDER)

    # 开局第一行就打印，直接出日志，不会空白卡住
    print("========== 全国IPTV扫描程序 已成功启动 ==========")
    print(f"所有扫描结果 统一保存至：{SAVE_FOLDER} 文件夹")

    # 逐省依次扫描
    for prov, seg in PROVINCE_IP_SEG:
        ok_data = scan_one_prov(prov, seg)
        file_path = os.path.join(SAVE_FOLDER, f"{prov}_config.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            for line in ok_data:
                f.write(line + ",12\n")

    print("\n==================== 所有省份扫描全部结束 ====================")

if __name__ == "__main__":
    main()
