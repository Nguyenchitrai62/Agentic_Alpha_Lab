"""Idea tournament harness (dev-only, 2026-10-05): a common, fast screen for new dip-rung decision models before any engine run.

Data: research/diagnostics/phase_agents/fills_U.parquet = every dip-rung fill of the standalone engine replica (v293, audited fidelity) for the
5 majors + 30 U2020 alts (survivorship-free), rungs 2.0..5.0 sigma_4h below the 4h bar open, standard grid, 2020-08..2025-09-24, with exact
net returns under take-profit 0.5 / 1.0 / 1.5 sigma (y0.5 / y1.0 / y1.5; close5 stop 4 sigma, 8-sigma backstop, bar-end exit, fees, adverse
funding) and the fill-time state x0..x6 (sp30, depth, volreg, trend, btc_sp30, dd24, hour; known at minute f - 1).
Decision under test = the SIZE multiplier of each majors rung (R2 rungs 2.5 / 3.0 / 3.5 / 4.0 / 5.0) set when the bid is placed at the bar
open T (bar-open information only; fill-time ideas must be labelled bot-only). The take-profit is held at the DEPLOYED agent's choice
(v321 R2 table) so only sizing differs.
Folds (walk-forward, the deployed protocol): test year Y = [anchor, anchor + 365 d) for anchors 2021-09-24 .. 2024-09-24; a model for year Y
may train ONLY on rows with t_exit < anchor - 7 days (any of the 35 coins). The most recent year (>= 2025-09-24) is not in this data and must
never be touched. Labels: y_dep = net return at the deployed TP.
Score per year (equal exposure): new sizes are rescaled so their mean equals the deployed sizes' mean in that year; S = sum(size * y_dep);
gain = S_new - S_dep (units: equity-notional per unit rung size). GRADUATION (fixed before any idea is scored): gain > 0 in >= 3 of 4 years
AND total gain > 0 AND the worst single-day sum(size * y_dep) not more than 20 % worse than the deployed one -> engine test (registered).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FILLS = ROOT / "research/diagnostics/phase_agents/fills_U.parquet"
TABLE = ROOT / "research/diagnostics/phase_agents/tables/r2_table_s0.parquet"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
EMBARGO = pd.Timedelta(days=7)
DEV_END = pd.Timestamp("2025-09-24", tz="UTC")


def load():
    """All rung fills (35 coins) with T = bar open, k = rung depth; majors R2 rows carry the deployed size / tp and y_dep."""
    d = pd.read_parquet(FILLS)
    d = d[d.t_fill < DEV_END].copy()
    d["T"] = d.t_fill - pd.to_timedelta(d.f, unit="min")
    d["k"] = d.x1
    tab = pd.read_parquet(TABLE)
    tab["k"] = tab.rung.map(dict(enumerate(R2)))
    d = d.merge(tab[["T", "sym", "k", "size", "tp"]].rename(columns={"size": "size_dep", "tp": "tp_dep"}), on=["T", "sym", "k"], how="left")
    ycol = {0.5: "y0.5", 1.0: "y1.0", 1.5: "y1.5"}
    tp = d.tp_dep.fillna(1.0)
    d["y_dep"] = np.select([tp == 0.5, tp == 1.5], [d["y0.5"], d["y1.5"]], d["y1.0"])
    return d.reset_index(drop=True)


def folds(d):
    """[(year index, anchor, train mask, test mask)]: train = any coin, t_exit < anchor - 7 d; test = majors R2 rungs in the year."""
    out = []
    for y, a0 in enumerate(ANCHORS):
        tr = (d.t_exit < a0 - EMBARGO).to_numpy()
        te = (d.sym.isin(MAJORS) & d.k.isin(R2) & (d["T"] >= a0) & (d["T"] < a0 + pd.Timedelta(days=365)) & d.size_dep.notna()).to_numpy()
        out.append((y, a0, tr, te))
    return out


def score(d, size_new, name="idea"):
    """size_new: array aligned with d (NaN outside the test rows is fine). Returns the per-year table and the graduation flag."""
    size_new = np.asarray(size_new, float)
    rows, gains, tails = [], [], []
    for y, a0, tr, te in folds(d):
        sd, sn, yy = d.size_dep.to_numpy()[te], size_new[te], d.y_dep.to_numpy()[te]
        ok = np.isfinite(sn)
        sn = np.where(ok, sn, sd)
        sn = sn * sd.mean() / max(sn.mean(), 1e-12)        # equal exposure
        Sd, Sn = float((sd * yy).sum()), float((sn * yy).sum())
        day = d["T"][te].dt.floor("D").to_numpy()
        td = pd.Series(sd * yy).groupby(day).sum().min()
        tn = pd.Series(sn * yy).groupby(day).sum().min()
        ic = float(pd.Series(sn).corr(pd.Series(yy), method="spearman"))
        rows.append(dict(year=str(a0.date()), n=int(te.sum()), S_dep=round(Sd, 4), S_new=round(Sn, 4), gain=round(Sn - Sd, 4),
                         ic_size_y=round(ic, 4), worst_day_dep=round(float(td), 4), worst_day_new=round(float(tn), 4), coverage=round(float(ok.mean()), 3)))
        gains.append(Sn - Sd)
        tails.append((td, tn))
    worst_d, worst_n = min(t[0] for t in tails), min(t[1] for t in tails)
    grad = bool(sum(g > 0 for g in gains) >= 3 and sum(gains) > 0 and worst_n >= 1.2 * worst_d)
    return dict(name=name, years=rows, total_gain=round(float(sum(gains)), 4), graduates=grad)


def score_tp(d, tp_new, name="tp_idea"):
    """Take-profit decision under test (sizes fixed at the deployed size_dep): tp_new in {0.5, 1.0, 1.5} per row (NaN -> deployed tp).
    S = sum(size_dep * y[tp]); same graduation rule as score()."""
    tp_new = np.asarray(tp_new, float)
    Y = {0.5: d["y0.5"].to_numpy(), 1.0: d["y1.0"].to_numpy(), 1.5: d["y1.5"].to_numpy()}
    rows, gains, tails = [], [], []
    for y, a0, tr, te in folds(d):
        sd, yd = d.size_dep.to_numpy()[te], d.y_dep.to_numpy()[te]
        tn = np.where(np.isfinite(tp_new[te]), tp_new[te], d.tp_dep.to_numpy()[te])
        yn = np.select([tn == 0.5, tn == 1.5], [Y[0.5][te], Y[1.5][te]], Y[1.0][te])
        Sd, Sn = float((sd * yd).sum()), float((sd * yn).sum())
        day = d["T"][te].dt.floor("D").to_numpy()
        td, tnn = pd.Series(sd * yd).groupby(day).sum().min(), pd.Series(sd * yn).groupby(day).sum().min()
        rows.append(dict(year=str(a0.date()), n=int(te.sum()), S_dep=round(Sd, 4), S_new=round(Sn, 4), gain=round(Sn - Sd, 4),
                         changed=round(float((tn != d.tp_dep.to_numpy()[te]).mean()), 3), worst_day_dep=round(float(td), 4), worst_day_new=round(float(tnn), 4)))
        gains.append(Sn - Sd)
        tails.append((td, tnn))
    grad = bool(sum(g > 0 for g in gains) >= 3 and sum(gains) > 0 and min(t[1] for t in tails) >= 1.2 * min(t[0] for t in tails))
    return dict(name=name, years=rows, total_gain=round(float(sum(gains)), 4), graduates=grad)


def save(res, folder):
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / "score.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":  # sanity: the deployed sizes score zero gain; a constant size is the 'no agent' reference
    d = load()
    print("rows", len(d), "test rows", int(sum(te.sum() for *_, te in folds(d))))
    print(json.dumps(score(d, d.size_dep, "deployed"), indent=1))
    print(json.dumps(score(d, np.ones(len(d)), "flat_size_1"), indent=1))
