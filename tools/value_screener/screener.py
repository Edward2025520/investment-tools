"""沪深300价值投资筛选器 — 按李录/巴菲特框架评分排名。"""

import sys
import time
import warnings
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import pandas as pd

_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

warnings.filterwarnings("ignore")

# ── 硬性门槛 ──
MAX_PRICE = 20.0
MIN_ROE = 5.0
MAX_DEBT_RATIO = 70.0

# ── 评分权重（盈利能力:财务安全:估值合理 = 40:35:25）──
W_PROFIT = 0.40
W_SAFETY = 0.35
W_VALUE = 0.25


def get_hs300_constituents():
    """获取沪深300成分股列表。"""
    df = ak.index_stock_cons_weight_csindex("000300")
    return df[["成分券代码", "成分券名称", "权重"]].rename(
        columns={"成分券代码": "code", "成分券名称": "name", "权重": "weight"}
    )


def get_hs300_prices(hs300_codes):
    """获取沪深300成分股最新收盘价，返回 {code: price}。
    优先用新浪行情接口，失败则退回到逐只查询。"""
    # 尝试一：批量获取（新浪行情接口，一次返回全部）
    for attempt in range(3):
        try:
            spot = ak.stock_zh_a_spot()
            prices = {}
            for _, row in spot.iterrows():
                raw = row["代码"]  # "sh600519" / "sz000001"
                try:
                    price = float(row["最新价"])
                except (ValueError, TypeError):
                    continue
                # 去掉 sh/sz 前缀
                code = raw[2:] if raw.startswith(("sh", "sz")) else raw
                prices[code] = price
            found = [c for c in hs300_codes if c in prices]
            if len(found) >= len(hs300_codes) * 0.9:
                return prices
        except Exception:
            pass

    # 尝试二：逐只查询（新浪日线，并行）
    print("    [价格] 改用逐只查询...")

    def fetch_price(code):
        prefix = "sh" if code.startswith("6") else "sz"
        symbol = f"{prefix}{code}"
        try:
            df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
            if not df.empty:
                return code, float(df["close"].iloc[-1])
        except Exception:
            pass
        return code, None

    prices = {}
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(fetch_price, c): c for c in hs300_codes}
        done = 0
        for future in as_completed(futures):
            code, price = future.result()
            if price:
                prices[code] = price
            done += 1
            if done % 50 == 0 or done == len(hs300_codes):
                print(f"    价格进度: {done}/{len(hs300_codes)}")
    return prices


def fetch_financials(code):
    """获取单只股票的最新年度财务指标，返回 dict。"""
    try:
        df = ak.stock_financial_abstract_ths(symbol=code)
    except Exception:
        return None

    if df.empty:
        return None

    # 找最新年报（12月31日）
    annual = df[df["报告期"].str.contains(r"12-31", na=False)]
    if annual.empty:
        return None

    latest = annual.iloc[-1]
    result = {}

    # 净利润
    def parse_num(val):
        if val is None or val in ("", "--", "False", "None"):
            return None
        v = str(val).strip().replace(",", "")
        if v.endswith("%"):
            try:
                return float(v[:-1])
            except ValueError:
                return None
        if "亿" in v:
            try:
                return float(v.replace("亿", ""))
            except ValueError:
                return None
        if "万" in v:
            try:
                return round(float(v.replace("万", "")) / 1e4, 4)
            except ValueError:
                return None
        try:
            return float(v)
        except ValueError:
            return None

    result["净利润"] = parse_num(latest.get("净利润"))
    result["扣非净利润"] = parse_num(latest.get("扣非净利润"))
    result["营收"] = parse_num(latest.get("营业总收入"))
    result["每股收益"] = parse_num(latest.get("基本每股收益"))
    result["每股净资产"] = parse_num(latest.get("每股净资产"))
    result["每股经营现金流"] = parse_num(latest.get("每股经营现金流"))
    result["销售毛利率"] = parse_num(latest.get("销售毛利率"))
    result["销售净利率"] = parse_num(latest.get("销售净利率"))
    result["净资产收益率"] = parse_num(latest.get("净资产收益率"))
    result["资产负债率"] = parse_num(latest.get("资产负债率"))
    result["流动比率"] = parse_num(latest.get("流动比率"))
    result["营收增长率"] = parse_num(latest.get("营业总收入同比增长率"))
    result["净利润增长率"] = parse_num(latest.get("净利润同比增长率"))

    return result


