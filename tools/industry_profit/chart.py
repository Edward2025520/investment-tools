"""行业对比条形图：公司 vs 行业平均（每指标一张小图）。"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

from tools.industry_profit import config


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

_CATS = ["公司", "同行平均", "同行加权"]
_COLORS = ["#C0392B", "#2E86C1", "#8E44AD"]


def plot_compare(stats: dict, output_path: Path, title: str = "") -> None:
    """绘制 2×2 条形图。

    title 为顶部大标题（如"贵州茅台（600519） vs 白酒行业，42 家样本"），
    明确对比对象与行业。每格一个指标：三根柱子 = 公司 / 同行简单平均 /
    同行市值加权，排位直接写进格子标题（如"净利率 · 第 27/42 名"），
    不占图表区、不遮挡柱子数字。行业无此指标时整格显示占位文字。
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 9.5))
    axes = axes.flatten()

    for ax, m in zip(axes, config.METRICS):
        s = stats[m["key"]]
        if not s["n"] or s["target"] is None:
            ax.set_title(m["label"], fontsize=15, fontweight="bold")
            ax.text(0.5, 0.5, "该行业无此指标", ha="center", va="center",
                    transform=ax.transAxes, fontsize=13, color="#888888")
            ax.axis("off")
            continue

        rank, n = s["rank"], s["n"]
        sub = "" if rank is None else f" · 第 {rank}/{n} 名"
        ax.set_title(m["label"] + sub, fontsize=14, fontweight="bold", pad=14)

        vals = [s["target"], s["simple"], s["weighted"]]
        labels = ["" if v is None else f"{v:.1f}" for v in vals]
        bars = ax.bar(_CATS, [0 if v is None else v for v in vals],
                      color=_COLORS, edgecolor="white", linewidth=0.5, width=0.55)
        for b, lab in zip(bars, labels):
            if not lab:
                continue
            h = b.get_height()
            va = "bottom" if h >= 0 else "top"
            ax.annotate(lab, (b.get_x() + b.get_width() / 2, h), ha="center", va=va,
                        xytext=(0, 3 if h >= 0 else -3), textcoords="offset points",
                        fontsize=10, fontweight="bold")

        ax.axhline(0, color="gray", linewidth=0.8)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)

    fig.legend(
        [plt.Rectangle((0, 0), 1, 1, color=c) for c in _COLORS],
        ["红色 = 你输入的公司", "蓝色 = 同行简单平均（一视同仁）", "紫色 = 同行市值加权（大公司占比更重）"],
        loc="lower center", ncol=3, fontsize=10.5, frameon=False,
        bbox_to_anchor=(0.5, -0.01), handlelength=1.2, handleheight=1.2,
    )
    fig.suptitle(title, fontsize=15, fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0.09, 1, 0.97])
    fig.savefig(str(output_path), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
