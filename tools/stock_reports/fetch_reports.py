"""CLI 入口：A 股 / 港股年报按需下载工具。"""

import argparse
import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.stock_reports import cninfo_client  # noqa: E402
from tools.stock_reports import hkex_client  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从巨潮资讯网下载 A 股年报 PDF，或从港交所披露易下载港股年报 PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools/stock_reports/fetch_reports.py 000001\n"
            "  python tools/stock_reports/fetch_reports.py 600519 --years 8\n"
            "  python tools/stock_reports/fetch_reports.py 00700 --market hk\n"
            "  python tools/stock_reports/fetch_reports.py 700 --market hk --years 10\n"
            "  python tools/stock_reports/fetch_reports.py 000001 --output ./my_reports\n"
            "  python tools/stock_reports/fetch_reports.py 000001 --force\n"
        ),
    )
    parser.add_argument("stock_code", help="股票代码：A 股 000001 / sz000001 / 600519，港股 hk00700 / 00700 / 700")
    parser.add_argument(
        "--market",
        choices=["a", "hk"],
        default="a",
        help='市场选择: "a"=A 股（巨潮，默认）, "hk"=港股（披露易）',
    )
    parser.add_argument(
        "--years", type=int, default=5, help="下载最近 N 年年报（默认 5）"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出目录（默认 data/reports/{代码}）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载，覆盖已有文件",
    )
    return parser.parse_args()


def print_summary(code: str, result: dict) -> None:
    """打印下载结果摘要。"""
    total = result["total"]
    success = len(result["success"])
    failed = len(result["failed"])

    print(f"\n=== {code} 年报下载完成 ===")
    print(f"  总计: {total} 份")
    if success:
        print(f"  [OK] 成功: {success} 份")
        if result["success"]:
            print("       " + ", ".join(result["success"]))
    if failed:
        print(f"  [FAIL] 失败: {failed} 份")
        if result["failed"]:
            print("       " + ", ".join(result["failed"]))
    if total == 0:
        print("  （未找到符合条件的年报，请核对股票代码）")


def main() -> None:
    args = parse_args()
    code = args.stock_code

    client = hkex_client if args.market == "hk" else cninfo_client
    try:
        result = asyncio.run(
            client.download_annual_reports(
                stock_code=code,
                years=args.years,
                base_dir=args.output,
                force=args.force,
            )
        )
    except Exception as e:
        print(f"\n[错误] 下载失败: {e}")
        print("  请检查网络连接后重试。")
        sys.exit(1)
    print_summary(code, result)


if __name__ == "__main__":
    main()
