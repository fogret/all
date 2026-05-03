# -*- coding: utf-8 -*-
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor

# 低配稳跑 不卡死
THREAD_NUM = 30
TIMEOUT = 1.5
SAVE_FOLDER = "ip_scan"
SCAN_PORTS = ["4000","4022","8188","8800"]

# 你原版全部网段 原样不动
PROVINCE_IP_SEG = [
    ("北京", "219.142"),("天津", "60.28"),("河北", "60.6"),
    ("山西", "59.49"),("内蒙古", "1.24"),("辽宁", "61.133"),
    ("吉林", "58.154"),("黑龙江", "112.100"),("上海", "116.228"),
    ("江苏", "58.192"),("浙江", "60.12"),("安徽", "60.166"),
    ("福建", "218.85"),("江西", "59.52"),("山东", "58.56"),
    ("河南", "61.158"),("湖北", "58.48"),("湖南", "36.111"),
    ("广东", "113.96"),("广西", "116.252"),("海南", "218.77"),
    ("重庆", "61.128"),("四川", "61.139"),("贵州", "61.159"),
    ("云南", "222.172"),("西藏", "59.151"),("陕西", "113.140"),
    ("甘肃", "42.90"),("青海", "36.255"),("宁夏", "59.110"),
    ("新疆", "124.88"),
]

# 单IP单独检测
def check_udpxy(ip, port):
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

# 单省份 分段生成IP 不一次性加载海量数据
def scan_prov(prov, ab):
    print(f"\n======== 开始扫描 {prov} {ab}.x.x ========")
    alive = []
    # 分段循环，慢慢生成，不会开局卡死
    for c in range(0,256):
        batch_ip = []
        for d in range(1,255):
            batch_ip.append(f"{ab}.{c}.{d}")
        
        # 每一段小批量扫描
        with ThreadPoolExecutor(max_workers=THREAD_NUM) as t:
            for ip in batch_ip:
                for p in SCAN_PORTS:
                    res = check_udpxy(ip, p)
                    if res:
                        alive.append(res)
        
        # 每跑完一段打印进度
        print(f"{prov} 已扫描到 {c}/255 段 | 当前有效：{len(alive)}")

    alive = list(set(alive))
    print(f"✅ {prov} 扫描完成，有效IP：{len(alive)}")
    return alive

def main():
    if not os.path.exists(SAVE_FOLDER):
        os.mkdir(SAVE_FOLDER)

    # 开局立刻打印，马上出日志
    print("===== 程序正常启动，开始扫描 =====")

    for prov, ab in PROVINCE_IP_SEG:
        data = scan_prov(prov, ab)
        path = os.path.join(SAVE_FOLDER, f"{prov}_config.txt")
        with open(path, "w", encoding="utf-8") as f:
            for line in data:
                f.write(line + ",12\n")

    print("\n===== 全部省份扫描完毕 =====")

if __name__ == "__main__":
    main()
