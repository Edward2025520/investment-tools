"""报告产物：三张图 + Markdown 方法/结果文档。

图表以“分布与位置”为主，不表达优劣结论；文档明确声明不构成投资建议。
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tools.screen_csi500 import config
from tools.valuation.chart import _setup_font

_setup_font()

# 图2 的 y 轴裁剪范围：个别 ROE 深度为负的样本会把整幅压扁成一团
ROE_Y_LO, ROE_Y_HI = -20, 75

# 价值陷阱排查：PE 分位与 PB 分位背离多少，算“便宜的来源是盈利而非股价”
TRAP_GAP = 0.30


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"代码": str})
    # 明细 CSV 只留“通过/淘汰原因”文本列，内部布尔标记在报告侧派生
    df["_p1"] = df["第1层_排除"] == "通过"
    df["_p2"] = df["第2层_健康成长"] == "通过"
    df["_p3"] = df["第3层_估值"] == "通过"
    return df


def plot_valuation_distribution(df: pd.DataFrame, out: Path) -> None:
    """全样本“自身估值分位”直方，阈值线与候选叠标。"""
    vals = df["自身分位"].dropna()
    cand = df.loc[df["候选"] == "是", "自身分位"].dropna()
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(vals, bins=np.linspace(0, 1, 21), color="#5DADE2", alpha=0.8, edgecolor="white")
    if len(cand):
        ax.hist(cand, bins=np.linspace(0, 1, 21), color="#C0392B", alpha=0.9, edgecolor="white")
    ax.axvline(config.SELF_PCTL_MAX, color="#C0392B", linestyle="--", linewidth=1.5)
    ax.text(config.SELF_PCTL_MAX, ax.get_ylim()[1] * 0.95,
            f" 阈值 {config.SELF_PCTL_MAX:.0%}", color="#C0392B", va="top", fontsize=10)
    ax.set_xlabel("自身历史估值分位（PE 与 PB 取较低者，越低越便宜）")
    ax.set_ylabel("只数")
    ax.set_title(f"中证500 估值分位分布（n={len(vals)}，红=候选 {len(cand)}）",
                 fontsize=12.5, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(str(out / "valuation_distribution.png"), dpi=200,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_roe_vs_valuation(df: pd.DataFrame, out: Path) -> None:
    """ROE(3年均) vs 自身估值分位散点；通过前两层的点单独着色。

    y 轴裁到 [ROE_Y_LO, ROE_Y_HI]，被裁掉的只数写进标题，避免读者误判样本量。
    """
    d = df.dropna(subset=["ROE3年均", "自身分位"])
    fig, ax = plt.subplots(figsize=(9, 6))
    pass12 = d[d["_p1"] & d["_p2"]]
    ax.scatter(d["自身分位"], d["ROE3年均"], s=22, color="#B0BEC5", alpha=0.7,
               label="全样本")
    ax.scatter(pass12["自身分位"], pass12["ROE3年均"], s=30, color="#2E86C1", alpha=0.9,
               label="过前两层（健康+成长）")
    ax.axvline(config.SELF_PCTL_MAX, color="#C0392B", linestyle="--", linewidth=1)
    ax.axhline(config.ROE_MEAN_MIN, color="#27AE60", linestyle="--", linewidth=1)
    ax.set_xlabel("自身历史估值分位（越低越便宜）")
    ax.set_ylabel("ROE 近 3 年均值（%）")
    n_off = int((d["ROE3年均"] < ROE_Y_LO).sum())
    ax.set_ylim(ROE_Y_LO, ROE_Y_HI)
    title = "中证500：盈利水平 vs 估值分位（左下=又便宜又赚钱）"
    if n_off:
        title += f"\n（y 轴裁至 {ROE_Y_LO}%~{ROE_Y_HI}%，另有 {n_off} 只 ROE<{ROE_Y_LO}% 未显示）"
    ax.set_title(title, fontsize=12.5, fontweight="bold")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(str(out / "roe_vs_valuation.png"), dpi=200,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_industry_mix(df: pd.DataFrame, out: Path) -> None:
    """候选 vs 全样本的行业分布对比。"""
    allc = df["申万一级"].value_counts()
    cand = df.loc[df["候选"] == "是", "申万一级"].value_counts().reindex(allc.index).fillna(0)
    idx = np.arange(len(allc))
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(idx - 0.2, allc.values, 0.4, color="#AED6F1", label="全样本")
    ax.bar(idx + 0.2, cand.values, 0.4, color="#C0392B", label="候选")
    ax.set_xticks(idx)
    ax.set_xticklabels(allc.index, rotation=60, ha="right", fontsize=8.5)
    ax.set_ylabel("只数")
    ax.set_title("行业分布：全样本 vs 候选", fontsize=12.5, fontweight="bold")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(str(out / "industry_mix.png"), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _trap_gap(df: pd.DataFrame) -> pd.DataFrame:
    """候选按 gap = PB分位 − PE分位 排序。

    gap 为正：PE 分位低于 PB 分位，盈利相对净资产在高位，低 PE 是盈利撑的。
    gap 为负：股价/净资产分位更低，而盈利已在下行。
    """
    d = df[df["候选"] == "是"].copy().dropna(subset=["PE分位5年", "PB分位5年"])
    d["trap_gap"] = d["PB分位5年"] - d["PE分位5年"]
    return d.sort_values("trap_gap", ascending=False)


def plot_trap(df: pd.DataFrame, out: Path) -> None:
    """PE 分位 vs PB 分位散点：对角线上方＝低 PE 由盈利高位撑起。"""
    d = _trap_gap(df)
    a = d[d["trap_gap"] >= TRAP_GAP]
    b = d[d["trap_gap"] <= -TRAP_GAP]
    mid = d[d["trap_gap"].abs() < TRAP_GAP]

    fig, ax = plt.subplots(figsize=(8.5, 7))
    ax.plot([0, 1], [0, 1], color="#7F8C8D", linestyle="--", linewidth=1, zorder=1)
    for off in (TRAP_GAP, -TRAP_GAP):
        ax.plot([0, 1], [off, 1 + off], color="#BDC3C7", linestyle=":", linewidth=1, zorder=1)
    ax.scatter(mid["PE分位5年"], mid["PB分位5年"], s=34, color="#B0BEC5",
               label=f"两信号一致（{len(mid)} 只）", zorder=3)
    ax.scatter(a["PE分位5年"], a["PB分位5年"], s=52, color="#C0392B",
               label=f"PE 便宜、PB 不便宜（{len(a)} 只）", zorder=4)
    ax.scatter(b["PE分位5年"], b["PB分位5年"], s=52, color="#2E86C1",
               label=f"PB 便宜、PE 不便宜（{len(b)} 只）", zorder=4)
    for _, r in pd.concat([a, b]).iterrows():
        ax.annotate(r["名称"], (r["PE分位5年"], r["PB分位5年"]),
                    textcoords="offset points", xytext=(6, 4), fontsize=7.5, color="#2C3E50")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("PE 自身 5 年分位（越低＝PE 看着越便宜）")
    ax.set_ylabel("PB 自身 5 年分位（越低＝净资产角度越便宜）")
    ax.set_title("候选股：PE 分位 vs PB 分位\n"
                 "（对角线上方＝低 PE 由盈利高位撑起，下方＝盈利已在下行）",
                 fontsize=12, fontweight="bold")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(str(out / "trap_scatter.png"), dpi=200,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_markdown(df: pd.DataFrame, out: Path, meta: dict) -> Path:
    """方法章 + 结果章 + 局限声明，Markdown 供导出 docx。"""
    n = len(df)
    p1 = int(df["_p1"].sum())
    p2 = int((df["_p1"] & df["_p2"]).sum())
    cand = df[df["候选"] == "是"].sort_values("自身分位")
    tgroup = _trap_gap(df)
    tgroup_a = tgroup[tgroup["trap_gap"] >= TRAP_GAP]
    tgroup_b = tgroup[tgroup["trap_gap"] <= -TRAP_GAP]
    tgroup_mid = tgroup[tgroup["trap_gap"].abs() < TRAP_GAP]

    top_reasons = df.loc[~df["_p1"], "第1层_排除"].str.split("|").explode().value_counts()
    l2_reasons = df.loc[df["_p1"] & ~df["_p2"], "第2层_健康成长"].str.split("|").explode().value_counts()
    l3_reasons = df.loc[df["_p1"] & df["_p2"] & ~df["_p3"], "第3层_估值"].str.split("|").explode().value_counts()

    def bullets(s, k=6):
        return "\n".join(f"- {i}：{v} 只" for i, v in s.head(k).items()) or "- （无）"

    shown = ["代码", "名称", "申万一级", "ROE3年均", "现金含量3年", "营收CAGR", "扣非CAGR",
             "资产负债率", "自身分位", "同行分位"]

    def table(d):
        if d.empty:
            return "（无符合条件的候选）"
        head = "| " + " | ".join(shown) + " |"
        sep = "|" + "---|" * len(shown)
        body = []
        for _, r in d.iterrows():
            cells = []
            for c in shown:
                v = r.get(c)
                if c in ("自身分位", "同行分位") and pd.notna(v):
                    cells.append(f"{v:.0%}")
                elif pd.isna(v):
                    cells.append("-")
                else:
                    cells.append(str(v))
            body.append("| " + " | ".join(cells) + " |")
        return "\n".join([head, sep, *body])

    trap_cols = ["代码", "名称", "申万一级", "PE分位5年", "PB分位5年", "trap_gap",
                 "最新扣非同比", "上年扣非同比", "ROE3年均", "ROE3年最低"]

    def trap_table(d):
        if d.empty:
            return "（无）"
        head = ("| 代码 | 名称 | 申万一级 | PE分位 | PB分位 | gap | "
                "最新扣非同比 | 上年扣非同比 | ROE3年均 | ROE3年最低 |")
        sep = "|" + "---|" * len(trap_cols)
        body = []
        for _, r in d.iterrows():
            cells = []
            for c in trap_cols:
                v = r.get(c)
                if c in ("PE分位5年", "PB分位5年") and pd.notna(v):
                    cells.append(f"{v:.0%}")
                elif c == "trap_gap" and pd.notna(v):
                    cells.append(f"{v:+.2f}")
                elif pd.isna(v):
                    cells.append("-")
                elif c in ("最新扣非同比", "上年扣非同比"):
                    cells.append(f"{v:+.1f}%")
                else:
                    cells.append(str(v))
            body.append("| " + " | ".join(cells) + " |")
        return "\n".join([head, sep, *body])

    md = f"""# 中证500 低估值·财务健康·成长 筛选报告

