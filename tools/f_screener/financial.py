"""金融股识别：关键词 + 手动覆盖。"""

import warnings
from functools import lru_cache
from typing import Tuple

import akshare as ak

from tools.f_screener.config import FINANCIAL_KEYWORDS, MANUAL_FINANCIAL, MANUAL_NON_FINANCIAL


@lru_cache(maxsize=1)
def _load_code_names() -> dict[str, str]:
    """一次性加载全市场 代码->简称 映射（稳定接口，缓存）。"""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = ak.stock_info_a_code_name()
        return dict(zip(df["code"], df["name"]))
    except Exception:
        return {}


def _fetch_name(symbol: str) -> str:
    """获取股票简称（以市场映射为准，避免逐只请求）。"""
    return _load_code_names().get(symbol, "")


def _fetch_industry(symbol: str) -> str:
    """获取行业（可选增强，失败返回空串）。"""
    try:
        df = ak.stock_individual_info_em(symbol=symbol)
        info = dict(zip(df["item"], df["value"]))
        return str(info.get("行业", ""))
    except Exception:
        return ""


def detect_financial(symbol: str, name: str = "", industry: str = "") -> Tuple[bool, str]:
    """判断股票是否为金融股，返回 (是否金融股, 命中依据)。

    优先级：手动覆盖 > 简称关键词 > 行业关键词。
    """
    if symbol in MANUAL_NON_FINANCIAL:
        return False, "手动放行"
    if symbol in MANUAL_FINANCIAL:
        return True, "手动标记"

    name = name or _fetch_name(symbol)
    industry = industry or _fetch_industry(symbol)

    for kw in FINANCIAL_KEYWORDS:
        if kw in name:
            return True, f"简称「{name}」含「{kw}」"
        if kw in industry:
            return True, f"行业「{industry}」含「{kw}」"
    return False, ""
