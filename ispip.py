# -*- coding: utf-8 -*-
import os
import requests
import math

# 输出文件夹
SAVE_DIR = "./ispip"
os.makedirs(SAVE_DIR, exist_ok=True)

# 输出文件路径
TEL_FILE = os.path.join(SAVE_DIR, "telecom_cidr.txt")
UNI_FILE = os.path.join(SAVE_DIR, "unicom_cidr.txt")
CMCC_FILE = os.path.join(SAVE_DIR, "mobile_cidr.txt")
ALL_FILE = os.path.join(SAVE_DIR, "cn_all_cidr.txt")

# 清空旧文件
for f in [TEL_FILE, UNI_FILE, CMCC_FILE, ALL_FILE]:
    open(f, "w", encoding="utf-8").close()

# 下载APNIC数据
url = "http://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest"
res = requests.get(url, timeout=15)
data = res.text

# 提取中国IPv4
cn_lines = []
for line in data.splitlines():
    parts = line.split("|")
    if len(parts) < 5:
        continue
    if parts[0] == "apnic" and parts[1] == "CN" and parts[2] == "ipv4":
        ip = parts[3]
        count = int(parts[4])
        cidr = 32 - int(math.log2(count))
        cidr_line = f"{ip}/{cidr}"
        cn_lines.append(cidr_line)

# 写入全部网段
with open(ALL_FILE, "w", encoding="utf-8") as f:
    for line in cn_lines:
        f.write(line + "\n")

# 运营商特征匹配
def get_isp(cidr):
    ip_head = cidr.split("/")[0]
    # 电信特征段
    telecom_key = ["27.", "36.", "39.", "42.", "49.", "58.", "59.", "60.", "61.", "113.", "114.", "115.", "116.", "117.", "118.", "119.", "120.", "121.", "122.", "123."]
    # 联通特征段
    unicom_key = ["112.", "124.", "202.", "210.", "211.", "218.", "219.", "220.", "221.", "222."]
    # 移动特征段
    cmcc_key = ["111.", "110.", "183.", "182.", "117.", "223."]

    for k in telecom_key:
        if ip_head.startswith(k):
            return "tel"
    for k in unicom_key:
        if ip_head.startswith(k):
            return "uni"
    for k in cmcc_key:
        if ip_head.startswith(k):
            return "cmcc"
    return "tel"

# 分类写入
for line in cn_lines:
    isp = get_isp(line)
    if isp == "tel":
        with open(TEL_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    elif isp == "uni":
        with open(UNI_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    else:
        with open(CMCC_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

print("✅ 全国运营商IP网段采集完成")
print(f"电信：{TEL_FILE}")
print(f"联通：{UNI_FILE}")
print(f"移动：{CMCC_FILE}")
