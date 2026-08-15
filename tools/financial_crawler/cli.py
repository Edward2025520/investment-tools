"""CLI 入口：A 股/港股财报数据获取与可视化。"""

import argparse
import sys
from pathlib import Path

# 项目根路径
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.financial_crawler import akshare_client, chart, utils


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 AKShare 获取 A 股/港股/美股四张财报表并生成 PNG 图表及 CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools/financial_crawler/cli.py 600519\n"
            "  python tools/financial_crawler/cli.py 03690.HK\n"
            "  python tools/financial_crawler/cli.py NVDA\n"
            "  python tools/financial_crawler/cli.py --codes 600519,03690.HK,NVDA\n"
        ),
    )
    parser.add_argument("stock_code", nargs="?", help="股票代码：A 股 600519，港股 03690.HK，美股 NVDA")
    parser.add_argument(
        "--codes",
        help="批量模式，逗号分隔：600519,03690.HK,NVDA",
    )
    parser.add_argument(
        "--years", type=int, default=10, help="取最近 N 年数据（默认 10，不足则取全部）"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出目录（默认 data/reports/{代码}）",
    )
    return parser.parse_args()


def process_stock(code: str, years: int, base_dir: Path) -> bool:
    """处理单只股票：获取数据 → 生成图表。"""
    try:
        _, market = utils.normalize_code(code)
    except ValueError as e:
        print(f"\n[错误] {code}: {e}")
        return False

    market_map = {"a": "A 股", "hk": "港股", "us": "美股"}
    market_label = market_map.get(market, market)
    print(f"\n{'='*50}")
    print(f"  {code}（{market_label}）")
    print(f"{'='*50}")

    output_dir = utils.resolve_output_path(code, base_dir)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    print(f"  输出目录: {output_dir}")
    print(f"  图表目录: {charts_dir}")

    try:
        data = akshare_client.fetch_all(code, years=years)
    except Exception as e:
        print(f"  [失败] 网络错误或数据源不可用: {e}")
        return False

    # 检查是否有足够数据
    valid_tables = {k: v for k, v in data.items() if not v.empty}
    if not valid_tables:
        print(f"  [失败] 未获取到有效数据")
        return False

    # 检查年限是否充足
    min_years = min(len(v) for v in valid_tables.values())
    print(f"  有效数据年限: {min_years} 年")
    if min_years < 5:
        print(f"  [警告] 数据不足 5 年，图表可能参考价值有限")

    generated = chart.plot_all(data, charts_dir, market=market)

    # 导出 CSV
    csv_count = 0
    try:
        raw_data = akshare_client.fetch_raw_all(code, years=years)
        for name, df in raw_data.items():
            if df is not None and not df.empty:
                csv_path = charts_dir / f"{name}.csv"
                df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                csv_count += 1
    except Exception as e:
        print(f"  [警告] CSV 导出失败: {e}")

    print(f"  完成: 生成 {len(generated)} 张图表 + {csv_count} 个 CSV")
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

    success = 0
    for code in codes:
        if process_stock(code, args.years, args.output):
            success += 1

    print(f"\n{'='*50}")
    print(f"  全部完成: {success}/{len(codes)} 成功")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
