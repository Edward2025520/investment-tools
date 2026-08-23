# financial_crawler — 财报图表生成器

输入一只 A 股 / 港股 / 美股代码，自动去网上拉这家公司近几年财报，画成图表存成 PNG，同时把原始数据存成 CSV，方便你自己看、自己算。

## 怎么用

```bash
# A 股：直接输 6 位代码
python tools/financial_crawler/cli.py 600519

# 港股：代码后必须加 .HK
python tools/financial_crawler/cli.py 03690.HK

# 美股：直接输代码
python tools/financial_crawler/cli.py NVDA

# 一次看多只
python tools/financial_crawler/cli.py --codes 600519,03690.HK,NVDA

# 看几年（默认 10 年）
python tools/financial_crawler/cli.py 600519 --years 5
```

## 图表按市场不同

各市场能拿到的数据不一样，所以画最有价值的图：

| 市场 | 图表 | 内容 |
|------|------|------|
| A 股 | 4 张 | 利润表、资产负债表、现金流量表、财务指标（最全） |
| 港股 | 3 张 | 利润表、财务指标，另把资产负债率和现金流合并成一张概览 |
| 美股 | 2 张 | 利润表、财务指标（数据源有限，简化版） |

- **利润表**：营收和净利润（柱子）+ 营收增长率（折线）——这家公司这几年卖得多不多、赚得稳不稳
- **财务指标**：ROE、毛利率、净利率——赚钱效率高不高
- **资产负债表 / 现金流量表**：家底厚不厚、现金流健康不健康

图表里中文会自动处理，不用手动配字体。

## 输出文件

每只股票的结果在 `data/reports/{股票代码}/charts/financial/`：

```text
data/reports/600519/
├── 贵州茅台_2024_年度报告.pdf    # 年报 PDF（stock_reports 下的，和本工具无关）
└── charts/
    └── financial/               # 本工具的输出
        ├── profit.png            # 利润表
        ├── indicators.png        # 财务指标
        ├── balance.png           # [A股] 资产负债表
        ├── cashflow.png          # [A股] 现金流量表
        ├── hk_overview.png       # [港股] 资产负债率+现金流概览
        ├── profit.csv            # 利润表原始数据
        ├── balance.csv
        ├── cashflow.csv
        └── indicators.csv
```

提示：

- 港股和美股因为数据源限制，部分表格（现金流明细、资产负债表绝对值）可能不完整
- 保险类公司（如 BRK_B）科目结构和普通公司不一样，现金流量图可能没有数据

## 市场自动识别

| 输入示例 | 识别结果 |
|---------|---------|
| `600519` / `000001` | A 股 |
| `03690.HK` / `00700.HK` | 港股（必须带 `.HK`） |
| `NVDA` / `BRK_B` / `AAPL` | 美股 |

## 数据源

| 市场 | 数据源 | 能看几年 |
|------|--------|---------|
| A 股 | 同花顺 | 10 年+ |
| 港股 | 东方财富 | 约 9-10 年 |
| 美股 | 东方财富 | 约 10 年 |

## 代码结构

```
tools/financial_crawler/
├── cli.py              # 入口：接收代码、调流程
├── akshare_client.py   # 拉数据（A股同花顺、港/美股东方财富）
├── chart.py            # 画图（按市场差异 + 中文字体自动检测）
├── utils.py            # 工具函数（代码归一化、输出路径）
├── config.py           # 配置
└── README.md
```
