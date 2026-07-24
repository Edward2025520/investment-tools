# 投资工具集

A 股年报下载、利润表分析、三地财报数据可视化的工具集合。

## 工具

| 工具 | 功能 | 数据源 |
|------|------|--------|
| stock_reports | 下载 A 股/港股年报 PDF | 巨潮资讯网、港交所披露易 |
| profit_analyzer | 从年报 PDF 提取利润表并生成趋势图 | 依赖 stock_reports 的输出 |
| financial_crawler | 获取 A/港/美股四张财报表数据，生成图表+CSV | AKShare（同花顺、东方财富） |
| value_screener | 价值筛选 | — |

## 快速开始

```bash
# 安装依赖
pip install httpx tqdm akshare matplotlib pdfplumber

# 下载年报（A 股）
python tools/stock_reports/fetch_reports.py 600519

# 利润表分析
python tools/profit_analyzer/cli.py 600519

# 财报表（在线获取）
python tools/financial_crawler/cli.py 600519
```

## 数据流

stock_reports 下载 PDF → profit_analyzer 分析。financial_crawler 独立在线获取。
