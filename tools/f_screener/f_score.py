"""皮奥特洛斯基 F-Score 九项评分。"""

from typing import Optional

import pandas as pd

# 9 项评分标准名称（顺序对应 F-Score 原文）
SCORE_ITEMS = [
    "ROA>0",
    "经营现金流>0",
    "ΔROA",
    "现金流>净利",
    "长期负债率↓",
    "流动比率↑",
    "未增发",
    "毛利率↑",
    "资产周转率↑",
]


def _val(series: Optional[pd.Series], idx) -> Optional[float]:
    """取值，空值/NaN 返回 None。"""
    if series is None or idx not in series.index:
        return None
    v = series.loc[idx]
    if pd.isna(v):
        return None
    return float(v)


def _roa(m: pd.DataFrame, idx) -> Optional[float]:
    net = _val(m.get("净利润"), idx)
    assets = _val(m.get("总资产"), idx)
    if net is None or assets in (None, 0):
        return None
    return net / assets


def score_9(metrics: pd.DataFrame) -> tuple[list, int]:
    """对按年份排序（倒序）的指标表打分，返回 (明细列表, 适用项数)。

    明细元素为 True/False/None（None=缺数据无法判断）。
    取最近两个完整财年：now=第一行，prev=第二行。
    """
    if metrics.empty:
        return [], 0
    years = sorted(metrics.index, reverse=True)
    now, prev = years[0], years[1] if len(years) > 1 else None

    net_now = _val(metrics.get("净利润"), now)
    assets_now = _val(metrics.get("总资产"), now)
    ocf_now = _val(metrics.get("经营现金流"), now)
    lt_debt_now = _val(metrics.get("长期负债"), now)
    cr_now = _val(metrics.get("流动比率"), now)
    share_now = _val(metrics.get("实收资本"), now)
    gm_now = _val(metrics.get("销售毛利率"), now)
    rev_now = _val(metrics.get("营业收入"), now)

    roa_now = _roa(metrics, now)
    roa_prev = _roa(metrics, prev) if prev is not None else None

    # 5. 长期负债率 = 长期负债/总资产
    lt_ratio_now = (lt_debt_now / assets_now) if lt_debt_now is not None and assets_now not in (None, 0) else None
    lt_ratio_prev = None
    if prev is not None:
        lt_debt_prev = _val(metrics.get("长期负债"), prev)
        assets_prev = _val(metrics.get("总资产"), prev)
        if lt_debt_prev is not None and assets_prev not in (None, 0):
            lt_ratio_prev = lt_debt_prev / assets_prev

    # 9. 资产周转率 = 营业收入/总资产
    turnover_now = (rev_now / assets_now) if rev_now is not None and assets_now not in (None, 0) else None
    turnover_prev = None
    if prev is not None:
        rev_prev = _val(metrics.get("营业收入"), prev)
        assets_prev = _val(metrics.get("总资产"), prev)
        if rev_prev is not None and assets_prev not in (None, 0):
            turnover_prev = rev_prev / assets_prev

    def _gt(a, b):
        return True if a is not None and b is not None and a > b else (None if (a is None or b is None) else False)

    items = [
        # 1. ROA > 0
        True if roa_now is not None and roa_now > 0 else (None if roa_now is None else False),
        # 2. 经营现金流 > 0
        True if ocf_now is not None and ocf_now > 0 else (None if ocf_now is None else False),
        # 3. ΔROA > 0
        _gt(roa_now, roa_prev),
        # 4. 经营现金流 > 净利润
        _gt(ocf_now, net_now),
        # 5. 长期负债率下降
        True if lt_ratio_now is not None and lt_ratio_prev is not None and lt_ratio_now < lt_ratio_prev
        else (None if (lt_ratio_now is None or lt_ratio_prev is None) else False),
        # 6. 流动比率上升
        None if cr_now is None or prev is None else
        (True if (cr_prev := _val(metrics.get("流动比率"), prev)) is not None and cr_now > cr_prev else
         (None if (cr_prev := _val(metrics.get("流动比率"), prev)) is None else False)),
        # 7. 未增发股票
        None if share_now is None or prev is None else
        (True if (share_prev := _val(metrics.get("实收资本"), prev)) is not None and share_now <= share_prev else
         (None if (share_prev := _val(metrics.get("实收资本"), prev)) is None else False)),
        # 8. 毛利率上升
        _gt(gm_now, _val(metrics.get("销售毛利率"), prev) if prev is not None else None),
        # 9. 资产周转率上升
        _gt(turnover_now, turnover_prev),
    ]

    applied = sum(1 for v in items if v is not None)
    return items, applied
