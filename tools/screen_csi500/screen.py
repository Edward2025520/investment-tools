"""分层筛选：排除 → 财务健康+成长 → 估值分位。产出全样本明细与候选清单。

只做描述性判定：给出“是否满足你设定的条件”，不下“好不好/买不买”结论。
"""

import math

import pandas as pd

from tools.screen_csi500 import config, data

# 同行对比的行业粒度：优先申万二级（可比性更好），样本不足 5 家时回退申万一级
PEER_LEVEL = "申万二级"
PEER_LEVEL_FALLBACK = "申万一级"


def _cagr(first, last, years) -> float:
    """(last/first)^(1/years)-1，单位 %。首值为负/零或跨度非法 → None。"""
    if first is None or last is None or years <= 0:
        return None
    if first <= 0 or last <= 0:
        return None
    try:
        return round(((last / first) ** (1 / years) - 1) * 100, 2)
    except (ValueError, ZeroDivisionError):
        return None


def _build_rows(cons: list[dict], fin: dict, val: dict, imap: dict) -> list[dict]:
    rows = []
    for it in cons:
        code, name = it["code"], it["name"]
        info = imap.get(code) or {}
        f = fin.get(code) or []
        v = val.get(code) or {"pe": [], "pb": []}

        r = {
            "代码": code, "名称": name,
            "申万一级": info.get("sw1") or "",
            "申万二级": info.get("sw2") or "",
            "年报期数": len(f),
        }
        if f:
            last = f[-1]
            r["资产负债率"] = last.get("debt_ratio")
            r["营收"] = last.get("revenue")
            r["扣非净利"] = last.get("deducted")
            last3 = f[-3:] if len(f) >= 3 else f
            r["扣非为正年数"] = sum(1 for x in last3 if (x.get("deducted") or -1) > 0)
            roes = [x["roe"] for x in last3 if x.get("roe") is not None]
            r["ROE3年均"] = round(sum(roes) / len(roes), 2) if roes else None
            r["ROE3年最低"] = min(roes) if roes else None
            if len(f) >= 2:
                span = len(f) - 1
                r["营收CAGR"] = _cagr(f[0].get("revenue"), last.get("revenue"), span)
                r["扣非CAGR"] = _cagr(f[0].get("deducted"), last.get("deducted"), span)
            num = sum(x["ocf_ps"] for x in last3 if x.get("ocf_ps") is not None)
            den = sum(x["eps"] for x in last3 if x.get("eps") is not None)
            r["现金含量3年"] = round(num / den, 2) if den and den > 0 else None
            yoys = [x["deducted_yoy"] for x in f if x.get("deducted_yoy") is not None]
            r["最新扣非同比"] = yoys[-1] if yoys else None
            r["上年扣非同比"] = yoys[-2] if len(yoys) >= 2 else None
        for k in ("资产负债率", "ROE3年均", "ROE3年最低", "营收CAGR", "扣非CAGR",
                  "现金含量3年", "营收", "扣非净利", "扣非为正年数", "年报期数",
                  "最新扣非同比", "上年扣非同比"):
            r.setdefault(k, None)

        r["PE分位5年"] = data.percentile_now(v.get("pe"), config.VAL_WINDOW_YEARS)
        r["PB分位5年"] = data.percentile_now(v.get("pb"), config.VAL_WINDOW_YEARS)
        mins = [x for x in (r["PE分位5年"], r["PB分位5年"]) if x is not None]
        r["自身分位"] = min(mins) if mins else None
        rows.append(r)

    df = pd.DataFrame(rows)

    # 行业内相对量：资产负债率分位、PE/PB 分位
    # 样本 = 中证500 内部同行业。优先按申万二级分组（可比性更好），但中证500
    # 只有 500 只，细分行业常凑不满 5 家，故不足时回退到申万一级。
    def pctl_by_group(col, out):
        df[out] = None

        def assign(group_col, mask=None):
            sub = df if mask is None else df[mask]
            for _, idx in sub.groupby(group_col).groups.items():
                valid = df.loc[idx, col].dropna()
                if len(valid) < 5:
                    continue
                df.loc[valid.index, out] = valid.rank(pct=True).round(4)

        assign(PEER_LEVEL)
        assign(PEER_LEVEL_FALLBACK, df[out].isna())

    pctl_by_group("资产负债率", "负债行业分位")
    pctl_by_group("PE分位5年", "PE同行分位")
    pctl_by_group("PB分位5年", "PB同行分位")

    def peer_min(row):
        vals = [x for x in (row.get("PE同行分位"), row.get("PB同行分位")) if pd.notna(x)]
        return min(vals) if vals else None
    df["同行分位"] = df.apply(peer_min, axis=1)

    return df


