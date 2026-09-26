"""pattern_lab_r2: meta-label 4h EMA20/200 ribbon trades with pattern/indicator features.

  python scripts/pattern_lab_meta.py dev
  python scripts/pattern_lab_meta.py opened   # once, after dev selections are frozen
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from agentic_alpha_lab.backtest.ma_ribbon import ACTUAL_FUNDING, NORMAL, STRESS, backtest, funding_per_bar, ribbon_target, summarize
from agentic_alpha_lab.models.pattern_pipeline import build_matrix
from agentic_alpha_lab.patterns.common import load_bars, load_funding

PROTOCOL = Path("configs/pattern_lab_r2_protocol.json")
PROTOCOL_SHA = "f5f8b8ec15b59205eef3ded7515f3f376c5621100cfc43d229a6635ce25b25c1"
R1 = json.loads(Path("configs/pattern_lab_r1_protocol.json").read_text())
OUT = Path("artifacts/research/pattern_lab/meta_4h")
REFIT, EMBARGO = 540, 12
THRESHOLDS = (0.40, 0.45, 0.50, 0.55, 0.60)
SETS = {"base": (), "all": ("cdl", "chp", "ind")}
SCEN = {"normal": NORMAL, "stress": STRESS, "actual_funding": ACTUAL_FUNDING}


def idx_first(bars, date):
    return int(np.flatnonzero(bars["open_time"] >= pd.Timestamp(date, tz="UTC"))[0])


def idx_last(bars, date):
    return int(np.flatnonzero(bars["open_time"] < pd.Timestamp(date, tz="UTC") + pd.Timedelta("1D"))[-1])


def primary_trades(target: np.ndarray, bars: pd.DataFrame, fc: np.ndarray) -> pd.DataFrame:
    o = bars["open"].to_numpy(float)
    rows, n = [], len(target)
    t = 1
    while t < n - 1:
        s = target[t]
        if s != 0 and target[t - 1] != s:
            e = t + 1
            while e < n and target[e] == s:
                e += 1
            if e >= n - 1:
                break  # still open at the end of the data: label not realized
            gross = s * (o[e + 1] / o[t + 1] - 1)
            funding = NORMAL.flat_funding_rate * fc[t + 1 : e + 1].sum() if s > 0 else 0.0
            net = gross - 2 * NORMAL.fee - funding
            rows.append(dict(entry=t, exit_decision=e, exit_fill=e + 1, side=int(s), net=net))
            t = e
        else:
            t += 1
    return pd.DataFrame(rows)


def filtered_target(target: np.ndarray, trades: pd.DataFrame, take: np.ndarray) -> np.ndarray:
    out = np.zeros_like(target)
    for a, b, side, ok in zip(trades.entry.to_numpy(), trades.exit_decision.to_numpy(), trades.side.to_numpy(), take):
        if ok:
            out[int(a) : int(b)] = side
    return out


def model():
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=30, l2_regularization=1.0, random_state=0)


def wf_probs(xt: np.ndarray, y: np.ndarray, trades: pd.DataFrame, first: int, last: int, fit_limit: int | None = None) -> np.ndarray:
    p = np.full(len(trades), np.nan)
    entry, exit_fill = trades.entry.to_numpy(), trades.exit_fill.to_numpy()
    for r in range(first, last + 1, REFIT):
        cutoff = r if fit_limit is None else min(r, fit_limit)
        sel = (entry >= r) & (entry < min(r + REFIT, last + 1))
        if not sel.any():
            continue
        tr = exit_fill + EMBARGO < cutoff
        if tr.sum() < 40 or len(set(y[tr])) < 2:
            continue
        m = model().fit(xt[tr], y[tr])
        p[sel] = m.predict_proba(xt[sel])[:, 1]
    return p


def evaluate(bars, tgt, rng, fr, fc):
    return {k: {m: round(v, 4) if isinstance(v, float) else v for m, v in summarize(backtest(bars, tgt, rng[0], rng[1], c, fr, fc)).items()} for k, c in SCEN.items()}


def main(phase: str, only: list[str] | None = None) -> None:
    if hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() != PROTOCOL_SHA:
        raise SystemExit("protocol changed")
    opened = phase == "opened"
    bars = load_bars("4h", include_opened_year=opened)
    daily = load_bars("1d", include_opened_year=opened)
    funding = load_funding(include_opened_year=opened)
    fr, fc = funding_per_bar(bars, funding)
    OUT.mkdir(parents=True, exist_ok=True)
    wf_first = idx_first(bars, "2021-01-01")
    dev_last = idx_last(bars, R1["windows"]["development_decisions"][1])
    val_first = idx_first(bars, R1["windows"]["selection_validation"][0])
    frozen_path = OUT / "frozen_selection.json"
    selections = json.loads(frozen_path.read_text())["selections"] if frozen_path.exists() else {}
    report = {"protocol_sha256": PROTOCOL_SHA, "phase": phase, "rows": {}}
    if opened:
        marker = OUT / "opened_year_evaluated.txt"
        if marker.exists():
            raise SystemExit("opened-year check already run")
        marker.write_text(pd.Timestamp.utcnow().isoformat())
        ho = (idx_first(bars, R1["windows"]["opened_year_check"][0]), idx_last(bars, R1["windows"]["opened_year_check"][1]))
    matrices = {}
    for direction in ("long", "long_short"):
        target = ribbon_target(bars["close"], 20, 200, "ribbon", direction, "EMA")
        trades = primary_trades(target, bars, fc)
        y = (trades.net > 0).astype(int).to_numpy()
        pname = f"P_{direction}"
        if opened:
            report["rows"][f"{pname}|unfiltered"] = evaluate(bars, target, ho, fr, fc)
        else:
            report["rows"][f"{pname}|unfiltered"] = {w: evaluate(bars, target, r, fr, fc) for w, r in
                                                      (("wf", (wf_first, dev_last)), ("pre_val", (wf_first, val_first - 1)), ("val", (val_first, dev_last)))}
            report[f"{pname}_trades"] = dict(n=len(trades), win_rate=float(y.mean()), mean_net=float(trades.net.mean()))
        for sname, blocks in SETS.items():
            if only and sname not in only:
                continue
            t0 = time.time()
            if sname not in matrices:
                x = build_matrix(bars, daily, funding, blocks)
                dev_x = x.iloc[: dev_last + 1]
                matrices[sname] = x[[c for c in x.columns if dev_x[c].notna().mean() > 0.5 and dev_x[c].nunique(dropna=True) > 1]]
            x = matrices[sname]
            key = f"{pname}|{sname}"
            if opened:
                sel = selections[key]
                x = x[sel["columns"]]
            xt = np.column_stack([x.to_numpy(np.float32)[trades.entry.to_numpy()], trades.side.to_numpy()])
            if opened:
                for mode, lim in (("frozen", ho[0]), ("walk_forward", None)):
                    p = wf_probs(xt, y, trades, ho[0], ho[1], lim)
                    take = np.nan_to_num(p, nan=0.0) > sel["threshold"]
                    report["rows"][f"{key}|{mode}"] = evaluate(bars, filtered_target(target, trades, take), ho, fr, fc)
                    r = report["rows"][f"{key}|{mode}"]
                    print(key, mode, r["normal"]["net_pct"], r["stress"]["net_pct"], r["normal"]["dd_intrabar_pct"], r["normal"]["trades"], flush=True)
                continue
            p = wf_probs(xt, y, trades, wf_first, dev_last)
            per = {}
            for th in THRESHOLDS:
                take = np.nan_to_num(p, nan=0.0) > th
                per[th] = evaluate(bars, filtered_target(target, trades, take), (val_first, dev_last), fr, fc)
            elig = [th for th in THRESHOLDS if per[th]["normal"]["trades"] >= 20]
            best = max(elig, key=lambda th: (round(per[th]["normal"]["net_pct"], 6), th)) if elig else None
            m = ~np.isnan(p)
            row = {"threshold": best, "auc": float(roc_auc_score(y[m], p[m])) if m.sum() > 30 else None, "n_scored": int(m.sum()),
                   "validation_by_threshold": {str(k): {"net": v["normal"]["net_pct"], "trades": v["normal"]["trades"]} for k, v in per.items()}}
            if best is not None:
                take = np.nan_to_num(p, nan=0.0) > best
                tgt = filtered_target(target, trades, take)
                row["wf"] = evaluate(bars, tgt, (wf_first, dev_last), fr, fc)
                row["pre_val"] = evaluate(bars, tgt, (wf_first, val_first - 1), fr, fc)
                row["val"] = per[best]
                base_wf = report["rows"][f"{pname}|unfiltered"]["wf"]
                row["dev_accept"] = bool(row["wf"]["stress"]["net_pct"] > 0 and row["wf"]["normal"]["sharpe"] > base_wf["normal"]["sharpe"] and row["wf"]["normal"]["trades"] >= 60)
                selections[key] = {"threshold": best, "columns": list(x.columns), "dev_accept": row["dev_accept"]}
                print(key, "th", best, "auc", row["auc"], "wf", row["wf"]["normal"]["net_pct"], row["wf"]["stress"]["net_pct"], "sharpe", row["wf"]["normal"]["sharpe"],
                      "vs unfiltered", base_wf["normal"]["net_pct"], base_wf["normal"]["sharpe"], "pre_val", row["pre_val"]["normal"]["net_pct"],
                      "accept", row["dev_accept"], f"{time.time() - t0:.0f}s", flush=True)
            report["rows"][key] = row
    name = "opened_year_report.json" if opened else "dev_report.json"
    (OUT / name).write_text(json.dumps(report, indent=1, default=str))
    if not opened:
        frozen_path.write_text(json.dumps({"protocol_sha256": PROTOCOL_SHA, "frozen_at": pd.Timestamp.utcnow().isoformat(), "selections": selections}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["dev", "opened"])
    ap.add_argument("--sets", nargs="*")
    a = ap.parse_args()
    main(a.phase, a.sets)
