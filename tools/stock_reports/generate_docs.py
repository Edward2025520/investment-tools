"""生成用户操作手册 .docx。"""

from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE

OUTPUT_PATH = Path(__file__).resolve().parent / "A股年报爬取工具使用说明.docx"

_CODE_FONT = "Consolas"
_MAIN_COLOR = RGBColor(0x1A, 0x73, 0xE8)  # 蓝色


def _add_code_block(doc: Document, code: str) -> None:
    """添加代码块（灰色背景，等宽字体）。"""
    for i, line in enumerate(code.strip().split("\n")):
        p = doc.add_paragraph()
        p.style = doc.styles["Code"]
        run = p.add_run(line.strip())
        run.font.name = _CODE_FONT
        run.font.size = Pt(10)
        if line.startswith("#"):
            run.font.color.rgb = RGBColor(0x00, 0x80, 0x00)


def _add_table_row(table, cells_text: list[str], is_header: bool = False):
    row = table.add_row()
    for i, text in enumerate(cells_text):
        cell = row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(text)
        run.font.size = Pt(10)
        if is_header:
            run.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            from docx.oxml.ns import qn
            shading = cell._element.get_or_add_tcPr()
            shading_elm = shading.makeelement(qn("w:shd"), {
                qn("w:fill"): "1A73E8",
                qn("w:val"): "clear",
            })
            shading.append(shading_elm)


