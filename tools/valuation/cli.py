"""CLI：tools/valuation 子命令 quality（盈利质量）。

后续阶段在 cli.main 里增挂 intrinsic / relative 子命令。
"""

import argparse
import json
import re
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.financial_crawler import utils as fc_utils
from tools.valuation import analysis, chart, config, data

_RE_A = re.compile(r"^\d{6}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A 股盈利质量 / 内在价值区间 / 行业相对估值（金额亿元）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("quality", help="盈利质量：净利 vs 经营现金流 vs 自由现金流",
                       description="把净利润还原成现金：逐年 归母/扣非净利、OCF、FCF(=OCF−资本开支)，"
                                   "附 净利≠OCF 的桥明细与跨年现金含量。")
    q.add_argument("stock_code", nargs="?", help="A 股 6 位代码")
    q.add_argument("--codes", help="批量模式，逗号分隔")
    q.add_argument("--years", type=int, default=config.QUALITY_YEARS,
                   help=f"取最近 N 个年报期（默认 {config.QUALITY_YEARS}）")
    q.add_argument("--output", type=Path, default=None, help="输出根目录（默认 data/reports）")
    q.set_defaults(func=_cmd_quality)

    p = sub.add_parser("intrinsic", help="估值区间：两阶段现金流折现给区间",
                       description="FCF0=经营现金流−资本开支，取最近正 FCF 年；显性期 Σ折现 + 永续终值，"
                                   "减净债务 = 股东价值 → 每股。给区间不给买卖结论，数值由假设主导。")
    p.add_argument("stock_code", help="A 股 6 位代码")
    p.add_argument("--years", type=int, default=config.INTRINSIC_YEARS,
                   help=f"显性期年数（默认 {config.INTRINSIC_YEARS}）")
    p.add_argument("--wacc", type=float, default=config.WACC,
                   help=f"折现率 WACC（默认 {config.WACC}）")
    p.add_argument("--growth", type=float, default=config.GROWTH,
                   help=f"显性期年增速 g（默认 {config.GROWTH}）")
    p.add_argument("--terminal-g", type=float, default=config.TERMINAL_G,
                   help=f"永续增速 gt（默认 {config.TERMINAL_G}，须 < wacc）")
    p.add_argument("--output", type=Path, default=None, help="输出根目录（默认 data/reports）")
    p.set_defaults(func=_cmd_intrinsic)

    r = sub.add_parser("relative", help="同行相对估值：描述性分位，不给结论",
                       description="把公司放回同行里比贵贱：同行 PE(静态)/PB 分布 + 目标所在分位。"
                                   "只描述、不评分、不推荐。")
    r.add_argument("stock_code", help="A 股 6 位代码")
    r.add_argument("--level", type=int, default=config.RELATIVE_LEVEL, choices=[1, 2, 3],
                   help=f"对比行业粒度：1 申万一级 / 2 二级 / 3 三级（默认 {config.RELATIVE_LEVEL}）")
    r.add_argument("--refresh-cache", action="store_true", help="强制重建行业映射缓存")
    r.add_argument("--output", type=Path, default=None, help="输出根目录（默认 data/reports）")
    r.set_defaults(func=_cmd_relative)

    return parser.parse_args()


def _pad(s, width: int) -> str:
    s = str(s)
    diff = sum(1 for c in s if "一" <= c <= "鿿")
    return s.ljust(width + diff)


def _fmt(v) -> str:
    return "-" if v is None else f"{v:.2f}"


def _company_name(code: str):
    """从已存在的行业映射缓存读公司简称；无缓存不联网，仅作图题美化。"""
    p = config.PROJECT_ROOT / "data" / "industry_map.json"
    try:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            info = d.get(code) or {}
            return info.get("name") or None
    except Exception:
        return None
    return None


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, int):
        return str(v)
    return f"{v:.2f}"


