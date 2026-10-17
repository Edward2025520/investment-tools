"""入口：跑中证指数成分股筛选，输出明细/候选 CSV、四张图、Markdown 与 Word 报告。

用法：
    python tools/screen_csi500/run.py                  # 中证500 全量
    python tools/screen_csi500/run.py --index 1000     # 中证1000 全量
    python tools/screen_csi500/run.py --limit 30       # 小样本试跑
    python tools/screen_csi500/run.py --refresh        # 强制重抓
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.common import net
from tools.screen_csi500 import config, report, report_docx, screen

net.install_default_timeout()


def _out_dir(index_key: str) -> Path:
    d = config.DATA_DIR / "reports" / "_screens" / f"csi{index_key}_{date.today():%Y%m%d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description="中证指数成分股分层筛选（描述性，不构成投资建议）")
    ap.add_argument("--index", default=config.DEFAULT_INDEX, choices=sorted(config.INDICES),
                    help="指数简称：500 或 1000（默认 500）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 只（试跑用）")
    ap.add_argument("--refresh", action="store_true", help="强制重抓缓存")
    args = ap.parse_args()

    name, _ = config.index_meta(args.index)
    print(f"[{name}筛选] 拉取成分与指标…")
    res = screen.run_screen(refresh=args.refresh, limit=args.limit, index_key=args.index)
    df = res["frame"]

    out = _out_dir(args.index)
    full = out / f"csi{args.index}_metrics.csv"
    df.drop(columns=[c for c in df.columns if c.startswith("_")]).to_csv(
        full, index=False, encoding="utf-8-sig")
    cand = df[df["候选"] == "是"].drop(columns=[c for c in df.columns if c.startswith("_")])
    cand_path = out / f"csi{args.index}_candidates.csv"
    cand.to_csv(cand_path, index=False, encoding="utf-8-sig")

    n = res["n"]
    p1 = int(df["_p1"].sum())
    p2 = int((df["_p1"] & df["_p2"]).sum())
    p3 = int((df["_p1"] & df["_p2"] & df["_p3"]).sum())
    if (df["申万一级"].fillna("").astype(str).str.strip() == "").all():
        print(
            "\n  [警告] 行业标签全部缺失：强周期排除与同行估值分位失效，样本会整批被淘汰，"
            "结果不可用。\n"
            "  请先重建映射缓存：\n"
            "    conda run -n ai python tools/industry_profit/cli.py 600519 --refresh-cache"
        )
    print(f"\n  样本 {n} 只")
    print(f"  过第1层(排除)        : {p1}")
    print(f"  过1+2层(健康+成长)   : {p2}")
    print(f"  过全部三层(候选)     : {p3}")
    print(f"\n  已输出:\n    {full}\n    {cand_path}")

    print("\n[生成报告] 绘图与报告…")
    md = report.build(out, index_name=name)["markdown"]
    docx_path = out / f"{name}筛选报告.docx"
    imgs = sorted(out.glob("*.png"))
    report_docx.convert(md, docx_path, imgs)
    print(f"\n  报告: {md}\n  Word: {docx_path}\n  图表: {len(imgs)} 张 PNG -> {out}")


if __name__ == "__main__":
    main()
