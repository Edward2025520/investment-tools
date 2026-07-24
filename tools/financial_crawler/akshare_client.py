"""AKShare 数据获取封装——A 股用同花顺接口，港股用东方财富接口。"""

import re
import warnings
from typing import Optional

import akshare as ak
import pandas as pd

from tools.financial_crawler import utils


def _parse_number(x) -> Optional[float]:
    """将 '853.10亿' / '17.92%' / 'False' 转为浮点数（亿元）。"""
    if isinstance(x, (int, float)):
        return round(float(x) / 1e8, 2) if abs(float(x)) > 1e8 else round(float(x), 2)
    if not isinstance(x, str):
        return None
    x = x.strip()
    if not x or x in ("--", "False", "None", ""):
        return None
    # 百分比值：直接去 % 号，不做单位转换
    if x.endswith('%'):
        try:
            return round(float(x[:-1]), 2)
        except ValueError:
            return None
    try:
        return round(float(x) / 1e8, 2)
    except ValueError:
        pass
    unit = 1
    if "亿" in x:
        unit = 1
        x = x.replace("亿", "")
    elif "万" in x:
        unit = 1e-4
        x = x.replace("万", "")
    try:
        return round(float(x) * unit, 2)
    except ValueError:
        return None


def _filter_annual(df: pd.DataFrame) -> pd.DataFrame:
    """只保留年报（12-31）数据，按年份倒序排列。"""
    if "报告期" in df.columns:
        date_col = "报告期"
    elif "REPORT_DATE" in df.columns:
        date_col = "REPORT_DATE"
    else:
        return df
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df[df[date_col].dt.month == 12].dropna(subset=[date_col])
    df = df.sort_values(date_col, ascending=False).reset_index(drop=True)
    return df


def _truncate_years(df: pd.DataFrame, years: int = 10) -> pd.DataFrame:
    """截取最近 N 年数据。"""
    return df.head(max(years, 1))


# ── A 股：同花顺接口 ──


def fetch_a_profit(symbol: str, years: int = 10) -> pd.DataFrame:
    """A 股利润表。"""
    df = ak.stock_financial_benefit_ths(symbol=symbol)
    df = _filter_annual(df)
    # 提取核心字段
    cols = {"*营业总收入": "营业收入", "*归属于母公司所有者的净利润": "归母净利润", "*净利润": "净利润"}
    rename = {k: v for k, v in cols.items() if k in df.columns}
    if not rename:
        return pd.DataFrame()
    out = df[list(rename.keys())].rename(columns=rename)
    for c in out.columns:
        out[c] = out[c].apply(_parse_number)
    out["报告期"] = pd.to_datetime(df["报告期"]).dt.year
    out = _truncate_years(out, years)
    return out.set_index("报告期")


def fetch_a_balance(symbol: str, years: int = 10) -> pd.DataFrame:
    """A 股资产负债表。"""
    df = ak.stock_financial_debt_ths(symbol=symbol)
    df = _filter_annual(df)
    cols = {"*资产合计": "总资产", "*负债合计": "总负债", "*归属于母公司所有者权益合计": "股东权益"}
    rename = {k: v for k, v in cols.items() if k in df.columns}
    if not rename:
        return pd.DataFrame()
    out = df[list(rename.keys())].rename(columns=rename)
    for c in out.columns:
        out[c] = out[c].apply(_parse_number)
    out["报告期"] = pd.to_datetime(df["报告期"]).dt.year
    out = _truncate_years(out, years)
    return out.set_index("报告期")


def fetch_a_cashflow(symbol: str, years: int = 10) -> pd.DataFrame:
    """A 股现金流量表。"""
    df = ak.stock_financial_cash_ths(symbol=symbol)
    df = _filter_annual(df)
    cols = {
        "*经营活动产生的现金流量净额": "经营现金流",
        "*投资活动产生的现金流量净额": "投资现金流",
        "*筹资活动产生的现金流量净额": "融资现金流",
    }
    rename = {k: v for k, v in cols.items() if k in df.columns}
    if not rename:
        return pd.DataFrame()
    out = df[list(rename.keys())].rename(columns=rename)
    for c in out.columns:
        out[c] = out[c].apply(_parse_number)
    out["报告期"] = pd.to_datetime(df["报告期"]).dt.year
    out = _truncate_years(out, years)
    return out.set_index("报告期")


def fetch_a_indicators(symbol: str, years: int = 10) -> pd.DataFrame:
    """A 股财务指标。"""
    df = ak.stock_financial_abstract_ths(symbol=symbol)
    df = _filter_annual(df)
    rename = {}
    if "销售毛利率" in df.columns:
        rename["销售毛利率"] = "毛利率"
    if "销售净利率" in df.columns:
        rename["销售净利率"] = "净利率"
    if "净资产收益率" in df.columns:
        rename["净资产收益率"] = "ROE"
    if not rename:
        return pd.DataFrame()
    out = df[list(rename.keys())].rename(columns=rename)
    for c in out.columns:
        out[c] = out[c].apply(_parse_number)
    out["报告期"] = pd.to_datetime(df["报告期"]).dt.year
    out = _truncate_years(out, years)
    return out.set_index("报告期")


