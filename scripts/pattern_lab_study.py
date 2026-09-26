"""pattern_lab_r1 study: development walk-forward + threshold selection, then a one-shot opened-year check.

  python scripts/pattern_lab_study.py dev --tf 4h
  python scripts/pattern_lab_study.py opened --tf 4h   # only after dev selections are frozen
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from agentic_alpha_lab.backtest.bracket import bracket_backtest, summarize_bracket, triple_barrier
from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, STRESS, backtest, funding_per_bar, summarize
from agentic_alpha_lab.models.pattern_pipeline import build_matrix, policy, walk_forward_probs
from agentic_alpha_lab.patterns.common import load_bars, load_funding

PROTOCOL = Path("configs/pattern_lab_r1_protocol.json")
PROTOCOL_SHA = "24cf15909f050eafc2b9369d9891c6d4d85161c1e522fe42cfa34d76be7f203c"
OUT = Path("artifacts/research/pattern_lab")
TF = {"4h": dict(horizon=12, refit=540, bars_per_day=6), "1d": dict(horizon=10, refit=90, bars_per_day=1)}
FEATURE_SETS = {
    "base": (),
    "base+candles": ("cdl",),
    "base+chart": ("chp",),
    "base+indicators": ("ind",),
    "all": ("cdl", "chp", "ind"),
}
THRESHOLDS = (0.40, 0.45, 0.50, 0.55, 0.60)


def first_index(bars, date):
    return int(np.flatnonzero(bars["open_time"] >= pd.Timestamp(date, tz="UTC"))[0])


def last_index(bars, date):
    return int(np.flatnonzero(bars["open_time"] < pd.Timestamp(date, tz="UTC") + pd.Timedelta("1D"))[-1])


def available_sets():
    import importlib
    ok = {}
    for name, blocks in FEATURE_SETS.items():
        try:
            for b in blocks:
                importlib.import_module({"cdl": "agentic_alpha_lab.patterns.candles", "chp": "agentic_alpha_lab.patterns.chart", "ind": "agentic_alpha_lab.patterns.indicators"}[b])
            ok[name] = blocks
        except ImportError:
            pass
    return ok


def evaluate_rows(bars, sig, outc, rng, fc):
    rows = {}
    for cname, costs in (("normal", NORMAL), ("stress", STRESS)):
        res = bracket_backtest(bars, sig, outc, rng[0], rng[1], costs, fc)
        rows[cname] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in summarize_bracket(res, bars, *rng).items()}
    return rows


def auc(y, p):
    m = ~np.isnan(y) & ~np.isnan(p)
    return float(roc_auc_score(y[m], p[m])) if m.sum() > 50 and len(set(y[m])) > 1 else None


def run(phase: str, tf: str, sets: list[str] | None) -> None:
    if hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() != PROTOCOL_SHA:
        raise SystemExit("protocol changed")
    proto = json.loads(PROTOCOL.read_text())
    cfg = TF[tf]
    opened = phase == "opened"
    bars = load_bars(tf, include_opened_year=opened)
    daily = load_bars("1d", include_opened_year=opened)
    funding = load_funding(include_opened_year=opened)
    fr, fc = funding_per_bar(bars, funding)
    outc = triple_barrier(bars, 2.0, 1.0, cfg["horizon"])
    y_long, y_short = outc.label(1), outc.label(-1)
    realized_at = np.arange(len(bars)) + cfg["horizon"]
    embargo = cfg["horizon"]
    wf_first = first_index(bars, "2021-01-01")
    dev_last = last_index(bars, proto["windows"]["development_decisions"][1])
    val_first = first_index(bars, proto["windows"]["selection_validation"][0])
    out_dir = OUT / f"model_{tf}"
    out_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = out_dir / "frozen_selection.json"

    if opened:
        frozen = json.loads(frozen_path.read_text())
        ho_first = first_index(bars, proto["windows"]["opened_year_check"][0])
        ho_last = last_index(bars, proto["windows"]["opened_year_check"][1])
        marker = out_dir / "opened_year_evaluated.txt"
        if marker.exists():
            raise SystemExit("opened-year check already run for this tf; results are final")
        marker.write_text(pd.Timestamp.utcnow().isoformat())
        report = {"frozen": frozen, "window": [str(bars.open_time[ho_first]), str(bars.open_time[ho_last])], "rows": {}}
        bh = summarize(backtest(bars, np.ones(len(bars), dtype=int), ho_first, ho_last, NORMAL, fr, fc))
        report["buy_hold"] = {k: round(v, 4) if isinstance(v, float) else v for k, v in bh.items()}
        for name, sel in frozen["selections"].items():
            blocks = FEATURE_SETS[sel["feature_set"]]
            x = build_matrix(bars, daily, funding, blocks)[sel["columns"]]
            gate = x["d_ribbon"].to_numpy() if sel["gated"] else None
            for mode, fit_limit in (("frozen", ho_first), ("walk_forward", None)):
                p = walk_forward_probs(x, y_long, y_short, realized_at, ho_first, ho_last, cfg["refit"], embargo, fit_limit)
                sig = policy(p, sel["threshold"], gate)
                rows = evaluate_rows(bars, sig, outc, (ho_first, ho_last), fc)
                rows["auc_long"], rows["auc_short"] = auc(y_long[ho_first:ho_last + 1], p[0, ho_first:ho_last + 1]), auc(y_short[ho_first:ho_last + 1], p[1, ho_first:ho_last + 1])
                report["rows"][f"{name}|{mode}"] = rows
                print(name, mode, rows["normal"]["net_pct"], rows["stress"]["net_pct"], rows["normal"]["dd_intrabar_pct"], rows["normal"]["trades"], flush=True)
        (out_dir / "opened_year_report.json").write_text(json.dumps(report, indent=1, default=str))
        return

    report = {"protocol_sha256": PROTOCOL_SHA, "tf": tf, "windows": {
        "walk_forward": [str(bars.open_time[wf_first]), str(bars.open_time[dev_last])],
        "validation": [str(bars.open_time[val_first]), str(bars.open_time[dev_last])]}, "rows": {}}
    bh = {}
    for label_, rng in (("wf", (wf_first, dev_last)), ("pre_val", (wf_first, val_first - 1)), ("val", (val_first, dev_last))):
        bh[label_] = {k: round(v, 4) if isinstance(v, float) else v for k, v in summarize(backtest(bars, np.ones(len(bars), dtype=int), rng[0], rng[1], NORMAL, fr, fc)).items()}
    report["buy_hold"] = bh
    # label/sanity: unconditional trade outcomes
    report["unconditional"] = {
        "long_win_rate": float(np.nanmean(y_long[wf_first:dev_last])), "short_win_rate": float(np.nanmean(y_short[wf_first:dev_last])),
        "long_tp_rate": float(np.mean(outc.exit_kind[0, wf_first:dev_last] == 1)), "short_tp_rate": float(np.mean(outc.exit_kind[1, wf_first:dev_last] == 1)),
    }
    selections = json.loads(frozen_path.read_text())["selections"] if frozen_path.exists() else {}
    todo = available_sets()
    for name, blocks in todo.items():
        if sets and name not in sets:
            continue
        t0 = time.time()
        x = build_matrix(bars, daily, funding, blocks)
        dev_x = x.iloc[: dev_last + 1]
        keep = [c for c in x.columns if dev_x[c].notna().mean() > 0.5 and dev_x[c].nunique(dropna=True) > 1]
        x = x[keep]
        p = walk_forward_probs(x, y_long, y_short, realized_at, wf_first, dev_last, cfg["refit"], embargo)
        np.save(out_dir / f"wf_probs_{name.replace('+', '_')}.npy", p)
        for gated in (False, True):
            gate = x["d_ribbon"].to_numpy() if gated else None
            key = f"{name}|{'gated' if gated else 'ungated'}"
            per_th = {}
            for th in THRESHOLDS:
                sig = policy(p, th, gate)
                per_th[th] = evaluate_rows(bars, sig, outc, (val_first, dev_last), fc)
            elig = [th for th in THRESHOLDS if per_th[th]["normal"]["trades"] >= 30]
            if not elig:
                report["rows"][key] = {"selected": None, "reason": "no threshold with >= 30 validation trades"}
                continue
            best = max(elig, key=lambda th: (round(per_th[th]["normal"]["net_pct"], 6), th))
            sig = policy(p, best, gate)
            row = {
                "threshold": best,
                "validation_by_threshold": {str(k): {"net": v["normal"]["net_pct"], "net_stress": v["stress"]["net_pct"], "trades": v["normal"]["trades"]} for k, v in per_th.items()},
                "wf": evaluate_rows(bars, sig, outc, (wf_first, dev_last), fc),
                "pre_val": evaluate_rows(bars, sig, outc, (wf_first, val_first - 1), fc),
                "val": per_th[best],
                "auc_long": auc(y_long[wf_first:dev_last + 1], p[0, wf_first:dev_last + 1]),
                "auc_short": auc(y_short[wf_first:dev_last + 1], p[1, wf_first:dev_last + 1]),
                "n_features": len(keep),
            }
            wf = row["wf"]
            row["dev_accept"] = bool(wf["stress"]["net_pct"] > 0 and wf["normal"]["sharpe"] > bh["wf"]["sharpe"] and wf["normal"]["trades"] >= 100)
            report["rows"][key] = row
            selections[key] = {"feature_set": name, "gated": gated, "threshold": best, "columns": keep, "dev_accept": row["dev_accept"]}
            print(key, "th", best, "wf net", wf["normal"]["net_pct"], "stress", wf["stress"]["net_pct"], "dd", wf["normal"]["dd_intrabar_pct"],
                  "trades", wf["normal"]["trades"], "pre_val", row["pre_val"]["normal"]["net_pct"], "auc", row["auc_long"], row["auc_short"],
                  "accept", row["dev_accept"], f"{time.time() - t0:.0f}s", flush=True)
    prev = json.loads((out_dir / "dev_report.json").read_text()) if (out_dir / "dev_report.json").exists() else {"rows": {}}
    prev.update({k: v for k, v in report.items() if k != "rows"})
    prev["rows"].update(report["rows"])
    (out_dir / "dev_report.json").write_text(json.dumps(prev, indent=1, default=str))
    frozen_path.write_text(json.dumps({"protocol_sha256": PROTOCOL_SHA, "frozen_at": pd.Timestamp.utcnow().isoformat(), "selections": selections}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["dev", "opened"])
    ap.add_argument("--tf", default="4h", choices=list(TF))
    ap.add_argument("--sets", nargs="*")
    a = ap.parse_args()
    run(a.phase, a.tf, a.sets)
