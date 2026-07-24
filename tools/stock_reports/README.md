# stock_reports — A 股/港股年报 PDF 下载工具

从巨潮资讯网（A 股）和港交所披露易（港股）按需下载上市公司年报 PDF。

## 安装

```bash
pip install httpx tqdm
```

## 用法

```bash
# A 股：6 位股票代码
python tools/stock_reports/fetch_reports.py 000001
python tools/stock_reports/fetch_reports.py 600519 --years 8

# 港股
python tools/stock_reports/fetch_reports.py 00700 --market hk

# 自定义输出目录
python tools/stock_reports/fetch_reports.py 000001 --output ./my_reports

# 强制重新下载
python tools/stock_reports/fetch_reports.py 000001 --force
```

## 输出

文件保存到 `data/reports/{股票代码}/`，格式：`{公司简称}_{年份}_年度报告.pdf`。

## 数据源

| 市场 | 数据源 | 接口 |
|------|--------|------|
| A 股 | 巨潮资讯网 | POST全文搜索 + 静态CDN下载 |
| 港股 | 港交所披露易 | JSF会话 + 标题搜索 |

## 项目结构

```
stock_reports/
├── fetch_reports.py   # CLI 入口
├── cninfo_client.py   # 巨潮 API 封装（异步 httpx）
├── hkex_client.py     # 港交所 API 封装（JSF 会话）
├── utils.py           # 代码归一化、路径、文件命名
└── generate_docs.py   # 生成 Word 使用说明
```
