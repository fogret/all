import os
import time
import requests
import aiohttp
import asyncio

# 并发数 自己随便改 越大越快
CONCURRENCY = 120

# ============================
# 读取 alias.txt（统一频道名）
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
# 读取 demo.txt（分类 + 顺序）
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
# 异步单个链接测速
# ============================
async def async_test_speed(session, url):
    try:
        start = time.time()
        async with session.head(url, timeout=3) as r:
            await r.read()
        end = time.time()
        return url, end - start
    except:
        return url, 9999


# ============================
# 批量异步并发测速
# ============================
async def batch_speed_sort(url_list):
    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [async_test_speed(session, u) for u in url_list]
        res = await asyncio.gather(*tasks)
        # 按延迟从小到大排序
        sorted_urls = sorted(res, key=lambda x: x[1])
        return [i[0] for i in sorted_urls]


# ============================
# 处理 zubo_all.txt
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

    result = {cat: {} for cat in category_order}

    # 先收集所有需要测速的链接
    speed_todo = {}
    for cat in category_order:
        order_list = category_channels[cat]
        for cname in order_list:
            urls = [url for (name, url) in all_channels if name == cname]
            if urls:
                speed_todo[cname] = urls

    # 统一批量异步测速排序
    loop = asyncio.get_event_loop()
    for cname, urls in speed_todo.items():
        sorted_urls = loop.run_until_complete(batch_speed_sort(urls))
        # 放回对应分类
        for cat in category_order:
            if cname in category_channels[cat]:
                result[cat][cname] = sorted_urls

    return result


# ============================
# 输出最终 m3u
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
# 主流程
# ============================
def main():
    print("开始加载配置...")
    alias_map = load_alias("alias.txt")
    category_order, category_channels = load_demo("demo.txt")
    print("开始极速异步测速排序...")
    result = process_final_output("zubo_all.txt", alias_map, category_order, category_channels)
    write_m3u(result, "zubo_all.m3u")
    print("全部完成！")


if __name__ == "__main__":
    main()
