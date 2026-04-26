from threading import Thread
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 固定分类列表 ====================
CATEGORIES = [
    "央视频道",
    "卫视频道",
    "数字频道",
    "电影频道",
    "付费频道",
    "IPTV频道",
    "华数频道",
    "BesTV&iHOT频道",
    "河南频道",
    "上海频道",
    "青海频道",
    "北京频道",
    "河北频道",
    "湖南频道",
    "福建频道",
    "陕西频道",
    "海南频道",
    "重庆频道",
    "内蒙古频道",
    "云南频道",
    "江苏频道",
    "山东频道",
    "浙江频道",
    "山西频道",
    "安徽频道",
    "湖北频道",
    "贵州频道",
    "广西频道",
    "甘肃频道",
    "新疆频道",
    "江西频道",
    "吉林频道",
    "四川频道",
    "广东频道",
    "宁夏频道",
    "天津频道",
    "黑龙江频道",
    "辽宁频道"
]

def read_config(config_file):
    print(f"[读取配置] {config_file}")
    ip_configs = []
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if "," in line and not line.startswith("#"):
                    parts = line.split(',')
                    ip_part, port = parts[0].strip().split(':')
                    a, b, c, d = ip_part.split('.')
                    option = int(parts[1])
                    url_end = "/status" if option >= 10 else "/stat"
                    ip = f"{a}.{b}.{c}.1" if option % 2 == 0 else f"{a}.{b}.1.1"
                    ip_configs.append((ip, port, option, url_end))
                    print(f"[配置行{line_num}] http://{ip}:{port}{url_end}")
        return ip_configs
    except Exception as e:
        print(f"[读取错误] {e}")
        return []

def generate_ip_ports(ip, port, option):
    a, b, c, d = ip.split('.')
    if option in (2, 12):
        cs = c.split('-')
        c_start = int(cs[0])
        c_end = int(cs[1]) + 1 if len(cs) == 2 else int(c) + 8
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(c_start, c_end) for y in range(1, 256)]
    elif option in (0, 10):
        return [f"{a}.{b}.{c}.{y}:{port}" for y in range(1, 256)]
    else:
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(256) for y in range(1, 256)]

def check_ip_port(ip_port, url_end):
    try:
        url = f"http://{ip_port}{url_end}"
        start = time.time()
        resp = requests.get(url, timeout=2)
        resp.raise_for_status()
        cost = round((time.time() - start) * 1000)
        text = resp.text
        if "Multi stream daemon" in text or "udpxy status" in text:
            print(f"[有效] {url} 耗时 {cost}ms")
            return ip_port, cost
        else:
            print(f"[无效] {url} 非udpxy")
            return None
    except Exception as e:
        print(f"[超时/失败] http://{ip_port}{url_end}")
        return None

def scan_ip_port(ip, port, option, url_end):
    valid = []
    ip_ports = generate_ip_ports(ip, port, option)
    total = len(ip_ports)
    checked = [0]
    print(f"[扫描开始] 总计 {total} 个地址")

    def progress():
        while checked[0] < total:
            print(f"[进度] 已扫 {checked[0]}/{total} | 有效 {len(valid)}")
            time.sleep(10)
    Thread(target=progress, daemon=True).start()

    workers = 300 if option % 2 == 1 else 100
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futs = {executor.submit(check_ip_port, p, url_end): p for p in ip_ports}
        for f in as_completed(futs):
            res = f.result()
            if res:
                valid.append(res)
            checked[0] += 1

    valid.sort(key=lambda x: x[1])
    print(f"[扫描完成] 有效地址：{len(valid)}")
    return [p for p, t in valid]

