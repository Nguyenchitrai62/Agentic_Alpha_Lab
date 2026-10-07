"""oc_idea7: VRP-regime dip BUDGET dial (IDEAS.md idea #7).

Frozen PLAN.md definitions. LIGHT: hourly data only, one process, < 1 GB.
Causality: a bar with END = t+1h is usable at time U iff END < U.

Market-wide BTC VRP_z per 4h bar T; sleeve multiplier m(T) in {0.75,1.0,1.25};
size_new = size_dep * m(T); scored with harness5 equal-exposure renormalisation.
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

OUT = ROOT / "research" / "tournament" / "oc_idea7"
DVOL_PANEL = ROOT / "research" / "tournament" / "oc_dvol" / "dvol_hourly.parquet"
HOURLY = H5.HOURLY
MAJORS = H5.MAJORS
R2 = H5.R2
ANCHORS = H5.ANCHORS
DEV_END = H5.DEV_END
FEAT_START = pd.Timestamp("2021-06-30", tz="UTC")
WIN_H = 2160
MIN_WIN = 1728
MIN_TRAIN = 100
MULT = (0.75, 1.0, 1.25)  # lo / mid / hi, single pre-registered triple


def assign_mult(v: np.ndarray, q33: float, q67: float) -> np.ndarray:
    """Bar multiplier: 1.25 if v > q67, 0.75 if v <= q33 (NaN -> 1.0), else 1.0."""
    m = np.full(len(np.atleast_1d(v)), 1.0)
    vv = np.atleast_1d(v).astype(float)
    lo = np.isfinite(vv) & (vv <= q33)
    hi = np.isfinite(vv) & (vv > q67)
    m[lo] = 0.75
    m[hi] = 1.25
    return m


def load_dvol_arrays() -> tuple[np.ndarray, np.ndarray]:
    """BTC DVOL: sorted bar-END ns + closes (t = bar START in panel)."""
    dv = pd.read_parquet(DVOL_PANEL)
    dv = dv[dv["sym"] == "BTCDVOL"].sort_values("t").reset_index(drop=True)
    ends = (dv["t"] + pd.Timedelta(hours=1)).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    return ends, dv["close"].to_numpy(float)


def load_btc_daily() -> tuple[np.ndarray, np.ndarray]:
    """BTCUSDT daily closes: bar-END ns (D 00:00) + closes (23:00 hourly bars)."""
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h = h[(h["sym"] == "BTCUSDT") & (h["t"] < DEV_END)].sort_values("t").reset_index(drop=True)
    d2300 = h[h["t"].dt.strftime("%H:%M") == "23:00"].copy()
    ends = (d2300["t"] + pd.Timedelta(hours=1)).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    return ends, d2300["close"].to_numpy(float)


def build_vrpz_per_T(Tvals: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """Market-wide BTC VRP_z for each bar T (strict end<T as-of)."""
    return vrpz_from_arrays(Tvals, *load_dvol_arrays(), *load_btc_daily())


def vrpz_from_arrays(Tvals: pd.DatetimeIndex, d_ends: np.ndarray, d_cl: np.ndarray,
                     c_ends: np.ndarray, c_cl: np.ndarray) -> tuple[pd.Series, pd.Series]:
    """Market-wide BTC VRP_z for each bar T from raw arrays (strict end<T as-of)."""
    g0 = pd.Timestamp("2021-04-01", tz="UTC")
    G = pd.date_range(g0, pd.Timestamp("2026-09-23 23:00", tz="UTC"), freq="h", tz="UTC")
    gns = G.to_numpy(dtype="datetime64[ns]").astype(np.int64)

    di = np.searchsorted(d_ends, gns, side="left") - 1  # last dvol bar with end < g
    dvol_g = np.full(len(G), np.nan)
    ok = di >= 0
    dvol_g[ok] = d_cl[di[ok]]

    ci = np.searchsorted(c_ends, gns, side="left") - 1  # last daily close with end < g
    rv_g = np.full(len(G), np.nan)
    has = np.where(ci >= 30)[0]
    for i in has:
        seg = c_cl[ci[i] - 30: ci[i] + 1]
        if np.all(np.isfinite(seg)) and np.all(seg > 0):
            r = np.log(seg[1:] / seg[:-1])
            rv_g[i] = float(np.std(r, ddof=1) * np.sqrt(365) * 100)

    prem = dvol_g - rv_g
    valid = np.isfinite(prem)
    c1 = np.cumsum(valid.astype(float))
    s1 = np.cumsum(np.where(valid, prem, 0.0))
    s2 = np.cumsum(np.where(valid, prem ** 2, 0.0))
    c1p = np.concatenate([[0.0], c1])
    s1p = np.concatenate([[0.0], s1])
    s2p = np.concatenate([[0.0], s2])

    gpos = {int(v): i for i, v in enumerate(gns)}
    Tn = Tvals.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    z = np.full(len(Tn), np.nan)
    p0 = np.full(len(Tn), np.nan)
    for j, t in enumerate(Tn):
        i = gpos.get(int(t), None)
        if i is None or not np.isfinite(prem[i]):
            continue
        lo, hi = i - WIN_H, i - 1  # lags 1..2160 (grid steps of 1h)
        a, b = max(lo, 0), hi
        if b < 0:
            continue
        cnt = c1p[b + 1] - c1p[a]
        if cnt < MIN_WIN:
            continue
        m1 = (s1p[b + 1] - s1p[a]) / cnt
        var = ((s2p[b + 1] - s2p[a]) - (s1p[b + 1] - s1p[a]) ** 2 / cnt) / (cnt - 1)
        if not np.isfinite(var) or var <= 0:
            continue
        p0[j] = prem[i]
        z[j] = (prem[i] - m1) / np.sqrt(var)
    return pd.Series(z, index=Tvals), pd.Series(p0, index=Tvals)


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if int(m.sum()) < 30:
        return float("nan")
    return float(st.spearmanr(x[m], y[m])[0])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    is_r2 = d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
    # Cut-off training universe: majors x R2 depths by fill grid (x1), NOT
    # requiring size_dep (the deployed table starts at 2021-09-24, so the
    # year-1 pre-anchor pool would otherwise be empty).
    univ = d["sym"].isin(MAJORS) & d["x1"].isin(R2)
    years = [((d["T"] >= a0) & (d["T"] < a0 + pd.Timedelta(days=365))).to_numpy()
             for a0 in ANCHORS]

    Tuniq = pd.DatetimeIndex(sorted(d.loc[univ, "T"].unique()))
    z_s, prem_s = build_vrpz_per_T(Tuniq)
    zmap = dict(zip(Tuniq, z_s.to_numpy(float)))
    pmap = dict(zip(Tuniq, prem_s.to_numpy(float)))
    d["VRP_z"] = d["T"].map(zmap).astype(float)
    d["prem"] = d["T"].map(pmap).astype(float)
    d[["T", "sym", "x1", "y_dep", "size_dep", "VRP_z", "prem"]].to_parquet(
        OUT / "features_idea7.parquet")

    zv = d["VRP_z"].to_numpy(float)
    yv = d["y_dep"].to_numpy(float)
    univ_np = univ.to_numpy()
    # Feature-training pool (cut-offs): majors-R2 fills, no size_dep needed.
    feas = (d["T"] >= FEAT_START).to_numpy() & np.isfinite(zv) & univ_np

    # --- sequential screen: cut-offs from strictly previous data ---
    size_seq = np.full(len(d), np.nan)
    seq_info = []
    for k, a0 in enumerate(ANCHORS):
        tr = feas & (d["T"] < a0).to_numpy()
        te = years[k] & is_r2.to_numpy()
        cut = {"q33": None, "q67": None, "n_train": int(tr.sum())}
        m = np.full(len(d), np.nan)
        if int(tr.sum()) >= MIN_TRAIN:
            q33, q67 = (float(np.quantile(zv[tr], 1 / 3)),
                        float(np.quantile(zv[tr], 2 / 3)))
            cut = {"q33": q33, "q67": q67, "n_train": int(tr.sum())}
            m[te] = assign_mult(zv[te], q33, q67)
        size_seq[te] = d["size_dep"].to_numpy()[te] * np.where(
            np.isfinite(m[te]), m[te], 1.0)
        seq_info.append(cut)

    res_seq = H5.score(d, size_seq, name="vrp_budget_seq")

    # --- LOYO screen: cut-offs from the other four years ---
    loyo = []
    for hh in range(5):
        tr = np.zeros(len(d), bool)
        for k in range(5):
            if k != hh:
                tr |= years[k]
        tr &= feas
        te = years[hh] & is_r2.to_numpy()
        rec = {"heldout": str(ANCHORS[hh].date()), "n_train": int(tr.sum()),
               "q33": None, "q67": None, "gain": None, "pass": False}
        if int(tr.sum()) >= MIN_TRAIN and int(te.sum()):
            q33, q67 = (float(np.quantile(zv[tr], 1 / 3)),
                        float(np.quantile(zv[tr], 2 / 3)))
            rec["q33"], rec["q67"] = q33, q67
            sd = d["size_dep"].to_numpy()[te]
            sn = sd * assign_mult(zv[te], q33, q67)
            sn = sn * sd.mean() / max(sn.mean(), 1e-12)  # same renorm as harness5
            yy = yv[te]
            rec["gain"] = round(float((sn * yy).sum() - (sd * yy).sum()), 4)
            rec["pass"] = bool(rec["gain"] > 0)
        loyo.append(rec)

    # --- assemble results ---
    sd_all = d["size_dep"].to_numpy()
    years_out = []
    for k, (a0, yr, cut) in enumerate(zip(ANCHORS, res_seq["years"], seq_info)):
        te = years[k] & is_r2.to_numpy()
        cov = float(np.isfinite(zv[te]).mean()) if int(te.sum()) else float("nan")
        mm = assign_mult(zv[te], cut["q33"], cut["q67"]) if cut["q33"] is not None else np.ones(int(te.sum()))
        raw_new = float((sd_all[te] * np.where(np.isfinite(zv[te]), mm, 1.0) * yv[te]).sum())
        raw_dep = float((sd_all[te] * yv[te]).sum())
        shares = {nm: round(float(np.mean(mm == v)), 3) for nm, v in
                  (("lo_0.75", 0.75), ("mid_1.0", 1.0), ("hi_1.25", 1.25))}
        gain = yr["gain"] if yr["gain"] is not None else float("nan")
        wd, wn = yr["worst_day_dep"], yr["worst_day_new"]
        tail_ok = bool(np.isfinite(wn) and np.isfinite(wd) and wn >= wd)
        years_out.append({
            "anchor": str(a0.date()), "n": int(te.sum()), "coverage": round(cov, 4),
            "cutoffs": cut, "S_dep": yr["S_dep"], "S_new": yr["S_new"],
            "gain": gain, "gain_pass": bool(np.isfinite(gain) and gain > 0),
            "worst_day_dep": wd, "worst_day_new": wn, "tail_pass": tail_ok,
            "S_raw_dep": round(raw_dep, 4), "S_raw_new": round(raw_new, 4),
            "retention_raw": round(raw_new / raw_dep, 4) if raw_dep > 0 else None,
            "mult_shares": shares,
            "spearman_vrpz_ydep": round(spearman(zv[te], yv[te]), 4),
        })

    n_gain = sum(1 for y in years_out if y["gain_pass"])
    n_loyo = sum(1 for r in loyo if r["pass"])
    n_tail = sum(1 for y in years_out if y["tail_pass"])
    promising = bool(n_gain >= 4 and n_loyo >= 4 and n_tail >= 4)
    res = {
        "meta": {
            "fills": str(H5.FILLS), "hourly": str(H5.HOURLY),
            "dvol_panel": str(DVOL_PANEL),
            "universe": "majors x R2(2.5,3,3.5,4,5), market-wide BTC VRP_z budget",
            "outcome": "y_dep (deployed TP, exact net)",
            "variant": "single pre-registered triple m={1.25 if VRP_z>q67, 0.75 if VRP_z<=q33, else 1.0}",
            "vrpz": "90d z of (BTC DVOL asof - rv30 hourly) over <=2160 hourly asof lags, min 1728; end<T strict",
            "realised_note": "30d realised from hourly closes (LIGHT equivalent of 1m; 30d window)",
            "T_min": str(d.loc[is_r2, "T"].min()), "T_max": str(d.loc[is_r2, "T"].max()),
            "unit": "native size*y_dep units; bps x1e4 for reference",
        },
        "years": years_out,
        "loyo": loyo,
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
        print(y["anchor"], "n", y["n"], "gain", y["gain"], "pass", y["gain_pass"],
              "W", y["worst_day_dep"], "->", y["worst_day_new"], "tail", y["tail_pass"],
              "ret_raw", y["retention_raw"], "rho", y["spearman_vrpz_ydep"])
    for r in loyo:
        print("LOYO", r["heldout"], "gain", r["gain"], "pass", r["pass"])


if __name__ == "__main__":
    main()
