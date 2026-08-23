"""指标定义、申万层级与路径配置。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "reports"
CACHE_PATH = PROJECT_ROOT / "data" / "industry_map.json"
INDEX_CACHE = PROJECT_ROOT / "data" / "industry_map_index.json"

DEFAULT_YEARS = 3
DEFAULT_LEVEL = 2

# 指标：key → (展示名, 同花顺摘要列名)。ROA 由 ROE 与资产负债率推导。
METRICS = [
    {"key": "net_margin", "label": "净利率", "ths_col": "销售净利率"},
    {"key": "gross_margin", "label": "毛利率", "ths_col": "销售毛利率"},
    {"key": "roe", "label": "ROE", "ths_col": "净资产收益率"},
    {"key": "roa", "label": "ROA", "ths_col": None},
]
DEBT_RATIO_COL = "资产负债率"

# 申万层级 → 映射字典字段名
LEVEL_COL = {1: "sw1", 2: "sw2", 3: "sw3"}
