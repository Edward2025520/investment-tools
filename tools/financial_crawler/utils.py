"""代码归一化、路径解析工具"""

import re
from pathlib import Path
from typing import Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "reports"

# A 股：6 位数字
_RE_A = re.compile(r"^(sz|sh|SH|SZ)?(\d{6})$")
# 港股：数字后可选 .HK，或 hk 前缀
_RE_HK = re.compile(r"^(?:hk[\s:]?)?(\d{1,5})(?:\.HK)?$", re.IGNORECASE)


def normalize_code(stock_code: str) -> tuple[str, str]:
    """归一化股票代码，返回 (纯代码, 市场标识)。

    >>> normalize_code("600519")
    ('600519', 'a')
    >>> normalize_code("03690.HK")
    ('03690.HK', 'hk')
    >>> normalize_code("00700")
    ('00700.HK', 'hk')
    >>> normalize_code("NVDA")
    ('NVDA', 'us')
    """
    code = stock_code.strip()

    m = _RE_HK.match(code)
    if m:
        padded = m.group(1).zfill(5)
        return f"{padded}.HK", "hk"

    m = _RE_A.match(code)
    if m:
        return m.group(2), "a"

    # 剩余视为美股
    return code.upper(), "us"


def resolve_output_path(stock_code: str, base_dir: Optional[Union[str, Path]] = None) -> Path:
    """返回该股票的财报输出目录。"""
    code, _ = normalize_code(stock_code)
    # 港股去 .HK 后缀做目录名
    dir_name = code.replace(".HK", "")
    base = Path(base_dir) if base_dir else DEFAULT_OUTPUT
    path = base / dir_name
    path.mkdir(parents=True, exist_ok=True)
    return path
