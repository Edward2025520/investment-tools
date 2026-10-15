"""算数：quality 逐年表 + intrinsic 两阶段折现 / 敏感性网格。"""

import pandas as pd

from tools.valuation import config


def _na(v) -> bool:
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _v(r, col):
    x = r.get(col)
    return None if _na(x) else float(x)


def _sum(*vals):
    """把非 None 项相加；全空返回 None（折旧摊销/ΔWC 用，缺明细就当没有）。"""
    present = [v for v in vals if v is not None]
    return round(sum(present), 2) if present else None


def _sub(a, b):
    return round(a - b, 2) if a is not None and b is not None else None


def quality_frame(frame: pd.DataFrame, years: int) -> dict:
    """逐年 quality 行（升序取最近 years 期）+ 跨年现金含量。

    现金含量 = ΣOCF / Σ归母净利（仅在两项都全的年对里累计）；
    分母 ≤0（累计亏损）或样本不足时无意义 → None。
    """
    recent = frame.sort_index().tail(years)
    rows = []
    cash_num = cash_den = 0.0
    for year, r in recent.iterrows():
        gm = _v(r, "归母净利")
        dk = _v(r, "扣非净利")
        ocf = _v(r, "OCF")
        capex = _v(r, "资本开支")
        dep, amort, lt = _v(r, "折旧"), _v(r, "无形摊销"), _v(r, "长摊摊销")
        inv, recv, pay = (_v(r, "存货减少"), _v(r, "应收减少"), _v(r, "应付增加"))

        wc_items = [inv, recv, pay]
        if ocf is not None and gm is not None:
            cash_num += ocf
            cash_den += gm
        rows.append({
            "年份": int(year),
            "归母净利": gm,
            "扣非净利": dk,
            "扣非差": _sub(gm, dk),
            "OCF": ocf,
            "资本开支": capex,
            "FCF(经营近似)": _sub(ocf, capex),
            # 桥明细（净利 → OCF 差在哪）
            "折旧摊销": _sum(dep, amort, lt) if dep is not None else None,
            "ΔWC经营": _sum(*wc_items),
            "存货减少": inv,
            "应收减少": recv,
            "应付增加": pay,
        })

    if cash_den > 0:
        cash_content = round(cash_num / cash_den, 3)
    else:
        cash_content = None
    return {"years": [r["年份"] for r in rows], "rows": rows,
            "cash_content": cash_content, "n": len(rows)}


# ── intrinsic：两阶段现金流折现 ──

def pick_base_fcf(frame: pd.DataFrame):
    """默认 FCF0：最近一个 OCF−资本开支 > 0 的年。全非正 → None。"""
    fcf = (frame["OCF"] - frame["资本开支"]).dropna()
    pos = fcf[fcf > 0]
    if pos.empty:
        return None
    year = int(pos.index[-1])
    return year, round(float(pos.iloc[-1]), 2)


def balance_point(frame: pd.DataFrame):
    """最近一年 货币资金/归母权益 齐 → (year, cash, short, long, equity, absent)。

    短借/长借为空按 0 计（报表不列该行项即无此类借款），科目名记入 absent 供上层
    明示口径；货币资金/归母权益缺失说明取数不完整，返回 None 不猜。
    """
    have = frame[["货币资金", "归母权益"]].dropna()
    if have.empty:
        return None
    year = int(have.index[-1])
    r = frame.loc[year]
    absent = [n for n in ("短期借款", "长期借款") if pd.isna(r[n])]
    short = 0.0 if "短期借款" in absent else float(r["短期借款"])
    long = 0.0 if "长期借款" in absent else float(r["长期借款"])
    return year, float(r["货币资金"]), short, long, float(r["归母权益"]), absent


def dcf_ev(fcf0: float, g: float, gt: float, w: float, y: int) -> float:
    """两阶段折现：显性期 ΣFCF0(1+g)^i/(1+w)^i + 终值折回。w 必须 > gt。"""
    total = 0.0
    f = fcf0
    for i in range(1, y + 1):
        f *= (1 + g)
        total += f / ((1 + w) ** i)
    tv = f * (1 + gt) / (w - gt)
    total += tv / ((1 + w) ** y)
    return total


def _axis(lo: float, hi: float, step: float) -> list:
    out, x = [], lo
    while x <= hi + 1e-9:
        out.append(round(x, 4))
        x += step
    return out


