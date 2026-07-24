"""CLI 入口：利润表分析工具"""

import argparse
import sys
from pathlib import Path

import pandas as pd

_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.profit_analyzer import config
from tools.profit_analyzer.reader import collect_all_years
from tools.profit_analyzer.chart import generate_chart


def parse_args():
    parser = argparse.ArgumentParser(
        description='A 股利润表分析工具 — 从已下载的年报 PDF 中提取利润表数据并生成趋势图',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  python tools/profit_analyzer/cli.py 600519\n'
            '  python tools/profit_analyzer/cli.py 600519 --years 8\n'
            '  python tools/profit_analyzer/cli.py 600519 --metrics 营收,毛利率,归母净利润\n'
            '  python tools/profit_analyzer/cli.py 600519 --no-chart\n'
        ),
    )
    parser.add_argument('stock_code', help='A 股股票代码，如 600519、000001')
    parser.add_argument('--years', type=int, default=5,
                        help='分析最近 N 年（默认 5）')
    parser.add_argument('--metrics',
                        help='筛选指标，逗号分隔，如 "营收,毛利率,ROE"（默认全部）')
    parser.add_argument('--no-chart', action='store_true',
                        help='只打印数据摘要，不出图')
    return parser.parse_args()


def print_summary(df):
    """终端打印数据摘要。"""
    if df.empty:
        return
    print('\n' + '=' * 60)
    print(f'  利润表数据摘要（亿元，ROE/毛利率/净利率 为 %）')
    print('=' * 60)

    # 格式化输出
    table = df.copy()
    for col in table.columns:
        if col in ('ROE', '毛利率', '净利率'):
            table[col] = table[col].apply(lambda x: f'{x:.2f}' if pd.notna(x) else 'N/A')
        else:
            table[col] = table[col].apply(lambda x: f'{x:.2f}' if pd.notna(x) else 'N/A')

    print(table.to_string())
    print('=' * 60)


def main():
    args = parse_args()

    print(f'正在分析 {args.stock_code} 最近 {args.years} 年年报...')
    print('─' * 40)

    df = collect_all_years(args.stock_code, years=args.years)
    if df.empty:
        sys.exit(1)

    # 解析指标筛选
    metrics_filter = None
    if args.metrics:
        # 支持中文名和别名
        raw = [m.strip() for m in args.metrics.split(',')]
        metrics_filter = [m for m in raw if m in config.ALL_METRICS]
        if not metrics_filter:
            print(f'[警告] 未识别到有效指标，显示全部')
        else:
            df = df[[c for c in metrics_filter if c in df.columns]]

    print_summary(df)

    if not args.no_chart:
        generate_chart(df, args.stock_code, metrics_filter=metrics_filter)


if __name__ == '__main__':
    main()