def _cmd_quality(args) -> None:
    codes = []
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    elif args.stock_code:
        codes = [args.stock_code.strip()]
    else:
        print("quality 需要股票代码，或使用 --codes 批量模式")
        sys.exit(1)

    success = 0
    for code in codes:
        if _process_quality(code, args.years, args.output):
            success += 1
    print(f"\n全部完成: {success}/{len(codes)} 成功")


def _process_quality(code: str, years: int, base_dir: Path) -> bool:
    code = code.strip()
    if not _RE_A.match(code):
        print(f"\n[错误] {code}: 仅支持 A 股 6 位代码")
        return False

    print(f"\n[获取] {code} 近 {min(years, 20)} 年年报科目（首跑需拉三张原始年报表，约 10~30 秒）")
    frame = data.annual_frame(code)
    if frame is None or "归母净利" not in frame.columns \
            or frame["归母净利"].notna().sum() == 0:
        print("  [失败] 财务数据获取失败（网络异常或该股无有效年报科目）")
        return False

    res = analysis.quality_frame(frame, years)
    name = _company_name(code)
    who = f"{code} {name}" if name else code

    print(f"\n{who}  盈利质量 · 单位：亿元 · 近 {res['n']} 个年报期（{res['years'][0]}~{res['years'][-1]}）")
    print(f"  FCF(经营近似) = 经营现金流净额 − 资本开支；扣非差 = 归母 − 扣非")
    print(f"  {'-'*78}")
    print("  " + "".join(_pad(c, 13) for c in config.QUALITY_COLS))
    print(f"  {'-'*78}")
    print("  （注：金额单位均为亿元；仅“现金含量”为倍数）")
    for row in res["rows"]:
        print("  " + "".join(_pad(_fmt(row[c]) if c != "年份" else row["年份"], 13)
                             for c in config.QUALITY_COLS))
    cc = res["cash_content"]
    if cc is None:
        print("\n  现金含量(ΣOCF/Σ归母净利 跨 N 年): 无意义"
              "（累计利润为负或利润/现金流数据不全）")
    else:
        print(f"\n  现金含量(ΣOCF/Σ归母净利 跨 {res['n']} 年): {cc:.2f}"
              f"  ← 每 1 元净利润对应 {cc:.2f} 元经营现金流")
    ocf_signs = {1 if r["OCF"] > 0 else -1 for r in res["rows"] if r["OCF"] is not None}
    if len(ocf_signs) > 1:
        print("  注：这几年的经营现金流有正有负（银行/券商等资金往来型，或应收存货大起大落时常见），"
              "现金含量参考意义有限，重点看波动成因而非单个数字")

    out_dir = fc_utils.resolve_output_path(code, base_dir) / "charts" / "valuation"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "quality.csv"
    base = config.QUALITY_COLS + config.QUALITY_BRIDGE_COLS
    header = ["年份" if c == "年份" else f"{c}(亿元)" for c in base]
    csv_lines = [",".join(header)]
    for dr in res["rows"]:
        csv_lines.append(",".join(_cell(dr.get(c)) for c in base))
    csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8-sig")

    png_path = out_dir / "quality.png"
    title = f"{who} 盈利质量 · 单位：亿元"
    if cc is not None:
        title += f"\n近 {res['n']} 年现金含量(ΣOCF/Σ归母) = {cc:.2f}"
    chart.plot_quality(res, png_path, title=title)

    print(f"\n  已输出:")
    print(f"    {csv_path}")
    print(f"    {png_path}")
    return True


def _pct(x) -> str:
    return f"{x*100:.0f}%"


def _cmd_intrinsic(args) -> None:
    if args.terminal_g >= args.wacc:
        print(f"[错误] 永续增速({args.terminal_g:.2f}) 须小于折现率({args.wacc:.2f})，否则终值无意义")
        sys.exit(1)
    _process_intrinsic(args.stock_code, args.years, args.wacc, args.growth,
                       args.terminal_g, args.output)


