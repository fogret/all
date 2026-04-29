import os
import time
import requests
import aiohttp
import asyncio

# 并发数 自己随意修改
CONCURRENCY = 120
SPEED_TIMEOUT = 3

# 全国省份顺序分组
PROVINCE_LIST = [
    "河南", "浙江", "江苏", "天津", "湖北", "青海", "北京", "河北",
    "湖南", "上海", "福建", "陕西", "海南", "重庆", "内蒙古",
    "云南", "山东", "山西", "广东", "广西", "安徽", "四川", "辽宁",
    "吉林", "黑龙江", "贵州", "江西", "宁夏", "甘肃", "新疆", "西藏"
]

# ============================
# 读取 alias.txt 统一标准频道名
# ============================
def load_alias(alias_file):
    alias_map = {}
    if os.path.exists(alias_file):
        with open(alias_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or ',' not in line:
                    continue
                old, new = line.split(',', 1)
                alias_map[old.strip()] = new.strip()
    return alias_map

# ============================
# 读取 demo.txt 分类 + 固定输出顺序
# ============================
def load_demo(demo_file):
    categories = {}
    category_order = []
    current_category = None

    with open(demo_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.endswith(",#genre#"):
                category = line.replace(",#genre#", "").strip()
                current_category = category
                category_order.append(category)
                categories[current_category] = []
                continue
            if current_category:
                categories[current_category].append(line)
    return category_order, categories

# ============================
# 异步单链接测速
# ============================
async def async_test_speed(session, url):
    try:
        start = time.time()
        async with session.head(url, timeout=SPEED_TIMEOUT) as r:
            await r.read()
        end = time.time()
        return url, end - start
    except:
        return url, 9999

# ============================
# 单省批量异步并发测速排序
# ============================
async def batch_speed_sort(url_list):
    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [async_test_speed(session, u) for u in url_list]
        res = await asyncio.gather(*tasks)
        sorted_urls = sorted(res, key=lambda x: x[1])
        return [i[0] for i in sorted_urls]

# ============================
# 按省份自动拆分所有频道链接
# ============================
def split_by_province(all_channels):
    province_data = {p: [] for p in PROVINCE_LIST}
    province_data["其他"] = []

    for name, url in all_channels:
        match = False
        for p in PROVINCE_LIST:
            if p in name:
                province_data[p].append((name, url))
                match = True
                break
        if not match:
            province_data["其他"].append((name, url))
    return province_data

# ============================
# 逐省依次扫描、测速、统计日志
# ============================
def process_final_output(input_txt, alias_map, category_order, category_channels):
    all_channels = []
    with open(input_txt, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if "," in line and not line.endswith("#genre#"):
                name, url = line.split(",", 1)
                name = name.strip()
                url = url.strip()
                if name in alias_map:
                    name = alias_map[name]
                all_channels.append((name, url))

    # 按省份分组 修复变量报错
    province_data = split_by_province(all_channels)
    result = {cat: {} for cat in category_order}

    # 一个省跑完 再跑下一个省
    for province, channel_list in province_data.items():
        total = len(channel_list)
        if total == 0:
            continue

        print(f"\n【{province}】待扫描总数：{total} 条")

        name_url_dict = {}
        for n, u in channel_list:
            if n not in name_url_dict:
                name_url_dict[n] = []
            name_url_dict[n].append(u)

        finish_count = 0
        loop = asyncio.get_event_loop()
        for cname, urls in name_url_dict.items():
            sorted_urls = loop.run_until_complete(batch_speed_sort(urls))
            finish_count += len(urls)
            print(f"【{province}】已扫描完成：{finish_count}/{total}")

            for cat in category_order:
                if cname in category_channels[cat]:
                    result[cat][cname] = sorted_urls

    return result

# ============================
# 输出标准 m3u + 你要的更新时间格式
# ============================
def write_m3u(result, output_file):
    now = time.strftime("%Y/%m/%d %H:%M")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f'#EXTINF:-1 group-title="{now}更新",IPTV源\n')
        f.write("http://127.0.0.1/empty\n\n")
        for cat in result:
            for cname, urls in result[cat].items():
                for url in urls:
                    f.write(f'#EXTINF:-1 group-title="{cat}",{cname}\n')
                    f.write(url + "\n")

# ============================
# 主入口
# ============================
def main():
    print("=== 开始加载别名、分类配置 ===")
    alias_map = load_alias("alias.txt")
    category_order, category_channels = load_demo("demo.txt")
    print("=== 开始逐省顺序扫描测速 ===")

    result = process_final_output("zubo_all.txt", alias_map, category_order, category_channels)

    write_m3u(result, "zubo_all.m3u")
    print("\n=== 全部省份扫描完毕，已生成 zubo_all.m3u ===")

if __name__ == "__main__":
    main()
