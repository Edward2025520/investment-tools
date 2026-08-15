"""数据获取：同花顺四表原始年报 + 按年份对齐合并。"""

import sys
import warnings
from pathlib import Path
from typing import Optional

import akshare as ak
import pandas as pd

# 项目根路径，复用 financial_crawler 的工具函数
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.financial_crawler.akshare_client import _filter_annual, _parse_number
from tools.f_screener.config import FIELD_CANDIDATES


def _first_present(df: pd.DataFrame, *names: str) -> Optional[str]:
    """返回首个存在的列名，否则 None。"""
    for name in names:
        if name in df.columns:
            return name
    return None


def _as_money(df: pd.DataFrame, col: str) -> pd.Series:
    """金额字段解析（元→亿元），复用 _parse_number。"""
    return df[col].apply(_parse_number)


def _as_metric(df: pd.DataFrame, col: str) -> pd.Series:
    """比率/数值字段解析：去 % 号，数值原样（不做亿换算）。"""
    def parse(x):
        if isinstance(x, (int, float)):
            return float(x)
        if not isinstance(x, str):
            return None
        x = x.strip()
        if not x or x in ("--", "False", "None", ""):
            return None
        x = x.replace("%", "").replace(",", "")
        try:
            return float(x)
        except ValueError:
            return None
    return df[col].apply(parse)


def _fetch_raw_table(fetcher, symbol: str, years: int) -> pd.DataFrame:
    """调用 THS 接口并过滤出年报数据。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = fetcher(symbol=symbol)
    return _filter_annual(df).head(years)


def fetch_raw_annual(symbol: str, years: int = 8) -> dict[str, pd.DataFrame]:
    """获取 A 股四张原始年报表，返回 {表名: DataFrame}。"""
    fetchers = {
        "profit": ak.stock_financial_benefit_ths,
        "balance": ak.stock_financial_debt_ths,
        "cashflow": ak.stock_financial_cash_ths,
        "indicators": ak.stock_financial_abstract_ths,
    }
    result = {}
    for name, fn in fetchers.items():
        try:
            result[name] = _fetch_raw_table(fn, symbol, years)
        except Exception as e:
            print(f"  [警告] {name} 表获取失败: {e}")
            result[name] = pd.DataFrame()
    return result


def build_metrics(symbol: str, years: int = 8) -> pd.DataFrame:
    """按年份对齐四表字段，返回索引=年份的 DataFrame。

    缺列返回空 DataFrame，缺值以 NaN 表示（不推断不补 0）。
    """
    tables = fetch_raw_annual(symbol, years)

    # 年份索引（以利润表为准）
    profit = tables.get("profit")
    if profit is None or profit.empty or "报告期" not in profit.columns:
        return pd.DataFrame()
    years_idx = pd.to_datetime(profit["报告期"]).dt.year

    out = pd.DataFrame(index=years_idx)
    out.index.name = "报告期"

    # 按字段取数
    def _extract(name: str, table_name: str, parser) -> Optional[pd.Series]:
        table = tables.get(table_name)
        if table is None or table.empty:
            return None
        col = _first_present(table, *FIELD_CANDIDATES[name])
        if not col:
            return None
        return parser(table, col)

    money_fields = [
        ("营业收入", "profit"), ("营业成本", "profit"), ("净利润", "profit"),
        ("经营现金流", "cashflow"),
        ("总资产", "balance"), ("长期负债", "balance"), ("实收资本", "balance"),
    ]
    for field, table_name in money_fields:
        series = _extract(field, table_name, _as_money)
        if series is not None:
            out[field] = series.values

    metric_fields = [("流动比率", "indicators"), ("销售毛利率", "indicators")]
    for field, table_name in metric_fields:
        series = _extract(field, table_name, _as_metric)
        if series is not None:
            out[field] = series.values

    return out
