"""中证500 筛选：路径、缓存与阈值配置。

阈值全部集中在此，便于调参重跑。透明可改，不在代码里藏隐含假设。
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

CONS_CACHE = DATA_DIR / "csi500_cons.json"               # 成分名单
VAL_CACHE_DIR = DATA_DIR / "csi500_valuation"            # 每股 PE/PB 估值历史
FIN_CACHE_DIR = DATA_DIR / "csi500_financial"            # 每股 THS 摘要指标
INDUSTRY_MAP = DATA_DIR / "industry_map_index.json"      # 申万一级行业标签（降级源）

CONS_MAX_AGE_DAYS = 1        # 成分名单按日刷新
VAL_MAX_AGE_DAYS = 1         # 估值分位要现价，按日刷新
FIN_MAX_AGE_DAYS = 90        # 财报指标按季刷新即可

# 强周期行业（申万一级）——用户明确不碰
CYCLICAL_SW1 = {
    "煤炭", "钢铁", "有色金属", "基础化工", "石油石化", "房地产",
    "非银金融", "建筑材料", "建筑装饰", "交通运输",
}

# 第 1 层 排除
MIN_LISTED_YEARS = 3          # 上市/有年报不足 3 年 → 排除
PROFIT_POSITIVE_MIN_YEARS = 2  # 近 3 年扣非净利为正的最少年数
DEBT_ABS_MAX = 85.0          # 资产负债率绝对上限（%），超过直接排除
DEBT_INDUSTRY_PCTL = 0.80    # 行业内资产负债率分位上限（超过即高负债）

# 第 2 层 财务健康 + 成长
ROE_MEAN_MIN = 8.0           # 近 3 年 ROE 均值下限（%）
ROE_EACH_MIN = 0.0           # 近 3 年 ROE 每年下限（%），剔除某年亏损
CASH_CONTENT_MIN = 0.8       # Σ每股经营现金流 / Σ每股收益
REVENUE_CAGR_MIN = 0.0       # 营收 3 年 CAGR 下限（%）
PROFIT_CAGR_MIN = 0.0        # 扣非净利 3 年 CAGR 下限（%）

# 第 3 层 估值
VAL_WINDOW_YEARS = 5         # 历史分位窗口（百度估值为双周频）
SELF_PCTL_MAX = 0.35         # 自身 PE(或 PB) 历史分位上限（低=便宜）
PEER_PCTL_MAX = 0.50         # 同行业 PE(或 PB) 分位上限（降级到一级，标注局限）

# 分位取 PE 与 PB 中较低者作为“自身便宜度”；两者都需为正
SELF_USE_MIN_OF_PE_PB = True
