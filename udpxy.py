# -*- coding: utf-8 -*-
import os
import requests
from concurrent.futures import ThreadPoolExecutor
import sys

# ===================== 核心配置 =====================
SCAN_THREADS = 60
CHECK_TIMEOUT = 1.0
SAVE_DIR = "ip"
IPTV_PORTS = [4000, 4022, 8012, 8188, 8686, 8800, 2083, 7086]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 按运营商分类的/24网段列表（每个仅256个IP，不卡死）
SEG_BY_OP = {
    "电信": [
        "113.0.0.0/24", "113.0.1.0/24", "113.0.2.0/24",
        "114.0.0.0/24", "114.0.1.0/24", "114.0.2.0/24",
        "211.0.0.0/24", "211.0.1.0/24", "211.0.2.0/24"
    ],
    "联通": [
        "121.0.0.0/24", "121.0.1.0/24", "121.0.2.0/24",
        "123.0.0.0/24", "123.0.1.0/24", "123.0.2.0/24",
        "60.0.0.0/24", "60.0.1.0/24", "60.0.2.0/24"
    ],
    "移动": [
        "171.0.0.0/24", "171.0.1.0/24", "171.0.2.0/24",
        "221.0.0.0/24", "221.0.1.0/24", "221.0.2.0/24",
        "58.0.0.0/24", "58.0.1.0/24", "58.0.2.0/24"
    ]
}

# ===================== 工具函数 =====================
def cidr_to_ips(cidr):
    ip_part, mask = cidr.split('/')
    mask = int(mask)
    a, b, c, d = map(int, ip_part.split('.'))
    base = (a << 24) | (b << 16) | (c << 8) | d
    prefix = base & (0xFFFFFFFF << (32 - mask))
    ips = []
    for i in range(0, 2**(32 - mask)):
        ip = prefix + i
        if (ip >> 24) & 0xFF == 127:
            continue
        ips.append(f"{(ip>>24)&0xff}.{(ip>>16)&0xff}.{(ip>>8)&0xff}.{ip&0xff}")
    return ips

def check_iptv(ip, port):
    try:
        url1 = f"http://{ip}:{port}/stat"
        url2 = f"http://{ip}:{port}/status"
        r1 = requests.get(url1, timeout=CHECK_TIMEOUT, headers=HEADERS)
        r2 = requests.get(url2, timeout=CHECK_TIMEOUT, headers=HEADERS)
        if "udpxy" in r1.text or "Multi stream daemon" in r1.text or "udpxy" in r2.text:
            return f"{ip}:{port}"
    except:
        return None

# ===================== 按运营商+网段扫描 =====================
def scan_op(op_name, seg_list):
    op_alive = []
    print(f"\n========================================", flush=True)
    print(f"【开始扫描 {op_name} 网段】", flush=True)
    print("========================================", flush=True)
    sys.stdout.flush()

    for seg in seg_list:
        print(f"\n📡 开始扫描网段：{seg}", flush=True)
        sys.stdout.flush()

        ips = cidr_to_ips(seg)
        tasks = [(ip, port) for ip in ips for port in IPTV_PORTS]

        with ThreadPoolExecutor(max_workers=SCAN_THREADS) as exe:
            results = list(exe.map(lambda x: check_iptv(*x), tasks))

        alive = [r for r in results if r]
        op_alive.extend(alive)
        print(f"✅ 网段 {seg} 完成，有效IP：{len(alive)} 条", flush=True)
        sys.stdout.flush()

    op_alive = sorted(list(set(op_alive)))
    print(f"\n✅ {op_name} 全部网段扫描完成，累计有效IP：{len(op_alive)} 条", flush=True)
    sys.stdout.flush()
    return op_alive

# ===================== 主程序 =====================
def main():
    print("✅ 脚本已启动，开始按运营商分段扫描", flush=True)
    sys.stdout.flush()

    all_alive = {}

    # 按顺序：电信 → 联通 → 移动
    for op, seg_list in SEG_BY_OP.items():
        res = scan_op(op, seg_list)
        all_alive[op] = res

    # 按运营商分别保存文件
    if not os.path.exists(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    for op, ip_list in all_alive.items():
        fn = f"{op}_config.txt"
        path = os.path.join(SAVE_DIR, fn)
        lines = sorted(list(set([x + ",12" for x in ip_list])))
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"📁 已生成：ip/{fn}，共 {len(lines)} 条", flush=True)
        sys.stdout.flush()

    print("\n🎉 全部运营商分段扫描完成！", flush=True)
    total = sum(len(v) for v in all_alive.values())
    print(f"全局总有效IP：{total} 条", flush=True)
    sys.stdout.flush()

if __name__ == "__main__":
    main()
