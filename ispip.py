# -*- coding: utf-8 -*-
import os
import requests
import math

# 文件夹配置
SAVE_DIR = "./ispip"
CONFIG_DIR = "./ip"
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# 运营商文件
TEL_TXT = os.path.join(SAVE_DIR, "telecom.txt")
UNI_TXT = os.path.join(SAVE_DIR, "unicom.txt")
CMCC_TXT = os.path.join(SAVE_DIR, "mobile.txt")
ALL_TXT = os.path.join(SAVE_DIR, "cn_all.txt")

# 常用扫描端口 跟你原有配置完全一致
PORT_LIST = ["4022","8188","8889","8077","7788"]

# 省份IP前缀库
prov_prefix = {
    "北京": ["219.142","123.127"],
    "天津": ["60.28","221.238"],
    "河北": ["60.6","121.18"],
    "山西": ["59.49","218.22"],
    "内蒙古": ["1.24","220.200"],
    "辽宁": ["61.133","219.148"],
    "吉林": ["58.154","221.8"],
    "黑龙江": ["112.100","222.170"],
    "上海": ["116.228","219.230"],
    "江苏": ["58.192","221.226"],
    "浙江": ["60.12","220.189"],
    "安徽": ["60.166","218.92"],
    "福建": ["218.85","120.35"],
    "江西": ["59.52","220.165"],
    "山东": ["58.56","221.2"],
    "河南": ["115.46","222.138"],
    "湖北": ["59.173","219.132"],
    "湖南": ["118.248","222.240"],
    "广东": ["113.13","219.136"],
    "广西": ["113.16","222.82"],
    "海南": ["110.190","113.96"],
    "重庆": ["106.83","113.24"],
    "四川": ["118.112","218.6"],
    "贵州": ["218.86","121.32"],
    "云南": ["113.114","221.3"],
    "陕西": ["61.185","113.224"],
    "甘肃": ["118.120","220.160"]
}

# 下载APNIC IP库
url = "https://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest"
req = requests.get(url, timeout=25)
raw_data = req.text

# 提取所有中国IPv4网段
ip_list = []
for line in raw_data.splitlines():
    arr = line.split("|")
    if len(arr) < 5:
        continue
    if arr[0] == "apnic" and arr[1] == "CN" and arr[2] == "ipv4":
        ip = arr[3]
        num = int(arr[4])
        cidr = 32 - int(math.log2(num))
        ip_list.append(f"{ip}/{cidr}")

# 追加写入全国总网段（不覆盖旧数据）
with open(ALL_TXT, "a", encoding="utf-8") as f:
    for item in ip_list:
        f.write(item + "\n")

# 判断运营商
def get_isp(ip):
    t = ["27.","36.","39.","58.","59.","60.","61.","113.","114.","118.","119."]
    u = ["112.","124.","218.","219.","220.","221.","222."]
    m = ["110.","111.","182.","183.","223."]
    if any(ip.startswith(x) for x in t):
        return "telecom"
    elif any(ip.startswith(x) for x in u):
        return "unicom"
    elif any(ip.startswith(x) for x in m):
        return "mobile"
    return "telecom"

# 匹配省份
def get_prov(ip):
    for prov, keys in prov_prefix.items():
        for k in keys:
            if ip.startswith(k):
                return prov
    return ""

# 追加打开运营商文件
ft = open(TEL_TXT, "a", encoding="utf-8")
fu = open(UNI_TXT, "a", encoding="utf-8")
fm = open(CMCC_TXT, "a", encoding="utf-8")

# 初始化各省配置文件 追加模式
prov_files = {}
for p in prov_prefix:
    prov_files[f"{p}_dx"] = open(f"{CONFIG_DIR}/{p}_电信_config.txt", "a", encoding="utf-8")
    prov_files[f"{p}_lt"] = open(f"{CONFIG_DIR}/{p}_联通_config.txt", "a", encoding="utf-8")
    prov_files[f"{p}_yd"] = open(f"{CONFIG_DIR}/{p}_移动_config.txt", "a", encoding="utf-8")

# 遍历追加写入config，保留旧数据
for cidr_ip in ip_list:
    ip_addr = cidr_ip.split("/")[0]
    prov_name = get_prov(ip_addr)
    isp_type = get_isp(ip_addr)

    # 追加运营商网段
    if isp_type == "telecom":
        ft.write(cidr_ip + "\n")
    elif isp_type == "unicom":
        fu.write(cidr_ip + "\n")
    else:
        fm.write(cidr_ip + "\n")

    # 无匹配省份直接跳过
    if not prov_name:
        continue

    # 截取前3段IP，生成标准扫描格式
    seg3 = ".".join(ip_addr.split(".")[:3]) + ".1"
    for port in PORT_LIST:
        line = f"{seg3}:{port},11"
        if isp_type == "telecom":
            prov_files[f"{prov_name}_dx"].write(line + "\n")
        elif isp_type == "unicom":
            prov_files[f"{prov_name}_lt"].write(line + "\n")
        else:
            prov_files[f"{prov_name}_yd"].write(line + "\n")

# 关闭全部文件
ft.close()
fu.close()
fm.close()
for f in prov_files.values():
    f.close()

print("✅ 执行完成")
print("✅ 所有文件已【追加新增】，旧数据全部保留不删除")
print("✅ 新网段自动追加到原有config文件末尾")
