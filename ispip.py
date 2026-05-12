# -*- coding: utf-8 -*-
import os
import requests
import math

# 根目录配置
SAVE_DIR = "./ispip"
CONFIG_OUT_DIR = "./ip"
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(CONFIG_OUT_DIR, exist_ok=True)

# 运营商总文件
TEL_FILE = os.path.join(SAVE_DIR, "telecom_cidr.txt")
UNI_FILE = os.path.join(SAVE_DIR, "unicom_cidr.txt")
CMCC_FILE = os.path.join(SAVE_DIR, "mobile_cidr.txt")
ALL_FILE = os.path.join(SAVE_DIR, "cn_all_cidr.txt")

# 清空旧文件
for f in [TEL_FILE, UNI_FILE, CMCC_FILE, ALL_FILE]:
    open(f, "w", encoding="utf-8").close()

# 固定端口（和你现有扫描端口完全对齐）
SCAN_PORTS = [
    "4022",
    "8188",
    "8889",
    "7788",
    "8077"
]

# 全国省份IP前缀映射
province_prefix = {
    "北京": ["1.20.", "1.21.", "219.142.", "123.127."],
    "天津": ["60.28.", "111.13.", "221.238."],
    "河北": ["60.6.", "110.240.", "121.18."],
    "山西": ["59.49.", "111.123.", "218.22."],
    "内蒙古": ["1.24.", "111.112.", "220.200."],
    "辽宁": ["61.133.", "113.234.", "219.148."],
    "吉林": ["58.154.", "114.220.", "221.8."],
    "黑龙江": ["112.100.", "114.235.", "222.170."],
    "上海": ["116.228.", "218.1.", "219.230."],
    "江苏": ["58.192.", "113.4.", "221.226."],
    "浙江": ["60.12.", "115.196.", "220.189."],
    "安徽": ["60.166.", "113.27.", "218.92."],
    "福建": ["218.85.", "110.80.", "120.35."],
    "江西": ["59.52.", "111.75.", "220.165."],
    "山东": ["58.56.", "112.240.", "221.2."],
    "河南": ["115.46.", "123.5.", "222.138."],
    "湖北": ["59.173.", "113.57.", "219.132."],
    "湖南": ["118.248.", "111.7.", "222.240."],
    "广东": ["113.13.", "121.8.", "219.136."],
    "广西": ["113.16.", "120.39.", "222.82."],
    "海南": ["110.190.", "113.96."],
    "重庆": ["106.83.", "113.24."],
    "四川": ["118.112.", "113.204.", "218.6."],
    "贵州": ["218.86.", "110.91.", "121.32."],
    "云南": ["113.114.", "120.41.", "221.3."],
    "西藏": ["111.196."],
    "陕西": ["61.185.", "113.224."],
    "甘肃": ["118.120.", "220.160."],
    "青海": ["111.130."],
    "宁夏": ["111.140."],
    "新疆": ["124.88.", "113.104."]
}

# 下载APNIC网段
url = "https://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest"
res = requests.get(url, timeout=20)
data = res.text

# 提取中国IPv4 CIDR
cn_lines = []
for line in data.splitlines():
    parts = line.split("|")
    if len(parts) < 5:
        continue
    if parts[0] == "apnic" and parts[1] == "CN" and parts[2] == "ipv4":
        ip = parts[3]
        ip_count = int(parts[4])
        cidr = 32 - int(math.log2(ip_count))
        cn_lines.append(f"{ip}/{cidr}")

# 写入全国总网段
with open(ALL_FILE, "w", encoding="utf-8") as f:
    for line in cn_lines:
        f.write(line + "\n")

# 运营商判断
def get_isp_type(ip_str):
    telecom = ["27.","36.","39.","49.","58.","59.","60.","61.","113.","114.","115.","116.","118.","119.","120.","121."]
    unicom = ["112.","124.","202.","210.","211.","218.","219.","220.","221.","222."]
    mobile = ["110.","111.","182.","183.","223."]
    if any(ip_str.startswith(i) for i in telecom):
        return "telecom"
    elif any(ip_str.startswith(i) for i in unicom):
        return "unicom"
    elif any(ip_str.startswith(i) for i in mobile):
        return "mobile"
    return "telecom"

# 省份匹配
def get_province(ip_str):
    for prov, pres in province_prefix.items():
        for pre in pres:
            if ip_str.startswith(pre):
                return prov
    return None

# 初始化运营商总文件
ft = open(TEL_FILE,"w",encoding="utf-8")
fu = open(UNI_FILE,"w",encoding="utf-8")
fm = open(CMCC_FILE,"w",encoding="utf-8")

# 初始化各省配置文件
prov_conf = {}
for p in province_prefix:
    prov_conf[f"{p}_telecom"] = open(os.path.join(CONFIG_OUT_DIR,f"{p}_电信_config.txt"),"w",encoding="utf-8")
    prov_conf[f"{p}_unicom"] = open(os.path.join(CONFIG_OUT_DIR,f"{p}_联通_config.txt"),"w",encoding="utf-8")
    prov_conf[f"{p}_mobile"] = open(os.path.join(CONFIG_OUT_DIR,f"{p}_移动_config.txt"),"w",encoding="utf-8")

# 批量转换生成config格式
for item in cn_lines:
    ip_only = item.split("/")[0]
    prov = get_province(ip_only)
    isp = get_isp_type(ip_only)

    # 写入运营商总网段
    if isp == "telecom":
        ft.write(item+"\n")
    elif isp == "unicom":
        fu.write(item+"\n")
    else:
        fm.write(item+"\n")

    # 匹配省份+写入标准config格式
    if not prov:
        continue
    a,b,c,_ = ip_only.split(".")
    base_seg = f"{a}.{b}.c.1"

    # 多端口批量生成，和你原有配置格式完全一致
    for port in SCAN_PORTS:
        line = f"{base_seg}:{port},11"
        if isp == "telecom":
            prov_conf[f"{prov}_telecom"].write(line+"\n")
        elif isp == "unicom":
            prov_conf[f"{prov}_unicom"].write(line+"\n")
        else:
            prov_conf[f"{prov}_mobile"].write(line+"\n")

# 关闭所有文件
ft.close()
fu.close()
fm.close()
for f in prov_conf.values():
    f.close()

print("✅ 全部完成")
print("✅ 已自动生成：各省 电信/联通/移动 _config.txt 扫描配置文件")
print("✅ 文件直接保存在 /ip 目录，可直接被扫描程序调用")
