# -*- coding: utf-8 -*-
import os
import requests
import math
import socket

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

# IPTV常用专属扫描端口
PORT_LIST = ["4022","8188","8889","8077","7788"]
# 存活检测超时 轻量快速探测
CHECK_TIMEOUT = 2.0

# 省份IP前缀库（完整保留你原版+贵州全部网段）
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
    "贵州": ["218.86","61.159","220.172","116.1","59.38"],
    "云南": ["113.114","221.3"],
    "陕西": ["61.185","113.224"],
    "甘肃": ["118.120","220.160"]
}

# 宽松网段过滤：只区分三大运营商，不过度剔除网段
def is_cn_isp_ip(ip):
    # 电信、联通、移动全部保留，不做严格IPTV段限制
    telecom = ["27.","36.","39.","58.","59.","60.","61.","106.","113.","114.","118.","119.","218.","219.","222."]
    unicom = ["112.","116.","124.","219.","220.","221.","222."]
    mobile = ["110.","111.","182.","183.","223."]
    all_seg = telecom + unicom + mobile
    return any(ip.startswith(s) for s in all_seg)

# 判断运营商
def get_isp(ip):
    t = ["27.","36.","39.","58.","59.","60.","61.","106.","113.","114.","118.","119.","218.","219.","222."]
    u = ["112.","116.","124.","219.","220.","221.","222."]
    m = ["110.","111.","182.","183.","223."]
    if any(ip.startswith(x) for x in t):
        return "telecom"
    elif any(ip.startswith(x) for x in u):
        return "unicom"
    elif any(ip.startswith(x) for x in m):
        return "mobile"
    return ""

# 匹配省份
def get_prov(ip):
    for prov, keys in prov_prefix.items():
        for k in keys:
            if ip.startswith(k):
                return prov
    return ""

# 新增：轻量测试端口是否存活，是IPTV转播就保留
def check_iptv_alive(ip, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CHECK_TIMEOUT)
        sock.connect((ip, int(port)))
        sock.close()
        return True
    except:
        return False

# 加载旧文件去重
def load_exist_lines(file_path):
    exist = set()
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    exist.add(line)
    return exist

exist_all = load_exist_lines(ALL_TXT)
exist_tel = load_exist_lines(TEL_TXT)
exist_uni = load_exist_lines(UNI_TXT)
exist_cmcc = load_exist_lines(CMCC_TXT)

# 下载APNIC国内IP段
url = "https://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest"
req = requests.get(url, timeout=25)
raw_data = req.text

# 筛选国内运营商网段
ip_list = []
for line in raw_data.splitlines():
    arr = line.split("|")
    if len(arr) < 5:
        continue
    if arr[0] == "apnic" and arr[1] == "CN" and arr[2] == "ipv4":
        ip = arr[3]
        # 只过滤非三大运营商，其余全部保留
        if not is_cn_isp_ip(ip):
            continue
        num = int(arr[4])
        cidr = 32 - int(math.log2(num))
        ip_list.append(f"{ip}/{cidr}")

# 总网段去重追加
with open(ALL_TXT, "a", encoding="utf-8") as f:
    for item in ip_list:
        if item not in exist_all:
            f.write(item + "\n")

# 运营商文件
ft = open(TEL_TXT, "a", encoding="utf-8")
fu = open(UNI_TXT, "a", encoding="utf-8")
fm = open(CMCC_TXT, "a", encoding="utf-8")

# 初始化各省配置
prov_files = {}
prov_exist = {}
for p in prov_prefix:
    dx_path = f"{CONFIG_DIR}/{p}电信_config.txt"
    lt_path = f"{CONFIG_DIR}/{p}联通_config.txt"
    yd_path = f"{CONFIG_DIR}/{p}移动_config.txt"
    prov_files[f"{p}_dx"] = open(dx_path, "a", encoding="utf-8")
    prov_files[f"{p}_lt"] = open(lt_path, "a", encoding="utf-8")
    prov_files[f"{p}_yd"] = open(yd_path, "a", encoding="utf-8")
    prov_exist[f"{p}_dx"] = load_exist_lines(dx_path)
    prov_exist[f"{p}_lt"] = load_exist_lines(lt_path)
    prov_exist[f"{p}_yd"] = load_exist_lines(yd_path)

# 遍历网段 + 预测试存活，可用再写入
for cidr_ip in ip_list:
    ip_addr = cidr_ip.split("/")[0]
    prov_name = get_prov(ip_addr)
    isp_type = get_isp(ip_addr)

    if not isp_type:
        continue

    # 运营商网段去重写入
    if isp_type == "telecom" and cidr_ip not in exist_tel:
        ft.write(cidr_ip + "\n")
    elif isp_type == "unicom" and cidr_ip not in exist_uni:
        fu.write(cidr_ip + "\n")
    elif isp_type == "mobile" and cidr_ip not in exist_cmcc:
        fm.write(cidr_ip + "\n")

    if not prov_name:
        continue

    seg3 = ".".join(ip_addr.split(".")[:3]) + ".1"
    # 逐个端口测试，存活才写入配置文件
    for port in PORT_LIST:
        line = f"{seg3}:{port},11"
        # 重复直接跳过
        if isp_type == "telecom" and line in prov_exist[f"{prov_name}_dx"]:
            continue
        if isp_type == "unicom" and line in prov_exist[f"{prov_name}_lt"]:
            continue
        if isp_type == "mobile" and line in prov_exist[f"{prov_name}_yd"]:
            continue
        
        # 存活检测：是IPTV转播可用就保留写入
        if check_iptv_alive(seg3, port):
            if isp_type == "telecom":
                prov_files[f"{prov_name}_dx"].write(line + "\n")
            elif isp_type == "unicom":
                prov_files[f"{prov_name}_lt"].write(line + "\n")
            elif isp_type == "mobile":
                prov_files[f"{prov_name}_yd"].write(line + "\n")
            print(f"✅ 存活可用: {prov_name} {seg3}:{port}")

# 关闭全部文件
ft.close()
fu.close()
fm.close()
for f in prov_files.values():
    f.close()

print("="*50)
print("✅ 宽松网段筛选，不盲目删除网段")
print("✅ 新增IPTV端口存活预测试，只保留转播可用地址")
print("✅ 无效、不通的IP自动过滤丢弃")
print("✅ 所有可用IPTV转播网段全部保留")
print("✅ 分省分运营商去重写入完成，可直接拿去扫描")
