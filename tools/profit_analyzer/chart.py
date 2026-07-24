"""matplotlib 多子图趋势图 — 动态布局"""

import matplotlib
matplotlib.use('Agg')  # 无头模式

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.font_manager as fm
import pandas as pd
from pathlib import Path

from tools.profit_analyzer import config

# ── 中文字体 ──────────────────────────────────────────

_CN_FONTS = [
    'Microsoft YaHei', 'SimHei', 'DengXian', 'Source Han Sans SC',
    'Noto Sans CJK SC', 'PingFang SC', 'STHeiti',
]


def _setup_font():
    """查找可用中文字体并设为 rcParams。"""
    available = {f.name for f in fm.fontManager.ttflist}
    for name in _CN_FONTS:
        if name in available:
            plt.rcParams['font.sans-serif'] = [name, 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
            return name
    # fallback: 扫描系统字体目录
    for f in fm.fontManager.ttflist:
        if any(c > '一' for c in f.name):
            plt.rcParams['font.sans-serif'] = [f.name, 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
            return f.name
    print('[警告] 未找到中文字体，图表中文可能显示为方框')
    return None


# ── 子图定义 ──────────────────────────────────────────

class SubplotDef:
    """单个子图的配置。"""

    def __init__(self, title, required,
                 kind='line', ylabel='',
                 secondary=None):
        self.title = title
        self.required = required
        self.kind = kind
        self.ylabel = ylabel
        self.secondary = secondary or []


def _build_subplots(df):
    """根据 DataFrame 可用的列动态构建子图列表。"""
    cols = set(df.columns)
    plots = []

    # 1. 营收 + 增速（柱状+折线）
    if '营业收入' in cols:
        plots.append(SubplotDef(
            '营业收入与增速', ['营业收入'],
            kind='bar_line', ylabel='亿元',
        ))

    # 2. 毛利率 + 净利率（折线）
    if '毛利率' in cols:
        plots.append(SubplotDef(
            '毛利率与净利率', ['毛利率', '净利率'],
            kind='line', ylabel='%',
        ))

    # 3. 三项费用率（折线）
    sales_metrics = [m for m in ['销售费用', '管理费用', '研发费用', '财务费用'] if m in cols]
    if len(sales_metrics) >= 2:
        required = sales_metrics
        plots.append(SubplotDef(
            '费用明细（亿元）', required,
            kind='line', ylabel='亿元',
        ))

    # 4. 归母净利润 + 扣非净利润（折线）
    profit_cols = [m for m in ['归母净利润', '扣非净利润'] if m in cols]
    if profit_cols:
        plots.append(SubplotDef(
            '归母净利润与扣非净利润', profit_cols,
            kind='line', ylabel='亿元',
        ))

    # 5. ROE（柱状图）
    if 'ROE' in cols:
        plots.append(SubplotDef(
            '加权平均净资产收益率(ROE)', ['ROE'],
            kind='bar', ylabel='%',
        ))

    return plots


# ── 绘图 ──────────────────────────────────────────────

def _plot_bar_line(ax, df: pd.DataFrame, defn: SubplotDef):
    """柱状图（营收）+ 折线（同比增速）。"""
    data = df['营业收入'].dropna()
    years = data.index.astype(str)
    values = data.values

    bars = ax.bar(years, values, color='#4A90D9', width=0.5, alpha=0.85)
    ax.set_ylabel(defn.ylabel, fontsize=10)

    # 增速折线（次坐标轴）
    if len(values) >= 2:
        growth = pd.Series(values).pct_change() * 100
        ax2 = ax.twinx()
        ax2.plot(years, growth.values, color='#E74C3C', marker='o',
                 linewidth=1.8, markersize=5)
        ax2.set_ylabel('同比增速(%)', fontsize=10, color='#E74C3C')
        ax2.tick_params(axis='y', labelcolor='#E74C3C')
        for i, g in enumerate(growth.values):
            if not pd.isna(g):
                ax2.annotate(f'{g:.1f}%', (years[i], g),
                             textcoords='offset points', xytext=(0, 8),
                             fontsize=8, ha='center', color='#E74C3C')

    # 在柱子上标数值
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f'{val:.1f}', ha='center', va='bottom', fontsize=8)


def _plot_lines(ax, df: pd.DataFrame, defn: SubplotDef):
    """多系列折线图。"""
    for col in defn.required:
        if col in df.columns:
            data = df[col].dropna()
            ax.plot(data.index.astype(str), data.values,
                    marker='o', linewidth=1.8, markersize=5, label=col)
    ax.set_ylabel(defn.ylabel, fontsize=10)
    ax.legend(fontsize=8, loc='best')


def _plot_bar(ax, df: pd.DataFrame, defn: SubplotDef):
    """柱状图（单系列）。"""
    for col in defn.required:
        if col in df.columns:
            data = df[col].dropna()
            years = data.index.astype(str)
            vals = data.values
            ax.bar(years, vals, color='#27AE60', width=0.5, alpha=0.85, label=col)
            for y, v in zip(years, vals):
                ax.text(y, v, f'{v:.1f}', ha='center', va='bottom', fontsize=9)
    ax.set_ylabel(defn.ylabel, fontsize=10)


# ── 入口 ──────────────────────────────────────────────

def generate_chart(df, code, stock_name='',
                   metrics_filter=None,
                   output_dir=None):
    """生成多子图趋势图并保存 PNG。"""
    _setup_font()

    if df.empty:
        print('[错误] 无数据，无法生成图表')
        return

    # 如果指定了筛选指标，只保留需要的
    plot_df = df.copy()
    if metrics_filter:
        keep = [c for c in metrics_filter if c in plot_df.columns]
        plot_df = plot_df[keep]

    # 构建子图
    plots = _build_subplots(plot_df)
    if not plots:
        print('[错误] 无可用的指标生成子图')
        return

    n = len(plots)
    cols = min(2, n)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(7 * cols, 4 * rows))
    axes = axes.flatten() if n > 1 else [axes]

    # 标题
    name = stock_name or f'{code}'
    year_range = f'{plot_df.index.min()}-{plot_df.index.max()}'
    fig.suptitle(f'{name}  利润表趋势分析 ({year_range})',
                 fontsize=14, fontweight='bold', y=0.98)

    for i, defn in enumerate(plots):
        ax = axes[i]
        if defn.kind == 'bar_line':
            _plot_bar_line(ax, plot_df, defn)
        elif defn.kind == 'bar':
            _plot_bar(ax, plot_df, defn)
        else:
            _plot_lines(ax, plot_df, defn)
        ax.set_title(defn.title, fontsize=11, pad=8)
        ax.tick_params(axis='x', rotation=30)
        ax.grid(axis='y', alpha=0.3)

    # 隐藏多余子图
    for i in range(n, len(axes)):
        axes[i].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    # 保存
    out_dir = Path(output_dir) if output_dir else config.DATA_DIR / code
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{code}_利润表趋势.png'
    fig.savefig(out_path, dpi=200, bbox_inches='tight')
    plt.close(fig)

    print(f'\n[OK] 图表已保存 → {out_path}')
    return str(out_path)
