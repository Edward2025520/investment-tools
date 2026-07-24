"""PDF 解析：基于表格提取的利润表数据获取"""

import re
from pathlib import Path

import pdfplumber
import pandas as pd

from tools.profit_analyzer import config
from tools.profit_analyzer.utils import has_chinese

# ── 工具函数 ──────────────────────────────────────────────


def _extract_year(filename):
    m = re.search(r'(\d{4})', filename)
    return int(m.group(1)) if m else None


def _clean(s):
    if s is None:
        return ''
    return re.sub(r'\s+', '', s.strip())


def _parse_num(text, divisor=None):
    """提取文本中第一个财务数值，除以 divisor 转为亿元。"""
    if not text:
        return None
    text = text.replace(',', '').replace(' ', '')
    m = re.search(r'-?[\d]+\.?\d*', text)
    if m:
        val = float(m.group())
        if divisor is not None:
            return round(val / divisor, 4)
        # fallback heuristic：≥500 视为元 → 亿元
        if abs(val) >= 500:
            return round(val / 1e8, 4)
        return round(val, 4)
    return None


def _detect_unit(texts, page_indices):
    """在指定页附近搜索单位声明，返回转为亿元的 divisor。"""
    for idx in page_indices:
        if 0 <= idx < len(texts):
            text = texts[idx]
            for pattern, divisor in config.UNIT_PATTERNS:
                if pattern in text:
                    return divisor
    return None


def _is_financial_row(label, row):
    """判断一行是否是财务数据行（非空首列，至少有一个大数）。"""
    if not label:
        return False
    for cell in row[1:]:
        if cell and re.search(r'[\d,]+\.?\d*', cell.replace(',', '')):
            return True
    return False


# ── PDF 扫描 ────────────────────────────────────────────


def find_pdfs(code):
    report_dir = config.DATA_DIR / code
    if not report_dir.exists():
        return []
    result = []
    for f in sorted(report_dir.glob('*.pdf')):
        year = _extract_year(f.name)
        if year and '摘要' not in f.name:
            result.append((year, f))
    result.sort(key=lambda x: x[0], reverse=True)
    return result


# ── 表格定位 ─────────────────────────────────────────────


def _find_main_tables(page):
    tables = page.extract_tables()
    found = []
    for table in tables:
        if not table or len(table) < 3:
            continue
        head = ''.join(_clean(c) for c in table[0])
        if '主要会计数据' in head or '主要财务指标' in head:
            found.append(table)
            continue
        # 通用规则：任何含"营业收入"+大额数字的表格
        has_revenue = False
        has_big_num = False
        for row in table:
            joined = ''.join(_clean(c) for c in row)
            if '营业收入' in joined:
                has_revenue = True
            for n in re.findall(r'[\d,]+\.?\d*', joined):
                try:
                    if float(n.replace(',', '')) > 100:
                        has_big_num = True
                except ValueError:
                    pass
        if has_revenue and has_big_num:
            found.append(table)
    return found


def _find_profit_table(page):
    tables = page.extract_tables()
    for table in tables:
        if not table or len(table) < 3:
            continue
        for row in table[:3]:
            rt = ''.join(_clean(c) for c in row)
            if '营业总收入' in rt or '营业收入' in rt:
                return table
    return None


def _find_continuation(pages, start):
    """在 start 页及后续页中找合并利润表的续表，返回合并后的行列表。"""
    collected = []
    for idx in range(start, min(start + 3, len(pages))):
        tables = pages[idx].extract_tables()
        if not tables:
            continue
        for table in tables:
            if not table or len(table) < 2:
                continue
            has_num = False
            for row in table:
                for cell in row[1:]:
                    if cell and re.search(r'[\d,]+\.?\d*', cell):
                        has_num = True
                        break
                if has_num:
                    break
            if not has_num:
                continue
            # 跳过续表顶部的文本碎片（跨页行首截断）
            start_row = 0
            for ri, row in enumerate(table):
                first = _clean(row[0]) if row and row[0] else ''
                if not first or re.match(r'^[a-z]', first) or len(first) < 2:
                    start_row = ri + 1
                else:
                    break
            # 跳过表头行（如"项目"行）
            if start_row < len(table) and table[start_row] and _clean(table[start_row][0]) in ('项目', ''):
                start_row += 1
            collected.extend(table[start_row:])
        if collected:
            continue
        break
    return collected if collected else None


# ── 解析：基于文本的利润表提取（通解）─────────────────────


