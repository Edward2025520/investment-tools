"""指标口径、路径与估值默认假设配置。"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "reports"
RE_A = re.compile(r"^\d{6}$")

# 每股原始年报科目序列缓存
RAW_CACHE_DIR = PROJECT_ROOT / "data" / "valuation_annual"
CACHE_MAX_AGE_DAYS = 90
RAW_YEARS = 20  # 每股最多存 20 个年报期，覆盖任意 --years

# quality 默认
QUALITY_YEARS = 8

# intrinsic 默认（保守）
INTRINSIC_YEARS = 10
WACC = 0.10
GROWTH = 0.03
TERMINAL_G = 0.02
# 图中 3 条增速线 = 基准 ± 此带宽
GROWTH_BAND = 0.02
# 敏感性网格（intrinsic 专用）
WACC_RANGE = (0.07, 0.11)
WACC_STEP = 0.01
TG_RANGE = (0.0, 0.04)
TG_STEP = 0.01

# relative 默认
RELATIVE_LEVEL = 2

# 科目别名：表名(同 fetch_raw_all 返回的 key) -> 规范列名 -> 命中该列名的候选子串（首个命中列优先）
# profit/balance/cashflow 对应同花顺三张原始年报表。
SUBJECT_ALIASES = {
    "profit": {
        "归母净利": ["归属于母公司所有者的净利润"],
        "扣非净利": ["扣除非经常性损益后的净利润"],
        "财务费用": ["财务费用"],
        "所得税": ["所得税费用"],
    },
    "balance": {
        "货币资金": ["货币资金"],
        "短期借款": ["短期借款"],
        "长期借款": ["长期借款"],
        "归母权益": ["归属于母公司所有者权益合计"],
        "应收": ["应收票据及应收账款", "应收账款"],
        "存货": ["存货"],
        "应付": ["应付票据及应付账款", "应付账款"],
        "合同负债": ["合同负债"],
    },
    "cashflow": {
        "OCF": ["经营活动产生的现金流量净额"],
        "资本开支": ["购建固定资产、无形资产和其他长期资产支付的现金"],
        "折旧": ["固定资产折旧、油气资产折耗、生产性生物资产折旧"],
        "无形摊销": ["无形资产摊销"],
        "长摊摊销": ["长期待摊费用摊销"],
        "存货减少": ["存货的减少"],
        "应收减少": ["经营性应收项目的减少"],
        "应付增加": ["经营性应付项目的增加"],
    },
}

# 终端逐行表 + CSV 的展示顺序与中文标签（现金含量为跨年汇总，单独打印不进逐行表）
QUALITY_COLS = ["年份", "归母净利", "扣非净利", "扣非差", "OCF",
                "资本开支", "FCF(经营近似)"]
# 仅写进 CSV 的桥成分明细（教学用：为什么净利≠OCF）
QUALITY_BRIDGE_COLS = ["折旧摊销", "ΔWC经营", "存货减少", "应收减少", "应付增加"]
