# financial_crawler — A 股/港股/美股财报数据可视化工具

从 AKShare 获取 A 股、港股、美股的四张财报表数据，生成 PNG 图表 + CSV 数据。

## 环境

```bash
pip install akshare matplotlib
```

## 使用方法

```bash
# A 股：6 位代码
python tools/financial_crawler/cli.py 600519
python tools/financial_crawler/cli.py 601169

# 港股：代码后加 .HK
python tools/financial_crawler/cli.py 03690.HK
python tools/financial_crawler/cli.py 00700.HK

# 美股：直接输入代码
python tools/financial_crawler/cli.py NVDA
python tools/financial_crawler/cli.py BRK_B

# 批量
python tools/financial_crawler/cli.py --codes 600519,03690.HK,NVDA

# 指定年限
python tools/financial_crawler/cli.py 600519 --years 5
```

## 输出

每只股票在 `data/reports/{代码}/` 下生成 4 张 PNG + 4 个 CSV：

```
data/reports/{股票代码}/
├── profit.png         # 利润表：营收、归母净利润（柱状）+ 营收增长率（折线，副Y轴）
├── balance.png        # 资产负债表：绝对值指标（柱状）+ 比率指标（折线，副Y轴）
├── cashflow.png       # 现金流量表：经营/投资/融资现金流
├── indicators.png     # 财务指标：ROE、毛利率、净利率
├── profit.csv         # 利润表原始数据
├── balance.csv        # 资产负债表原始数据
├── cashflow.csv       # 现金流量表原始数据
└── indicators.csv     # 财务指标原始数据
```

提示：港股和美股因数据源限制，部分指标（现金流明细、资产负债表绝对值）可能不完整。
保险类公司（如 BRK_B）科目结构不同，现金流量图可能无数据。

## 市场自动识别

| 输入示例 | 识别结果 |
|---------|---------|
| `600519` / `000001` | A 股 |
| `03690.HK` / `00700.HK` | 港股 |
| `NVDA` / `BRK_B` / `AAPL` | 美股 |

## 数据源

| 市场 | 数据源 | 覆盖年限 |
|------|--------|---------|
| A 股 | 同花顺 (ths) | 10 年+ |
| 港股 | 东方财富 (EM) | 约 9-10 年 |
| 美股 | 东方财富 (EM) | 约 10 年 |

## 项目结构

```
tools/financial_crawler/
├── cli.py              # CLI 入口
├── akshare_client.py   # 数据获取封装
├── chart.py            # 图表绘制
├── utils.py            # 工具函数
├── config.py           # 配置
└── README.md
```
