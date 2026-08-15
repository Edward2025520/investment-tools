"""CLI 入口：皮奥特洛斯基 F-Score 自选股财务质量筛选器。"""

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

# 项目根路径
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.f_screener import data, f_score, financial

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "screening"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="皮奥特洛斯基 F-Score 自选股财务质量筛选器（A股）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools/f_screener/cli.py --codes 600519,000001,601169\n"
            "  python tools/f_screener/cli.py --file watchlist.txt\n"
            "  python tools/f_screener/cli.py --codes 600519 --min-score 6\n"
        ),
    )
    parser.add_argument("--codes", help="逗号分隔的股票代码：600519,000001")
    parser.add_argument("--file", type=Path, help="股票清单文件（逐行，支持 # 注释）")
    parser.add_argument(
        "--output", type=Path, default=None,
        help="输出 CSV 目录（默认 data/screening/）",
    )
    parser.add_argument("--years", type=int, default=8, help="取最近 N 年年报（默认 8）")
    parser.add_argument(
        "--include-financial", action="store_true",
        help="包含金融股（默认排除）",
    )
    parser.add_argument("--min-score", type=int, default=0, help="只输出总分 ≥ N 的股票")
    parser.add_argument("--verbose", action="store_true", help="显示每只股票详细信息")
    return parser.parse_args()


def read_codes_from_file(path: Path) -> list[str]:
    """读取清单文件，逐行，跳过空行和 # 注释。"""
    codes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            codes.append(line)
    return codes


def _row_val(row, field: str):
    """取某行字段值，缺失返回 None。"""
    if row is None or field not in row.index:
        return None
    v = row[field]
    return None if pd.isna(v) else round(float(v), 2)


def _roa(row):
    """ROA = 净利润/总资产×100。"""
    net, assets = _row_val(row, "净利润"), _row_val(row, "总资产")
    if net is None or assets in (None, 0):
        return None
    return round(net / assets * 100, 2)


def score_stock(code: str, years: int) -> dict:
    """对单只股票评分，返回结果字典。"""
    metrics = data.build_metrics(code, years)
    if metrics.empty:
        return {"code": code, "name": "", "industry": "", "years": 0,
                "total": None, "applied": 0, "items": [], "error": "无数据"}

    items, applied = f_score.score_9(metrics)
    total = sum(1 for v in items if v is True)
    # 公司简称（稳定市场映射），行业暂缺
    name = financial._fetch_name(code)

    # 今年/去年关键指标对比
    now_row = metrics.iloc[0]
    prev_row = metrics.iloc[1] if len(metrics) > 1 else None
    cmp = {
        "营收": (_row_val(now_row, "营业收入"), _row_val(prev_row, "营业收入")),
        "净利润": (_row_val(now_row, "净利润"), _row_val(prev_row, "净利润")),
        "毛利率": (_row_val(now_row, "销售毛利率"), _row_val(prev_row, "销售毛利率")),
        "ROA": (_roa(now_row), _roa(prev_row)),
        "现金流": (_row_val(now_row, "经营现金流"), _row_val(prev_row, "经营现金流")),
    }

    return {"code": code, "name": name, "industry": "",
            "years": len(metrics), "total": total, "applied": applied, "items": items,
            "cmp": cmp}


# 今年/去年对比列：字段名 → (表头, 单位)
CMP_COLUMNS = [
    ("营收", "营收", "亿"),
    ("净利润", "净利", "亿"),
    ("毛利率", "毛利率", "%"),
    ("ROA", "ROA", "%"),
    ("现金流", "现金流", "亿"),
]


def _fmt_pair(pair, unit: str) -> str:
    """格式化为 今/昨，缺失显示 -。"""
    now, prev = pair
    n = "-" if now is None else f"{now:g}"
    p = "-" if prev is None else f"{prev:g}"
    return f"{n}/{p}"