def calc_pe_pb(fin, price):
    """计算 PE 和 PB。"""
    eps = fin.get("每股收益")
    bvps = fin.get("每股净资产")
    pe = round(price / eps, 2) if (eps and eps > 0 and price) else None
    pb = round(price / bvps, 2) if (bvps and bvps > 0 and price) else None
    return pe, pb


def score_profit(fin):
    """盈利能力评分（满分100）。"""
    score = 0.0
    items = 0

    roe = fin.get("净资产收益率")
    if roe is not None:
        # ROE >=20% 给100, <5% 给0
        s = min(max((roe - 5) / 15 * 100, 0), 100)
        score += s * 0.40
        items += 0.40

    gm = fin.get("销售毛利率")
    if gm is not None:
        s = min(max((gm - 10) / 30 * 100, 0), 100)
        score += s * 0.25
        items += 0.25

    nm = fin.get("销售净利率")
    if nm is not None:
        s = min(max((nm - 3) / 15 * 100, 0), 100)
        score += s * 0.20
        items += 0.20

    cf = fin.get("每股经营现金流")
    eps = fin.get("每股收益")
    if cf is not None and eps is not None and eps > 0:
        ratio = cf / eps
        s = min(ratio * 50, 100)
        score += s * 0.15
        items += 0.15

    return score / items if items > 0 else 0


def score_safety(fin):
    """财务安全评分（满分100）。"""
    score = 0.0
    items = 0

    dr = fin.get("资产负债率")
    if dr is not None:
        # 资产负债率 <=30% 给100, >=70% 给0
        s = min(max((70 - dr) / 40 * 100, 0), 100)
        score += s * 0.50
        items += 0.50

    cr = fin.get("流动比率")
    if cr is not None:
        # 1.5-3倍最佳，过高过低都扣分
        if 1.5 <= cr <= 3.0:
            s = 100
        elif cr < 0.8:
            s = 0
        elif cr < 1.5:
            s = (cr - 0.8) / 0.7 * 100
        else:
            s = max(100 - (cr - 3) * 30, 0)
        score += s * 0.30
        items += 0.30

    # 营收增长（间接反映经营健康）
    rev_g = fin.get("营收增长率")
    if rev_g is not None:
        s = min(max(rev_g * 3, 0), 100)
        score += s * 0.20
        items += 0.20

    return score / items if items > 0 else 0


def score_valuation(pe, pb, fin, price):
    """估值合理评分（满分100）。"""
    score = 0.0
    items = 0

    if pe is not None and pe > 0:
        roe = fin.get("净资产收益率", 0) or 0
        # 高ROE可容忍高PE：合理PE = ROE * 2
        fair_pe = max(roe * 2, 10)
        if pe <= fair_pe:
            s = 100
        elif pe <= fair_pe * 1.5:
            s = 50
        elif pe <= fair_pe * 2:
            s = 25
        else:
            s = 0
        score += s * 0.50
        items += 0.50

    if pb is not None and pb > 0:
        roe = fin.get("净资产收益率", 0) or 0
        # PB合理值 = ROE / 5 * 1.5
        fair_pb = max(roe / 5 * 1.5, 1)
        if pb <= fair_pb:
            s = 100
        elif pb <= fair_pb * 1.5:
            s = 60
        elif pb <= fair_pb * 2:
            s = 30
        else:
            s = 10
        score += s * 0.30
        items += 0.30

    # PE倒数 vs 国债收益率（2.5%）
    if pe is not None and pe > 0:
        yield_pct = 1 / pe * 100
        if yield_pct >= 4:
            s = 100
        elif yield_pct >= 2.5:
            s = 60
        elif yield_pct >= 1.5:
            s = 30
        else:
            s = 10
        score += s * 0.20
        items += 0.20

    return score / items if items > 0 else 0


