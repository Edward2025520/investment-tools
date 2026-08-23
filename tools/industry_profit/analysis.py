"""行业平均（简单/市值加权）与排名百分位计算。"""

from tools.industry_profit import config


def compute_stats(metrics: dict[str, dict], target_code: str, mapping: dict) -> dict:
    """计算各指标统计量，返回 {指标key: {target, simple, weighted, rank, n}}。

    rank 为从高到低的排位（1 = 行业第一），比用百分位更直观：
    高于目标 = rank-1 家，低于目标 = n-rank 家。
    """
    stats = {}
    for m in config.METRICS:
        key = m["key"]
        vals = {c: mv[key] for c, mv in metrics.items() if mv.get(key) is not None}
        n = len(vals)
        if not n:
            stats[key] = {"target": None, "simple": None, "weighted": None,
                          "rank": None, "n": 0}
            continue

        target = vals.get(target_code)
        simple = round(sum(vals.values()) / n, 2)

        wsum = wcap = 0.0
        for c, v in vals.items():
            cap = mapping.get(c, {}).get("market_cap")
            if cap and cap > 0:
                wsum += cap * v
                wcap += cap
        weighted = round(wsum / wcap, 2) if wcap else None

        # 排位：数值越大越靠前（含并列），含目标自身
        if target is None:
            rank = None
        else:
            above = sum(1 for v in vals.values() if v > target)
            rank = above + 1

        stats[key] = {"target": target, "simple": simple, "weighted": weighted,
                      "rank": rank, "n": n}
    return stats