def print_table(rows: list[dict]) -> None:
    """终端打印对齐表格（含今年/去年对比列）。"""
    if not rows:
        return
    width_code = max(len(r["code"]) for r in rows) + 2
    width_name = max(len(r["name"]) for r in rows) + 2
    # 表头
    header = (f"{'代码'.ljust(width_code)}{'简称'.ljust(width_name)}{'总分':<6}"
              f"{'适用项':<8}{'评分':<6}")
    for _, label, unit in CMP_COLUMNS:
        header += f"{f'{label}(今/昨{unit})':<16}"
    # 值对齐宽度
    widths = [max(len(_fmt_pair(r["cmp"][k], u)) for r in rows) + 2
              for k, _, u in CMP_COLUMNS]

    print(f"\n{'='*110}")
    print(f"  F-Score 筛选结果（{len(rows)} 只）")
    print(f"{'='*110}")
    print(header)
    for r in rows:
        ratio = f"{sum(1 for v in r['items'] if v is True) / r['applied']:.2f}" if r["applied"] else "-"
        line = (f"{r['code'].ljust(width_code)}{r['name'].ljust(width_name)}"
                f"{str(r['total']).ljust(6)}{str(r['applied']).ljust(8)}{ratio.ljust(6)}")
        for (k, _, u), w in zip(CMP_COLUMNS, widths):
            line += _fmt_pair(r["cmp"][k], u).ljust(w)
        print(line)
    print(f"{'='*110}")


def main() -> None:
    args = parse_args()

    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    elif args.file:
        codes = read_codes_from_file(args.file)
    else:
        print("请指定 --codes 或 --file")
        sys.exit(1)

    output_dir = args.output if args.output else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d")
    out_path = output_dir / f"fscore_{stamp}.csv"
    skipped_path = output_dir / f"fscore_skipped_{stamp}.csv"

    scored, skipped, errors = [], [], []
    for code in codes:
        print(f"\n==> 处理 {code}")
        if not args.include_financial:
            is_fin, reason = financial.detect_financial(code)
            if is_fin:
                print(f"  [跳过] 金融股（{reason}）")
                skipped.append({"code": code, "reason": reason})
                continue

        result = score_stock(code, args.years)
        if result["total"] is None:
            print(f"  [错误] {result.get('error', '评分失败')}")
            errors.append(result)
            continue
        if args.min_score and result["total"] < args.min_score:
            print(f"  [过滤] 总分 {result['total']} < {args.min_score}")
            continue
        print(f"  F-Score: {result['total']} / {result['applied']} 适用项")
        if args.verbose:
            for item, val in zip(f_score.SCORE_ITEMS, result["items"]):
                mark = "Y" if val is True else ("N" if val is False else "-")
                print(f"    {mark} {item}")
        scored.append(result)

    # 终端输出
    print_table(scored)
    if skipped:
        print(f"  金融股跳过 {len(skipped)} 只")
    if errors:
        print(f"  处理失败 {len(errors)} 只")

    # 保存 CSV
    if scored:
        cmp_headers = [f"{label}今({unit})" for label, _, unit in CMP_COLUMNS] + \
                      [f"{label}昨({unit})" for label, _, unit in CMP_COLUMNS]
        header = ["代码", "简称", "行业", "数据年限", "总分", "适用项", "评分",
                  *cmp_headers, *f_score.SCORE_ITEMS]
        lines = [",".join(header)]
        for r in scored:
            ratio = f"{sum(1 for v in r['items'] if v is True) / r['applied']:.2f}" if r["applied"] else ""
            items_str = ",".join("1" if v is True else ("0" if v is False else "") for v in r["items"])
            cmp_strs = []
            for k, _, _ in CMP_COLUMNS:
                now = r["cmp"][k][0]
                cmp_strs.append("" if now is None else f"{now:g}")
            for k, _, _ in CMP_COLUMNS:
                prev = r["cmp"][k][1]
                cmp_strs.append("" if prev is None else f"{prev:g}")
            lines.append(",".join([
                r["code"], r["name"], r["industry"], str(r["years"]),
                str(r["total"]), str(r["applied"]), ratio,
                *cmp_strs, items_str,
            ]))
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
        print(f"\nCSV 已保存: {out_path}")

    if skipped:
        lines = [",".join(["代码", "原因"])]
        lines += [",".join([r["code"], r["reason"]]) for r in skipped]
        skipped_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
        print(f"金融股列表已保存: {skipped_path}")


if __name__ == "__main__":
    main()
