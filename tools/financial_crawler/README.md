# financial_crawler — A 股/港股/美股财报数据可视化工具

从 AKShare 获取 A 股、港股、美股财报数据，按市场差异化生成 PNG 图表 + CSV 数据。

## 安装

```bash
pip install akshare matplotlib pandas
```

## 使用方法

```bash
# A 股：6 位代码
python tools/financial_crawler/cli.py 600519

# 港股：代码后必须加 .HK
python tools/financial_crawler/cli.py 03690.HK
python tools/financial_crawler/cli.py 00700.HK

# 美股：直接输入代码
python tools/financial_crawler/cli.py NVDA

# 批量
python tools/financial_crawler/cli.py --codes 600519,03690.HK,NVDA

# 指定年限（默认 10）
python tools/financial_crawler/cli.py 600519 --years 5
```

## 图表按市场差异化

各市场根据可获取的数据制定最有价值的图表：

| 市场 | 图表 | 说明 |
|------|------|------|
| A 股 | `profit` / `balance` / `cashflow` / `indicators` | 4 张全表：利润表、资产负债表、现金流量表、财务指标 |
| 港股 | `profit` / `indicators` / `hk_overview` | 3 张：利润表、财务指标，另将资产负债率与现金流合并为一张概览图 |
| 美股 | `profit` / `indicators` | 2 张：利润表、财务指标（简化版） |

中文字体自动检测（微软雅黑、黑体、等线等），无需手动配置。

## 输出

每只股票在 `data/reports/{代码}/charts/` 下生成图表 + 对应 CSV（按实际可获取的数据导出），年报 PDF 留在上级目录：

```
data/reports/{股票代码}/
├── {公司简称}_{年份}_年度报告.pdf   # 年报 PDF（stock_reports 下载）
└── charts/                        # 本工具的图表数据
    ├── profit.png         # 利润表：营收、归母净利润（柱状）+ 营收增长率（折线，副Y轴）
    ├── indicators.png     # 财务指标：ROE、毛利率、净利率
    ├── balance.png        # [A股] 资产负债表：绝对值指标（柱状）+ 比率指标（折线）
    ├── cashflow.png       # [A股] 现金流量表：经营/投资/融资现金流
    ├── hk_overview.png    # [港股] 资产负债率 + 现金流合并概览
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
| `03690.HK` / `00700.HK` | 港股（必须带 `.HK` 后缀） |
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
├── chart.py            # 图表绘制（市场差异化 + 字体自动检测）
├── utils.py            # 工具函数（代码归一化）
├── config.py           # 配置
└── README.md
```
