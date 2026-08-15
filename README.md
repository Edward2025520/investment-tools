# 投资工具集

A 股/港股年报下载、三地财报数据可视化的工具集合。

## 工具

| 工具 | 功能 | 数据源 |
|------|------|--------|
| stock_reports | 下载 A 股/港股年报 PDF | 巨潮资讯网、港交所披露易 |
| financial_crawler | 获取 A/港/美股财报数据，生成差异化图表+CSV | AKShare（同花顺、东方财富） |
| f_screener | 皮奥特洛斯基 F-Score 自选股财务质量筛选 | AKShare（同花顺） |

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 下载年报（A 股）
python tools/stock_reports/fetch_reports.py 600519

# 财报表（在线获取）
python tools/financial_crawler/cli.py 600519

# F-Score 财务质量筛选（A股）
python tools/f_screener/cli.py --codes 600519,002594
```

## 数据流

stock_reports 下载 PDF，financial_crawler 独立在线获取图表。
