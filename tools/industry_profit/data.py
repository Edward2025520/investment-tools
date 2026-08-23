"""数据获取：申万行业映射缓存构建、行业成分股财务指标。"""

import json
import re
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path
from typing import Optional

import akshare as ak
import pandas as pd
import requests
from bs4 import BeautifulSoup

from tools.industry_profit import config

_RE_CODE = re.compile(r"(\d{6})")
_LEGULEGU_URL = "https://legulegu.com/stockdata/index-composition"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _strip_code(raw) -> str:
    m = _RE_CODE.search(str(raw))
    return m.group(1) if m else str(raw).strip()


def _to_pct(x):
    """'17.92%' / 'False' / 数字 → float 百分比（单位已去除）。"""
    if isinstance(x, (int, float)):
        return None if pd.isna(x) else float(x)
    if not isinstance(x, str):
        return None
    s = x.strip()
    if s in ("", "--", "False", "None"):
        return None
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _legulegu_cons(sw_code: str) -> pd.DataFrame:
    """拉取申万行业成分股。legulegu 页面含 script/style，先剥离再解析。

    页面在限流时仍返回 200 但缺失表格（"No tables found"），调用方需重试。
    """
    url = f"{_LEGULEGU_URL}?industryCode={sw_code}"
    r = requests.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    return pd.read_html(StringIO(str(soup)))[0]


def _retry_info(fn, retries: int = 5):
    """akshare 申万列表接口偶发解析失败（legulegu 降级页缺字段），退避重试。"""
    backoff = (2, 4, 8, 16, 30)
    for attempt in range(retries):
        try:
            return fn()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(backoff[attempt])


# 全市场约 5000+ 只股票，缓存明显不足时提示重建
_MIN_CACHE_SIZE = 1000
_HIERARCHY_CACHE = config.PROJECT_ROOT / "data" / "sw_hierarchy.json"

# 申万一级行业指数代码 → 行业名。legulegu 不可用时的降级源
# （index_component_sw 走申万指数官网，不依赖 legulegu；只能到一级粒度）。
_SW_INDEX_CODES = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁",
    "801050": "有色金属", "801080": "电子", "801110": "家用电器",
    "801120": "食品饮料", "801130": "纺织服饰", "801140": "轻工制造",
    "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务",
    "801230": "综合", "801710": "建筑材料", "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备",
    "801950": "煤炭", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}


def _load_hierarchy():
    """申万二级/三级行业列表（含层级）。实时拉取失败时用本地缓存，冷启动失败则报错。"""
    try:
        second = _retry_info(ak.sw_index_second_info)
        third = _retry_info(ak.sw_index_third_info)
        payload = {
            "date": time.strftime("%Y-%m-%d"),
            "second": second.to_dict(orient="records"),
            "third": third.to_dict(orient="records"),
        }
        _HIERARCHY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _HIERARCHY_CACHE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return second, third
    except Exception:
        if _HIERARCHY_CACHE.exists():
            print("[警告] 申万层级实时获取失败，改用本地缓存")
            d = json.loads(_HIERARCHY_CACHE.read_text(encoding="utf-8"))
            return pd.DataFrame(d["second"]), pd.DataFrame(d["third"])
        raise RuntimeError("申万层级获取失败且无本地缓存（legulegu 不可用），请稍后重试")


