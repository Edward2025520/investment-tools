# stock_reports — A 股/港股年报 PDF 下载工具

从巨潮资讯网（A 股）和港交所披露易（港股）按需下载上市公司年报 PDF。

## 安装

```bash
pip install httpx tqdm beautifulsoup4 lxml
```

## 用法

```bash
# A 股：6 位代码，支持 sz/sh 前缀
python tools/stock_reports/fetch_reports.py 000001
python tools/stock_reports/fetch_reports.py 600519 --years 8

# 港股：支持 00700 / 700 / hk00700 三种写法
python tools/stock_reports/fetch_reports.py 00700 --market hk
python tools/stock_reports/fetch_reports.py 700 --market hk --years 10

# 自定义输出目录
python tools/stock_reports/fetch_reports.py 000001 --output ./my_reports

# 强制重新下载
python tools/stock_reports/fetch_reports.py 000001 --force
```

## 输出

文件保存到 `data/reports/{股票代码}/`：

- A 股：`{公司简称}_{年份}_年度报告.pdf`
- 港股：`{公司简称}_{年份}_年报.pdf`

网络错误会自动重试 3 次并打印友好错误信息，不会因单份失败中断。

## 数据源

| 市场 | 数据源 | 接口 | 特性 |
|------|--------|------|------|
| A 股 | 巨潮资讯网 | POST全文搜索 + 静态CDN下载 | 按关键词 "代码 年度报告" 检索，解析 `<em>` 提取简称 |
| 港股 | 港交所披露易 | JSF会话 + prefix.do股票过滤 + 标题搜索 | 通过 prefix.do 获取股票内部 stockId 做服务端过滤，只查目标股票记录，聚焦 1-6 月年报发布高峰，大幅减少请求量 |

港股 API 仅支持约 30 天时间跨度，内部按月分批查询、按年份去重并优先中文版。

## 项目结构

```
stock_reports/
├── fetch_reports.py   # CLI 入口（含错误处理）
├── cninfo_client.py   # 巨潮 API 封装（异步 httpx，HTML 实体转义）
├── hkex_client.py     # 港交所 API 封装（JSF 会话 + stockId 过滤）
├── generate_docs.py   # 生成 Word 使用说明
└── utils.py           # 代码归一化、路径、文件命名
```