> 生成日期：{meta['date']}　样本：{n} 只（中证500 当前成分）
> **本报告为描述性筛选结果，不构成任何投资建议或买卖推荐。** 所有阈值均为可调假设，
> 数值只反映“在该套条件下是否入选”，不代表公司好坏或未来收益。

## 一、方法与框架

筛选按三层漏斗进行，逐层收紧；每层淘汰原因均逐只记录在明细 CSV 中。

### 第 1 层：排除（先砍掉你明确不碰的）
- **强周期行业**：剔除申万一级 { '、'.join(sorted(config.CYCLICAL_SW1)) }
- **亏损/微利**：近 3 年年报扣非净利为正的年份 < {config.PROFIT_POSITIVE_MIN_YEARS} 年
- **高负债**：资产负债率 ≥ {config.DEBT_ABS_MAX:.0f}%，或处于同行业负债率前 {(1-config.DEBT_INDUSTRY_PCTL)*100:.0f}%
- **ST/退市风险、上市不足 {config.MIN_LISTED_YEARS} 年**

### 第 2 层：财务健康 + 成长
- **赚钱能力**：近 3 年 ROE 均值 ≥ {config.ROE_MEAN_MIN:.0f}%，且无一年的 ROE ≤ {config.ROE_EACH_MIN:.0f}%
- **利润是真钱**：近 3 年 Σ每股经营现金流 / Σ每股收益 ≥ {config.CASH_CONTENT_MIN}
- **成长**：营收与扣非净利的区间 CAGR 均 > {config.REVENUE_CAGR_MIN:.0f}%