def load_demo_channels():
    demo = "demo.txt"
    if not os.path.exists(demo):
        print(f"[警告] 未找到 {demo}")
        return {}
    cat_map = {}
    current = None
    with open(demo, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if ",#genre#" in line:
                current = line.split(',')[0]
                cat_map[current] = []
            elif current:
                cat_map[current].append(line)
    return cat_map

def multicast_province(config_file):
    fname = os.path.basename(config_file)
    province = fname.split('_')[0]
    print(f"\n{'='*30}\n[省份扫描] {province}\n{'='*30}")
    configs = list(set(read_config(config_file)))
    all_ips = []
    for ip, port, opt, end in configs:
        print(f"\n[扫描] {ip}:{port}{end}")
        all_ips += scan_ip_port(ip, port, opt, end)
    all_ips = sorted(set(all_ips))
    if not all_ips:
        print(f"[{province}] 无有效IP")
        return
    os.makedirs("ip", exist_ok=True)
    ip_out = f"ip/{province}_ip.txt"
    with open(ip_out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_ips))
    print(f"[{province}] 已保存 {len(all_ips)} 个IP到 {ip_out}")

    archive = f"ip/存档_{province}_ip.txt"
    if os.path.exists(archive):
        with open(archive, encoding='utf-8') as f:
            lines = f.read().splitlines()
        for ip_port in all_ips:
            ip, p = ip_port.split(':')
            a, b, c, d = ip.split('.')
            lines.append(f"{a}.{b}.{c}.1:{p}")
        with open(archive, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(set(lines))))

    tpl = f"template/template_{province}.txt"
    if os.path.exists(tpl):
        with open(tpl, encoding='utf-8') as f:
            tpl_content = f.read()
        output = []
        with open(ip_out, encoding='utf-8') as f:
            for idx, line in enumerate(f, 1):
                ip = line.strip()
                output.append(f"{province}-组播{idx},#genre#\n")
                output.append(tpl_content.replace("ipipip", ip))
        with open(f"组播_{province}.txt", 'w', encoding='utf-8') as f:
            f.writelines(output)
    else:
        print(f"[模板缺失] {tpl}")

def txt_to_m3u(in_txt, out_m3u):
    with open(in_txt, encoding='utf-8') as f:
        lines = f.read().splitlines()
    with open(out_m3u, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        group = ""
        for line in lines:
            line = line.strip()
            if ",#genre#" in line:
                group = line.split(',')[0]
            elif "," in line:
                name, url = line.split(',', 1)
                f.write(f'#EXTINF:-1 group-title="{group}",{name}\n{url}\n')

def main():
    os.makedirs("ip", exist_ok=True)
    os.makedirs("template", exist_ok=True)

    # 扫描各省配置
    for cfg in glob.glob("ip/*_config.txt"):
        multicast_province(cfg)

    # 加载频道名
    cat_channels = load_demo_channels()
    # 收集所有组播地址
    multicast_files = glob.glob("组播_*.txt")
    all_urls = []
    for mf in multicast_files:
        with open(mf, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if "," in line and not line.endswith("#genre#"):
                    parts = line.split(',', 1)
                    if len(parts) == 2:
                        all_urls.append(parts[1])

    # 去重并按速度排序（这里按顺序复用，保留测速顺序）
    valid_urls = sorted(set(all_urls))
    print(f"\n[汇总] 有效播放地址 {len(valid_urls)} 个")

    # 生成最终文件
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    update_time = now.strftime("%Y/%m/%d %H:%M")
    output_lines = [f"{update_time}更新,#genre#"]

    # 写入固定分类
    url_idx = 0
    for cat in CATEGORIES:
        output_lines.append(f"{cat},#genre#")
        channels = cat_channels.get(cat, [])
        for ch in channels:
            if url_idx < len(valid_urls):
                output_lines.append(f"{ch},{valid_urls[url_idx]}")
                url_idx += 1
            else:
                output_lines.append(f"{ch},")

    # 写入 zubo_all.txt
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write('\n'.join(output_lines))
    # 转m3u
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")

    print("\n[完成] 分类已正确生成，带北京时间更新时间")
    print(f"生成文件：zubo_all.txt / zubo_all.m3u")

if __name__ == "__main__":
    main()