def _find_profit_section(texts):
    """在全文文本中定位合并利润表章节，返回（起始页, 结束页）。"""
    total = len(texts)

    def _is_toc_page(txt):
        """判断是否目录页：含页码标记或页次表。"""
        if '目 录' in txt or '页次' in txt:
            return True
        # 合并利润表后跟年份（页标题），不是 TOC
        if re.search(r'合并利润表\s+20\d{2}', txt):
            return False
        # 后跟页码范围或短数字 → TOC 引用
        if re.search(r'合并利润表\s*\d{1,3}\s*[-–—]', txt):
            return True
        return False

    start = None
    for i, txt in enumerate(texts):
        if '合并利润表' not in txt or '合并现金流量表' in txt:
            continue
        # 排除目录页：页面标题不是"合并利润表"且内容含目录标记
        head = txt[:50].replace(' ', '')
        is_page_title = '合并利润表' in head
        if not is_page_title and _is_toc_page(txt):
            continue
        if not is_page_title and '合并利润表' not in txt[:200].replace(' ', ''):
            continue
        start = i
        break

    if start is None:
        return None

    end = min(start + 6, total)
    for i in range(start + 1, min(start + 10, total)):
        for m in config.PROFIT_END_MARKERS:
            if m in texts[i][:100]:
                end = i
                break
        if end < total:
            break
    return start, end


def _parse_profit_text(texts, page_range, unit_divisor):
    """从合并利润表页面的纯文本中解析科目数据。"""
    lines = []
    for idx in range(page_range[0], page_range[1]):
        for line in texts[idx].split('\n'):
            line = line.strip()
            if not line or line.startswith('合并利润表'):
                continue
            lines.append(line)

    result = {}

    for line in lines:
        # 提取所有数字
        nums_raw = re.findall(r'-?[\d,]+\.?\d*', line.replace(',', ''))
        if not nums_raw:
            continue
        nums_f = [float(n) for n in nums_raw]

        # 过滤附注编号（1~99 的正整数），保留小数、负数、>=100 的值
        data_nums = [n for n in nums_f if not (1 <= n < 100 and n == int(n))]
        if not data_nums:
            data_nums = nums_f[-1:]

        val = data_nums[0]  # 第一个财务值 = 本期数

        # 提取科目名：去掉前缀标记和数字部分
        label = line.strip()
        for prefix in ('减：', '加：'):
            if prefix in label:
                label = label.split(prefix, 1)[1]
        # 去掉行首非中文内容（数字、空白、标点）
        label = re.sub(r'^[\s\d,.\-\(\)%\[：\]]+', '', label)
        # 取中文部分（遇到非中文字符截断）
        m = re.match(r'([一-鿿　-〿\w]+)', label)
        if m:
            label = m.group(1)
        else:
            continue
        label = re.sub(r'\s+', '', label)
        if len(label) < 2 or label.startswith('其中'):
            continue

        for std_name, aliases in config.PROFIT_KEYWORDS.items():
            if std_name in result:
                continue
            for alias in aliases:
                if alias in label:
                    if std_name in ('净利润', '营业成本') and any(e in label for e in config.EXCLUDE_LABELS):
                        continue
                    # 银行版"减值损失前营业利润"含"营业利润"但非真正营业利润
                    if std_name == '营业利润' and '减值' in label:
                        continue
                    parsed = _parse_num(str(val), unit_divisor)
                    if parsed is not None:
                        result[std_name] = parsed
                    break

    return result


def _parse_main_tables(tables, keywords, unit_divisor):
    """从所有主要数据表中提取指标。"""
    result = {}

    for table in tables:
        # 确定数值列：找不含"增减"的年份列
        header = table[0]
        col = None
        for j, cell in enumerate(header):
            txt = _clean(cell)
            if re.search(r'202\d', txt) and '增减' not in txt \
               and '末期' not in txt and '末' not in txt:
                col = j
                break
        if col is None:
            col = 1

        # 找科目名列：数据行中第一个非空列
        # （表头合并单元格可能导致科目名偏移到 col 1）
        label_col = 0
        sample_rows = table[1:4]
        for row in sample_rows:
            for j, cell in enumerate(row):
                if cell and _clean(cell) and len(_clean(cell)) >= 2:
                    label_col = j
                    break
            if label_col > 0:
                break

        for row in table[1:]:
            if not row or len(row) <= max(col, label_col):
                continue
            label = _clean(row[label_col]) if row[label_col] else None
            if not label:
                continue
            if not _is_financial_row(label, row):
                continue

            for std_name, aliases in keywords.items():
                if std_name in result:
                    continue
                for alias in aliases:
                    if alias in label:
                        # ROE 是百分比值，不应用货币单位 divisor
                        div = None if std_name == 'ROE' else unit_divisor
                        raw_val = _parse_num(row[col], div) if col < len(row) else None
                        if raw_val is not None:
                            result[std_name] = raw_val
                        break

    return result


def _parse_profit_table(table, keywords, unit_divisor):
    """从利润表表格中提取费用明细。"""
    result = {}

    # 定位附注列和数据列（兼容"附注""注释"等用语）
    note_col = None
    for row in table[:3]:
        for j, cell in enumerate(row):
            txt = _clean(cell)
            if txt in ('附注', '注释') or txt.startswith(('附注', '注释')):
                note_col = j
                break

    data_col = (note_col + 1) if note_col is not None else 1

    for row in table:
        if not row or not row[0]:
            continue
        label = _clean(row[0])
        if not label:
            continue
        if label in ('项目', '附注'):
            continue
        # 章节标题行（一、二、三…）仅当数据列无值时跳过
        if re.match(r'^[一二三四五六七八九十]、', label):
            has_data = data_col < len(row) and row[data_col] and _clean(row[data_col])
            if not has_data:
                continue

        for std_name, aliases in keywords.items():
            if std_name in result:
                continue
            for alias in aliases:
                if alias in label:
                    raw_val = _parse_num(row[data_col], unit_divisor) if data_col < len(row) else None
                    if raw_val is not None:
                        result[std_name] = raw_val
                    break

    return result


