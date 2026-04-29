import os
import time
import requests

# ============================
# 读取 alias.txt（统一频道名）
# ============================
def load_alias(alias_file):
    alias_map = {}
    if os.path.exists(alias_file):
        with open(alias_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ',' in line:
                    old, new = line.split(',', 1)
                    alias_map[old.strip()] = new.strip()
    return alias_map


# ============================
# 读取 demo.txt（分类 + 顺序）
# ============================
def load_demo(demo_file):
    categories = {}          # {分类名: [频道顺序列表]}
    category_order = []      # 分类顺序

    current_category = None

    with open(demo_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            # 分类行
            if line.endswith(",#genre#"):
                category = line.replace(",#genre#", "").strip()
                current_category = category
                category_order.append(category)
                categories[current_category] = []
                continue

            # 分类内频道
            if current_category:
                categories[current_category].append(line)

    return category_order, categories


# ============================
# URL测速（越快越前）
# ============================
def test_speed(url):
    try:
        start = time.time()
        r = requests.get(url, timeout=1)
        end = time.time()
        return end - start
    except:
        return 9999


# ============================
# 处理 zubo_all.txt → 重新分类 + 排序 + 统一频道名
# ============================
def process_final_output(input_txt, alias_map, category_order, category_channels):
    # 读取所有频道
    all_channels = []   # [(频道名, URL)]

    with open(input_txt, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if "," in line and not line.endswith("#genre#"):
                name, url = line.split(",", 1)
                name = name.strip()
                url = url.strip()

                # 统一频道名
                if name in alias_map:
                    name = alias_map[name]

                all_channels.append((name, url))

    # 分类结果
    result = {cat: {} for cat in category_order}

    # 将频道按 demo.txt 分类
    for cat in category_order:
        order_list = category_channels[cat]  # 分类内频道顺序

        for cname in order_list:
            # 找到所有匹配的频道
            urls = [url for (name, url) in all_channels if name == cname]

            if urls:
                # 对同频道多个 URL 进行测速排序
                urls_sorted = sorted(urls, key=lambda u: test_speed(u))
                result[cat][cname] = urls_sorted

    return result


# ============================
# 输出最终 m3u
# ============================
def write_m3u(result, output_file):
    now = time.strftime("%Y/%m/%d %H:%M")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")

        # 顶部更新时间
        f.write(f'#EXTINF:-1 group-title="更新信息",更新时间：{now}\n')
        f.write("http://127.0.0.1/update\n\n")

        # 分类顺序输出
        for cat in result:
            for cname, urls in result[cat].items():
                for url in urls:
                    f.write(f'#EXTINF:-1 group-title="{cat}",{cname}\n')
                    f.write(url + "\n")


# ============================
# 主流程（增强模块）
# ============================
def main():
    alias_map = load_alias("alias.txt")
    category_order, category_channels = load_demo("demo.txt")

    result = process_final_output("zubo_all.txt", alias_map, category_order, category_channels)

    write_m3u(result, "zubo_all.m3u")


if __name__ == "__main__":
    main()