# ── 港股：东方财富接口 ──


def _fetch_hk_df(symbol: str, years: int = 10) -> pd.DataFrame:
    """获取港股分析指标原始数据，返回年报。"""
    code, _ = utils.normalize_code(symbol)
    pure_code = code.replace(".HK", "")
    df = ak.stock_financial_hk_analysis_indicator_em(symbol=pure_code)
    df = df[df["DATE_TYPE_CODE"] == "001"].copy()
    df = df.sort_values("REPORT_DATE", ascending=False).head(years)
    return df


def fetch_hk_profit(symbol: str, years: int = 10) -> pd.DataFrame:
    """港股利润表。"""
    df = _fetch_hk_df(symbol, years)
    data = {
        "营业收入": df["OPERATE_INCOME"].apply(_parse_number),
        "毛利": df["GROSS_PROFIT"].apply(_parse_number),
        "归母净利润": df["HOLDER_PROFIT"].apply(_parse_number),
    }
    out = pd.DataFrame(data, index=pd.to_datetime(df["REPORT_DATE"]).dt.year)
    out.index.name = "报告期"
    return out


def fetch_hk_balance(symbol: str, years: int = 10) -> pd.DataFrame:
    """港股资产负债表（港股提供比率类指标而非绝对值）。"""
    df = _fetch_hk_df(symbol, years)
    data = {
        "资产负债率(%)": df["DEBT_ASSET_RATIO"].apply(lambda x: round(float(x), 2) if x and x != "--" else None),
        "流动比率": df["CURRENT_RATIO"].apply(lambda x: round(float(x), 2) if x and x != "--" else None),
        "每股净资产(元)": df["BPS"].apply(lambda x: round(float(x), 2) if x and x != "--" else None),
    }
    out = pd.DataFrame(data, index=pd.to_datetime(df["REPORT_DATE"]).dt.year)
    out.index.name = "报告期"
    return out


def fetch_hk_cashflow(symbol: str, years: int = 10) -> pd.DataFrame:
    """港股现金流量表（港股仅提供每股经营现金流）。"""
    df = _fetch_hk_df(symbol, years)
    data = {
        "每股经营现金流(元)": df["PER_NETCASH_OPERATE"].apply(
            lambda x: round(float(x), 2) if x and x != "--" else None
        ),
    }
    out = pd.DataFrame(data, index=pd.to_datetime(df["REPORT_DATE"]).dt.year)
    out.index.name = "报告期"
    return out


def fetch_hk_indicators(symbol: str, years: int = 10) -> pd.DataFrame:
    """港股财务指标。"""
    df = _fetch_hk_df(symbol, years)
    data = {
        "ROE(%)": df["ROE_AVG"].apply(lambda x: round(float(x), 2) if x and x != "--" else None),
        "毛利率(%)": df["GROSS_PROFIT_RATIO"].apply(lambda x: round(float(x), 2) if x and x != "--" else None),
        "净利率(%)": df["NET_PROFIT_RATIO"].apply(lambda x: round(float(x), 2) if x and x != "--" else None),
    }
    out = pd.DataFrame(data, index=pd.to_datetime(df["REPORT_DATE"]).dt.year)
    out.index.name = "报告期"
    return out


# ── 美股：东方财富接口 ──


def _fetch_us_df(symbol: str, years: int = 10) -> pd.DataFrame:
    """获取美股分析指标原始数据，返回年报数据。"""
    code, _ = utils.normalize_code(symbol)
    df = ak.stock_financial_us_analysis_indicator_em(symbol=code)
    df = df[df["DATE_TYPE_CODE"] == "001"].copy()
    df = df.sort_values("REPORT_DATE", ascending=False).head(years)
    return df


def fetch_us_profit(symbol: str, years: int = 10) -> pd.DataFrame:
    """美股利润表。"""
    df = _fetch_us_df(symbol, years)
    rev_col = "OPERATE_INCOME" if "OPERATE_INCOME" in df.columns else "TOTAL_INCOME"
    gp_col = "GROSS_PROFIT" if "GROSS_PROFIT" in df.columns else None
    data = {
        "营业收入": df[rev_col].apply(_parse_number),
    }
    if gp_col:
        data["毛利"] = df[gp_col].apply(_parse_number)
    if "PARENT_HOLDER_NETPROFIT" in df.columns:
        data["归母净利润"] = df["PARENT_HOLDER_NETPROFIT"].apply(_parse_number)
    # 增长率
    rev = data["营业收入"].dropna()
    if len(rev) >= 2:
        growth = rev.pct_change(-1) * 100
        data["营收增长率(%)"] = growth.shift(1)
    out = pd.DataFrame(data, index=pd.to_datetime(df["REPORT_DATE"]).dt.year)
    out.index.name = "报告期"
    return out


