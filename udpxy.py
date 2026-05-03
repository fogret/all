# -*- coding: utf-8 -*-
print("程序已经成功启动！")
print("开始执行扫描任务")

import os
import requests

SAVE_DIR = "output"
if not os.path.exists(SAVE_DIR):
    os.mkdir(SAVE_DIR)

# 就先拿一个简单网段测试，先保证能输出日志、能运行
def main():
    print("正在扫描测试网段...")
    test_ip = "114.252.0.1"
    port = "4022"
    try:
        url = f"http://{test_ip}:{port}/stat"
        res = requests.get(url, timeout=2)
        print("请求完成，有返回数据")
    except:
        print("请求超时/无法连接")

    print("扫描执行结束")

if __name__ == "__main__":
    main()