### 第 3 层：估值分位（两个参照）
- **自身历史分位**：PE(TTM) 与 PB 在近 {config.VAL_WINDOW_YEARS} 年中的分位，取较低者 ≤ {config.SELF_PCTL_MAX:.0%}
- **同行分位**：同行业内 PE/PB 分位（取较低者）≤ {config.PEER_PCTL_MAX:.0%}
  （优先按申万二级分组，样本不足 5 家时回退申万一级）

## 二、结果

- 样本 {n} 只 → 过第 1 层 **{p1}** 只 → 过 1+2 层 **{p2}** 只 → **候选 {len(cand)} 只**

### 候选清单

{table(cand)}

### 主要淘汰原因（供调参参考）

**第 1 层**：
{bullets(top_reasons)}

**第 2 层**：
{bullets(l2_reasons)}

**第 3 层**：
{bullets(l3_reasons)}

### 图表
- `valuation_distribution.png`：全样本估值分位分布与阈值
- `roe_vs_valuation.png`：盈利水平 vs 估值分位（左下=又便宜又赚钱）
- `industry_mix.png`：全样本与候选的行业分布对比

## 三、价值陷阱排查

筛出来的“便宜”有两种来源：股价下跌造成的（可能被错杀），和盈利冲高造成的
“PE 看着便宜”。后者更危险——盈利一旦均值回归，PE 会立刻从便宜跳到贵。
区分二者要看 PB 分位：PB 的分母是净资产，比 PE 的盈利稳定得多。

