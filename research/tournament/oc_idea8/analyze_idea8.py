"""oc_idea8: dominance-momentum dip throttle (IDEAS.md idea #8).

Frozen PLAN.md definitions. LIGHT: 4h opens only, one process, < 1 GB.

Market-wide FLOW per 4h bar T: dom30 (BTC 30d log-ret minus equal-weight
majors 30d log-ret, 180 bars, identical math to oc_dombook) then
ddom(T) = dom30(T) - dom30 42 bars earlier (7 d on the 4h grid).
Alt-dip throttle: m = 0.5 on ETH/SOL/BNB/XRP fills when ddom(T) > q67
(pre-anchor 67th pct over full-opens-history bars < anchor), else 1.0;
BTC always 1.0. size_new = size_dep * m, scored with harness5
equal-exposure renormalisation per year (timing only).

  python research/tournament/oc_idea8/analyze_idea8.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5

OUT = ROOT / "research" / "tournament" / "oc_idea8"
OPENS = ROOT / "artifacts" / "research" / "engine_real" / "opens_v154.parquet"

MAJORS = H5.MAJORS
ALTS = ["ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = H5.R2
ANCHORS = H5.ANCHORS
YEAR_LEN = pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
B30 = 180   # 30 d in 4h bars
LAG7D = 42  # 7 d in 4h bars
MIN_TRAIN_BARS = 100
THROTTLE_MULT = 0.5


def assign_mult(sym: np.ndarray, ddom: np.ndarray, q67: float) -> np.ndarray:
    """Per-fill multiplier: 0.5 on alt fills with ddom > q67, else 1.0.

    NaN ddom -> 1.0; ddom == q67 (boundary tie) -> 1.0; BTC always 1.0.
    """
    sym = np.asarray(sym, dtype=object)
    vv = np.asarray(ddom, dtype=float)
    m = np.ones(len(vv))
    flag = np.isfinite(vv) & (vv > q67) & (sym != "BTCUSDT")
    m[flag] = THROTTLE_MULT
    return m


def load_opens_grid() -> pd.DataFrame:
    """Full 4h opens history restricted to bars < CUTOFF, sorted ascending."""
    o = pd.read_parquet(OPENS)
    o = o.sort_index()
    o = o[o.index < CUTOFF]
    assert o.index.is_monotonic_increasing and o.index.tz is not None
    return o[MAJORS]


def compute_dom_ddom(opens: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Causal dom30 + ddom on the full opens grid (PLAN-literal math)."""
    r30 = np.log(opens / opens.shift(B30))
    dom = r30["BTCUSDT"] - r30[MAJORS].mean(axis=1)
    ddom = dom - dom.shift(LAG7D)  # positional: 42 bars = 7 d on the 4h grid
    return dom, ddom


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if int(m.sum()) < 30:
        return float("nan")
    return float(st.spearmanr(x[m], y[m])[0])