# ── 主流程 ───────────────────────────────────────────────


def process_pdf(pdf_path):
    """处理单份年报 PDF。"""
    year_hint = _extract_year(pdf_path.name)

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        texts = [p.extract_text() or '' for p in pages]

        # 跳过英文版/非中文年报
        chinese_count = sum(1 for t in texts[:3] if has_chinese(t))
        if chinese_count == 0:
            print(f'  [跳过] {year_hint}年：非中文年报')
            return {}

        data = {}

        # Step 1: 提取主要会计数据+财务指标表格
        for pi in range(min(20, len(pages))):
            if '主要会计数据' not in texts[pi] and '会计数据和财务指标' not in texts[pi]:
                continue
            # 检查本页及前后页，如果没找到继续向后翻
            found_main = False
            for offset in [0, 1, -1, 2]:
                idx = pi + offset
                if 0 <= idx < len(pages):
                    tables = _find_main_tables(pages[idx])
                    if tables:
                        unit_divisor = _detect_unit(texts, range(max(0, idx-1), min(len(pages), idx+3)))
                        main_data = _parse_main_tables(tables, config.MAIN_KEYWORDS, unit_divisor)
                        data.update(main_data)
                        found_main = True
                        break
            if not found_main:
                # 关键词在目录页，向后翻找实际表格
                for extra in range(5, 30):
                    idx = pi + extra
                    if idx >= len(pages):
                        break
                    tables = _find_main_tables(pages[idx])
                    if tables:
                        unit_divisor = _detect_unit(texts, range(max(0, idx-1), min(len(pages), idx+3)))
                        main_data = _parse_main_tables(tables, config.MAIN_KEYWORDS, unit_divisor)
                        data.update(main_data)
                        break
            break

        # Step 2: 提取合并利润表（先表格提取，精度不够时用文本解析补漏）
        profit_data = {}

        # 2a: 表格提取（精度高，适合有表格式样的年报）
        for pi in range(len(pages)):
            txt = texts[pi]
            if '目 录' in txt and '合并利润表' in txt:
                continue
            if '合并利润表' not in txt:
                continue
            for offset in [0, 1, -1]:
                idx = pi + offset
                if 0 <= idx < len(pages):
                    table = _find_profit_table(pages[idx])
                    if not table:
                        continue
                    unit_divisor = _detect_unit(texts, range(max(0, idx-1), min(len(pages), idx+3)))
                    cont = _find_continuation(pages, idx + 1)
                    if cont:
                        table = table + cont
                    profit_data = _parse_profit_table(table, config.PROFIT_KEYWORDS, unit_divisor)
                    break
            if profit_data:
                break

        # 2b: 如果表格提取缺失关键指标（如银行无法解析表格），用文本解析补漏
        text_data = {}
        section = _find_profit_section(texts)
        if section:
            unit_divisor = _detect_unit(texts, range(max(0, section[0]-1), min(len(pages), section[1]+2)))
            text_data = _parse_profit_text(texts, section, unit_divisor)
            # 合并：表格优先，文本补充表格缺失的项
            for k, v in text_data.items():
                if k not in profit_data:
                    profit_data[k] = v

        data.update(profit_data)

    return data


# ── 跨年汇总 ────────────────────────────────────────────


def _calc_derived(df):
    d = df.copy()
    if '营业收入' in d.columns and '营业成本' in d.columns:
        d['毛利率'] = ((d['营业收入'] - d['营业成本']) / d['营业收入'] * 100).round(2)
    if '净利润' in d.columns and '营业收入' in d.columns:
        d['净利率'] = (d['净利润'] / d['营业收入'] * 100).round(2)
    return d


def collect_all_years(code, years=5):
    pdfs = find_pdfs(code)
    if not pdfs:
        print(f'[错误] 未找到 {code} 的年报，请先用 fetch_reports 下载')
        return pd.DataFrame()

    all_data = {}
    for year, path in pdfs:
        if len(all_data) >= years:
            break
        data = process_pdf(path)
        if data:
            all_data[year] = data
            print(f'  [OK] {year}年：提取到 {len(data)} 项指标（{len(all_data)}/{years}）')

    if not all_data:
        print(f'[错误] 未能从年报中提取到有效数据')
        return pd.DataFrame()

    df = pd.DataFrame.from_dict(all_data, orient='index')
    df.index.name = '年份'
    df.index = df.index.astype(int)
    df = df.sort_index()
    df = _calc_derived(df)

    cols = [c for c in config.ALL_METRICS if c in df.columns]
    return df[cols]
