# f_screener — 皮奥特洛斯基 F-Score 自选股筛选器（A股）

基于约瑟夫·皮奥特洛斯基（Joseph Piotroski）2000 年论文《Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers》的 9 项评分体系，对自选股清单做财务质量评分。

## 安装

```bash
pip install akshare pandas
```

## 用法

```bash
# 单只 / 多只
python tools/f_screener/cli.py --codes 600519
python tools/f_screener/cli.py --codes 600519,002594

# 从清单文件读取（逐行，支持 # 注释）
python tools/f_screener/cli.py --file watchlist.txt

# 只输出高分标的
python tools/f_screener/cli.py --codes 600519,002594 --min-score 5

# 显示 9 项明细
python tools/f_screener/cli.py --codes 600519 --verbose

# 强制包含金融股（默认排除）
python tools/f_screener/cli.py --codes 000001 --include-financial

# 指定年报年限（默认 8）
python tools/f_screener/cli.py --codes 600519 --years 10
```

## 今年/去年对比

终端表格和 CSV 均展示今年（最新年报）与去年（上一份年报）的关键指标对比：

```
代码      简称    总分  适用项  评分   营收(今/昨亿)      净利(今/昨亿)     毛利率(今/昨%)    ROA(今/昨%)     现金流(今/昨亿)
600519  贵州茅台  5    9      0.56  1720.54/1741.44  853.1/893.35    91.18/91.93    28.08/29.88    615.22/924.64
```

用于判断财务趋势：ROA、毛利率等指标应逐年改善才符合 F-Score 的「ΔROA」「毛利率↑」加分项。

## F-Score 9 项

| 类别 | 项目 | 说明 |
|------|------|------|
| 盈利能力 | ROA>0 | 净利润/总资产为正 |
| | 经营现金流>0 | 经营现金流为正 |
| | ΔROA | 今年 ROA 高于去年 |
| | 现金流>净利 | 经营现金流高于净利润（盈利质量） |
| 杠杆/流动性 | 长期负债率↓ | 长期负债/总资产下降 |
| | 流动比率↑ | 流动比率上升 |
| | 未增发 | 股本未增加（无稀释） |
| 经营效率 | 毛利率↑ | 毛利率上升 |
| | 资产周转率↑ | 营业收入/总资产上升 |

每满足一项得 1 分，总分 0-9。8-9 分为高质量，5-7 分为中等，0-4 分需警惕。

## 金融股处理

银行、保险、证券等金融股**默认排除**——它们的杠杆和流动性结构特殊，F-Score 第 5、6 项会失真。识别方式：股票简称/行业关键词自动匹配 + 手动名单（`config.py` 中 `MANUAL_FINANCIAL` 可手动补充，如东方财富 300059）。

## 输出

结果保存到 `data/screening/fscore_YYYYMMDD.csv`（utf-8-sig）：

```
代码,简称,行业,数据年限,总分,适用项,评分,营收今(亿),营收昨(亿),净利润今(亿),净利润昨(亿),毛利率今(%),毛利率昨(%),ROA今(%),ROA昨(%),现金流今(亿),现金流昨(亿),ROA>0,经营现金流>0,ΔROA,现金流>净利,长期负债率↓,流动比率↑,未增发,毛利率↑,资产周转率↑
600519,贵州茅台,,8,5,9,0.56,1720.54,1741.44,853.1,893.35,91.18,91.93,28.08,29.88,615.22,924.64,1,1,0,0,1,1,1,0,0
```

被跳过的金融股单独存 `fscore_skipped_YYYYMMDD.csv`。

## 数据源

同花顺（THS）财务接口，经 AKShare 获取，仅支持 A 股。

## 项目结构

```
f_screener/
├── cli.py        # CLI 入口（含今年/去年对比输出）
├── data.py       # 数据获取（四表原始年报 + 字段映射）
├── f_score.py    # 9 项评分
├── financial.py  # 金融股识别
└── config.py     # 关键词表、手动名单、字段映射
```

## 免责声明

工具仅提供量化筛选结果，不构成投资建议。F-Score 是财务质量指标，不含估值判断；高分不保证上涨，请结合基本面研究使用。