def maxdd(cum: np.ndarray) -> float:
    return float(np.min(cum - np.maximum.accumulate(cum))) if len(cum) else 0.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    opens = load_opens_grid()
    dom, ddom = compute_dom_ddom(opens)
    bar_time = opens.index
    bar_ddom = ddom.to_numpy(float)

    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    assert bool((d["T"] < CUTOFF).all()), "fills beyond market-data cutoff"
    is_r2 = (d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()).to_numpy()
    univ = (d["sym"].isin(MAJORS) & d["x1"].isin(R2)).to_numpy()
    Tvals = d["T"]
    pos = bar_time.get_indexer(Tvals)  # positional; -1 if T not on the grid
    n_missing_grid = int((pos < 0).sum())
    dom_v = np.full(len(d), np.nan)
    ddom_v = np.full(len(d), np.nan)
    ok = pos >= 0
    dom_full = dom.to_numpy(float)
    dom_v[ok] = dom_full[pos[ok]]
    ddom_v[ok] = bar_ddom[pos[ok]]

    d["dom30"] = dom_v
    d["ddom"] = ddom_v
    d.loc[univ, ["T", "sym", "x1", "y_dep", "size_dep", "dom30", "ddom"]].to_parquet(
        OUT / "features_idea8.parquet")

    years = [((d["T"] >= a0) & (d["T"] < a0 + YEAR_LEN)).to_numpy() for a0 in ANCHORS]
    zv = d["ddom"].to_numpy(float)
    yv = d["y_dep"].to_numpy(float)
    symv = d["sym"].to_numpy(dtype=object)
    sd_all = d["size_dep"].to_numpy(float)

    # --- sequential cut-offs: 67th pct of ddom over bars strictly < anchor ---
    bar_ns = bar_time.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    seq_q, seq_ntrain = [], []
    for a0 in ANCHORS:
        a_ns = int(a0.value)
        pool = bar_ddom[(bar_ns < a_ns) & np.isfinite(bar_ddom)]
        seq_ntrain.append(int(len(pool)))
        seq_q.append(float(np.quantile(pool, 2 / 3)) if len(pool) >= MIN_TRAIN_BARS else float("nan"))

    size_seq = np.full(len(d), np.nan)
    for k in range(5):
        te = years[k] & is_r2
        q = seq_q[k]
        m = assign_mult(symv[te], zv[te], q) if np.isfinite(q) else np.ones(int(te.sum()))
        size_seq[te] = sd_all[te] * m
    res_seq = H5.score(d, size_seq, name="domflow_throttle_seq")

    # --- LOYO cut-offs: 67th pct over bars inside the other 4 year windows ---
    loyo = []
    for hh in range(5):
        other = np.zeros(len(bar_time), bool)
        for k in range(5):
            if k != hh:
                m_ = np.asarray(bar_time >= ANCHORS[k]) & np.asarray(bar_time < ANCHORS[k] + YEAR_LEN)
                other |= m_
        pool = bar_ddom[other & np.isfinite(bar_ddom)]
        rec = {"heldout": str(ANCHORS[hh].date()), "n_train_bars": int(len(pool)),
               "q67": None, "gain": None, "pass": False}
        if len(pool) >= MIN_TRAIN_BARS:
            q = float(np.quantile(pool, 2 / 3))
            rec["q67"] = q
            te = years[hh] & is_r2
            sd = sd_all[te]
            sn = sd * assign_mult(symv[te], zv[te], q)
            sn = sn * sd.mean() / max(sn.mean(), 1e-12)  # same renorm as harness5
            yy = yv[te]
            rec["gain"] = round(float((sn * yy).sum() - (sd * yy).sum()), 4)
            rec["pass"] = bool(rec["gain"] > 0)
        loyo.append(rec)

    # --- assemble results ---
    years_out = []
    for k, (a0, yr) in enumerate(zip(ANCHORS, res_seq["years"])):
        te = years[k] & is_r2
        q = seq_q[k]
        m = assign_mult(symv[te], zv[te], q) if np.isfinite(q) else np.ones(int(te.sum()))
        alt = (symv[te] != "BTCUSDT")
        cov = float(np.isfinite(zv[te]).mean()) if int(te.sum()) else float("nan")
        thr_share = round(float((m == THROTTLE_MULT).mean()), 4) if int(te.sum()) else None
        thr_alt = round(float((m[alt] == THROTTLE_MULT).mean()), 4) if int(alt.sum()) else None
        sd = sd_all[te]
        sn_renorm_factor = sd.mean() / max((sd * m).mean(), 1e-12)
        sn = sd * m * sn_renorm_factor
        yy = yv[te]
        raw_new = float((sd * m * yy).sum())
        raw_dep = float((sd * yy).sum())
        per_coin = {}
        for s in MAJORS:
            ms = symv[te] == s
            per_coin[s] = {
                "n": int(ms.sum()),
                "thr_share": round(float((m[ms] == THROTTLE_MULT).mean()), 4) if int(ms.sum()) else None,
                "S_dep": round(float((sd[ms] * yy[ms]).sum()), 4),
                "S_new": round(float((sn[ms] * yy[ms]).sum()), 4),
                "gain": round(float(((sn[ms] - sd[ms]) * yy[ms]).sum()), 4),
            }
        gain = yr["gain"]
        wd, wn = yr["worst_day_dep"], yr["worst_day_new"]
        tail_ok = bool(np.isfinite(wn) and np.isfinite(wd) and wn >= wd)
        years_out.append({
            "anchor": str(a0.date()), "n": int(te.sum()), "coverage": round(cov, 4),
            "q67": q, "n_train_bars": seq_ntrain[k],
            "thr_share": thr_share, "thr_share_alts": thr_alt,
            "S_dep": yr["S_dep"], "S_new": yr["S_new"],
            "gain": gain, "gain_pass": bool(np.isfinite(gain) and gain > 0),
            "worst_day_dep": wd, "worst_day_new": wn, "tail_pass": tail_ok,
            "S_raw_dep": round(raw_dep, 4), "S_raw_new": round(raw_new, 4),
            "retention_raw": round(raw_new / raw_dep, 4) if raw_dep > 0 else None,
            "per_coin": per_coin,
            "spearman_ddom_ydep_alts": round(spearman(zv[te][alt], yy[alt]), 4),
        })

    # full-path worst-day / maxDD on concatenated renormalised daily sums
    dall_parts = []
    for k in range(5):
        te = years[k] & is_r2
        q = seq_q[k]
        m = assign_mult(symv[te], zv[te], q) if np.isfinite(q) else np.ones(int(te.sum()))
        sd = sd_all[te]
        sn = sd * m * sd.mean() / max((sd * m).mean(), 1e-12)
        yy = yv[te]
        day = d["T"][te].dt.floor("D")
        dall_parts.append(pd.DataFrame(
            {"dep": sd * yy, "new": sn * yy}, index=day.to_numpy()))
    dall = pd.concat(dall_parts).sort_index()
    dep_daily = dall.groupby(level=0)["dep"].sum()
    new_daily = dall.groupby(level=0)["new"].sum()
    path = {
        "worst_day_dep": round(float(dep_daily.min()), 4),
        "worst_day_new": round(float(new_daily.min()), 4),
        "maxDD_dep": round(maxdd(dep_daily.cumsum().to_numpy()), 4),
        "maxDD_new": round(maxdd(new_daily.cumsum().to_numpy()), 4),
    }

    n_gain = sum(1 for y in years_out if y["gain_pass"])
    n_loyo = sum(1 for r in loyo if r["pass"])
    n_tail = sum(1 for y in years_out if y["tail_pass"])
    promising = bool(n_gain >= 4 and n_loyo >= 4 and n_tail >= 4)
    res = {
        "meta": {
            "fills": str(H5.FILLS), "table": str(H5.TABLE),
            "opens": str(OPENS),
            "universe": "majors x R2(2.5,3,3.5,4,5), market-wide BTC-dominance FLOW throttle on alt dips",
            "outcome": "y_dep (deployed TP, exact net)",
            "variant": "single pre-registered rule m=0.5 on ETH/SOL/BNB/XRP fills iff ddom(T) > q67 else 1.0; BTC always 1.0",
            "dom30": "log(BTC[t]/BTC[t-180]) - mean_s log(S[t]/S[t-180]) on full 4h opens history, causal (oc_dombook math)",
            "ddom": "dom30[t] - dom30[t-42bars] (42 x 4h = 7 d, positional on sorted full grid)",
            "cutoffs": "q67 = 67th pct of ddom over full-grid bars strictly < anchor (sequential) resp. bars in other 4 year windows (LOYO)",
            "T_min": str(d.loc[is_r2, "T"].min()), "T_max": str(d.loc[is_r2, "T"].max()),
            "missing_grid_T": n_missing_grid,
            "unit": "native size*y_dep units",
        },
        "years": years_out,
        "loyo": loyo,
        "fullpath": path,
        "decision": {
            "gain_sequential": f"{n_gain}/5",
            "loyo_gain": f"{n_loyo}/5",
            "tail_not_worse": f"{n_tail}/5",
            "promising": promising,
        },
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years_out:
        print(y["anchor"], "n", y["n"], "q67", round(y["q67"], 4) if y["q67"] is not None else None,
              "thr", y["thr_share"], "gain", y["gain"], "pass", y["gain_pass"],
              "W", y["worst_day_dep"], "->", y["worst_day_new"], "tail", y["tail_pass"],
              "ret_raw", y["retention_raw"], "rho_alts", y["spearman_ddom_ydep_alts"])
    for r in loyo:
        print("LOYO", r["heldout"], "q67", r["q67"], "gain", r["gain"], "pass", r["pass"])
    print("fullpath", path)


if __name__ == "__main__":
    main()
