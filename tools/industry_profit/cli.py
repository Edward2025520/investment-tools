"""CLI 入口：单只 A 股 vs 申万行业平均盈利水平对比。"""

import argparse
import re
import sys
from pathlib import Path

# 项目根路径
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.financial_crawler import utils as fc_utils
from tools.industry_profit import analysis, chart, config, data

_RE_A = re.compile(r"^\d{6}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="单只 A 股 vs 申万行业平均盈利水平对比（净利率/毛利率/ROE/ROA）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools/industry_profit/cli.py 600519\n"
            "  python tools/industry_profit/cli.py 600519 --years 5 --level 2\n"
            "  python tools/industry_profit/cli.py --codes 600519,000858\n"
            "  python tools/industry_profit/cli.py 600519 --refresh-cache\n"
        ),
    )
    parser.add_argument("stock_code", nargs="?", help="A 股 6 位代码")
    parser.add_argument("--codes", help="批量模式，逗号分隔")
    parser.add_argument(
        "--years", type=int, default=config.DEFAULT_YEARS,
        help=f"取最近 N 年年报均值（默认 {config.DEFAULT_YEARS}）",
    )
    parser.add_argument(
        "--level", type=int, default=config.DEFAULT_LEVEL, choices=[1, 2, 3],
        help=f"对比行业粒度：1 申万一级 / 2 二级 / 3 三级（默认 {config.DEFAULT_LEVEL}）",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="输出根目录（默认 data/reports）",
    )
    parser.add_argument("--refresh-cache", action="store_true", help="强制重建行业映射缓存")
    parser.add_argument("--refresh-metrics", action="store_true",
                        help="同行财务指标强制实时重抓（默认走 90 天缓存）")
    parser.add_argument("--verbose", action="store_true", help="显示每只成分股指标")
    return parser.parse_args()


def _pad(s, width: int) -> str:
    s = str(s)
    diff = sum(1 for c in s if "一" <= c <= "鿿")
    return s.ljust(width + diff)


def _fmt(v):
    return "-" if v is None else f"{v:.2f}"