对 {len(cand)} 只候选定义 `gap = PB分位 − PE分位`：

- **A 组 gap ≥ {TRAP_GAP:.2f}**：PE 分位明显低于 PB 分位 → 盈利相对净资产处在
  历史高位，低 PE 是盈利撑出来的。共 {len(tgroup_a)} 只。
- **B 组 gap ≤ −{TRAP_GAP:.2f}**：PB 分位明显低于 PE 分位 → 净资产角度便宜，
  但盈利已经在下行。共 {len(tgroup_b)} 只。
- **其余 {len(tgroup_mid)} 只**两个信号一致，便宜的来源更可能是股价本身。

### A 组：低 PE 由盈利高位撑起

{trap_table(tgroup_a)}

### B 组：PB 便宜伴随盈利下行

{trap_table(tgroup_b)}

> 本排查是描述性的：只指出便宜的“来源”，不判断盈利会不会继续回落、股价会不会
> 反弹。gap 居中的 {len(tgroup_mid)} 只也不代表“干净”，仍需逐只看财报。

### 图表
- `trap_scatter.png`：候选股 PE 分位 vs PB 分位散点，对角线上方＝A 组

## 四、数据来源与口径

| 数据 | 来源 | 说明 |
|------|------|------|
| 成分名单 | 中证指数官网 | 当前时点成分（不含历史成分变动） |
| 财务指标 | 同花顺年报摘要 | 年报口径，近 4 期 |
| 估值历史 | 百度股市通 | **双周频**采样点位，非逐日 |
| 行业标签 | 申万 1/2/3 级映射 | 同行分位优先二级，样本不足回退一级 |

## 五、已知局限

1. **同行对比粒度受限**：优先按申万二级分组，但中证500 只有 500 只，二级只有约 65%
   的股票能凑够 5 家同行，其余回退申万一级，跨细分行业可比性因此变弱。
2. **同行样本仅中证500 内部**：基准是同行业内的中证500 成分股，不含行业内大市值龙头。
   美容护理、社会服务、商贸零售、纺织服饰成分不足 5 只，无法比较，其中个股按“无法评估”淘汰；
   营收/扣非 CAGR 在区间首末值为负时也算不出，同样按缺失淘汰。三类“要求型”条件
   （ROE、现金含量、成长性、估值分位）一律“缺失即淘汰”，不做缺失放行。
3. **估值分位为双周频**：窗口内点数有限（近 5 年约 90 点），分位精度受限。
4. **幸存者/时点偏差**：成分是当前名单，未回测历史成分。
5. **财务指标为年报口径**：不含最新季报，存在时滞。
6. **强周期按申万一级整类剔除**：可能误伤该行业内非周期细分。
7. **阈值主观**：所有门槛都是可调假设，改动会显著改变结果。

## 六、声明

本报告不推荐任何具体证券，不预测价格，不含目标价或评级。筛选条件与结果仅用于学习与
辅助你自己研究；任何买卖决策及风险由你自己承担。
"""
    p = out / "中证500筛选报告.md"
    p.write_text(md, encoding="utf-8")
    return p


def build(out_dir: Path) -> dict:
    df = _read(out_dir / "csi500_metrics.csv")
    meta = {"date": pd.Timestamp.today().strftime("%Y-%m-%d")}
    plot_valuation_distribution(df, out_dir)
    plot_roe_vs_valuation(df, out_dir)
    plot_industry_mix(df, out_dir)
    plot_trap(df, out_dir)
    md = write_markdown(df, out_dir, meta)
    return {"markdown": md, "dir": out_dir}
