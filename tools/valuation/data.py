"""数据获取：同花顺三张原始年报表科目抽取 → 逐年亿元序列 + 每股缓存。

缓存 data/valuation_annual/{code}.json 存逐年全套规范科目（亿元），
90 天有效期；换 --years 或后续阶段无需重抓。金额统一亿元。
"""

import datetime
import json
import time

import pandas as pd
import requests

from tools.financial_crawler import akshare_client as _akc
from tools.valuation import config

_QQ_URL = "https://qt.gtimg.cn/q="
_QQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_QQ_CHUNK = 50  # 腾讯批量行情单次建议上限

# 腾讯实时行情字段索引（已按 600519 实测核对）：
# 1 名称 / 3 现价(元) / 45 总市值(亿元) / 46 市净率 / 53 PE(静态)
# 53 已用 总市值÷最新年报归母净利 交叉验证完全一致；39/52 的 TTM/动态语义不能 100% 锁定，故只用静态。
_QQ_PRICE, _QQ_PE_TTM, _QQ_MCAP, _QQ_PB, _QQ_PE_STATIC = 3, 39, 45, 46, 53


def _tencent_symbol(code: str) -> str:
    """A 股 6 位代码 → 腾讯符号（sh/sz/bj 前缀）。"""
    if code[0] == "6":
        return "sh" + code
    if code[0] in ("0", "3"):
        return "sz" + code
    return "bj" + code


def _qq_num(f: list, i: int):
    try:
        v = f[i].strip()
        return float(v) if v not in ("", "-") else None
    except (IndexError, ValueError):
        return None


def fetch_quotes(codes: list) -> dict:
    """腾讯批量实时行情，返回 {6位代码: {name, price, pe_ttm, pb, market_cap_亿}}。

    只取请求成功的票；失败的代码缺失（调用方自行判定）。单只传 [code] 也行。
    """
    out = {}
    uniq = list(dict.fromkeys(c.strip() for c in codes if c))
    for i in range(0, len(uniq), _QQ_CHUNK):
        chunk = uniq[i:i + _QQ_CHUNK]
        syms = ",".join(_tencent_symbol(c) for c in chunk)
        payload = None
        for attempt in range(3):
            try:
                r = requests.get(_QQ_URL + syms, headers=_QQ_HEADERS, timeout=15)
                payload = r.content.decode("gbk", "ignore")
                break
            except Exception:
                if attempt == 2:
                    break
                time.sleep(2)
        if not payload:
            continue
        for line in payload.strip().split(";"):
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            market_code = key.split("_")[-1].strip()
            if len(market_code) < 2:
                continue
            code = market_code[-6:]
            f = val.strip().strip('"').split("~")
            if len(f) <= _QQ_MCAP or not code:
                continue
            price = _qq_num(f, _QQ_PRICE)
            mcap = _qq_num(f, _QQ_MCAP)
            if price is None or mcap is None:
                continue
            out[code] = {
                "name": f[1] if len(f) > 1 else code,
                "price": price,
                "pe_ttm": _qq_num(f, _QQ_PE_TTM),
                "pe_static": _qq_num(f, _QQ_PE_STATIC),
                "pb": _qq_num(f, _QQ_PB),
                "market_cap_亿": mcap,
            }
    return out

_ALL_SUBJECTS = [s for table in config.SUBJECT_ALIASES.values() for s in table]


def _na(v) -> bool:
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _parse_billion(x) -> float:
    """'853.10亿'/'1.23万亿'/'17.92%'/数值(元) → 亿元 float；无法解析/空 → None。"""
    if _na(x):
        return None
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        if "万亿" in s:  # 残留补丁：1 万亿 = 1e4 亿
            try:
                return round(float(s.split("万亿")[0]) * 1e4, 2)
            except ValueError:
                return None
    try:
        return _akc._parse_number(x)
    except Exception:
        return None


