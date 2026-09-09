"""R20-A v38conc (v62): CONCENTRATION check on NEW leg v38-isoall_1x vs majority_1x.

Analysis ONLY on frozen normal-scenario trades CSVs. No backtests, no fitting,
no refit, no live orders. Pre-spec: configs/opencode_v62_v38conc.json
(branches + concentration rule fixed BEFORE computing).

Policy:
  - v38-isoall_1x: computed FRESH from frozen normal_trades.csv (same method
    as v61, reusing helpers from scripts/opencode_r19e_monthattr.py).
  - majority_1x: REUSED verbatim from artifacts/research/opencode_v61_monthattr/
    summary.json (+ monthly CSV reference). Its trades CSV is NEVER re-read
    and nothing is recomputed for it.

New outputs only under artifacts/research/opencode_v62_v38conc/ (fail if exists).
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from opencode_r19e_monthattr import (  # noqa: E402  (reuse v61 helpers, recorded)
    gini_relative_mean_abs_diff,
    sha256,
)

CFG_PATH = ROOT / "configs/opencode_v62_v38conc.json"
V61_SUMMARY_PATH = ROOT / "artifacts/research/opencode_v61_monthattr/summary.json"
OUT_DIR = ROOT / "artifacts/research/opencode_v62_v38conc"


def analyze_fresh(branch_cfg: dict, rule: dict) -> dict:
    """Same monthly+trade attribution as v61 analyze_branch, fresh CSV read."""
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

    px = df.sort_values("net_pnl", ascending=False).reset_index(drop=True)
    top1_trade = float(px["net_pnl"].iloc[0])
    top5_sum = float(px["net_pnl"].head(5).sum())
    worst5_sum = float(px["net_pnl"].tail(5).sum())
    top_trades = px.head(20)[[c for c in
        ("exit_time", "direction", "leverage", "entry_time", "exit_reason",
         "gross_pnl", "fees", "funding", "net_pnl", "equity_after")
        if c in px.columns]].copy()
    top_trades["exit_time"] = top_trades["exit_time"].astype(str)
    if "entry_time" in top_trades.columns:
        top_trades["entry_time"] = top_trades["entry_time"].astype(str)

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
        "computed": "fresh (v62)",
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
            "top1_trade_share": top1_trade / total_net if total_net else None,
            "top5_trades_share": top5_sum / total_net if total_net else None,
            "worst5_drag_share": worst5_sum / total_net if total_net else None,
            "largest_win": top1_trade,
        },
        "verdict": verdict,
        "verdict_reasons": reasons,
        "_monthly_df": monthly,
        "_top_trades_df": top_trades,
    }


def reuse_v61(branch_cfg: dict) -> dict:
    """Copy majority_1x stats verbatim from v61 summary.json (no recompute)."""
    name = branch_cfg["branch"]
    v61 = json.loads(V61_SUMMARY_PATH.read_text(encoding="utf-8"))
    src = next((b for b in v61["branches"] if b["branch"] == name), None)
    if src is None:
        return {"branch": name, "status": "skipped_missing_in_v61",
                "expected": str(V61_SUMMARY_PATH)}
    out = {k: v for k, v in src.items() if not k.startswith("_")}
    out["status"] = "ok"
    out["computed"] = "reused_from_v61 (NOT recomputed)"
    out["reused_from"] = "artifacts/research/opencode_v61_monthattr/summary.json"
    out["monthly_csv_reference"] = "artifacts/research/opencode_v61_monthattr/majority_1x_monthly.csv"
    out["trades_csv"] = branch_cfg["trades_csv"]
    return out


def head_to_head(new: dict, ref: dict) -> dict:
    c, r = new["concentration"], ref["concentration"]
    t, u = new["trade_concentration"], ref["trade_concentration"]
    cmp_notes = []
    for key, label in [
        ("top1_month_share", "top1 month share"),
        ("top3_months_share", "top3 months share"),
        ("gini_monthly_net", "Gini monthly"),
    ]:
        a, b = c[key], r[key]
        if a is None or b is None:
            cmp_notes.append(f"{label}: null (khong so sanh duoc)")
        elif abs(a - b) < 1e-12:
            cmp_notes.append(f"{label}: bang nhau ({a:.1%})")
        else:
            better = "v38-isoall_1x" if a < b else "majority_1x"
            cmp_notes.append(
                f"{label}: v38-isoall_1x {a:.1%} vs majority_1x {b:.1%} -> "
                f"{better} phan tan hon (thap hon = phan tan hon)")
    cmp_notes.append(
        f"top5 trades share: v38-isoall_1x {t['top5_trades_share']:.1%} vs "
        f"majority_1x {u['top5_trades_share']:.1%} -> "
        f"{'v38 do tap trung HON' if t['top5_trades_share'] < u['top5_trades_share'] else 'v38 tap trung HON o cap do trade'}")
    cmp_notes.append(
        f"thang am: v38-isoall_1x {c['n_negative']}/{c['n_months_total']} vs "
        f"majority_1x {r['n_negative']}/{r['n_months_total']}")
    cmp_notes.append(
        f"best/worst: v38-isoall_1x {c['best_month']['month']} ({c['best_month']['net']:.2f}) / "
        f"{c['worst_month']['month']} ({c['worst_month']['net']:.2f}); majority_1x "
        f"{r['best_month']['month']} ({r['best_month']['net']:.2f}) / "
        f"{r['worst_month']['month']} ({r['worst_month']['net']:.2f})")
    worse_monthly = (c["top1_month_share"] or 0) > (r["top1_month_share"] or 0) and \
                    (c["top3_months_share"] or 0) > (r["top3_months_share"] or 0)
    worse_trade = (t["top5_trades_share"] or 0) > (u["top5_trades_share"] or 0)
    if worse_monthly and worse_trade:
        conclusion = ("v38-isoall_1x TAP TRUNG TE HON majority_1x ca hai cap do "
                      "(thang + trade).")
    elif worse_monthly:
        conclusion = ("v38-isoall_1x tap trung hon o cap do THANG, nhung do hon "
                      "o cap do trade.")
    elif worse_trade:
        conclusion = ("v38-isoall_1x tap trung hon o cap do TRADE, nhung do hon "
                      "o cap do thang.")
    else:
        conclusion = ("v38-isoall_1x KHONG tap trung te hon majority_1x "
                      "(phan tan hon hoac tuong duong ca hai cap do).")
    return {"comparisons": cmp_notes, "conclusion": conclusion,
            "verdicts": {"v38-isoall_1x": new["verdict"], "majority_1x": ref["verdict"]}}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    out = args.out
    if out.exists():
        raise FileExistsError("Khong ghi de (no overwrites); dung dir moi")
    out.mkdir(parents=True)

    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    rule = cfg["concentration_rule"]
    by_name = {b["branch"]: b for b in cfg["branches"]}

    new_res = analyze_fresh(by_name["v38-isoall_1x"], rule)
    monthly_df = new_res.pop("_monthly_df", None)
    top_df = new_res.pop("_top_trades_df", None)
    if new_res.get("status") == "ok":
        monthly_df.to_csv(out / "v38-isoall_1x_monthly.csv", index=False)
        top_df.to_csv(out / "v38-isoall_1x_top_trades.csv", index=False)

    ref_res = reuse_v61(by_name["majority_1x"])

    h2h = None
    if new_res.get("status") == "ok" and ref_res.get("status") == "ok":
        h2h = head_to_head(new_res, ref_res)

    summary = {
        "experiment": cfg["experiment"],
        "family": cfg["family"],
        "scenario": cfg["scenario"],
        "concentration_rule": cfg["concentration_rule"],
        "gini_definition": cfg["gini_definition"],
        "method": cfg["method"],
        "branches": [new_res, ref_res],
        "head_to_head": h2h,
        "helpers_reused": "scripts/opencode_r19e_monthattr.py:gini_relative_mean_abs_diff,sha256",
        "independent_test": False,
        "live_approved": False,
        "exploratory": True,
        "warning": ("EXPLORATORY tren khoang phat trien 2023-2026 da mo; KHONG phai kiem dinh "
                    "doc lap. Descriptive attribution tren trades CSV dong bang (normal). "
                    "Drawdown lay mau theo gia dong nen trade. Exit stop/timeout market-like "
                    "theo fee kich ban. Khong suy doan fill maker/hang doi tu OHLC."),
        "input_sha256": {},
    }
    fresh_csv = ROOT / by_name["v38-isoall_1x"]["trades_csv"]
    if fresh_csv.exists():
        summary["input_sha256"][by_name["v38-isoall_1x"]["trades_csv"]] = sha256(fresh_csv)
    summary["input_sha256"]["configs/opencode_v62_v38conc.json"] = sha256(CFG_PATH)
    summary["input_sha256"]["artifacts/research/opencode_v61_monthattr/summary.json (majority_1x reused)"] = sha256(V61_SUMMARY_PATH)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    c = new_res["concentration"]
    print(f"v38-isoall_1x: top1mo={c['top1_month_share']:.1%} "
          f"top3mo={c['top3_months_share']:.1%} gini={c['gini_monthly_net']:.3f} "
          f"top5tr={new_res['trade_concentration']['top5_trades_share']:.1%} -> {new_res['verdict']}")
    print(f"majority_1x (reused v61): top1mo={ref_res['concentration']['top1_month_share']:.1%} "
          f"top3mo={ref_res['concentration']['top3_months_share']:.1%} "
          f"gini={ref_res['concentration']['gini_monthly_net']:.3f} "
          f"top5tr={ref_res['trade_concentration']['top5_trades_share']:.1%} -> {ref_res['verdict']}")
    if h2h:
        print("H2H: " + h2h["conclusion"])
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