def fetch_us_balance(symbol: str, years: int = 10) -> pd.DataFrame:
    """美股资产负债表。"""
    df = _fetch_us_df(symbol, years)
    data = {}
    debt_col = "DEBT_ASSET_RATIO" if "DEBT_ASSET_RATIO" in df.columns else "DEBT_RATIO"
    if debt_col in df.columns:
        data["资产负债率(%)"] = df[debt_col].apply(
            lambda x: round(float(x), 2) if x and x != "--" else None)
    if "CURRENT_RATIO" in df.columns:
        data["流动比率"] = df["CURRENT_RATIO"].apply(
            lambda x: round(float(x), 2) if x and x != "--" else None)
    out = pd.DataFrame(data, index=pd.to_datetime(df["REPORT_DATE"]).dt.year)
    out.index.name = "报告期"
    return out


def fetch_us_cashflow(symbol: str, years: int = 10) -> pd.DataFrame:
    """美股现金流量表（有限）。"""
    df = _fetch_us_df(symbol, years)
    data = {
        "经营现金流/流动负债": df["OCF_LIQDEBT"].apply(
            lambda x: round(float(x), 2) if x and x != "--" else None),
    }
    out = pd.DataFrame(data, index=pd.to_datetime(df["REPORT_DATE"]).dt.year)
    out.index.name = "报告期"
    return out


def fetch_us_indicators(symbol: str, years: int = 10) -> pd.DataFrame:
    """美股财务指标。"""
    df = _fetch_us_df(symbol, years)
    data = {}
    roe_col = "ROE_AVG" if "ROE_AVG" in df.columns else "ROE"
    if roe_col in df.columns:
        data["ROE(%)"] = df[roe_col].apply(
            lambda x: round(float(x), 2) if x and x != "--" else None)
    if "GROSS_PROFIT_RATIO" in df.columns:
        data["毛利率(%)"] = df["GROSS_PROFIT_RATIO"].apply(
            lambda x: round(float(x), 2) if x and x != "--" else None)
    if "NET_PROFIT_RATIO" in df.columns:
        data["净利率(%)"] = df["NET_PROFIT_RATIO"].apply(
            lambda x: round(float(x), 2) if x and x != "--" else None)
    out = pd.DataFrame(data, index=pd.to_datetime(df["REPORT_DATE"]).dt.year)
    out.index.name = "报告期"
    return out


# ── 统一入口 ──


FETCH_MAP = {
    "a": {
        "profit": fetch_a_profit,
        "balance": fetch_a_balance,
        "cashflow": fetch_a_cashflow,
        "indicators": fetch_a_indicators,
    },
    "hk": {
        "profit": fetch_hk_profit,
        "balance": fetch_hk_balance,
        "cashflow": fetch_hk_cashflow,
        "indicators": fetch_hk_indicators,
    },
    "us": {
        "profit": fetch_us_profit,
        "balance": fetch_us_balance,
        "cashflow": fetch_us_cashflow,
        "indicators": fetch_us_indicators,
    },
}


def fetch_all(symbol: str, years: int = 10) -> dict[str, pd.DataFrame]:
    """获取指定股票的四张表数据，返回 {表名: DataFrame}。"""
    code, market = utils.normalize_code(symbol)
    fetchers = FETCH_MAP.get(market)
    if not fetchers:
        raise ValueError(f"不支持的市场: {market}")
    result = {}
    for name, fn in fetchers.items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                df = fn(symbol, years=years)
                result[name] = df
            except Exception as e:
                print(f"  [警告] {name} 获取失败: {e}")
                result[name] = pd.DataFrame()
    return result


_MARKET_FETCH_RAW = {
    "a": {
        "profit": lambda s, y: _filter_annual(ak.stock_financial_benefit_ths(symbol=s)).head(y),
        "balance": lambda s, y: _filter_annual(ak.stock_financial_debt_ths(symbol=s)).head(y),
        "cashflow": lambda s, y: _filter_annual(ak.stock_financial_cash_ths(symbol=s)).head(y),
        "indicators": lambda s, y: _filter_annual(ak.stock_financial_abstract_ths(symbol=s)).head(y),
    },
    "hk": {
        "profit": lambda s, y: _fetch_hk_df(s, y),
        "balance": lambda s, y: _fetch_hk_df(s, y),
        "cashflow": lambda s, y: _fetch_hk_df(s, y),
        "indicators": lambda s, y: _fetch_hk_df(s, y),
    },
    "us": {
        "profit": lambda s, y: _fetch_us_df(s, y),
        "balance": lambda s, y: _fetch_us_df(s, y),
        "cashflow": lambda s, y: _fetch_us_df(s, y),
        "indicators": lambda s, y: _fetch_us_df(s, y),
    },
}


def fetch_raw_all(symbol: str, years: int = 10) -> dict[str, pd.DataFrame]:
    """获取完整原始数据（用于 CSV 导出），返回 {表名: DataFrame}。"""
    _, market = utils.normalize_code(symbol)
    fns = _MARKET_FETCH_RAW.get(market)
    if not fns:
        return {}
    result = {}
    for name, fn in fns.items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                result[name] = fn(symbol, years)
            except Exception as e:
                print(f"  [警告] {name} 原始数据获取失败: {e}")
    return result
