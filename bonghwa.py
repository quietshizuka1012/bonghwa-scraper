import os
import sys
import json
import subprocess
import requests
from bs4 import BeautifulSoup
import re


ROOT_URL = "https://www.bonghwa.co.kr/"
LIST_URLS = [
    (5, "https://www.bonghwa.co.kr/listing.cfm?cat=5"),
    (7, "https://www.bonghwa.co.kr/listing.cfm?cat=7"),
]
COOKIES_FILE = "bonghwa_cookies.json"  # 由清除脚本输出


def run_cf_clearance_scraper(root_url: str, output_file: str, headed: bool = True, timeout: int = 30) -> None:
    """调用 cf-clearance-scraper/main.py，生成包含 cf_clearance 与 UA 的 JSON 文件。"""
    cf_script = os.path.join(os.path.dirname(__file__), "cf-clearance-scraper", "main.py")
    if not os.path.exists(cf_script):
        raise FileNotFoundError(f"未找到清除脚本: {cf_script}")

    args = [
        sys.executable,
        cf_script,
        root_url,
        "--file",
        output_file,
    ]
    if headed:
        args.append("--headed")
    if timeout:
        args.extend(["--timeout", str(timeout)])

    print(f"运行清除脚本以获取 cf_clearance：{' '.join(args)}")
    # headed 模式下会打开浏览器窗口，坐标点击由清除脚本内部处理
    subprocess.run(args, check=True)


def load_cf_info(output_file: str, prefer_domain: str = "bonghwa.co.kr") -> dict:
    """读取清除脚本输出的 JSON，返回最新条目的信息。"""
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 优先选择包含目标域名的键，否则取第一个键
    dom_key = next((k for k in data.keys() if prefer_domain in k), next(iter(data.keys()), None))
    entries = data.get(dom_key, [])
    if not entries:
        raise ValueError(f"输出文件中未找到域名数据：{output_file}")
    return entries[-1]


def make_headers_and_cookies(cf_info: dict) -> tuple[dict, dict]:
    ua = cf_info.get("user_agent") or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36"
    )
    headers = {
        "User-Agent": ua,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": ROOT_URL,
    }
    token = cf_info.get("cf_clearance")
    if not token:
        raise ValueError("未从输出中解析到 cf_clearance 值。")
    cookies = {"cf_clearance": token}
    return headers, cookies


def is_block_page(text: str) -> bool:
    tl = text.lower()
    # 更严格的 Cloudflare 拦截识别，避免 "cdnjs.cloudflare.com" 造成误判
    keywords = [
        "attention required",
        "just a moment",
        "checking your browser",
        "please verify you are a human",
        "cf-error",
        "captcha",
    ]
    return any(k in tl for k in keywords)


def fetch_page(url: str, headers: dict, cookies: dict) -> requests.Response:
    resp = requests.get(url, headers=headers, cookies=cookies, timeout=20)
    resp.encoding = "utf-8"
    return resp


def extract_items(doc: BeautifulSoup) -> list[dict]:
    items = []
    left_divs = doc.select('div.col-lg-9.col-md-8.col-sm-8')
    for left in left_divs:
        # 分类
        cat_span = left.find('span', class_='cattxt')
        category = cat_span.get_text(strip=True) if cat_span else ''
        # 描述文本：去掉“分类 : ”前缀
        full_text = left.get_text(separator=' ', strip=True)
        if category:
            prefix_pattern = re.compile(rf'^{re.escape(category)}\s*:\s*')
            desc = prefix_pattern.sub('', full_text)
        else:
            desc = full_text
        # 是否新发布标记
        is_new = bool(left.find('img', src=lambda s: s and 'icn_new' in s))
        # 右侧电话容器（紧邻的兄弟 div）
        right = left.find_next_sibling('div', class_='col-lg-3 col-md-4 col-sm-4')
        phones = []
        if right:
            txt = right.get_text(separator=' ', strip=True)
            phones = re.findall(r'0\d{1,2}-\d{3,4}-\d{4}', txt)
        # 收集条目
        if desc or phones:
            items.append({
                'category': category,
                'description': desc,
                'phones': phones,
                'new': is_new,
            })
    return items


def main():
    # 0) 读取现有 cookie/UA，如无则获取一次
    headers = None
    cookies = None
    try:
        cf_info = load_cf_info(COOKIES_FILE)
        headers, cookies = make_headers_and_cookies(cf_info)
        print("使用已有 cf_clearance 与 UA 进行访问...")
    except Exception:
        print("未找到有效的 cookie 文件，先获取一次...")
        run_cf_clearance_scraper(ROOT_URL, COOKIES_FILE, headed=True, timeout=30)
        cf_info = load_cf_info(COOKIES_FILE)
        headers, cookies = make_headers_and_cookies(cf_info)

    # 1) 依次抓取两个分类页；若出现拦截，按需刷新一次后重试
    refreshed = False
    for cat, url in LIST_URLS:
        try:
            resp = fetch_page(url, headers, cookies)
            blocked = (resp.status_code != 200) or is_block_page(resp.text)
            if blocked and not refreshed:
                print(f"cat={cat} 访问被拦截，触发一次刷新 cf_clearance ...")
                run_cf_clearance_scraper(ROOT_URL, COOKIES_FILE, headed=True, timeout=30)
                cf_info = load_cf_info(COOKIES_FILE)
                headers, cookies = make_headers_and_cookies(cf_info)
                refreshed = True
                # 重试当前页
                resp = fetch_page(url, headers, cookies)
            # 输出与保存
            print(f"[cat={cat}] 状态码: {resp.status_code}, 最终URL: {resp.url}")
            print(f"[cat={cat}] HTML长度: {len(resp.text)}")
            html_path = f"listing_cat{cat}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(resp.text)
            print(f"已保存完整HTML到: {html_path}")
            # 结构化解析
            soup = BeautifulSoup(resp.text, "lxml")
            listings = extract_items(soup)
            print(f"[cat={cat}] 解析到条目数量: {len(listings)}")
            for i, it in enumerate(listings[:20], 1):
                print(f"[{cat}-{i}] 分类: {it['category']}")
                print(f"    描述: {it['description']}")
                print(f"    电话: {', '.join(it['phones']) if it['phones'] else '无'}")
            json_path = f"listing_cat{cat}.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(listings, f, ensure_ascii=False, indent=2)
            print(f"已保存结构化数据到: {json_path}")
            # 按分类页关键词过滤并单独导出
            filter_keyword = '아파트임대' if cat == 5 else ('주택임대' if cat == 7 else None)
            if filter_keyword:
                filtered = [item for item in listings if item.get('category') == filter_keyword]
                filtered_path = f"listing_cat{cat}_{filter_keyword}.json"
                with open(filtered_path, 'w', encoding='utf-8') as f:
                    json.dump(filtered, f, ensure_ascii=False, indent=2)
                print(f"已导出“{filter_keyword}”过滤数据到: {filtered_path} (共 {len(filtered)} 条)")

if __name__ == "__main__":
    main()