def _process_intrinsic(code: str, years: int, wacc: float, growth: float,
                       term_g: float, base_dir: Path) -> None:
    code = code.strip()
    if not _RE_A.match(code):
        print(f"\n[错误] {code}: 仅支持 A 股 6 位代码")
        return

    print(f"\n[获取] {code} 年报科目 + 腾讯实时行情…")
    frame = data.annual_frame(code)
    if frame is None or "OCF" not in frame.columns or "资本开支" not in frame.columns \
            or frame["OCF"].notna().sum() == 0:
        print("  [失败] 财务数据获取失败（无有效现金流科目）")
        return
    q = data.fetch_quotes([code]).get(code)
    if q is None:
        print("  [失败] 行情快照获取失败（腾讯接口不可达？），无法换算每股")
        return

    res = analysis.equity_per_share(frame, q, wacc, growth, term_g, years)
    if not res.get("ok"):
        print(f"  [退出] {res['reason']}")
        return

    who = f"{code} {res['name']}"
    print(f"\n{who}  两阶段折现 · 金额亿元，现价/每股=元")
    print(f"  FCF0 = {res['fcf0']:.2f} 亿（{res['base_year']}，最近正 FCF 年）"
          f" · 总股本 {res['shares']:.2f} 亿股 · 现价 {res['price']:.2f} 元")
    print(f"  假设：WACC {_pct(res['wacc'])} · 显性增速 {_pct(res['growth'])}（{res['years']} 年）"
          f" · 永续增速 {_pct(res['term_g'])}")
    print(f"  企业价值 EV(折现值)      = {res['ev']:>12.2f} 亿元")
    if res.get("net_debt") is not None:
        sign = "净现金" if res["net_debt"] < 0 else "净债务"
        print(f"  − {sign}(短借+长借−货币资金) = {res['net_debt']:>12.2f} 亿元")
    else:
        print(f"  − 净债务（缺报表科目，未扣）")
    print(f"  = 股东价值             = {res['equity']:>12.2f} 亿元")
    print(f"  ÷ 总股本 {res['shares']:.2f} 亿股")
    print(f"\n  每股内在价值（基准假设）≈ {res['per_share']:.0f} 元")
    band = (f"WACC {res['axis_w'][0]*100:.0f}%~{res['axis_w'][-1]*100:.0f}% "
            f"× 永续 {res['axis_tg'][0]*100:.0f}%~{res['axis_tg'][-1]*100:.0f}%")
    print(f"  网格区间({band}): "
          f"{res['grid_lo']:.0f} ~ {res['grid_hi']:.0f} 元")
    if res.get("bvps") is not None:
        print(f"  每股净资产(下限参考)      ≈ {res['bvps']:.0f} 元")
    print(f"\n  ※ 内在价值≠目标价：仅教学区间，数值完全由假设主导；现价高于/低于该区间都不构成买卖依据")
    for n in res["notes"]:
        print(f"  注：{n}")

    out_dir = fc_utils.resolve_output_path(code, base_dir) / "charts" / "valuation"
    out_dir.mkdir(parents=True, exist_ok=True)

    # intrinsic.csv：假设表 + 结果（纯 key-value）
    rows = [
        ("项目", "数值"),
        ("代码", code), ("简称", res["name"]),
        ("FCF0基数年", str(res["base_year"])), ("FCF0(亿元)", f"{res['fcf0']:.2f}"),
        ("WACC", _pct(res["wacc"])), ("显性增速g", _pct(res["growth"])),
        ("永续增速gt", _pct(res["term_g"])), ("显性期年数", str(res["years"])),
        ("总股本(亿股)", f"{res['shares']:.4f}"), ("现价(元)", f"{res['price']:.2f}"),
        ("净债务(亿元,短借+长借−货币)", _fmt(res.get("net_debt"))),
        ("企业价值EV(亿元)", f"{res['ev']:.2f}"),
        ("股东价值(亿元)", f"{res['equity']:.2f}"),
        ("每股价值-基准假设(元)", f"{res['per_share']:.2f}"),
        ("每股价值-网格区间下限(元)", f"{res['grid_lo']:.2f}"),
        ("每股价值-网格区间上限(元)", f"{res['grid_hi']:.2f}"),
        ("每股净资产-下限参考(元)", _fmt(res.get("bvps"))),
    ]
    lines = [",".join(r) for r in rows]
    for n in res["notes"]:
        lines.append("口径备注," + n.replace(",", "；"))
    csv_path = out_dir / "intrinsic.csv"
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    # sensitivity.csv：wacc(行) × 永续增速(列) 每股价值网格
    srows = [["wacc\\gt"] + [f"{t:.2f}" for t in res["axis_tg"]]]
    for i, w in enumerate(res["axis_w"]):
        srows.append([f"{w:.2f}"] + ["" if c is None else f"{c:.2f}" for c in res["grid"][i]])
    sens_path = out_dir / "sensitivity.csv"
    sens_path.write_text("\n".join(",".join(map(str, r)) for r in srows) + "\n",
                         encoding="utf-8-sig")

    png_path = out_dir / "intrinsic.png"
    title = (f"{res['name']}({code}) 内在价值对折现率敏感 · 每股(元)\n"
             f"FCF0={res['fcf0']:.0f}亿({res['base_year']}) · 永续 {_pct(res['term_g'])} · "
             f"现价 {res['price']:.0f} 元 · 区间 {res['grid_lo']:.0f}~{res['grid_hi']:.0f} 元")
    chart.plot_intrinsic(res, png_path, title=title)

    print(f"\n  已输出:")
    print(f"    {csv_path}")
    print(f"    {sens_path}")
    print(f"    {png_path}")


