"""行业基准（中位数/截尾均值/简单平均/市值加权）、排名与杜邦分解。"""

from statistics import median
from typing import Optional

from tools.industry_profit import config

TRIM_PCT = 0.1  # 截尾均值：去掉上下各 10% 的极值


def _trimmed_mean(values: list, pct: float = TRIM_PCT) -> Optional[float]:
    """截尾均值：按 pct 去掉两端极值后取平均；样本太少时退化为算术平均。"""
    n = len(values)
    if not n:
        return None
    k = int(n * pct)
    if k == 0:
        return sum(values) / n
    kept = sorted(values)[k:n - k]
    return sum(kept) / len(kept) if kept else None


def dupont(net_margin, roa, roe) -> Optional[dict]:
    """杜邦分解：ROE = 净利率 × 总资产周转率 × 权益乘数（严格恒等）。

    周转率与权益乘数由 ROA、ROE 反推，不依赖资产负债表科目：
        周转率 = ROA / 净利率      权益乘数 = ROE / ROA
    三者相乘还原 ROE，无额外近似。净利率或 ROA 非正时分解无意义，返回 None。
    """
    if net_margin is None or roa is None or roe is None:
        return None
    if net_margin <= 0 or roa == 0:
        return None
    return {
        "net_margin": net_margin,
        "asset_turnover": roa / net_margin,
        "equity_multiplier": roe / roa,
    }


def dupont_compare(metrics: dict, target_code: str) -> Optional[dict]:
    """公司 vs 行业典型公司的杜邦对照。

    行业侧用"典型公司"：先取各指标的中位数，再由中位数的净利率/ROA/ROE
    反推因子——这样行业分解同样满足恒等式，而不是三个因子中位数的拼接
    （后者相乘不等于 ROE，会误导读者）。
    """
    def med(key):
        vals = [mv[key] for mv in metrics.values() if mv.get(key) is not None]
        return median(vals) if vals else None

    t = metrics.get(target_code)
    company = None
    if t:
        company = dupont(t.get("net_margin"), t.get("roa"), t.get("roe"))
    industry = dupont(med("net_margin"), med("roa"), med("roe"))
    if company is None and industry is None:
        return None
    return {"company": company, "industry": industry}


def compute_stats(metrics: dict, target_code: str, mapping: dict) -> dict:
    """计算各指标统计量，返回 {指标key: {target, median, simple, trimmed, weighted, rank, pct, n}}。

    四个基准回答不同问题：
        median  典型公司赚多少（对亏损/极值稳健，推荐主看）
        trimmed 截尾均值，去掉上下 10% 极值
        simple  算术平均，受极值影响大（行业亏损面大时会被拖成负数）
        weighted 市值加权，代表"行业整体"
    rank 为从高到低的名次（1 = 行业第一）；pct 为百分位（越小越靠前）。
    """
    stats = {}
    for m in config.METRICS:
        key = m["key"]
        vals = {c: mv[key] for c, mv in metrics.items() if mv.get(key) is not None}
        n = len(vals)
        if not n:
            stats[key] = {"target": None, "median": None, "simple": None,
                          "trimmed": None, "weighted": None,
                          "rank": None, "pct": None, "n": 0}
            continue

        target = vals.get(target_code)
        values = list(vals.values())
        trimmed = _trimmed_mean(values)

        wsum = wcap = 0.0
        for c, v in vals.items():
            cap = mapping.get(c, {}).get("market_cap")
            if cap and cap > 0:
                wsum += cap * v
                wcap += cap
        weighted = round(wsum / wcap, 2) if wcap else None

        # 排位：数值越大越靠前（含并列），含目标自身
        if target is None:
            rank = pct = None
        else:
            rank = sum(1 for v in values if v > target) + 1
            pct = round(rank / n * 100, 1)

        stats[key] = {
            "target": target,
            "median": round(median(values), 2),
            "simple": round(sum(values) / n, 2),
            "trimmed": round(trimmed, 2) if trimmed is not None else None,
            "weighted": weighted,
            "rank": rank,
            "pct": pct,
            "n": n,
        }
    return stats
