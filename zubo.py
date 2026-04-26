# -*- coding: utf-8 -*-
from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 配置 ====================
CONCURRENCY = 300
ALIAS_FILE = "alias.txt"
DEMO_FILE = "demo.txt"

# ==================== 读取别名映射（标准名在前，别名在后） ====================
def load_alias_map():
    alias_map = {}
    if os.path.exists(ALIAS_FILE):
        with open(ALIAS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or ',' not in line:
                    continue
                parts = [p.strip() for p in line.split(',') if p.strip()]
                if len(parts) < 1:
                    continue
                standard = parts[0]
                for alias in parts[1:]:
                    alias_map[alias] = standard
    return alias_map

# ==================== 统一频道名 ====================
def normalize_channel(name, alias_map):
    return alias_map.get(name, name)

# ==================== 读取 demo.txt 分类+频道列表 ====================
def load_demo_channels(alias_map):
    categories = []
    current_cat = None
    if not os.path.exists(DEMO_FILE):
        print(f"⚠️ 未找到 {DEMO_FILE}")
        return categories

    with open(DEMO_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if ',#genre#' in line:
                cat_name = line.split(',')[0].strip()
                current_cat = {
                    "name": cat_name,
                    "channels": []
                }
                categories.append(current_cat)
            else:
                if current_cat is not None:
                    ch = normalize_channel(line, alias_map)
                    current_cat["channels"].append(ch)
    return categories

# ==================== 读取扫描配置 ====================
def read_config(config_file):
    print(f"读取设置文件：{config_file}")
    ip_configs = []
    try:
        with open(config_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if "," in line and not line.startswith("#"):
                    parts = line.strip().split(',')
                    ip_part, port = parts[0].strip().split(':')
                    a, b, c, d = ip_part.split('.')
                    option = int(parts[1])
                    url_end = "/status" if option >= 10 else "/stat"
                    ip = f"{a}.{b}.{c}.1" if option % 2 == 0 else f"{a}.{b}.1.1"
                    ip_configs.append((ip, port, option, url_end))
                    print(f"第{line_num}行：http://{ip}:{port}{url_end} 添加到扫描列表")
        return ip_configs
    except Exception as e:
        print(f"读取文件错误: {e}")
        return []

# ==================== 生成IP段 ====================
def generate_ip_ports(ip, port, option):
    a, b, c, d = ip.split('.')
    if option == 2 or option == 12:
        if '-' in c:
            c_start, c_end = map(int, c.split('-'))
        else:
            c_start = int(c)
            c_end = c_start + 7
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(c_start, c_end + 1) for y in range(1, 256)]
    elif option == 0 or option == 10:
        return [f"{a}.{b}.{c}.{y}:{port}" for y in range(1, 256)]
    else:
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(256) for y in range(1, 256)]

# ==================== 检测 udpxy ====================
def check_ip_port(ip_port, url_end):
    start = time.time()
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=2.5)
        resp.raise_for_status()
        t = int((time.time() - start) * 1000)
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            print(f"✅ 有效 {url}  {t}ms")
            return ip_port
        else:
            print(f"❌ 无效 {url}  {t}ms")
    except Exception as e:
        t = int((time.time() - start) * 1000)
        print(f"⏱️ 超时 {ip_port}  {t}ms")
    return None

# ==================== 多线程扫描 ====================
def scan_ip_port(ip, port, option, url_end):
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    total = len(ip_ports)
    checked = [0]

    def progress():
        while checked[0] < total:
            p = int(checked[0] / total * 100)
            print(f"[测速] 进度 {p}% | 已扫 {checked[0]}/{total} | 有效 {len(valid_ip_ports)}")
            time.sleep(10)

    Thread(target=progress, daemon=True).start()

    max_workers = 300 if option % 2 == 1 else 100
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_ip_port, ipp, url_end): ipp for ipp in ip_ports}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                valid_ip_ports.append(res)
            checked[0] += 1

    return sorted(set(valid_ip_ports))

# ==================== 省份扫描 & 生成组播 ====================
def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"\n{'='*30}\n         开始扫描：{province}\n{'='*30}")
    configs = sorted(set(read_config(config_file)))
    print(f"读取完成，共 {len(configs)} 组")

    all_ips = []
    for ip, port, opt, end in configs:
        print(f"\n扫描目标：http://{ip}:{port}{end}")
        all_ips.extend(scan_ip_port(ip, port, opt, end))

    if not all_ips:
        print(f"\n❌ {province} 未扫描到有效udpxy")
        return

    all_ips = sorted(set(all_ips))
    print(f"\n✅ {province} 扫描完成，有效IP：{len(all_ips)}")

    os.makedirs("ip", exist_ok=True)
    with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_ips))

    # 存档
    archive = f"ip/存档_{province}_ip.txt"
    if os.path.exists(archive):
        with open(archive, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    else:
        lines = []

    for ipp in all_ips:
        ip_part, p = ipp.split(':')
        a, b, c, d = ip_part.split('.')
        lines.append(f"{a}.{b}.{c}.1:{p}\n")

    with open(archive, 'w', encoding='utf-8') as f:
        f.writelines(sorted(set(lines)))

    # 模板生成组播列表
    tpl = os.path.join('template', f"template_{province}.txt")
    if os.path.exists(tpl):
        with open(tpl, 'r', encoding='utf-8') as f:
            tpl_content = f.read()
        output = []
        with open(f"ip/{province}_ip.txt", 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f, 1):
                proxy = line.strip()
                output.append(f"{province}-组播{idx},#genre#\n")
                output.append(tpl_content.replace("ipipip", proxy))
        with open(f"组播_{province}.txt", 'w', encoding='utf-8') as f:
            f.writelines(output)
    else:
        print(f"⚠️ 无模板：{tpl}")

# ==================== txt 转 m3u ====================
def txt_to_m3u(in_txt, out_m3u):
    with open(in_txt, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(out_m3u, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        current_group = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ",#genre#" in line:
                current_group = line.split(',')[0].strip()
            else:
                if ',' in line:
                    ch_name, ch_url = line.split(',', 1)
                    f.write(f'#EXTINF:-1 group-title="{current_group}",{ch_name}\n')
                    f.write(f"{ch_url}\n")

# ==================== 主函数 ====================
def main():
    alias_map = load_alias_map()
    categories = load_demo_channels(alias_map)

    # 扫描所有省份
    for cfg in glob.glob(os.path.join('ip', '*_config.txt')):
        multicast_province(cfg)

    # 收集所有有效代理
    proxies = []
    for fn in glob.glob("ip/*_ip.txt"):
        if "存档" in fn:
            continue
        with open(fn, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    proxies.append(line)

    if not proxies:
        print("⚠️ 无可用代理，无法生成频道")
        return

    # 北京时间
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_cn = now_utc + datetime.timedelta(hours=8)
    update_time = now_cn.strftime("%Y/%m/%d %H:%M")

    # 生成最终列表
    output = [f"{update_time}更新,#genre#"]
    idx_proxy = 0

    for cat in categories:
        cat_name = cat["name"]
        channels = cat["channels"]
        output.append(f"{cat_name},#genre#")
        for ch in channels:
            if idx_proxy >= len(proxies):
                idx_proxy = 0
            proxy = proxies[idx_proxy]
            # 拼接组播地址（按你模板格式）
            addr = f"http://{proxy}/rtp/239.16.20.1:10010"
            output.append(f"{ch},{addr}")
            idx_proxy += 1

    with open("zubo_all.txt", 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))

    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print(f"\n🎉 全部完成：zubo_all.txt / zubo_all.m3u 已生成")

if __name__ == "__main__":
    main()