def main():
    print("=" * 60)
    print("  沪深300 价值投资筛选器")
    print("  框架：盈利能力>财务安全>估值合理")
    print("=" * 60)

    # Step 1: 获取沪深300成分股
    print("\n[1/4] 获取沪深300成分股...")
    hs300 = get_hs300_constituents()
    print(f"  沪深300共 {len(hs300)} 只股票")

    # Step 2: 获取股价，过滤
    print("\n[2/4] 获取最新股价...")
    hs300_codes = hs300["code"].tolist()
    all_prices = get_hs300_prices(hs300_codes)

    candidates = []
    for code in hs300_codes:
        price = all_prices.get(code)
        if price is None:
            continue
        if 0 < price <= MAX_PRICE:
            row = hs300[hs300["code"] == code].iloc[0]
            candidates.append((code, row["name"], price, row["weight"]))

    candidates.sort(key=lambda x: x[2])
    print(f"  沪深300中股价<=20元的股票: {len(candidates)} 只")

    # Step 3: 并行获取财务数据
    print("\n[3/4] 批量获取财务数据（并行请求，耗时较长）...")

    def fetch_one(code_name):
        code, name, price, weight = code_name
        fin = fetch_financials(code)
        if fin is None:
            return None
        return {
            "code": code,
            "name": name,
            "price": price,
            "weight": weight,
            "fin": fin,
        }

    batch = []
    codes_list = [(c, n, p, w) for c, n, p, w in candidates]
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_one, item): item for item in codes_list}
        done_count = 0
        for future in as_completed(futures):
            item = futures[future]
            done_count += 1
            try:
                result = future.result(timeout=60)
                if result:
                    batch.append(result)
            except Exception:
                pass
            if done_count % 30 == 0 or done_count == len(codes_list):
                print(f"    进度: {done_count}/{len(codes_list)}")

    # Step 4: 应用硬性门槛
    print(f"\n[4/4] 应用硬性门槛...")
    passed = []
    for item in batch:
        fin = item["fin"]
        roe = fin.get("净资产收益率")
        dr = fin.get("资产负债率")
        np = fin.get("净利润")

        if roe is None or roe < MIN_ROE:
            continue
        if dr is not None and dr > MAX_DEBT_RATIO:
            continue
        if np is None or np <= 0:
            continue
        if fin.get("每股收益") is None or fin["每股收益"] <= 0:
            continue

        pe, pb = calc_pe_pb(fin, item["price"])
        item["PE"] = pe
        item["PB"] = pb
        item["fin"]["PE"] = pe
        item["fin"]["PB"] = pb
        passed.append(item)

    print(f"  通过硬性门槛: {len(passed)} 只")

    if not passed:
        print("\n无合格股票")
        return

    # Step 5: 评分排名
    scored = []
    for item in passed:
        fin = item["fin"]
        s_profit = score_profit(fin)
        s_safety = score_safety(fin)
        s_value = score_valuation(item["PE"], item["PB"], fin, item["price"])
        total = s_profit * W_PROFIT + s_safety * W_SAFETY + s_value * W_VALUE
        scored.append({
            "code": item["code"],
            "name": item["name"],
            "price": item["price"],
            "PE": item["PE"],
            "PB": item["PB"],
            "ROE": fin.get("净资产收益率"),
            "毛利率": fin.get("销售毛利率"),
            "净利率": fin.get("销售净利率"),
            "资产负债率": fin.get("资产负债率"),
            "流动比率": fin.get("流动比率"),
            "净利润": fin.get("净利润"),
            "营收增长率": fin.get("营收增长率"),
            "score_profit": round(s_profit, 1),
            "score_safety": round(s_safety, 1),
            "score_value": round(s_value, 1),
            "total_score": round(total, 2),
        })

    scored.sort(key=lambda x: x["total_score"], reverse=True)

    # Step 6: 输出Top 10
    top10 = scored[:10]
    print("\n" + "=" * 60)
    print("  TOP 10 价值投资候选股票")
    print("=" * 60)
    print(f"{'排名':<4} {'代码':<8} {'名称':<10} {'股价':<6} {'ROE':<6} {'毛利率':<6} {'PE':<6} {'PB':<6} {'负债率':<6} {'总分':<6}")
    print("-" * 60)
    for i, item in enumerate(top10, 1):
        print(f"{i:<4} {item['code']:<8} {item['name']:<10} "
              f"{item['price']:<6.2f} {item['ROE'] or 0:<6.2f} "
              f"{item['毛利率'] or 0:<6.2f} {item['PE'] or 0:<6.2f} "
              f"{item['PB'] or 0:<6.2f} {item['资产负债率'] or 0:<6.2f} "
              f"{item['total_score']:<6.2f}")

    print("\n详细评分拆解：")
    print(f"{'排名':<4} {'名称':<10} {'盈利分':<8} {'安全分':<8} {'估值分':<8}")
    print("-" * 35)
    for i, item in enumerate(top10, 1):
        print(f"{i:<4} {item['name']:<10} "
              f"{item['score_profit']:<8.1f} {item['score_safety']:<8.1f} "
              f"{item['score_value']:<8.1f}")

    # 保存完整结果
    out_dir = _project_root / "data" / "screening"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "hs300_value_screen.csv"
    all_df = pd.DataFrame(scored)
    all_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n完整排名已保存 → {out_path}")


if __name__ == "__main__":
    main()