def _evaluate(df: pd.DataFrame) -> pd.DataFrame:
    c = config

    def _miss(v) -> bool:
        """pandas 把 None 读成 NaN，判断缺失必须同时覆盖两者。"""
        return v is None or pd.isna(v)

    def layer1(r):
        rs = []
        if not r["申万一级"]:
            rs.append("无行业标签")
        if r["申万一级"] in c.CYCLICAL_SW1:
            rs.append("强周期行业")
        if "ST" in r["名称"] or "退" in r["名称"]:
            rs.append("ST/退市风险")
        if (r["年报期数"] or 0) < c.MIN_LISTED_YEARS:
            rs.append(f"上市不足{c.MIN_LISTED_YEARS}年")
        if (r["扣非为正年数"] or 0) < c.PROFIT_POSITIVE_MIN_YEARS:
            rs.append("扣非近年多为负(亏损/微利)")
        dr = r["资产负债率"]
        if dr is not None and dr >= c.DEBT_ABS_MAX:
            rs.append(f"资产负债率≥{c.DEBT_ABS_MAX:.0f}%")
        dp = r["负债行业分位"]
        if pd.notna(dp) and dp > c.DEBT_INDUSTRY_PCTL:
            rs.append(f"负债率行业前{(1-c.DEBT_INDUSTRY_PCTL)*100:.0f}%")
        return rs

    def layer2(r):
        # 本层是"达标才通过"，数据缺失即无法证明达标，按淘汰处理并说明
        rs = []
        if _miss(r["ROE3年均"]):
            rs.append("ROE3年均缺失")
        elif r["ROE3年均"] < c.ROE_MEAN_MIN:
            rs.append(f"ROE3年均<{c.ROE_MEAN_MIN:.0f}%")
        if _miss(r["ROE3年最低"]):
            rs.append("ROE3年最低缺失")
        elif r["ROE3年最低"] <= c.ROE_EACH_MIN:
            rs.append("有年份ROE≤0")
        if _miss(r["现金含量3年"]):
            rs.append("现金含量缺失")
        elif r["现金含量3年"] < c.CASH_CONTENT_MIN:
            rs.append(f"现金含量<{c.CASH_CONTENT_MIN}")
        if _miss(r["营收CAGR"]):
            rs.append("营收CAGR缺失")
        elif r["营收CAGR"] <= c.REVENUE_CAGR_MIN:
            rs.append("营收未增长")
        if _miss(r["扣非CAGR"]):
            rs.append("扣非CAGR缺失")
        elif r["扣非CAGR"] <= c.PROFIT_CAGR_MIN:
            rs.append("扣非利润未增长")
        return rs

    def layer3(r):
        rs = []
        if _miss(r["自身分位"]):
            rs.append("自身估值无法计算")
        elif r["自身分位"] > c.SELF_PCTL_MAX:
            rs.append(f"自身估值分位>{c.SELF_PCTL_MAX:.0%}")
        if _miss(r["同行分位"]):
            rs.append("同行无法比较(行业样本不足)")
        elif r["同行分位"] > c.PEER_PCTL_MAX:
            rs.append(f"同行估值分位>{c.PEER_PCTL_MAX:.0%}")
        return rs

    df = df.copy()
    r1 = df.apply(layer1, axis=1)
    df["第1层_排除"] = r1.apply(lambda x: "通过" if not x else "|".join(x))
    df["_p1"] = r1.apply(lambda x: not x)
    r2 = df.apply(layer2, axis=1)
    df["第2层_健康成长"] = r2.apply(lambda x: "通过" if not x else "|".join(x))
    df["_p2"] = r2.apply(lambda x: not x)
    r3 = df.apply(layer3, axis=1)
    df["第3层_估值"] = r3.apply(lambda x: "通过" if not x else "|".join(x))
    df["_p3"] = r3.apply(lambda x: not x)

    df["通过层数"] = df[["_p1", "_p2", "_p3"]].sum(axis=1)
    df["候选"] = (df["_p1"] & df["_p2"] & df["_p3"]).map({True: "是", False: ""})
    return df


def run_screen(refresh: bool = False, limit: int = 0, verbose: bool = True,
               index_key: str = config.DEFAULT_INDEX) -> dict:
    cons = data.load_constituents(refresh=refresh, index_key=index_key)
    if limit:
        cons = cons[:limit]
    codes = [c["code"] for c in cons]
    if verbose:
        print(f"  成分 {len(codes)} 只，抓取财务/估值历史…")
    fin = data.fetch_financials(codes, refresh=refresh)
    val = data.fetch_valuations(codes, refresh=refresh)
    imap = data.load_industry_map()
    if verbose:
        print(f"  财务命中 {len(fin)}，估值命中 {len(val)}，行业标签可用 {sum(1 for c in codes if c in imap)}")
    df = _build_rows(cons, fin, val, imap)
    df = _evaluate(df)
    return {"frame": df, "n": len(df)}
