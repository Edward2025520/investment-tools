# 投资工具集

A 股 / 港股 / 美股的**年报下载**和**财报分析**小工具合集。每个工具都能独立运行。

## 工具一览

| 工具 | 它是干嘛的 | 数据源 |
|------|-----------|--------|
| stock_reports | 下载 A 股 / 港股年报 PDF 存到本地，方便离线翻看 | 巨潮资讯网、港交所披露易 |
| financial_crawler | 拉取 A/港/美股财报数据，自动画成图表 + 存 CSV | AKShare（同花顺、东方财富） |
| f_screener | 用 F-Score 方法给自选股做财务质量打分筛选 | AKShare（同花顺） |
| industry_profit | 看一只 A 股比**同行业公司**更能赚钱吗 | AKShare、legulegu |

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 下载年报（A 股）
python tools/stock_reports/fetch_reports.py 600519

# 财报图表（在线获取，A/港/美股都行）
python tools/financial_crawler/cli.py 600519

# F-Score 财务质量筛选（A股）
python tools/f_screener/cli.py --codes 600519,002594

# 行业盈利对比（A股，比同行更能赚钱吗）
python tools/industry_profit/cli.py 600519
```

## 两个分析工具的区别

- **financial_crawler**：看"这家公司自己"的财报趋势（营收、利润、现金流这几年怎么走）
- **industry_profit**：看"这家公司跟同行比"谁更能赚钱（净利率、ROE 等指标 vs 行业平均）

一个看纵向（自己跟自己的过去比），一个看横向（自己跟同行比）。

## 数据流

```text
stock_reports     下载年报 PDF     → data/reports/{代码}/xxx.pdf
financial_crawler 财报图表+CSV    → data/reports/{代码}/charts/financial/
industry_profit   行业对比图表+CSV → data/reports/{代码}/charts/industry_compare/
```

每个工具的详细说明见各自目录下的 `README.md`。
