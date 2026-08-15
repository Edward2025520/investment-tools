"""港交所披露易 API 封装——异步查询港股年报并下载 PDF。

核心机制：
  1. JSF 会话初始化（获 ViewState + POST 日期范围）
  2. 按月份分批查询（仅 1-6 月年报发布高峰），自动分页
  3. 客户端按股票代码 + 年报标题过滤
  4. 按年份去重、偏好中文、下载 PDF
"""

import json
import calendar
import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

from tools.stock_reports import utils

# ── 常量 ──
HKEX_SEARCH_PAGE = "https://www1.hkexnews.hk/search/titlesearch.xhtml"
HKEX_JSON_API = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
HKEX_PREFIX_API = "https://www1.hkexnews.hk/search/prefix.do"
HKEX_BASE = "https://www1.hkexnews.hk"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_INIT_PARAMS = {
    "sortDir": "0",
    "sortByRecordDate": "on",
    "searchType": "0",
    "category": "0",
    "t1code": "-2",
    "t2Gcode": "-2",
    "t2code": "-2",
    "documentType": "-1",
    "rowRange": "0",
    "lang": "EN",
}

# 年报标题匹配（排除中期/季度/摘要/ESG 等）
_RE_ANNUAL = re.compile(r"annual\s+report", re.IGNORECASE)
_RE_EXCLUDE = re.compile(
    r"(interim|quarterly|summary|environmental|esg|"
    r"circular|proxy|notice\s+of\s+|"
    r"results\s+announcement|reply\s+slip|"
    r"report\s+on\s+summary)",
    re.IGNORECASE,
)
_RE_YEAR = re.compile(r"(\d{4})")