def equity_per_share(frame: pd.DataFrame, q: dict, wacc, growth, term_g, years):
    """整份 intrinsic 报告（含基准每股、wacc×tg 网格区间、画图 3 条增速线）。

    q = fetch_quotes 单票：{name, price, pe_ttm, pb, market_cap_亿}。
    """
    notes = []
    base = pick_base_fcf(frame)
    if base is None:
        return {"ok": False, "reason": "近 20 个年报期 FCF(=OCF−资本开支) 无一年为正，DCF 无可折现基数"}
    base_year, fcf0 = base

    price = q.get("price")
    mcap = q.get("market_cap_亿")
    if price is None or not mcap or price <= 0:
        return {"ok": False, "reason": "行情快照缺失（现价/总市值），无法换算每股"}
    shares = round(mcap / price, 4)  # 亿股 = 总市值(亿元)/现价(元)

    # EV → 股东价值：减净债务（短借+长借−货币资金）
    bv = balance_point(frame)
    if bv is None:
        equity = None
        net_debt = None
        bvps = None
        notes.append("缺 货币资金/归母权益（银行等报表口径不同），未扣净债务、无每股净资产下限；"
                     "股东价值按 EV 近似")
    else:
        y_bal, cash, short, long, eq, absent = bv
        net_debt = round((short + long) - cash, 2)
        equity_base = eq
        bvps = round(equity_base / shares, 2) if shares else None
        if absent:
            notes.append("报表无 " + "、".join(absent) + " 行项，按 0 计")

    def value(w, g, gt):
        ev = dcf_ev(fcf0, g, gt, w, years)
        eq = ev - (net_debt or 0.0)
        return ev, eq / shares

    ev0, per_share = value(wacc, growth, term_g)
    ev0, equity0 = round(ev0, 2), round(ev0 - (net_debt or 0.0), 2)

    # wacc×永续增速网格 → 每股区间（轴自动包住用户设的 wacc/gt，默认参数时即 7~11%×0~4%）
    ws = _axis(min(config.WACC_RANGE[0], wacc), max(config.WACC_RANGE[1], wacc), config.WACC_STEP)
    gts = _axis(min(config.TG_RANGE[0], term_g), max(config.TG_RANGE[1], term_g), config.TG_STEP)
    grid = []
    for w in ws:
        row = []
        for gt in gts:
            row.append(None if w <= gt else round(value(w, growth, gt)[1], 2))
        grid.append(row)
    lo = min(c for r in grid for c in r if c is not None)
    hi = max(c for r in grid for c in r if c is not None)

    # 画图：每股随 wacc 变化，显性增速 基准±band 共 3 条，永续增速固定
    xw = _axis(min(config.WACC_RANGE[0] - 0.01, wacc), max(config.WACC_RANGE[1] + 0.01, wacc), 0.01)
    curves = []
    for g in sorted({round(growth - config.GROWTH_BAND, 4), growth,
                     round(growth + config.GROWTH_BAND, 4)}):
        ys = []
        for w in xw:
            if w <= term_g:
                ys.append(None)
            else:
                ys.append(round(value(w, g, term_g)[1], 2))
        curves.append({"g": g, "x": xw, "y": ys})

    return {
        "ok": True, "base_year": base_year, "fcf0": fcf0,
        "name": q.get("name") or "", "price": price, "shares": shares,
        "net_debt": net_debt, "bvps": bvps,
        "wacc": wacc, "growth": growth, "term_g": term_g, "years": years,
        "ev": ev0, "equity": equity0, "per_share": round(per_share, 2),
        "grid_lo": lo, "grid_hi": hi,
        "axis_w": ws, "axis_tg": gts, "grid": grid, "curves": curves,
        "notes": notes,
    }


# ── relative：同行横截面的描述性分位（无评分/推荐）──

def describe(vals: list):
    """正数数组的描述统计：中位/P25/P75/min/max。空 → None。"""
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)

    def q(p):
        i = (n - 1) * p
        lo = int(i)
        hi = min(lo + 1, n - 1)
        frac = i - lo
        return vals[lo] + (vals[hi] - vals[lo]) * frac
    return {"n": n, "median": q(0.5), "p25": q(0.25), "p75": q(0.75),
            "min": vals[0], "max": vals[-1]}


def percentile_rank(vals: list, target: float):
    """目标值在同行里的分位（0~100，低=更便宜一侧）。target 非法返回 None。"""
    if target is None or target <= 0:
        return None
    valid = [v for v in vals if v is not None and v > 0]
    if not valid:
        return None
    below = sum(1 for v in valid if v <= target)
    return round(100 * below / len(valid), 1)