def build_industry_map(refresh: bool = False, concurrency: int = 4) -> dict:
    """构建/加载 股票代码 → {简称, 申万1/2/3级, 市值} 全量映射。

    优先用 legulegu 源（完整 1/2/3 级 + 真实市值）；legulegu 不可用时自动降级
    到申万一级行业指数成分股（仅一级粒度，用指数权重代替市值做加权）。
    """
    cache = Path(config.CACHE_PATH)
    if cache.exists() and not refresh:
        mapping = json.loads(cache.read_text(encoding="utf-8"))
        if len(mapping) >= _MIN_CACHE_SIZE:
            return mapping
        print(f"[警告] legulegu 行业映射缓存不完整（{len(mapping)} 只），改用指数源")

    index_cache = Path(config.INDEX_CACHE)
    if index_cache.exists() and not refresh:
        print("[提示] 使用申万一级行业指数成分股映射（legulegu 缓存缺失/不完整时自动启用）")
        return build_industry_map_index()

    try:
        return _build_map_legulegu(refresh, concurrency)
    except RuntimeError as e:
        print(f"[警告] {e}")
        print("[提示] 改用申万一级行业指数成分股（仅支持一级对比，--level 2/3 会退化为一级）")
        return build_industry_map_index(refresh=True, concurrency=concurrency)


def _build_map_legulegu(refresh: bool, concurrency: int) -> dict:
    """遍历申万三级行业拉 legulegu 成分股，构建 1/2/3 级全量映射。

    legulegu 间歇性故障/限流，构建时降并发、退避重试，并支持断点续建：
    已成功收录的行业在重跑 --refresh-cache 时跳过，避免整轮重抓。
    """
    second, third = _load_hierarchy()
    # 二级行业名 → 一级行业名；三级行业代码 → (三级名, 二级名)
    second_parent = dict(zip(second["行业名称"], second["上级行业"]))
    third_levels = {
        row["行业代码"]: (row["行业名称"], row["上级行业"])
        for _, row in third.iterrows()
    }

    # 断点续建：载入旧缓存，只补抓尚未收录的行业
    mapping = {}
    if cache.exists():
        old = json.loads(cache.read_text(encoding="utf-8"))
        mapping.update(old)
        collected = {info.get("sw3_code") for info in old.values() if info.get("sw3_code")}
        todo = [c for c in third_levels if c not in collected]
        if todo != list(third_levels):
            print(f"  断点续建：跳过已收录的 {len(collected)} 个行业，补抓 {len(todo)} 个")
    else:
        todo = list(third_levels.keys())

    if not todo:
        print(f"  行业映射缓存已完整（{len(mapping)} 只），无需更新")
        return mapping

    total = len(todo)
    print(f"  遍历 {total} 个申万三级行业拉取成分股…")

    def fetch(code: str):
        backoff = (1, 2, 4, 8)
        df = None
        for attempt in range(4):
            try:
                df = _legulegu_cons(code)
                break
            except Exception:
                if attempt == 3:
                    return None
                time.sleep(backoff[attempt])
        sw3, sw2 = third_levels[code]
        sw1 = second_parent.get(sw2, "")
        rows = {}
        for _, row in df.iterrows():
            c = _strip_code(row["股票代码"])
            if not c or c in rows:
                continue
            cap = row.get("市值（亿元）")
            rows[c] = {
                "name": str(row["股票简称"]),
                "sw1": sw1,
                "sw2": sw2,
                "sw3": sw3,
                "sw3_code": code,
                "market_cap": None if pd.isna(cap) else float(cap),
            }
        return rows

    failed = 0
    done = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(fetch, c): c for c in todo}
        for fut in as_completed(futures):
            rows = fut.result()
            done += 1
            if rows:
                mapping.update(rows)
            else:
                failed += 1
            if done % 50 == 0 or done == total:
                print(f"    进度 {done}/{total}，已收录 {len(mapping)} 只，失败 {failed}")

    print(f"  行业映射构建完成，共 {len(mapping)} 只股票")
    if failed:
        print(f"  [警告] {failed}/{total} 个行业获取失败（多为 legulegu 故障/限流），"
              f"缓存不完整，重跑 --refresh-cache 会断点续建")

    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(cache)
    return mapping


def get_industry_members(mapping: dict, target: dict, level: int) -> list[str]:
    """返回目标公司所在行业（指定申万层级）的全部成分股代码。"""
    col = config.LEVEL_COL[level]
    val = target[col]
    return [c for c, info in mapping.items() if info.get(col) == val]


