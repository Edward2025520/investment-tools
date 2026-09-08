"""估值工具图表：quality 逐年净利/OCF/FCF 分组柱。中文字体照 industry_profit 配置。"""

from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt


def _setup_font():
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
    for f in fm.fontManager.ttflist:
        if any("一" <= c <= "鿿" for c in f.name):
            plt.rcParams["font.sans-serif"] = [f.name]
            plt.rcParams["axes.unicode_minus"] = False
            return


_setup_font()

_SERIES = [("归母净利", "#2E86C1"), ("OCF", "#27AE60"), ("FCF(经营近似)", "#E67E22")]


def _na(v) -> bool:
    import pandas as pd
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def plot_intrinsic(res: dict, output_path: Path, title: str = "") -> None:
    """每股内在价值随 WACC 变化的 3 条增速线 + 现价横线 + 每股净资产地板。

    假设用文本框标注在左上角，不遮挡曲线。区间只给在 CSV 的 wacc×tg 网格，
    此处不画热力图（产物以表为主）。
    """
    fig, ax = plt.subplots(figsize=(9.5, 6.0))
    colors = ["#2E86C1", "#C0392B", "#27AE60"]
    for curve, color in zip(res["curves"], colors):
        label = f"显性增速 {curve['g']*100:.0f}%"
        ax.plot(curve["x"], curve["y"], marker="o", markersize=3,
                color=color, linewidth=2, label=label)

    price = res.get("price")
    if price:
        ax.axhline(price, color="#555555", linestyle="--", linewidth=1.2)
        ax.text(0.985, price, f"现价 {price:.0f} 元", ha="right", va="bottom",
                transform=ax.get_yaxis_transform(), fontsize=10, color="#555555")
    bv = res.get("bvps")
    if bv:
        ax.axhline(bv, color="#8E44AD", linestyle=":", linewidth=1.2)
        ax.text(0.015, bv, f"每股净资产 {bv:.0f} 元(下限参考)", ha="left", va="bottom",
                transform=ax.get_yaxis_transform(), fontsize=10, color="#8E44AD")

    ax.set_xlabel("折现率 WACC")
    ax.set_ylabel("每股内在价值（元）")
    ax.set_xticks(res["axis_w"])
    ax.set_xticklabels([f"{w*100:.0f}%" for w in res["axis_w"]])
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=9.5, frameon=False)

    note = (f"FCF0 = {res['fcf0']:.0f} 亿（{res['base_year']}）· 永续增速 {res['term_g']*100:.0f}%"
            f" · 显性期 {res['years']} 年")
    if res.get("net_debt") is not None:
        note += f" · 净债务 {res['net_debt']:.0f} 亿"
    ax.text(0.015, 0.985, note, transform=ax.transAxes, fontsize=9, color="#595959",
            va="top", bbox=dict(boxstyle="round,pad=0.4", fc="#F2F2F2", ec="none"))
    ax.set_title(title, fontsize=12.5, fontweight="bold", pad=12)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_relative(panes: list, output_path: Path, title: str = "") -> None:
    """同行分布直方（左右两栏，各一个指标）+ 目标竖线 + 中位/分位标注。

    pane: {label, vals[正数], target|None, median, p25, p75, rank%|None, n_valid}。
    无评价句；仅把"公司在同行里处于什么位置"画清楚。
    """
    n = len(panes)
    fig, axes = plt.subplots(1, n, figsize=(6.0 * n, 5.2), squeeze=False)
    for ax, pane in zip(axes[0], panes):
        vals = [v for v in pane["vals"] if v is not None and v > 0]
        lo = min(vals) if vals else 1
        hi = max(vals) if vals else 10
        if lo <= 0:
            lo = 1e-9
        bins = np.geomspace(lo / 1.12, hi * 1.12, 18)
        if len(set(np.round(bins, 10))) < 3:  # 样本太少/值几乎相等，退化成对数底线
            bins = np.geomspace(max(lo, 1e-9) / 1.2, hi * 1.2, 6)
        ax.hist(vals, bins=bins, color="#5DADE2", alpha=0.75, edgecolor="white")
        ax.set_xscale("log")
        for label, v, color, ls in (("中位", pane.get("median"), "#2E86C1", "-"),
                                    ("P25", pane.get("p25"), "#85C1E9", "--"),
                                    ("P75", pane.get("p75"), "#85C1E9", "--")):
            if v is not None:
                ax.axvline(v, color=color, linestyle=ls, linewidth=1.1, alpha=0.8)
        ax.text(0.015, 0.985, f"中位 {pane.get('median') or '-'}",
                transform=ax.transAxes, va="top", fontsize=9.5, color="#2E86C1")
        target = pane.get("target")
        rank = pane.get("rank")
        if target is not None:
            ax.axvline(target, color="#C0392B", linewidth=2)
            tag = f"目标 {target:.1f}" + (f"\n分位 {rank:.0f}%（越低越便宜）" if rank is not None else "")
            ax.text(0.985, 0.985, tag, transform=ax.transAxes, ha="right", va="top",
                    fontsize=9.5, color="#C0392B", fontweight="bold")
        else:
            ax.text(0.985, 0.985, "目标无正倍数（亏损），无法定位分位",
                    transform=ax.transAxes, ha="right", va="top", fontsize=9,
                    color="#C0392B")
        ax.set_title(pane["label"], fontsize=11.5, fontweight="bold")
        ax.set_xlabel("对数刻度")
        ax.set_ylabel("同行家数")
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)
    fig.suptitle(title, fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(str(output_path), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_quality(res: dict, output_path: Path, title: str = "") -> None:
    rows = res["rows"]
    years = [r["年份"] for r in rows]
    n = len(years)
    x = range(n)
    width = 0.26
    fig, ax = plt.subplots(figsize=(max(7, 0.9 * n + 4), 5.4))

    for j, (key, color) in enumerate(_SERIES):
        vals = [r.get(key) for r in rows]
        off = (j - 1) * width
        bars = ax.bar([xi + off for xi in x], [0 if _na(v) else v for v in vals],
                      width, color=color, label=key)
        for b, val in zip(bars, vals):
            if _na(val):
                continue
            h = float(val)
            ax.annotate(f"{h:.0f}", (b.get_x() + b.get_width() / 2, h),
                        ha="center", va="bottom" if h >= 0 else "top",
                        xytext=(0, 2 if h >= 0 else -2), textcoords="offset points",
                        fontsize=8, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels([str(y) for y in years])
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    ax.set_ylabel("亿元")
    ax.legend(loc="best", fontsize=9.5, frameon=False)
    ax.set_title(title, fontsize=12.5, fontweight="bold", pad=12)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
