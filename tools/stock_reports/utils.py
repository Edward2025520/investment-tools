"""文件路径、命名、去重工具"""

import re
from pathlib import Path
from typing import Optional, Tuple, Union

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "data" / "reports"

# ── A 股相关 ──
_A_RE = re.compile(r"^(sz|sh)?(\d{6})$", re.IGNORECASE)

# ── 港股相关 ──
_HK_RE = re.compile(r"^(?:hk[\s:]?|HK\.)?(\d{1,5})(?:\.HK)?$")
_HK_VALID = re.compile(r"^(0\d{4}|[1-9]\d{4})$")


def normalize_hk_code(stock_code: str) -> Tuple[str, str]:
    """归一化港股股票代码，返回 (5位代码, 'hk')。

    >>> normalize_hk_code("00700")
    ('00700', 'hk')
    >>> normalize_hk_code("700")
    ('00700', 'hk')
    >>> normalize_hk_code("hk00700")
    ('00700', 'hk')
    >>> normalize_hk_code("0700.HK")
    ('00700', 'hk')
    """
    code = stock_code.strip()
    m = _HK_RE.match(code)
    if not m:
        raise ValueError(f"无效港股股票代码: {stock_code}")
    padded = m.group(1).zfill(5)
    if not _HK_VALID.match(padded):
        raise ValueError(f"港股代码超出范围: {padded}")
    return padded, "hk"


def normalize_code(
    stock_code: str,
    market: str = "a",
) -> Tuple[str, Optional[str]]:
    """归一化股票代码，返回 (纯数字代码, 市场前缀或 None)。

    market="a"（默认）：接受 000001、sz000001、sh600519
    market="hk"：接受 00700、700、hk00700、0700.HK

    >>> normalize_code("000001")
    ('000001', None)
    >>> normalize_code("00700", market="hk")
    ('00700', 'hk')
    """
    if market == "hk":
        return normalize_hk_code(stock_code)
    m = _A_RE.match(stock_code.strip())
    if not m:
        raise ValueError(f"无效股票代码: {stock_code}")
    return m.group(2), m.group(1)


def generate_filename(
    stock_name: str, stock_code: str, year: int, market: str = "a"
) -> str:
    """生成统一格式的文件名。

    A 股: {name}_{year}_年度报告.pdf
    港股: {name}_{year}_年报.pdf
    """
    safe_name = stock_name.strip().replace(" ", "")
    suffix = "_年报.pdf" if market == "hk" else "_年度报告.pdf"
    return f"{safe_name}_{year}{suffix}"


def resolve_output_path(
    stock_code: str, base_dir: Optional[Union[str, Path]] = None
) -> Path:
    """返回该股票的年报存放目录。"""
    base = Path(base_dir) if base_dir else DEFAULT_OUTPUT
    path = base / stock_code
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_exists(output_dir: Path, filename: str) -> bool:
    """判断文件是否已存在。"""
    return (output_dir / filename).exists()