async def _init_session(client: httpx.AsyncClient) -> None:
    """初始化 JSF 会话：GET 搜索页获 ViewState → POST 设日期范围（20 年）。"""
    resp = await client.get(
        HKEX_SEARCH_PAGE, params=_INIT_PARAMS, headers=_HEADERS, timeout=30
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    vs = soup.find("input", {"name": "javax.faces.ViewState"})
    if not vs:
        raise RuntimeError("无法提取 ViewState，页面结构可能已变更")
    viewstate = vs.get("value", "")

    form = soup.find("form")
    action = (form.get("action", "") if form else "") or "/search/titlesearch.xhtml"
    post_url = (
        f"{HKEX_BASE}{action}" if action.startswith("/") else action
    )

    now = datetime.now()
    date_from = (now - timedelta(days=365 * 20)).strftime("%Y%m%d")
    date_to = now.strftime("%Y%m%d")

    await client.post(
        post_url,
        data={
            "j_idt10": "j_idt10",
            "j_idt10:loadMoreRange": "100",
            "javax.faces.ViewState": viewstate,
            "from": date_from,
            "to": date_to,
        },
        headers={**_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )


async def _get_stock_id(client: httpx.AsyncClient, code: str) -> str:
    """通过 prefix.do 接口查询目标股票的内部 stockId（服务端过滤用）。

    返回 "-1"（全部股票）表示未找到，调用方据此回退到全市场查询。
    """
    try:
        resp = await client.get(
            HKEX_PREFIX_API,
            params={"lang": "EN", "type": "A", "name": code, "market": "SEHK", "callback": "callback"},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.text
        # 兼容 JSONP 包装 callback({...}) 与纯 JSON 两种响应
        start, end = body.find("({"), body.rfind("})")
        if start != -1 and end != -1:
            data = json.loads(body[start + 1 : end + 1])
        else:
            data = json.loads(body)
        for item in data.get("stockInfo", []):
            if item.get("code") == code:
                return str(item["stockId"])
    except Exception:
        pass
    return "-1"


async def _fetch_month(
    client: httpx.AsyncClient,
    year: int,
    month: int,
    lang: str = "E",
    stock_id: str = "-1",
) -> List[Dict[str, Any]]:
    """获取指定月份披露记录（自动分页）。

    stock_id 指定单只股票（服务端过滤），默认 "-1" 表示全部股票。
    lang="E" 英文标题，lang="H" 繁体中文标题。
    """
    _, last_day = calendar.monthrange(year, month)
    base_params = {
        "sortDir": "0",
        "sortByOptions": "DateTime",
        "category": "0",
        "market": "SEHK",
        "stockId": stock_id,
        "documentType": "-1",
        "fromDate": f"{year}{month:02d}01",
        "toDate": f"{year}{month:02d}{last_day:02d}",
        "title": "",
        "searchType": "0",
        "t1code": "-2",
        "t2Gcode": "-2",
        "t2code": "-2",
        "lang": lang,
    }
    headers = {
        **_HEADERS,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": HKEX_SEARCH_PAGE,
        "X-Requested-With": "XMLHttpRequest",
    }

    all_records: List[Dict] = []
    page_size = 10000
    while True:
        params = {**base_params, "rowRange": str(page_size)}
        resp = await client.get(HKEX_JSON_API, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        raw = body.get("result", "null")
        if raw and raw != "null":
            chunk = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, list) else [])
            new_records = chunk[len(all_records):]
            all_records.extend(new_records)

        if not body.get("hasNextRow", False):
            break
        page_size += 10000
        if page_size > 50000:
            break

    return all_records


def _is_annual_report(record: dict) -> bool:
    """判断是否为真实年报（非中期/季度/摘要/ESG）。"""
    title = record.get("TITLE", "")
    return bool(_RE_ANNUAL.search(title) and not _RE_EXCLUDE.search(title))


def _extract_year(title: str) -> Optional[int]:
    """从标题中提取财年。"""
    years = _RE_YEAR.findall(title)
    return max(int(y) for y in years) if years else None


def _has_chinese(text: str) -> bool:
    return bool(re.search(r"[一-鿿]", text))


def _match_stock(record: dict, target_code: str) -> bool:
    """检查记录的股票代码是否匹配目标（支持 5 位补齐格式）。"""
    code = record.get("STOCK_CODE", "").split("<br/>")[0].strip()
    return code == target_code


def _prefer_chinese(items: List[Dict]) -> List[Dict]:
    """按年份去重，中文版优先。"""
    by_year: Dict[int, dict] = {}
    for item in items:
        title = item.get("TITLE", "")
        year = _extract_year(title)
        if year is None:
            continue
        is_cn = _has_chinese(title)
        if year not in by_year:
            by_year[year] = item
        else:
            existing = by_year[year]
            existing_cn = _has_chinese(existing.get("TITLE", ""))
            if is_cn and not existing_cn:
                by_year[year] = item
            elif is_cn == existing_cn:
                if (item.get("DATE_TIME") or "") > (existing.get("DATE_TIME") or ""):
                    by_year[year] = item
    return sorted(by_year.values(), key=lambda x: x.get("DATE_TIME", ""), reverse=True)


async def fetch_annual_list(
    client: httpx.AsyncClient,
    stock_code: str,
    max_years: int = 10,
) -> List[Dict[str, Any]]:
    """按月份分批查询，聚焦 1-6 月年报发布高峰，过滤目标股票后去重返回前 N 年。

    港交所披露易 API 仅支持约 30 天的时间跨度，须按月查询。
    先通过 prefix.do 获取目标股票 stockId 做服务端过滤（只返回该股记录），
    找不到时回退到全市场查询。年报集中在次年 1-6 月发布，因此只查这 6 个月。
    """
    await _init_session(client)

    stock_id = await _get_stock_id(client, stock_code)
    if stock_id == "-1":
        print(f"  [提示] 未找到 {stock_code} 的 stockId，回退到全市场查询（较慢）")

    now = datetime.now()
    all_annual: List[Dict] = []

    for y in range(now.year + 1, now.year - max_years - 2, -1):
        for month in range(1, 7):  # 仅 1-6 月（年报发布高峰）
            for lang in ("E", "H"):
                try:
                    records = await _fetch_month(client, y, month, lang=lang, stock_id=stock_id)
                except Exception:
                    records = []
                for r in records:
                    if _match_stock(r, stock_code) and _is_annual_report(r):
                        all_annual.append(r)
            await asyncio.sleep(0.1)

        deduped = _prefer_chinese(all_annual)
        if len(deduped) >= max_years:
            return deduped[:max_years]

    return _prefer_chinese(all_annual)[:max_years]


def _build_download_url(file_link: str) -> str:
    """将 FILE_LINK 转为完整下载 URL。"""
    if file_link.startswith("http"):
        return file_link
    return urljoin(f"{HKEX_BASE}/", file_link.lstrip("/"))


async def download_pdf(
    client: httpx.AsyncClient,
    item: dict,
    output_dir: Path,
    sem: asyncio.Semaphore,
) -> Tuple[str, bool, str]:
    """下载单份 PDF。"""
    title = item.get("TITLE", "")
    year = _extract_year(title) or 0
    file_link = item.get("FILE_LINK", "")
    raw_name = item.get("STOCK_NAME", "")
    # 取主名（去除 <br/> 分隔的多柜台后缀）
    stock_name = raw_name.split("<br/>")[0].strip()
    year_label = f"{year}年"

    if not file_link:
        return "", False, year_label

    fname = utils.generate_filename(stock_name, "", year, market="hk")
    target = output_dir / fname
    if target.exists():
        return str(target), True, year_label

    url = _build_download_url(file_link)
    for attempt in range(3):
        try:
            async with sem:
                resp = await client.get(
                    url, headers=_HEADERS, timeout=120, follow_redirects=True,
                )
            resp.raise_for_status()
            target.write_bytes(resp.content)
            return str(target), True, year_label
        except (httpx.HTTPError, OSError):
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))
    return "", False, year_label


async def download_annual_reports(
    stock_code: str,
    years: int = 5,
    base_dir: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """主流程：归一化 → 查询 → 下载 → 返回摘要。"""
    code, _ = utils.normalize_code(stock_code, market="hk")
    output_dir = utils.resolve_output_path(code, base_dir)

    if force:
        for f in output_dir.glob("*.pdf"):
            f.unlink()

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    sem = asyncio.Semaphore(3)

    async with httpx.AsyncClient(limits=limits, timeout=30) as client:
        items = await fetch_annual_list(client, code, max_years=years)

    if not items:
        return {"success": [], "failed": [], "total": 0}

    result: Dict[str, Any] = {"success": [], "failed": [], "total": len(items)}

    async with httpx.AsyncClient(limits=limits, timeout=30) as client:
        tasks = [download_pdf(client, item, output_dir, sem) for item in items]
        for coro in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc=f"下载 {code} 港股年报",
            unit="份",
        ):
            _, ok, label = await coro
            if ok:
                result["success"].append(label)
            else:
                result["failed"].append(label)

    return result
