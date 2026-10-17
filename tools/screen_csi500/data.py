"""数据获取：中证500成分、估值历史分位、财务指标，全部带缓存与重试。

估值历史（百度，双周频）单独缓存；财务指标取自同花顺摘要（年报口径）。
行情复用 valuation 的腾讯批量接口；行业标签复用 industry_profit 的申万一级映射。
"""

import datetime
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import akshare as ak
import pandas as pd
import requests

from tools.screen_csi500 import config

_RE_AMT = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(万亿|亿|万)?$")


def _na(v) -> bool:
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _num(x) -> Optional[float]:
    """'58.57亿'/'1.23万亿'/'0.160'/数字 → float（原单位换算到“亿/元”由调用方决定）。

    仅做数值解析，不做百分比/金额语义判断。
    """
    if _na(x):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    if s in ("", "--", "False", "None", "-"):
        return None
    m = _RE_AMT.match(s)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "万亿":
        val *= 1e12
    elif unit == "亿":
        val *= 1e8
    elif unit == "万":
        val *= 1e4
    return val


def _pct(x) -> Optional[float]:
    """'17.92%'/'0.160'→ float 百分数（% 已去除）。无 % 的当数值本身。"""
    if _na(x):
        return None
    s = str(x).strip()
    if s in ("", "--", "False", "None", "-"):
        return None
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _cache_read(path: Path, max_age_days: int) -> Optional[dict]:
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(rec, dict):
        return None
    born = rec.get("fetched_at")
    if not isinstance(born, str):
        return None
    try:
        born = datetime.datetime.fromisoformat(born)
    except ValueError:
        return None
    if (datetime.datetime.now() - born).days >= max_age_days:
        return None
    return rec


def _cache_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": datetime.datetime.now().isoformat(timespec="seconds"), **payload}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _retry(fn, tries: int = 3, backoff=(1, 3, 6)):
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(backoff[i])


# ── 成分名单 ──

def load_constituents(refresh: bool = False, index_key: str = config.DEFAULT_INDEX) -> list[dict]:
    """指定指数的当前成分：[{code, name}]。走中证指数官网，按日缓存。"""
    name, code = config.index_meta(index_key)
    cache = config.cons_cache_path(index_key)
    rec = None if refresh else _cache_read(cache, config.CONS_MAX_AGE_DAYS)
    if rec is not None:
        return rec["items"]
    df = _retry(lambda: ak.index_stock_cons_csindex(symbol=code))
    if df is None or df.empty:
        raise RuntimeError(f"{name}成分获取失败（中证指数官网不可达）")
    items = [{"code": str(c).zfill(6), "name": str(n)}
             for c, n in zip(df["成分券代码"], df["成分券名称"])]
    items = [it for it in items if it["code"].isdigit()]
    _cache_write(cache, {"items": items})
    return items


# ── 估值历史（百度，双周频）──

_BAIDU_URL = "https://gushitong.baidu.com/opendata"
_BAIDU_TIMEOUT = 12.0


