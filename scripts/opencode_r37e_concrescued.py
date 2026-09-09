"""R37-E concrescued (v108): CONCENTRATION on rescued legs (v33-topdec, v55c-isoall).

Analysis ONLY on frozen normal-scenario trades CSVs. No backtests, no fitting,
no refit, no live orders. Pre-spec: configs/opencode_v108_concrescued.json
(branches + concentration rule fixed BEFORE computing).
New outputs only under artifacts/research/opencode_v108_concrescued/ (fail if exists).

Method: v61 verbatim (scripts/opencode_r19e_monthattr.py): monthly table by
exit_time + top-1/top-3 shares + Gini + top-5 trades + best/worst +
negative-month count. Reuses v61 helpers (sha256, gini_relative_mean_abs_diff);
recorded in summary.json method.reused_from.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from opencode_r19e_monthattr import (  # noqa: E402  (v61 helpers, reused verbatim)
    gini_relative_mean_abs_diff,
    sha256,
)

CFG_PATH = ROOT / "configs/opencode_v108_concrescued.json"
OUT_DIR = ROOT / "artifacts/research/opencode_v108_concrescued"


def analyze_branch(branch_cfg: dict) -> dict:
    """v61 analyze_branch verbatim, pointed at v108 CFG_PATH."""
    name = branch_cfg["branch"]
    csv_path = ROOT / branch_cfg["trades_csv"]
    if not csv_path.exists():
        return {"branch": name, "status": "skipped_missing_file",
                "expected": branch_cfg["trades_csv"]}
    df = pd.read_csv(csv_path)
    for col in ("exit_time", "net_pnl"):
        if col not in df.columns:
            raise ValueError(f"{name}: missing column {col}")
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
    df = df.sort_values("exit_time").reset_index(drop=True)
    total_net = float(df["net_pnl"].sum())

    # Calendar-month series, zero-filled over first..last exit month span.
    df["month"] = df["exit_time"].dt.strftime("%Y-%m")
    grp = df.groupby("month")
    monthly = grp.agg(
        n_trades=("net_pnl", "size"),
        n_wins=("net_pnl", lambda s: int((s > 0).sum())),
        gross_pnl=("gross_pnl", "sum") if "gross_pnl" in df.columns else ("net_pnl", "sum"),
        fees=("fees", "sum") if "fees" in df.columns else ("net_pnl", lambda s: 0.0),
        funding=("funding", "sum") if "funding" in df.columns else ("net_pnl", lambda s: 0.0),
        net_pnl=("net_pnl", "sum"),
    ).reset_index()
    span = pd.period_range(monthly["month"].min(), monthly["month"].max(), freq="M").strftime("%Y-%m")
    monthly = monthly.set_index("month").reindex(span, fill_value=0).reset_index()
    # reindex zeroes non-additive cols too; restore n_wins int
    monthly["n_wins"] = monthly["n_wins"].astype(int)
    monthly["cum_net"] = monthly["net_pnl"].cumsum()
    monthly = monthly.rename(columns={"index": "month"})
    if "month" not in monthly.columns:
        monthly = monthly.rename(columns={monthly.columns[0]: "month"})

    nets = monthly["net_pnl"].tolist()
    n = len(monthly)
    n_pos = int((monthly["net_pnl"] > 0).sum())
    n_neg = int((monthly["net_pnl"] < 0).sum())
    n_flat = int((monthly["net_pnl"] == 0).sum())
    best_row = monthly.loc[monthly["net_pnl"].idxmax()]
    worst_row = monthly.loc[monthly["net_pnl"].idxmin()]
    top3_sum = float(monthly["net_pnl"].nlargest(3).sum())
    top1_share = float(best_row["net_pnl"] / total_net) if total_net else None
    top3_share = float(top3_sum / total_net) if total_net else None
    gini = gini_relative_mean_abs_diff(nets)

    # Trade concentration.
    px = df.sort_values("net_pnl", ascending=False).reset_index(drop=True)
    top1_trade = float(px["net_pnl"].iloc[0])
    top5_sum = float(px["net_pnl"].head(5).sum())
    worst5_sum = float(px["net_pnl"].tail(5).sum())
    top1_trade_share = top1_trade / total_net if total_net else None
    top5_share = top5_sum / total_net if total_net else None
    worst5_drag = worst5_sum / total_net if total_net else None
    top_trades = px.head(20)[[c for c in
        ("exit_time", "direction", "leverage", "entry_time", "exit_reason",
         "gross_pnl", "fees", "funding", "net_pnl", "equity_after")
        if c in px.columns]].copy()
    top_trades["exit_time"] = top_trades["exit_time"].astype(str)
    if "entry_time" in top_trades.columns:
        top_trades["entry_time"] = top_trades["entry_time"].astype(str)

    cfg = json.loads(CFG_PATH.read_text())
    rule = cfg["concentration_rule"]
    reasons = []
    if not (total_net > 0):
        verdict = "concentrated (FAIL)"
        reasons.append("total_net <= 0 (no positive base)")
    else:
        fail_top1 = top1_share is not None and top1_share > rule["top1_month_share_gt"]
        fail_top3 = top3_share is not None and top3_share > rule["top3_months_share_gt"]
        if fail_top1:
            reasons.append(f"top1 month {top1_share:.1%} > {rule['top1_month_share_gt']:.0%}")
        if fail_top3:
            reasons.append(f"top3 months {top3_share:.1%} > {rule['top3_months_share_gt']:.0%}")
        verdict = "concentrated (FAIL)" if (fail_top1 or fail_top3) else "diffuse (PASS)"

    return {
        "branch": name,
        "status": "ok",
        "trades_csv": branch_cfg["trades_csv"],
        "n_trades": int(len(df)),
        "exit_span": [str(df["exit_time"].min()), str(df["exit_time"].max())],
        "total_gross": float(df["gross_pnl"].sum()) if "gross_pnl" in df.columns else None,
        "total_fees": float(df["fees"].sum()) if "fees" in df.columns else None,
        "total_funding": float(df["funding"].sum()) if "funding" in df.columns else None,
        "total_net": total_net,
        "monthly_table": monthly.to_dict(orient="records"),
        "concentration": {
            "n_months_total": n, "n_positive": n_pos,
            "n_negative": n_neg, "n_flat": n_flat,
            "best_month": {"month": str(best_row["month"]), "net": float(best_row["net_pnl"])},
            "worst_month": {"month": str(worst_row["month"]), "net": float(worst_row["net_pnl"])},
            "top1_month_share": top1_share,
            "top3_months_share": top3_share,
            "gini_monthly_net": gini,
        },
        "trade_concentration": {
            "top1_trade_share": top1_trade_share,
            "top5_trades_share": top5_share,
            "worst5_drag_share": worst5_drag,
            "largest_win": top1_trade,
        },
        "verdict": verdict,
        "verdict_reasons": reasons,
        "_monthly_df": monthly,
        "_top_trades_df": top_trades,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    out = args.out
    if out.exists():
        raise FileExistsError("Khong ghi de (no overwrites); dung dir moi")
    out.mkdir(parents=True)

    cfg = json.loads(CFG_PATH.read_text())
    results = []
    for b in cfg["branches"]:
        res = analyze_branch(b)
        results.append(res)
        monthly_df = res.pop("_monthly_df", None)
        top_df = res.pop("_top_trades_df", None)
        if res.get("status") == "ok":
            monthly_df.to_csv(out / f"{res['branch']}_monthly.csv", index=False)
            top_df.to_csv(out / f"{res['branch']}_top_trades.csv", index=False)

    summary = {
        "experiment": cfg["experiment"],
        "family": cfg["family"],
        "scenario": cfg["scenario"],
        "concentration_rule": cfg["concentration_rule"],
        "gini_definition": cfg["gini_definition"],
        "method": cfg["method"],
        "branches": results,
        "independent_test": False,
        "live_approved": False,
        "exploratory": True,
        "warning": ("EXPLORATORY tren khoang phat trien 2023-2026 da mo; KHONG phai kiem dinh "
                    "doc lap. Descriptive attribution tren trades CSV dong bang (normal). "
                    "Drawdown lay mau theo gia dong nen trade. Exit stop/timeout market-like "
                    "theo fee kich ban. Khong suy doan fill maker/hang doi tu OHLC."),
        "input_sha256": {b["trades_csv"]: sha256(ROOT / b["trades_csv"])
                         for b in cfg["branches"] if (ROOT / b["trades_csv"]).exists()},
    }
    summary["input_sha256"]["configs/opencode_v108_concrescued.json"] = sha256(CFG_PATH)
    summary["input_sha256"]["scripts/opencode_r37e_concrescued.py"] = sha256(
        ROOT / "scripts/opencode_r37e_concrescued.py")
    summary["input_sha256"]["scripts/opencode_r19e_monthattr.py (v61 helpers)"] = sha256(
        ROOT / "scripts/opencode_r19e_monthattr.py")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    for r in results:
        if r.get("status") == "ok":
            c = r["concentration"]
            print(f"{r['branch']}: top1mo={c['top1_month_share']:.1%} "
                  f"top3mo={c['top3_months_share']:.1%} gini={c['gini_monthly_net']:.3f} "
                  f"top5tr={r['trade_concentration']['top5_trades_share']:.1%} -> {r['verdict']}")
        else:
            print(f"{r['branch']}: SKIPPED ({r['status']}: {r.get('expected')})")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