def _cmd_relative(args) -> None:
    code = (args.stock_code or "").strip()
    if not _RE_A.match(code):
        print(f"[错误] {code}: 仅支持 A 股 6 位代码")
        sys.exit(1)
    ok = _process_relative(code, args.level, args.output, args.refresh_cache)
    sys.exit(0 if ok else 1)


def _process_relative(code: str, level: int, base_dir: Path, refresh_cache: bool) -> bool:
    from tools.industry_profit import config as ip_cfg
    from tools.industry_profit import data as ip_data

    print(f"\n[获取] {code} 行业映射（首次构建需数分钟，之后走缓存）+ 同行实时行情…")
    try:
        mapping = ip_data.build_industry_map(refresh=refresh_cache)
    except RuntimeError as e:
        print(f"  [错误] {e}")
        return False
    info = mapping.get(code)
    if not info:
        print(f"  [错误] {code}: 未在行业映射中找到，请用 --refresh-cache 重建缓存")
        return False

    granularity = ip_data.mapping_granularity(mapping)
    actual = level if granularity >= level else 1
    industry = info[ip_cfg.LEVEL_COL[actual]]
    degrade = actual < level
    members = ip_data.get_industry_members(mapping, info, actual)

    print(f"{'='*60}")
    print(f"  {code} {info['name']} |  {info['sw1']} → {info['sw2']} → {info['sw3']}")
    print(f"  对比行业（申万{actual}级）: {industry}，成分股 {len(members)} 家")
    if degrade:
        print(f"  注：数据源仅支持申万一级，已将申万{level}级自动降为 1 级")
    print(f"{'='*60}")

    quotes = data.fetch_quotes(members)
    rows = []
    for c in members:
        q = quotes.get(c)
        issues = []
        pe = pb = mcap = None
        if q is None:
            issues.append("行情缺失")
        else:
            pe, pb = q.get("pe_static"), q.get("pb")
            mcap = q.get("market_cap_亿")
            if pe is None or pe <= 0:
                issues.append("亏损(PE非正)")
            if pb is None or pb <= 0:
                issues.append("负净资产(PB非正)")
        rows.append({"code": c, "name": q["name"] if q else mapping[c].get("name") or c,
                     "pe": pe, "pb": pb, "mcap": mcap, "quote": q is not None,
                     "is_target": c == code, "issues": issues})

    pe_vals = [r["pe"] for r in rows if r["pe"] is not None and r["pe"] > 0]
    pb_vals = [r["pb"] for r in rows if r["pb"] is not None and r["pb"] > 0]
    tgt = next(r for r in rows if r["is_target"])
    t_pe = tgt["pe"] if tgt["pe"] is not None and tgt["pe"] > 0 else None
    t_pb = tgt["pb"] if tgt["pb"] is not None and tgt["pb"] > 0 else None
    d_pe, d_pb = analysis.describe(pe_vals), analysis.describe(pb_vals)
    r_pe, r_pb = analysis.percentile_rank(pe_vals, t_pe), analysis.percentile_rank(pb_vals, t_pb)

    print(f"\n  PE 为静态口径（总市值 ÷ 最新年报归母净利），同行可比；负 PE/PB（亏损/负净资产）剔除出分布单独计数")
    print(f"\n  {_pad('指标', 8)}{_pad('目标', 10)}{_pad('同行中位', 10)}"
          f"{_pad('P25', 9)}{_pad('P75', 9)}{_pad('目标分位(低=便宜)', 18)}")
    print(f"  {'-'*64}")
    for label, t, d, rank in (("PE(静态)", t_pe, d_pe, r_pe), ("PB", t_pb, d_pb, r_pb)):
        rank_s = "-" if rank is None else f"{rank:.0f}%"
        print(f"  {_pad(label, 8)}{_pad(_fmt(t), 10)}{_pad(_fmt(d['median'] if d else None), 10)}"
              f"{_pad(_fmt(d['p25'] if d else None), 9)}{_pad(_fmt(d['p75'] if d else None), 9)}"
              f"{_pad(rank_s, 18)}")
    n_miss = sum(1 for r in rows if not r["quote"])
    n_pe_bad = sum(1 for r in rows if r["quote"] and (r["pe"] is None or r["pe"] <= 0))
    n_pb_bad = sum(1 for r in rows if r["quote"] and (r["pb"] is None or r["pb"] <= 0))
    print(f"\n  样本：正 PE {len(pe_vals)} 家 / 正 PB {len(pb_vals)} 家"
          f"（剔除：行情缺失 {n_miss}，PE 非正(亏损) {n_pe_bad}，PB 非正(负净资产) {n_pb_bad}）")
    print(f"\n  ※ 仅描述目标在同行分布里的位置，无买入/卖出/评级结论")

    out_dir = fc_utils.resolve_output_path(code, base_dir) / "charts" / "valuation"
    out_dir.mkdir(parents=True, exist_ok=True)

    def ccell(v, nd=2):
        return "" if v is None else f"{v:.{nd}f}"
    header = ["代码", "简称", "PE(静态)", "PB", "总市值(亿元)", "标记", "备注"]
    lines = [",".join(header)]
    for r in sorted(rows, key=lambda x: x["code"]):
        lines.append(",".join([
            r["code"], r["name"] or "", ccell(r["pe"]), ccell(r["pb"]), ccell(r["mcap"], 1),
            "目标" if r["is_target"] else "", "；".join(r["issues"])]))
    csv_path = out_dir / "relative.csv"
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    def pane(label, vals, t, d, rank):
        return {"label": label, "vals": vals, "target": t,
                "median": (d or {}).get("median"), "p25": (d or {}).get("p25"),
                "p75": (d or {}).get("p75"), "rank": rank}
    panes = [pane("PE(静态)", pe_vals, t_pe, d_pe, r_pe),
             pane("PB", pb_vals, t_pb, d_pb, r_pb)]
    png_path = out_dir / "relative.png"
    title = (f"{info['name']}（{code}） vs {industry}（申万{actual}级）· {len(members)} 家样本\n"
             f"PE 静态=总市值÷最新年报归母净利 · 描述性分位，无推荐")
    if degrade:
        title = title.replace("（申万%d级）" % actual, "（申万%d级，已降级）" % actual)
    chart.plot_relative(panes, png_path, title=title)

    print(f"\n  已输出:")
    print(f"    {csv_path}")
    print(f"    {png_path}")
    return True


def main() -> None:
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