def _fetch_baidu_valuation(code: str, indicator: str, timeout: float = _BAIDU_TIMEOUT):
    """百度股市通估值序列（带超时）。

    akshare 的 stock_zh_valuation_baidu 内部 requests.get 没设 timeout，服务器
    不响应时请求会永久挂起，并发抓取时整个任务会卡死，因此本模块自实现一份。
    """
    params = {
        "openapi": "1", "dspName": "iphone", "tn": "tangram", "client": "app",
        "query": indicator, "code": code, "word": "", "resource_id": "51171",
        "market": "ab", "tag": indicator, "chart_select": "全部",
        "industry_select": "", "skip_industry": "1", "finClientType": "pc",
    }
    r = requests.get(_BAIDU_URL, params=params, timeout=timeout)
    r.raise_for_status()
    body = (r.json()["Result"][0]["DisplayData"]["resultData"]
            ["tplData"]["result"]["chartInfo"][0]["body"])
    df = pd.DataFrame(body, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df

def _val_cache_path(code: str) -> Path:
    return config.VAL_CACHE_DIR / f"{code}.json"


def load_valuation(code: str, refresh: bool = False) -> Optional[dict]:
    """{pe: [[date,value],...], pb: [[...]]}；按日缓存。"""
    path = _val_cache_path(code)
    rec = None if refresh else _cache_read(path, config.VAL_MAX_AGE_DAYS)
    if rec is not None:
        return {"pe": rec.get("pe") or [], "pb": rec.get("pb") or []}
    pe = _retry(lambda: _fetch_baidu_valuation(code, "市盈率(TTM)"))
    pb = _retry(lambda: _fetch_baidu_valuation(code, "市净率"))
    if pe is None and pb is None:
        return None

    def ser(df):
        if df is None or df.empty:
            return []
        return [[str(d), None if _na(v) else float(v)]
                for d, v in zip(df["date"], df["value"])]
    payload = {"pe": ser(pe), "pb": ser(pb)}
    _cache_write(path, payload)
    return payload


def percentile_now(series: list, years: int) -> Optional[float]:
    """末值在近 years 年（仅取正值）里的分位 0~1；样本不足或末值非正 → None。"""
    if not series:
        return None
    pts = [(pd.to_datetime(d, errors="coerce"), v) for d, v in series]
    pts = [(d, v) for d, v in pts if d is not None and not pd.isna(d) and v is not None and v > 0]
    pts.sort(key=lambda x: x[0])
    if len(pts) < 12:
        return None
    latest_date, cur = pts[-1]
    cutoff = latest_date - pd.Timedelta(days=365 * years)
    win = [v for d, v in pts if d >= cutoff]
    if len(win) < 12:
        return None
    return round(sum(1 for v in win if v <= cur) / len(win), 4)


# ── 财务指标（同花顺摘要，年报口径）──

def _fin_cache_path(code: str) -> Path:
    return config.FIN_CACHE_DIR / f"{code}.json"


_FIN_FIELDS = {
    "revenue": "营业总收入",
    "revenue_yoy": "营业总收入同比增长率",
    "deducted": "扣非净利润",
    "deducted_yoy": "扣非净利润同比增长率",
    "roe": "净资产收益率",
    "gross_margin": "销售毛利率",
    "net_margin": "销售净利率",
    "debt_ratio": "资产负债率",
    "eps": "基本每股收益",
    "ocf_ps": "每股经营现金流",
    "ar_days": "应收账款周转天数",
}


def load_financial(code: str, refresh: bool = False) -> Optional[dict]:
    """近 4 个年报期指标：[{date, revenue(元), ..., debt_ratio(%), ...}]，按季缓存。"""
    path = _fin_cache_path(code)
    rec = None if refresh else _cache_read(path, config.FIN_MAX_AGE_DAYS)
    if rec is not None:
        return rec["rows"]

    df = _retry(lambda: ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期"))
    if df is None or df.empty or "报告期" not in df.columns:
        return None
    df = df.copy()
    df["报告期"] = pd.to_datetime(df["报告期"], errors="coerce")
    ann = df[(df["报告期"].dt.month == 12)].dropna(subset=["报告期"])
    ann = ann.sort_values("报告期", ascending=False).head(4)
    if ann.empty:
        return None

    rows = []
    for _, r in ann.iterrows():
        row = {"date": r["报告期"].strftime("%Y-%m-%d")}
        row["revenue"] = _num(r.get("营业总收入"))
        row["deducted"] = _num(r.get("扣非净利润"))
        for k in ("revenue_yoy", "deducted_yoy", "roe", "gross_margin",
                  "net_margin", "debt_ratio", "ar_days"):
            row[k] = _pct(r.get(_FIN_FIELDS[k]))
        row["eps"] = _pct(r.get("基本每股收益"))
        row["ocf_ps"] = _pct(r.get("每股经营现金流"))
        rows.append(row)
    rows = list(reversed(rows))  # 升序
    _cache_write(path, {"rows": rows})
    return rows


def _fetch_round(out: dict, codes: list, loader, refresh: bool, concurrency: int) -> None:
    """并发跑一轮 loader，命中的写进 out。"""
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = {pool.submit(loader, c, refresh): c for c in codes}
        for f in as_completed(futs):
            c = futs[f]
            try:
                r = f.result()
            except Exception:
                r = None
            if r:
                out[c] = r


def _fetch_with_retry(codes: list[str], loader, refresh: bool,
                      concurrency: int, label: str) -> dict:
    """并发抓取；首轮未命中的降并发补抓一轮。

    未命中绝大多数是并发限流，不是数据不存在——实测中证1000 首轮并发 8 丢了 145 只
    （全集中在同一代码段），串行补抓 30/30 全部成功。所以值得降并发补一轮。
    """
    out = {}
    _fetch_round(out, codes, loader, refresh, concurrency)
    failed = [c for c in codes if c not in out]
    if failed:
        print(f"    {label}首轮 {len(failed)} 只未命中，降并发补抓…")
        _fetch_round(out, failed, loader, refresh, 2)
        still = [c for c in failed if c not in out]
        if still:
            print(f"    [警告] {label}仍有 {len(still)} 只未命中（可能确实无数据）")
    return out


def fetch_financials(codes: list[str], refresh: bool = False, concurrency: int = 8) -> dict:
    return _fetch_with_retry(codes, load_financial, refresh, concurrency, "财务")


def fetch_valuations(codes: list[str], refresh: bool = False, concurrency: int = 4) -> dict:
    return _fetch_with_retry(codes, load_valuation, refresh, concurrency, "估值")


_MIN_INDUSTRY_MAP = 1000  # 少于这个数视为不完整，退回降级源


def load_industry_map() -> dict:
    """行业标签：优先完整 1/2/3 级映射，缺失或不完整时退回仅一级的降级源。"""
    for path in (config.INDUSTRY_MAP, config.INDEX_MAP):
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if len(m) >= _MIN_INDUSTRY_MAP:
            return m
    return {}


def fetch_quotes(codes: list[str]) -> dict:
    from tools.valuation.data import fetch_quotes as _fq
    return _fq(codes)