def process(code: str, years: int, level: int, base_dir: Path, mapping: dict,
            verbose: bool = False, refresh_metrics: bool = False) -> bool:
    code = code.strip()
    if not _RE_A.match(code):
        print(f"\n[错误] {code}: 仅支持 A 股 6 位代码")
        return False
    info = mapping.get(code)
    if not info:
        print(f"\n[错误] {code}: 未在行业映射中找到该股票，请用 --refresh-cache 重建缓存")
        return False

    # 数据源只到申万一级时（降级源 sw1==sw2==sw3），请求更细粒度自动降为 1 级并全程标注
    granularity = data.mapping_granularity(mapping)
    actual_level = level if granularity >= level else 1
    level_label = config.LEVEL_COL[actual_level]
    degrade_note = ""
    if actual_level < level:
        degrade_note = f"数据源仅支持申万一级，已将申万{level}级自动降为 1 级"

    members = data.get_industry_members(mapping, info, actual_level)
    print(f"\n{'='*60}")
    print(f"  {code} {info['name']}  |  {info['sw1']} → {info['sw2']} → {info['sw3']}")
    print(f"  对比行业（申万{actual_level}级）: {info[level_label]}，成分股 {len(members)} 家")
    if degrade_note:
        print(f"  注：{degrade_note}，以下对比以申万一级为准")
    print(f"{'='*60}")

    # 主角每次实时抓最新且写缓存；同行走 90 天缓存（--refresh-metrics 强制全量重抓）
    peer_codes = [c for c in members if c != code]
    metrics = data.fetch_metrics_batch(peer_codes, years, refresh=refresh_metrics)
    target = data.resolve_stock_metrics(code, years, force_fresh=True)
    if target:
        metrics[code] = target
    if code not in metrics:
        print(f"  [失败] 目标公司财务数据获取失败")
        return False
    print(f"  财务数据获取成功: {len(metrics)}/{len(members)} 家"
          + ("（同行已实时重抓）" if refresh_metrics else ""))

    stats = analysis.compute_stats(metrics, code, mapping)

    if verbose:
        name_w = max(len(mapping[c]["name"]) for c in metrics)
        print(f"\n  {'代码':<8}{'简称':<{name_w}}{'净利率':>8}{'毛利率':>8}{'ROE':>8}{'ROA':>8}")
        for c in metrics:
            print(f"  {c:<8}{mapping[c]['name']:<{name_w}}"
                  f"{_fmt(metrics[c]['net_margin']):>8}{_fmt(metrics[c]['gross_margin']):>8}"
                  f"{_fmt(metrics[c]['roe']):>8}{_fmt(metrics[c]['roa']):>8}")

    print(f"\n  {_pad('指标', 8)}{_pad('公司值', 12)}{_pad('中位数', 12)}"
          f"{_pad('截尾均值', 12)}{_pad('简单平均', 12)}{_pad('市值加权', 12)}"
          f"{_pad('排位', 14)}{_pad('百分位', 10)}")
    print(f"  {'-'*82}")
    for m in config.METRICS:
        s = stats[m["key"]]
        rank = "-" if s["rank"] is None else f"第{s['rank']}/{s['n']}名"
        pct = "-" if s["pct"] is None else f"{s['pct']:.0f}%"
        print(f"  {_pad(m['label'], 8)}{_pad(_fmt(s['target']), 12)}"
              f"{_pad(_fmt(s['median']), 12)}{_pad(_fmt(s['trimmed']), 12)}"
              f"{_pad(_fmt(s['simple']), 12)}{_pad(_fmt(s['weighted']), 12)}"
              f"{_pad(rank, 14)}{_pad(pct, 10)}")
    print(f"\n  注：中位数＝典型公司水平，对亏损与极值稳健，建议主看；"
          f"简单平均在行业亏损面大时会被拖成负数")

    dp = analysis.dupont_compare(metrics, code)
    if dp and dp["company"]:
        print(f"\n  杜邦分解：ROE = 净利率 × 总资产周转率 × 权益乘数")
        print(f"  {'-'*64}")
        print(f"  {_pad('', 10)}{_pad('净利率', 12)}{_pad('周转率', 12)}"
              f"{_pad('权益乘数', 12)}{_pad('ROE', 12)}")
        dp_rows = [("公司", dp["company"])]
        if dp["industry"]:
            dp_rows.append(("同行中位", dp["industry"]))
        for label, d in dp_rows:
            roe_check = d["net_margin"] * d["asset_turnover"] * d["equity_multiplier"]
            turn = f"{d['asset_turnover']:.4f}"  # 4 位：银行等低周转行业，位数少了验算会失准
            print(f"  {_pad(label, 10)}{_pad(_fmt(d['net_margin']), 12)}"
                  f"{_pad(turn, 12)}"
                  f"{_pad(_fmt(d['equity_multiplier']), 12)}{_pad(_fmt(roe_check), 12)}")
        print(f"  周转率 = ROA ÷ 净利率，权益乘数 = ROE ÷ ROA，三者相乘恒等于 ROE")

    # 输出到 charts/industry_compare/ 子目录，与 financial_crawler 隔离
    out_dir = fc_utils.resolve_output_path(code, base_dir) / "charts" / "industry_compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "industry_compare.csv"
    header = ["指标", "公司值", "中位数", "截尾均值", "简单平均", "市值加权",
              "行业排位", "百分位"]
    if degrade_note:
        header.append("口径备注")
    rows = [header]
    for i, m in enumerate(config.METRICS):
        s = stats[m["key"]]
        row = [
            m["label"],
            "" if s["target"] is None else f"{s['target']:.2f}",
            "" if s["median"] is None else f"{s['median']:.2f}",
            "" if s["trimmed"] is None else f"{s['trimmed']:.2f}",
            "" if s["simple"] is None else f"{s['simple']:.2f}",
            "" if s["weighted"] is None else f"{s['weighted']:.2f}",
            "" if s["rank"] is None else f"第{s['rank']}/{s['n']}名",
            "" if s["pct"] is None else f"{s['pct']:.1f}%",
        ]
        if degrade_note:
            row.append(degrade_note if i == 0 else "")
        rows.append(row)
    csv_path.write_text("\n".join(",".join(r) for r in rows) + "\n", encoding="utf-8-sig")

    png_path = out_dir / "industry_compare.png"
    title = f"{info['name']}（{code}） vs {info[level_label]}行业，{len(members)} 家样本"
    if degrade_note:
        title += f"\n（注：{degrade_note}）"
    chart.plot_compare(stats, png_path, title=title)

    print(f"\n  已输出:")
    print(f"    {csv_path}")
    print(f"    {png_path}")
    return True


def main() -> None:
    args = parse_args()

    codes = []
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    elif args.stock_code:
        codes = [args.stock_code.strip()]
    else:
        print("请指定股票代码，或使用 --codes 批量模式")
        sys.exit(1)

    try:
        mapping = data.build_industry_map(refresh=args.refresh_cache)
    except RuntimeError as e:
        print(f"\n[错误] {e}")
        sys.exit(1)

    success = 0
    for code in codes:
        if process(code, args.years, args.level, args.output, mapping,
                   args.verbose, args.refresh_metrics):
            success += 1

    print(f"\n全部完成: {success}/{len(codes)} 成功")


if __name__ == "__main__":
    main()
