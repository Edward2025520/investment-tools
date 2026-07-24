"""巨潮资讯网 API 封装——异步查询年报列表并下载 PDF。"""

import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import httpx
from tqdm import tqdm

from tools.stock_reports import utils

FULLTEXT_URL = "http://www.cninfo.com.cn/new/fulltextSearch/full"
DOWNLOAD_HOST = "http://static.cninfo.com.cn"

_EM_TAG = re.compile(r"</?em>")
# 匹配 "XXXX年年度报告"，排除半年度、摘要、补充公告
_RE_ANNUAL = re.compile(
    r"(\d{4})\s*年\s*年度报告(?!\s*(?:摘要|补充|已取消|催告|英文版|英文))(?<!半年)"
)
# 提取 <em>标签内的证券简称
_RE_SHORT = re.compile(r"<em>([^<]+)</em>")


async def fetch_annual_list(
    client: httpx.AsyncClient,
    stock_code: str,
    max_years: int = 10,
) -> List[Dict[str, Any]]:
    """通过关键词搜索查询该股票所有可查年报。

    使用 "股票代码 年度报告" 作为关键词 + 全文搜索，精准定位年报公告。
    翻遍所有页收集全量年报，按年份排序取最新的 N 年。
    返回每条含 secName, announcementTitle, announceTime, adjunctUrl。
    """
    year_map: Dict[int, dict] = {}

    for page in range(1, 11):  # 最多 10 页
        payload = {
            "searchkey": f"{stock_code} 年度报告",
            "sdate": "",
            "edate": "",
            "isfulltext": "true",
            "sortName": "announceTime",
            "sortType": "desc",
            "pageNum": page,
            "pageSize": 50,
        }
        resp = await client.post(FULLTEXT_URL, data=payload)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("announcements") or []
        if not items:
            break

        for item in items:
            title = _EM_TAG.sub("", item.get("announcementTitle", ""))
            m = _RE_ANNUAL.search(title)
            if not m:
                continue
            year = int(m.group(1))
            if year not in year_map or item.get("announcementTime", 0) > year_map[year].get("announcementTime", 0):
                item["year"] = year
                year_map[year] = item

        # 已到最后一页，停止翻页
        if len(items) < 50:
            break

    result = sorted(year_map.values(), key=lambda x: x["year"], reverse=True)
    return result[:max_years]


def _extract_name(item: dict) -> str:
    """提取公司简称，优先从 secName 取，否则从标题中提取。"""
    name = item.get("secName", "")
    if name:
        return _EM_TAG.sub("", name).strip()
    m = _RE_SHORT.search(item.get("announcementTitle", ""))
    if m:
        return m.group(1).strip()
    return ""


def _build_filename(item: dict) -> str:
    """生成统一文件名：简称_年份_年度报告.pdf"""
    name = _extract_name(item)
    if not name:
        name = item.get("secCode", "")
    year = item.get("year", 0)
    return utils.generate_filename(name, "", year)


async def download_pdf(
    client: httpx.AsyncClient,
    item: dict,
    output_dir: Path,
    sem: asyncio.Semaphore,
) -> Tuple[str, bool, str]:
    """下载单份 PDF。返回 (文件路径, 是否成功, 年份标签)。"""
    fname = _build_filename(item)
    target = output_dir / fname
    year_label = f"{item.get('year', '?')}年"

    if target.exists():
        return str(target), True, year_label

    adjunct_url = item.get("adjunctUrl", "")
    if not adjunct_url:
        return "", False, year_label

    url = f"{DOWNLOAD_HOST}/{adjunct_url}"
    for attempt in range(3):
        try:
            async with sem:
                resp = await client.get(url, timeout=60)
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
    """主流程：查询 → 下载 → 返回摘要。"""
    code, _ = utils.normalize_code(stock_code)
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
            desc=f"下载 {code} 年报",
            unit="份",
        ):
            _, ok, label = await coro
            if ok:
                result["success"].append(label)
            else:
                result["failed"].append(label)

    return result