def fetch_stock_metrics(code: str, years: int) -> Optional[dict]:
    """取单只股票近 N 年年报各指标均值，失败返回 None。"""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
    except Exception:
        return None
    if df is None or df.empty or "报告期" not in df.columns:
        return None

    annual = df[["报告期"]].copy()
    annual["报告期"] = pd.to_datetime(annual["报告期"], errors="coerce")
    annual = annual[annual["报告期"].dt.month == 12].dropna(subset=["报告期"])
    annual = annual.sort_values("报告期", ascending=False).head(years)
    if annual.empty:
        return None

    def col_means(name: str):
        if name not in df.columns:
            return None
        vals = df.loc[annual.index, name].map(_to_pct).dropna()
        return round(float(vals.mean()), 2) if len(vals) else None

    def col_series(name: str):
        if name not in df.columns:
            return None
        return df.loc[annual.index, name].map(_to_pct)

    net_margin = col_means("销售净利率")
    gross_margin = col_means("销售毛利率")
    roe = col_means("净资产收益率")

    # ROA ≈ ROE × (1 − 资产负债率/100)
    roe_ser, debt_ser = col_series("净资产收益率"), col_series("资产负债率")
    roa = None
    if roe_ser is not None and debt_ser is not None:
        years_roa = [r * (1 - d / 100) for r, d in zip(roe_ser, debt_ser)
                     if r is not None and d is not None]
        if years_roa:
            roa = round(sum(years_roa) / len(years_roa), 2)

    return {
        "net_margin": net_margin,
        "gross_margin": gross_margin,
        "roe": roe,
        "roa": roa,
    }


def fetch_metrics_batch(codes: list[str], years: int, concurrency: int = 8) -> dict[str, dict]:
    """并发获取一批成分股指标，返回 {代码: 指标}。"""
    result = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(fetch_stock_metrics, c, years): c for c in codes}
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                m = fut.result()
            except Exception:
                m = None
            if m:
                result[c] = m
    return result


def build_industry_map_index(refresh: bool = False, concurrency: int = 8) -> dict:
    """申万一级行业指数成分股映射（legulegu 不可用时的降级源）。

    遍历 31 个申万一级行业指数拉成分股，行业粒度只有一级（sw1=sw2=sw3），
    用指数权重当市值做加权（指数权重即市值权重）。结果缓存到独立 JSON，
    避免与 legulegu 的 1/2/3 级映射互相污染。
    """
    cache = Path(config.INDEX_CACHE)
    if cache.exists() and not refresh:
        mapping = json.loads(cache.read_text(encoding="utf-8"))
        if len(mapping) < _MIN_CACHE_SIZE:
            print(f"[警告] 指数成分映射缓存不完整（{len(mapping)} 只），建议 --refresh-cache 重建")
        return mapping

    print(f"  遍历 {len(_SW_INDEX_CODES)} 个申万一级行业指数拉取成分股…")

    def fetch(cn):
        code, name = cn
        try:
            df = _retry_info(lambda: ak.index_component_sw(symbol=code))
        except Exception:
            return None
        rows = {}
        for _, row in df.iterrows():
            c = _strip_code(row["证券代码"])
            if not c or c in rows:
                continue
            rows[c] = {
                "name": str(row["证券名称"]),
                "sw1": name, "sw2": name, "sw3": name,
                "market_cap": float(row["最新权重"]),
            }
        return rows

    failed = 0
    mapping = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(fetch, cn): cn for cn in _SW_INDEX_CODES.items()}
        for fut in as_completed(futures):
            rows = fut.result()
            if rows:
                mapping.update(rows)
            else:
                failed += 1

    print(f"  指数映射构建完成，共 {len(mapping)} 只股票"
          + (f"，{failed} 个行业失败" if failed else ""))
    if failed:
        print(f"  [警告] {failed} 个行业指数获取失败，重跑 --refresh-cache 会重试")

    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(cache)
    return mapping
