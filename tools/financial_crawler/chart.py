"""matplotlib 图表绘制——四张财报 PNG。"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as mticker
import pandas as pd

from tools.financial_crawler import config


def _setup_font():
    """自动查找中文字体，避免硬编码平台特定字体名。"""
    _CN_FONTS = [
        "Microsoft YaHei", "SimHei", "DengXian", "Source Han Sans SC",
        "Noto Sans CJK SC", "PingFang SC", "STHeiti", "DejaVu Sans",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in _CN_FONTS:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return
    # fallback: 任意含 CJK 字符的字体
    for f in fm.fontManager.ttflist:
        if any("一" <= c <= "鿿" for c in f.name):
            plt.rcParams["font.sans-serif"] = [f.name]
            plt.rcParams["axes.unicode_minus"] = False
            return
    print("[警告] 未找到中文字体，图表中文可能显示为方框")

_setup_font()


def _save(fig: plt.Figure, path: Path) -> None:
    fig.savefig(str(path), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _bar_labels(ax: plt.Axes, fmt: str = "{:.0f}") -> None:
    for p in ax.patches:
        if p.get_height() != 0:
            va = "bottom" if p.get_height() > 0 else "top"
            offset = 8 if p.get_height() > 0 else -8
            ax.annotate(
                fmt.format(p.get_height()),
                (p.get_x() + p.get_width() / 2, p.get_height()),
                ha="center", va=va, fontsize=7, color="#333333",
                xytext=(0, offset), textcoords="offset points",
            )


def _growth_rate(series: pd.Series) -> pd.Series:
    """计算同比增长率（%），数据按年份倒序传入。"""
    rev = series.dropna().astype(float)
    if len(rev) < 2:
        return pd.Series(index=series.index)
    # 倒序：索引0是最近一年，索引1是前一年
    # pct_change(-1)：后一年/前一年
    growth = rev.pct_change(-1) * 100
    return growth.reindex(series.index)


def plot_profit(df: pd.DataFrame, output_path: Path) -> bool:
    """利润表：营收、归母净利润（柱状）+ 增长率（折线，副Y轴）。"""
    if df.empty:
        return False

    fig, ax1 = plt.subplots(figsize=config.FIG_SIZE)
    years = df.index.astype(str)
    x = range(len(years))
    colors = config.PROFIT_COLORS

    # 主Y：营收 + 归母净利润 分组柱状
    main_cols = [c for c in df.columns if c in ("营业收入", "毛利", "归母净利润", "净利润")]
    if not main_cols:
        main_cols = df.columns.tolist()[:2]
    n = len(main_cols)
    width = 0.3
    for i, col in enumerate(main_cols):
        ax1.bar(
            [xi + (i - (n - 1) / 2) * width for xi in x],
            df[col].astype(float).values, width=width,
            color=colors[i % len(colors)], label=col, edgecolor="white", linewidth=0.5,
        )

    ax1.set_ylabel("亿元", fontsize=11)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(years)
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))

    # 副Y：营收增长率
    rev_col = next((c for c in ("营业收入", "营收增长率(%)") if c in df.columns), None)
    if rev_col and "营收增长率(%)" not in df.columns:
        growth = _growth_rate(df[rev_col])
        ax2 = ax1.twinx()
        ax2.plot(x, growth.values, marker="D", color=colors[-1], linewidth=1.5,
                 linestyle="--", label="营收增长率(%)", markersize=4)
        for xi, g in zip(x, growth.values):
            if pd.notna(g):
                ax2.annotate(f"{g:.1f}%", (xi, g), textcoords="offset points",
                            xytext=(0, -12), ha="center", fontsize=7, color=colors[-1])
        ax2.set_ylabel("增长率(%)", fontsize=11)
        ax2.legend(loc="upper left", frameon=True, fancybox=True, fontsize=9)
    elif "营收增长率(%)" in df.columns:
        ax2 = ax1.twinx()
        ax2.plot(x, df["营收增长率(%)"].astype(float).values, marker="D",
                 color=colors[-1], linewidth=1.5, linestyle="--",
                 label="营收增长率(%)", markersize=4)
        ax2.set_ylabel("增长率(%)", fontsize=11)
        ax2.legend(loc="upper left", frameon=True, fancybox=True, fontsize=9)

    _bar_labels(ax1, "{:.1f}")
    ax1.set_title("利润表", fontsize=14, fontweight="bold", pad=15)
    ax1.set_xlabel("报告期", fontsize=11)
    lines1, labels1 = ax1.get_legend_handles_labels()
    ax1.legend(lines1, labels1, loc="upper right", frameon=True, fancybox=True, fontsize=9)
    ax1.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    _save(fig, output_path)
    return True


def plot_balance(df: pd.DataFrame, output_path: Path) -> bool:
    """资产负债表：总资产/总负债/股东权益（柱状）+ 资产负债率（副Y）。"""
    if df.empty:
        return False

    fig, ax1 = plt.subplots(figsize=config.FIG_SIZE)
    years = df.index.astype(str)
    x = range(len(years))

    # 主Y：绝对值类指标（柱状）
    bar_cols = [c for c in df.columns if "率" not in c and "比" not in c]
    if bar_cols:
        n = len(bar_cols)
        width = 0.25
        for i, col in enumerate(bar_cols):
            ax1.bar(
                [xi + (i - (n - 1) / 2) * width for xi in x],
                df[col].astype(float).values, width=width,
                color=config.BALANCE_COLORS[i % len(config.BALANCE_COLORS)],
                label=col, edgecolor="white", linewidth=0.5,
            )
        _bar_labels(ax1, "{:.1f}")

    ax1.set_ylabel("亿元" if bar_cols else "", fontsize=11)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(years)
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))

    # 副Y：比率类指标
    ratio_cols = [c for c in df.columns if "率" in c or "比" in c]
    if ratio_cols:
        ax2 = ax1.twinx()
        for col in ratio_cols:
            ax2.plot(x, df[col].astype(float).values, marker="D", linewidth=1.5,
                     label=col, markersize=4)
        ax2.set_ylabel("%", fontsize=11)
        ax2.legend(loc="upper left", frameon=True, fancybox=True, fontsize=9)

    ax1.set_title("资产负债表", fontsize=14, fontweight="bold", pad=15)
    ax1.set_xlabel("报告期", fontsize=11)
    if bar_cols:
        lines1, labels1 = ax1.get_legend_handles_labels()
        ax1.legend(lines1, labels1, loc="upper right", frameon=True, fancybox=True, fontsize=9)
    ax1.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    _save(fig, output_path)
    return True


def plot_cashflow(df: pd.DataFrame, output_path: Path) -> bool:
    """现金流量表：经营/投资/融资现金流 柱状图。"""
    if df.empty:
        return False

    fig, ax = plt.subplots(figsize=config.FIG_SIZE)
    years = df.index.astype(str)
    n = len(df.columns)
    width = 0.25
    x = range(len(years))
    colors = config.CASHFLOW_COLORS[:n]

    for i, col in enumerate(df.columns):
        ax.bar(
            [xi + (i - (n - 1) / 2) * width for xi in x],
            df[col].astype(float).values, width=width,
            color=colors[i], label=col, edgecolor="white", linewidth=0.5,
        )

    _bar_labels(ax, "{:.1f}")
    ax.set_title("现金流量表", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("报告期", fontsize=11)
    ax.set_ylabel("亿元", fontsize=11)
    ax.set_xticks(list(x))
    ax.set_xticklabels(years)
    ax.legend(frameon=True, fancybox=True, fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    fig.tight_layout()
    _save(fig, output_path)
    return True


def plot_indicators(df: pd.DataFrame, output_path: Path) -> bool:
    """财务指标：ROE、毛利率、净利率 折线图。"""
    if df.empty:
        return False

    fig, ax = plt.subplots(figsize=config.FIG_SIZE)
    years = df.index.astype(str)
    colors = config.INDICATOR_COLORS

    for i, col in enumerate(df.columns):
        ax.plot(years, df[col].astype(float).values, marker="s",
                linewidth=2, color=colors[i % len(colors)], label=col)
        for xi, y in enumerate(df[col].astype(float).values):
            if pd.notna(y):
                ax.annotate(f"{y:.1f}", (xi, y), textcoords="offset points",
                            xytext=(0, 10), ha="center", fontsize=7,
                            color=colors[i % len(colors)])

    ax.set_title("财务指标（%）", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("报告期", fontsize=11)
    ax.legend(frameon=True, fancybox=True, fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    fig.tight_layout()
    _save(fig, output_path)
    return True


def plot_hk_overview(balance: pd.DataFrame, cashflow: pd.DataFrame, output_path: Path) -> bool:
    """港股概览：资产负债率 + 流动比率 + 每股经营现金流 折线图。"""
    if balance.empty and cashflow.empty:
        return False

    fig, ax1 = plt.subplots(figsize=config.FIG_SIZE)

    # 左侧 Y：资产负债率、流动比率
    has_balance = False
    if not balance.empty:
        for col in balance.columns:
            vals = balance[col].astype(float)
            ax1.plot(balance.index.astype(str), vals.values, marker="s",
                     linewidth=2, label=col, markersize=6)
            for xi, v in enumerate(vals.values):
                if pd.notna(v):
                    ax1.annotate(f"{v:.1f}", (xi, v), textcoords="offset points",
                                xytext=(0, 10), ha="center", fontsize=7)
        has_balance = True

    ax1.set_ylabel("比率", fontsize=11)
    ax1.grid(axis="y", alpha=0.3)

    # 右侧 Y：每股经营现金流
    if not cashflow.empty and "每股经营现金流(元)" in cashflow.columns:
        ax2 = ax1.twinx()
        vals = cashflow["每股经营现金流(元)"].astype(float)
        ax2.plot(cashflow.index.astype(str), vals.values, marker="D",
                 linewidth=2, linestyle="--", color="#E74C3C",
                 label="每股经营现金流(元)", markersize=6)
        for xi, v in enumerate(vals.values):
            if pd.notna(v):
                ax2.annotate(f"{v:.1f}", (xi, v), textcoords="offset points",
                            xytext=(0, -12), ha="center", fontsize=7, color="#E74C3C")
        ax2.set_ylabel("元", fontsize=11)
        ax2.legend(loc="upper left", frameon=True, fancybox=True, fontsize=9)

    ax1.set_title("港股概览", fontsize=14, fontweight="bold", pad=15)
    ax1.set_xlabel("报告期", fontsize=11)
    if has_balance:
        lines1, labels1 = ax1.get_legend_handles_labels()
        ax1.legend(lines1, labels1, loc="upper right", frameon=True, fancybox=True, fontsize=9)
    fig.tight_layout()
    _save(fig, output_path)
    return True


# 按市场区分的图表配置
_MARKET_PLOTS = {
    "a": {
        "profit": ("profit.png", plot_profit),
        "balance": ("balance.png", plot_balance),
        "cashflow": ("cashflow.png", plot_cashflow),
        "indicators": ("indicators.png", plot_indicators),
    },
    "hk": {
        "profit": ("profit.png", plot_profit),
        "indicators": ("indicators.png", plot_indicators),
    },
    "us": {
        "profit": ("profit.png", plot_profit),
        "indicators": ("indicators.png", plot_indicators),
    },
}


def plot_all(data: dict[str, pd.DataFrame], output_dir: Path, market: str = "a") -> list[str]:
    """生成图表（按市场区分），返回已生成的文件路径列表。"""
    plots = _MARKET_PLOTS.get(market, _MARKET_PLOTS["a"])
    generated = []
    for name, (fname, func) in plots.items():
        df = data.get(name)
        if df is None or df.empty:
            print(f"  [跳过] {name}：无数据")
            continue
        path = output_dir / fname
        if func(df, path):
            generated.append(str(path))
            print(f"  [生成] {path.name}")

    # 港股额外生成概览图
    if market == "hk":
        balance = data.get("balance", pd.DataFrame())
        cashflow = data.get("cashflow", pd.DataFrame())
        overview_path = output_dir / "hk_overview.png"
        if plot_hk_overview(balance, cashflow, overview_path):
            generated.append(str(overview_path))
            print(f"  [生成] {overview_path.name}")

    return generated
