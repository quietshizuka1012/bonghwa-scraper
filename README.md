# Bonghwa Scraper

抓取 Bonghwa 网站 `cat=5` 和 `cat=7` 两个分类页，按需刷新 Cloudflare `cf_clearance`，解析结构化数据，并将指定类别汇总导出为带编号文档。

- 按需刷新：优先使用已有 `bonghwa_cookies.json` 中的 `cf_clearance`，仅在访问被拦截或返回非 200 时调用清除脚本刷新并重试。
- 解析输出：保存完整 HTML、解析成结构化 JSON，并对 `cat=5` 过滤“아파트임대”、`cat=7` 过滤“주택임대”。
- 汇总导出：将两个过滤结果汇总为 `임대汇总.txt`，条目编号形如 `[cat-序号]`。

## 目录结构

```
.
├─ bonghwa.py                 # 抓取与解析（含按需刷新 cf_clearance）
├─ export_summary.py          # 汇总两个过滤后的 JSON 并生成带编号文档
├─ cf-clearance-scraper/
│  ├─ main.py                 # 交互式获取 Cloudflare cf_clearance 的脚本
│  └─ requirements.txt        # 子模块依赖
└─ （运行后生成的文件）
   ├─ listing_cat5.html / listing_cat7.html
   ├─ listing_cat5.json  / listing_cat7.json
   ├─ listing_cat5_아파트임대.json
   └─ listing_cat7_주택임대.json
```

## 环境要求

- Windows（推荐），Python 3.10+。
- 已安装 Chrome（或 Chromium 浏览器）。

## 安装依赖

建议使用虚拟环境：

```
python -m venv .venv
.venv\Scripts\activate
```

安装依赖：

```
# 抓取与解析脚本所需
pip install requests beautifulsoup4 lxml

# Cloudflare 清除脚本所需
pip install -r cf-clearance-scraper/requirements.txt
```

## 使用方法

1) 如无 `bonghwa_cookies.json`，先获取一次 `cf_clearance`（会打开浏览器窗口，按脚本固定坐标自动点击，直至发放 cookie）：

```
python cf-clearance-scraper/main.py https://www.bonghwa.co.kr/ --file bonghwa_cookies.json --headed --timeout 30
```

2) 抓取与解析两个分类页（cat=5、cat=7），并按类别过滤导出：

```
python bonghwa.py
```

- 输出：
  - `listing_cat5.html`、`listing_cat7.html`（完整 HTML）
  - `listing_cat5.json`、`listing_cat7.json`（结构化 JSON）
  - `listing_cat5_아파트임대.json`（cat=5 过滤）
  - `listing_cat7_주택임대.json`（cat=7 过滤）

3) 生成带编号的汇总文档：

```
python export_summary.py
```

- 输出：`임대汇总.txt`，包含：
  - `cat=7`（주택임대）总数与明细，编号 `[7-1]...`
  - `cat=5`（아파트임대）总数与明细，编号 `[5-1]...`

## 运行逻辑说明

- 按需刷新策略：
  - 首选读取 `bonghwa_cookies.json` 的最新条目（含 `cf_clearance` 与 UA）。
  - 访问分类页时若状态码非 200 或检测到 Cloudflare 拦截关键词，触发一次刷新并重试当前页。
- 解析逻辑：
  - 从左列抓取分类与描述，右列抓取电话号码；识别“新发布”图标。
  - `cat=5` 仅保留 `category` 为“아파트임대”；`cat=7` 仅保留“주택임대”。

## 常见问题

- 仍被拦截：重新执行清除脚本（headed 模式）并手动辅助点击；确保浏览器已安装且可正常启动。
- 依赖安装失败：优先在虚拟环境中安装；升级 `pip`（`python -m pip install -U pip`）。
- 字体/编码显示异常：确保终端使用 UTF-8 编码；文件均以 UTF-8 保存。

## 授权与致谢

- `cf-clearance-scraper` 目录来自子模块代码，保留其依赖与用法以实现 Cloudflare 通过；如需独立升级请参考其 README 与发行说明。