def build_doc() -> Path:
    doc = Document()

    # ── 样式 ──
    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.font.size = Pt(11)
    style.paragraph_format.line_spacing = 1.35

    # 代码块样式
    code_style = doc.styles.add_style("Code", WD_STYLE_TYPE.PARAGRAPH)
    code_style.font.size = Pt(10)
    code_style.font.name = _CODE_FONT
    code_style.paragraph_format.space_before = Pt(0)
    code_style.paragraph_format.space_after = Pt(0)
    code_style.paragraph_format.line_spacing = 1.2

    # ── 封面 ──
    for _ in range(6):
        doc.add_paragraph()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("A 股年报爬取工具")
    run.font.size = Pt(28)
    run.font.color.rgb = _MAIN_COLOR
    run.bold = True

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("使用说明")
    run.font.size = Pt(18)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_paragraph()
    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = info.add_run("数据源：巨潮资讯网（cninfo.com.cn）")
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    doc.add_page_break()

    # ── 目录占位 ──
    toc = doc.add_paragraph()
    run = toc.add_run("（在 Word 中按 Ctrl+A → F9 刷新目录）")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    # ── 1. 概述 ──
    doc.add_heading("1  概述", level=1)
    doc.add_paragraph(
        "本工具用于从巨潮资讯网按需下载 A 股上市公司年度报告（PDF 格式）。"
        "输入股票代码，自动获取最近 N 年的年报原文，保存到本地。"
    )
    doc.add_paragraph("适用人群：价值投资者、证券分析人员、上市公司研究人员。")
    doc.add_paragraph("""
核心特性：
  • 异步并发下载，速度比串行请求快 3-5 倍
  • 自动跳过已下载文件，避免重复
  • 按年度去重，同一年的多次更新只保留最新版
  • 文件名格式统一：公司简称_年份_年度报告.pdf
    """.strip())

    # ── 2. 环境要求 ──
    doc.add_heading("2  环境要求", level=1)
    doc.add_paragraph("本工具依赖以下 Python 环境：")

    table = doc.add_table(rows=0, cols=3)
    _add_table_row(table, ["项目", "要求", "说明"], is_header=True)
    _add_table_row(table, ["Python", "3.9+", "推荐通过 Anaconda 管理"])
    _add_table_row(table, ["httpx", "≥0.28", "异步 HTTP 客户端"])
    _add_table_row(table, ["tqdm", "≥4.67", "进度条显示"])
    doc.add_paragraph()

    # ── 3. 安装 ──
    doc.add_heading("3  安装", level=1)

    doc.add_heading("3.1  安装 Python 依赖", level=2)
    _add_code_block(doc, """# 激活你的 conda 环境
conda activate ai

# 安装依赖
pip install httpx tqdm""")

    doc.add_heading("3.2  下载工具代码", level=2)
    doc.add_paragraph(
        "将本项目中的 tools/stock_reports/ 目录复制到你的工作目录下。"
        "目录结构："
    )
    _add_code_block(doc, """your_project/
  tools/
    stock_reports/
      __init__.py
      fetch_reports.py      # CLI 入口
      cninfo_client.py      # 巨潮 API 封装
      utils.py              # 路径与文件工具
  data/
    reports/                # 年报存放目录（自动创建）""")

    # ── 4. 使用方法 ──
    doc.add_heading("4  使用方法", level=1)

    doc.add_heading("4.1  基本用法", level=2)
    doc.add_paragraph("下载最近 5 年的年报（默认）：")
    _add_code_block(doc, """python tools/stock_reports/fetch_reports.py 000001""")

    doc.add_paragraph("指定股票代码时，以下格式均可自动识别：")
    _add_code_block(doc, """# 纯数字代码
python tools/stock_reports/fetch_reports.py 000001

# 带市场前缀
python tools/stock_reports/fetch_reports.py sz000001
python tools/stock_reports/fetch_reports.py sh600519""")

    doc.add_heading("4.2  自定义参数", level=2)
    doc.add_paragraph("控制下载年份数：")
    _add_code_block(doc, """# 下载最近 8 年
python tools/stock_reports/fetch_reports.py 600519 --years 8""")

    doc.add_paragraph("指定输出目录：")
    _add_code_block(doc, """python tools/stock_reports/fetch_reports.py 002142 --output ./my_reports""")

    doc.add_paragraph("强制重新下载（覆盖已有文件）：")
    _add_code_block(doc, """python tools/stock_reports/fetch_reports.py 000001 --force""")

    doc.add_heading("4.3  组合使用", level=2)
    _add_code_block(doc, """# 下载平安银行 10 年年报，存到自定义目录
python tools/stock_reports/fetch_reports.py 000001 --years 10 --output ./my_reports

# 重新下载茅台 3 年年报
python tools/stock_reports/fetch_reports.py 600519 --years 3 --force""")

    # ── 5. 输出说明 ──
    doc.add_heading("5  输出说明", level=1)

    doc.add_paragraph("运行完成后，文件保存在 data/reports/{股票代码}/ 目录下：")
    _add_code_block(doc, """data/reports/
  ├── 000001/
  │   ├── 平安银行_2021_年度报告.pdf
  │   ├── 平安银行_2022_年度报告.pdf
  │   ├── 平安银行_2023_年度报告.pdf
  │   ├── 平安银行_2024_年度报告.pdf
  │   └── 平安银行_2025_年度报告.pdf
  └── 600519/
      └── ...""")

    p = doc.add_paragraph()
    run = p.add_run("输出摘要示例：")
    run.bold = True
    _add_code_block(doc, """=== 000001 年报下载完成 ===
  总计: 5 份
  ✓ 成功: 5 份
       2025年, 2024年, 2023年, 2022年, 2021年""")

    # ── 6. 常见问题 ──
    doc.add_heading("6  常见问题", level=1)

    faq = [
        (
            "运行提示「python: can't open file」？",
            "说明你不在项目目录下。先 cd 到项目根目录，"
            "或者输入完整路径：python tools/stock_reports/fetch_reports.py 股票代码。",
        ),
        (
            "直接运行 .py 文件打开了 PyCharm / IDE？",
            "Windows 的 .py 文件关联到了 IDE。务必在命令前加 python 来执行，"
            "即 python fetch_reports.py 而不是直接 fetch_reports.py。",
        ),
        (
            "下载失败或报错怎么办？",
            "工具内置了重试机制（失败自动重试 3 次）。如果仍然失败，"
            "请检查网络连接，然后重新运行命令。已下载的文件不会重复下载。",
        ),
        (
            "提示「未找到符合条件的年报」",
            "可能原因：①股票代码输入错误；②该股票确实没有发布过年报（极少见）；"
            "③该股票刚上市不久，数据量较少。",
        ),
        (
            "下载速度慢",
            "工具使用异步并发下载（最多 3 个并发），速度受限于巨潮服务器的响应时间。"
            "正常情况下 5 份年报约 5-15 秒。如果持续很慢，请检查网络连接。",
        ),
        (
            "年报年份不对（比如要 2024 年的却没下载）",
            "巨潮的年报在发布时可能有延迟。如果确认巨潮官网已发布但工具未抓到，"
            "可以尝试增加 --years 参数多取几页。",
        ),
        (
            "提示找不到模块？",
            "请确认已安装所需依赖：pip install httpx tqdm。如果使用虚拟环境，"
            "确保激活了正确的环境后再运行。",
        ),
    ]
    for q, a in faq:
        doc.add_heading(q, level=2)
        doc.add_paragraph(a)

    doc.add_page_break()
    # ── 7. 技术说明 ──
    doc.add_heading("7  技术说明", level=1)
    doc.add_paragraph("""
  • 数据来源：巨潮资讯网（cninfo.com.cn），证监会指定的上市公司信息披露平台
  • 查询接口：POST /new/fulltextSearch/full（时间倒序，分页获取）
  • 下载地址：http://static.cninfo.com.cn/{adjunctUrl}
  • 重试策略：失败自动重试 3 次，间隔递增（1s → 2s）
  • 并发控制：最多 3 个 PDF 同时下载，避免对服务器造成压力
  • 文件命名：公司简称_年份_年度报告.pdf（如平安银行_2024_年度报告.pdf）
    """.strip())

    # 保存
    doc.save(str(OUTPUT_PATH))
    return OUTPUT_PATH


if __name__ == "__main__":
    path = build_doc()
    print(f"文档已生成：{path}")
