import os
import json
from datetime import datetime


BASE_DIR = os.path.dirname(__file__)
FILE_CAT7 = os.path.join(BASE_DIR, 'listing_cat7_주택임대.json')
FILE_CAT5 = os.path.join(BASE_DIR, 'listing_cat5_아파트임대.json')
OUTPUT_TXT = os.path.join(BASE_DIR, '임대汇总.txt')


def load_json(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_entry(idx: int, item: dict, cat: int) -> str:
    category = item.get('category') or ''
    description = item.get('description') or ''
    phones = ', '.join(item.get('phones') or []) if item.get('phones') else '无'
    is_new = '是' if item.get('new') else '否'
    lines = [
        f"[{cat}-{idx}] 分类: {category}",
        f"    描述: {description}",
        f"    电话: {phones}",
        f"    新发布: {is_new}",
    ]
    return '\n'.join(lines)


def build_document(cat7_items: list, cat5_items: list) -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    parts = [
        f"임대汇总文档", 
        f"生成时间: {now}",
        "",
        "==== 주택임대 (cat=7) ===="
    ]
    if cat7_items:
        parts.append(f"总计: {len(cat7_items)} 条")
        for i, item in enumerate(cat7_items, 1):
            parts.append(format_entry(i, item, 7))
    else:
        parts.append("无数据")
    parts.extend(["", "==== 아파트임대 (cat=5) ===="])
    if cat5_items:
        parts.append(f"总计: {len(cat5_items)} 条")
        for i, item in enumerate(cat5_items, 1):
            parts.append(format_entry(i, item, 5))
    else:
        parts.append("无数据")
    parts.append("")
    return '\n'.join(parts)


def main():
    cat7 = load_json(FILE_CAT7)
    cat5 = load_json(FILE_CAT5)
    doc = build_document(cat7, cat5)
    with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
        f.write(doc)
    print(f"已生成汇总文档: {OUTPUT_TXT}")
    print(f"cat=7 条目: {len(cat7)} 条, cat=5 条目: {len(cat5)} 条")


if __name__ == '__main__':
    main()
