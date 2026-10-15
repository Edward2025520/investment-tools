# 投资工具集

A 股 / 港股 / 美股的**年报下载**和**财报分析**小工具合集。每个工具都能独立运行。

## 工具一览

| 工具 | 它是干嘛的 | 数据源 |
|------|-----------|--------|
| stock_reports | 下载 A 股 / 港股年报 PDF 存到本地，方便离线翻看 | 巨潮资讯网、港交所披露易 |
| financial_crawler | 拉取 A/港/美股财报数据，自动画成图表 + 存 CSV | AKShare（同花顺、东方财富） |
| f_screener | 用 F-Score 方法给自选股做财务质量打分筛选 | AKShare（同花顺） |
| industry_profit | 看一只 A 股比**同行业公司**更能赚钱吗 | AKShare、legulegu |
| valuation | 把净利润还原成现金，再算值多少钱（盈利质量 / 现金流折现 / 同行相对估值） | AKShare、腾讯行情 |
| screen_csi500 | 把中证500 全样本过三道筛子，输出候选清单与报告 | 中证指数官网、同花顺、百度股市通 |

## 快速开始

下面的命令用 `python` 表示；本机运行请统一用 `conda run -n ai python`。

```bash
# 安装依赖
pip install -r requirements.txt

# 下载年报（A 股）
python tools/stock_reports/fetch_reports.py 600519

# 财报图表（在线获取，A/港/美股都行）
python tools/financial_crawler/cli.py 600519

# F-Score 财务质量筛选（A 股）
python tools/f_screener/cli.py --codes 600519,002594

# 行业盈利对比（A 股，比同行更能赚钱吗）
python tools/industry_profit/cli.py 600519

# 盈利质量 / 估值区间 / 同行相对估值（A 股）
python tools/valuation/cli.py quality 600519
python tools/valuation/cli.py intrinsic 600519
python tools/valuation/cli.py relative 600519

# 中证500 三层筛选
python tools/screen_csi500/run.py
```

## 这些工具分别在回答什么问题

- **看自己**：`financial_crawler` 看这家公司自己的营收、利润、现金流这几年怎么走
- **比同行**：`industry_profit` 看它跟同行比谁更能赚钱；`valuation relative` 看它在同行里估值贵不贵
- **查质量**：`f_screener` 用 9 项判断给财务质量打分；`valuation quality` 把净利润还原成现金，看赚的是不是真钱
- **算值多少**：`valuation intrinsic` 用现金流折现算出一个估值区间
- **批量筛选**：`screen_csi500` 把一个指数按三层条件过筛

纵向（自己跟自己的过去比）和横向（自己跟同行比）是两回事，别混着看。

## 数据流

```text
stock_reports     下载年报 PDF        → data/reports/{代码}/*.pdf
financial_crawler 财报图表 + CSV      → data/reports/{代码}/charts/financial/
industry_profit   行业对比图表 + CSV  → data/reports/{代码}/charts/industry_compare/
valuation         估值图表 + CSV      → data/reports/{代码}/charts/valuation/
f_screener        打分结果 CSV        → data/screening/
screen_csi500     筛选明细 + 候选 + 报告 → data/reports/_screens/csi500_YYYYMMDD/
```

`data/` 是各工具共用的输出目录，不入 git。

每个工具的详细说明见各自目录下的 `README.md`。

## 声明

所有工具只做描述性分析与教学演示，不推荐具体标的、不预测走势、不给买卖结论；任何决策与风险由使用者自己承担。