def extract_subject(raw_df, aliases) -> dict:
    """在一张原始年报表里按候选子串定位科目，返回 {年份int: 亿元float|None}。

    候选子串按序取首个命中的列（如优先"应收票据及应收账款"再回落"应收账款"）。
    """
    out = {}
    if raw_df is None or raw_df.empty:
        return out
    cols = [str(c) for c in raw_df.columns]
    hit_col = None
    for cand in aliases:
        for c in cols:
            if cand in c:
                hit_col = c
                break
        if hit_col is not None:
            break
    if hit_col is None or "报告期" not in raw_df.columns:
        return out
    for _, row in raw_df.iterrows():
        try:
            y = pd.to_datetime(row["报告期"], errors="coerce")
        except Exception:
            continue
        if pd.isna(y):
            continue
        out[y.year] = _parse_billion(row[hit_col])
    return out


def _cache_path(code: str):
    return config.RAW_CACHE_DIR / f"{code}.json"


def _load_cache(code: str) -> dict:
    try:
        rec = json.loads(_cache_path(code).read_text(encoding="utf-8"))
    except Exception:
        return None
    return rec if isinstance(rec, dict) else None


def _cache_fresh(rec: dict) -> bool:
    born = rec.get("fetched_at")
    if not isinstance(born, str):
        return False
    try:
        born = datetime.datetime.fromisoformat(born)
    except ValueError:
        return False
    return (datetime.datetime.now() - born).days < config.CACHE_MAX_AGE_DAYS


def _save_cache(code: str, rows: list) -> None:
    path = _cache_path(code)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": "ths_raw_3tables",
        "rows": rows,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _rows_to_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if "年份" in df.columns:
        df = df.set_index("年份")
    df = df.reindex(columns=_ALL_SUBJECTS)
    return df.sort_index()


def _usable(rec: dict) -> bool:
    """缓存是否可当完整数据用：至少有一个年 OCF 与 归母净利 均非空。

    防部分抓取（某张表失败）把全 None 缓存当成完整数据反复命中。
    quality 主用这两列；intrinsic 需要的权益列在实现时单独校验，
    缺失则对那只股票触发补抓（银行等 balance 偶发失败的样本不受 quality 阻塞）。
    """
    for row in rec.get("rows") or []:
        if row.get("OCF") is not None and row.get("归母净利") is not None:
            return True
    return False


def _rows_from_raw(raw: dict) -> list:
    by_year = {}
    for table, subjects in config.SUBJECT_ALIASES.items():
        df = raw.get(table)
        if df is None or df.empty:
            continue
        for sub, aliases in subjects.items():
            for y, v in extract_subject(df, aliases).items():
                by_year.setdefault(y, {})[sub] = v
    rows = []
    for y in sorted(by_year):
        rec_row = {"年份": y}
        rec_row.update({s: by_year[y].get(s) for s in _ALL_SUBJECTS})
        rows.append(rec_row)
    return rows


def annual_frame(code: str, years: int = config.RAW_YEARS):
    """逐年(升序, index=年份) 全套规范科目亿元序列；缓存缺失/过期则实时重抓。

    抓取部分失败（缺某张表）时不覆盖旧缓存：优先回落已有的可用旧缓存，
    完全无数据才返回 None（不落缓存便于下次重试）。
    """
    rec = _load_cache(code)
    if rec is not None and _cache_fresh(rec) and _usable(rec):
        return _rows_to_frame(rec["rows"])

    raw = _akc.fetch_raw_all(code, years=years)
    rows = _rows_from_raw(raw)
    if not rows:
        return _rows_to_frame(rec["rows"]) if rec is not None and _usable(rec) else None

    partial = {"fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
               "source": "ths_raw_3tables", "rows": rows}
    if _usable(partial):
        _save_cache(code, rows)
        return _rows_to_frame(rows)
    # 本次缺关键表：保留旧可用缓存，不覆盖成残缺版本
    if rec is not None and _usable(rec):
        return _rows_to_frame(rec["rows"])
    return None
