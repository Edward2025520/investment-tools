# stock_reports — 年报 PDF 下载器

输入股票代码，自动去交易所官网把这家公司历年的年报 PDF 下载到本地，方便离线翻看。支持 A 股（巨潮资讯网）和港股（港交所披露易）。

## 怎么用

```bash
# A 股：6 位代码，带不带 sz/sh 前缀都行
python tools/stock_reports/fetch_reports.py 000001
python tools/stock_reports/fetch_reports.py 600519 --years 8

# 港股：支持 00700 / 700 / hk00700 三种写法
python tools/stock_reports/fetch_reports.py 00700 --market hk
python tools/stock_reports/fetch_reports.py 700 --market hk --years 10

# 自定义下载到别的目录
python tools/stock_reports/fetch_reports.py 000001 --output ./my_reports

# 强制重新下载（即使本地已有）
python tools/stock_reports/fetch_reports.py 000001 --force
```

默认下载最近 5 年年报，`--years 8` 就是最近 8 年。

## 下载到哪

保存到 `data/reports/{股票代码}/`：

- A 股：`{公司简称}_{年份}_年度报告.pdf`，比如 `贵州茅台_2024_年度报告.pdf`
- 港股：`{公司简称}_{年份}_年报.pdf`

## 有什么讲究

- 哪份文件是年报、不是半年报/季报？工具会按标题关键字（"年度报告"/"年报"）自动过滤
- A 股和港股各有各的坑（A 股检索有同名干扰、港股 API 一次只能查一个月），工具内部都处理好了
- 网络出错会自动重试 3 次，个别文件下载失败不会让整批中断

## 数据源

| 市场 | 来源 | 说明 |
|------|------|------|
| A 股 | 巨潮资讯网 | 上市公司公告的官方发布渠道 |
| 港股 | 港交所披露易 | 港股公司公告的官方发布渠道 |

## 代码结构

```
tools/stock_reports/
├── fetch_reports.py   # 入口（含错误处理）
├── cninfo_client.py   # A 股下载逻辑
├── hkex_client.py     # 港股下载逻辑
├── generate_docs.py   # 生成 Word 使用说明
└── utils.py           # 工具函数（代码归一化、路径、文件命名）
```
