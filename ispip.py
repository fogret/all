# -*- coding: utf-8 -*-
import os
import requests
import math

# 输出根目录
SAVE_DIR = "./ispip"
os.makedirs(SAVE_DIR, exist_ok=True)

# 运营商总文件
TEL_FILE = os.path.join(SAVE_DIR, "telecom_cidr.txt")
UNI_FILE = os.path.join(SAVE_DIR, "unicom_cidr.txt")
CMCC_FILE = os.path.join(SAVE_DIR, "mobile_cidr.txt")
ALL_FILE = os.path.join(SAVE_DIR, "cn_all_cidr.txt")

# 清空旧文件
for f in [TEL_FILE, UNI_FILE, CMCC_FILE, ALL_FILE]:
    open(f, "w", encoding="utf-8").close()

# 下载APNIC最新IP库
url = "https://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest"
res = requests.get(url, timeout=20)
data = res.text

# 省份IP前缀映射（IPTV常用精准分段）
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

# 初始化各省文件
prov_file_map = {}
for prov in province_prefix.keys():
    prov_path = os.path.join(SAVE_DIR, f"{prov}_ip.txt")
    prov_file_map[prov] = open(prov_path, "w", encoding="utf-8")

# 提取中国IPv4+换算CIDR
cn_lines = []
for line in data.splitlines():
    parts = line.split("|")
    if len(parts) < 5:
        continue
    if parts[0] == "apnic" and parts[1] == "CN" and parts[2] == "ipv4":
        ip = parts[3]
        ip_count = int(parts[4])
        cidr = 32 - int(math.log2(ip_count))
        cidr_line = f"{ip}/{cidr}"
        cn_lines.append(cidr_line)

# 写入全国总网段
with open(ALL_FILE, "w", encoding="utf-8") as f:
    for line in cn_lines:
        f.write(line + "\n")

# 运营商分类
def get_isp_type(ip_str):
    telecom = ["27.","36.","39.","49.","58.","59.","60.","61.","113.","114.","115.","116.","118.","119.","120.","121."]
    unicom = ["112.","124.","202.","210.","211.","218.","219.","220.","221.","222."]
    mobile = ["110.","111.","182.","183.","223."]
    if any(ip_str.startswith(i) for i in telecom):
        return "tel"
    elif any(ip_str.startswith(i) for i in unicom):
        return "uni"
    elif any(ip_str.startswith(i) for i in mobile):
        return "cmcc"
    return "tel"

# 匹配省份
def get_province(ip_str):
    for prov, pres in province_prefix.items():
        for pre in pres:
            if ip_str.startswith(pre):
                return prov
    return "其他省份"

# 批量分类写入
for item in cn_lines:
    ip_only = item.split("/")[0]
    # 写入运营商
    isp = get_isp_type(ip_only)
    if isp == "tel":
        open(TEL_FILE,"a",encoding="utf-8").write(item+"\n")
    elif isp == "uni":
        open(UNI_FILE,"a",encoding="utf-8").write(item+"\n")
    else:
        open(CMCC_FILE,"a",encoding="utf-8").write(item+"\n")
    # 写入对应省份
    prov = get_province(ip_only)
    if prov in prov_file_map:
        prov_file_map[prov].write(item+"\n")

# 关闭所有省份文件
for f in prov_file_map.values():
    f.close()

print("✅ 全国+各省+三大运营商 IP网段 全部生成完成")
print(f"✅ 共生成 {len(province_prefix)} 个省份独立IP文件")
