"""oc_idea6: basis-MOMENTUM dip throttle (IDEAS.md idea #6).

Frozen PLAN.md definitions. LIGHT: delivery-hourly + hourly panel + fills
only, one process, < 1 GB. No 1m data.

Market-wide signal per 4h bar T: mom(T) = BTC front-quarterly annualised
basis(T) - basis(T-24h), where basis(S) is the last 4h delivery close
strictly before S (4h closes from data/raw/qbasis_20261003 BTC legs,
annualised vs the hourly_ext BTCUSDT perp close, UM preferred else CM,
front = nearest expiry > C + 7d, ln(F/P)*365/DTE).
Throttle: m = 0.5 on ALL 5 majors fills iff mom(T) < p20 (walk-forward 20th
pct over 4h grid bars strictly < anchor), else 1.0. size_new = size_dep * m,
scored with harness5 equal-exposure renormalisation per year (timing only).

  python research/tournament/oc_idea6/analyze_idea6.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5

OUT = ROOT / "research" / "tournament" / "oc_idea6"
QDIR = ROOT / "data" / "raw" / "qbasis_20261003"
HOURLY = ROOT / "research" / "tournament" / "ext" / "hourly_ext.parquet"

MAJORS = H5.MAJORS
R2 = H5.R2
ANCHORS = H5.ANCHORS
YEAR_LEN = pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
GRID_START = pd.Timestamp("2020-08-01", tz="UTC")
ROLL_DAYS = 7
MIN_TRAIN_BARS = 100
THROTTLE_MULT = 0.5
LAG24 = pd.Timedelta(hours=24)


def expiry_from_name(name: str) -> pd.Timestamp:
    m = re.search(r"_(\d{6})_1h", name)
    yy, mm, dd = int(m.group(1)[:2]), int(m.group(1)[2:4]), int(m.group(1)[4:6])
    return pd.Timestamp(2000 + yy, mm, dd, 8, tz="UTC")


def load_venue_closes(coin_pat: str) -> dict:
    """{expiry -> DataFrame(close_time, close)} for one venue glob, causal-ready.

    Drops any bar with close_time >= CUTOFF. One file at a time (LIGHT).
    """
    out = {}
    for path in sorted(QDIR.glob(coin_pat)):
        e = expiry_from_name(path.name)
        d = pd.read_parquet(path, columns=["open_time", "close"])
        ct = pd.DatetimeIndex(pd.to_datetime(d["open_time"], utc=True) + pd.Timedelta(hours=1))
        cl = d["close"].astype(float).to_numpy()
        m = ct < CUTOFF
        ct = ct[m]
        cl = cl[m]
        o = np.argsort(ct.asi8)
        out[e] = pd.DataFrame({"close_time": ct[o],
                               "close": cl[o]}).reset_index(drop=True)
    return out


def venue_hourly_qb(exp_closes: dict, perp: pd.DataFrame) -> pd.DataFrame:
    """Annualised front basis per perp hourly close (causal backward asof)."""
    C = pd.DatetimeIndex(pd.to_datetime(perp["close_time"], utc=True))
    P = perp["perp_close"].to_numpy(float)
    exps = sorted(exp_closes)
    exp_ns = np.array([int(e.value) for e in exps], dtype=np.int64)
    cns = C.asi8
    seven = np.int64(7 * 86400 * 10 ** 9)
    fi = np.searchsorted(exp_ns, cns + seven, side="right")  # first E > C+7d
    qb = np.full(len(C), np.nan)
    front = np.full(len(C), -1, dtype=np.int64)
    for j, e in enumerate(exps):
        m = fi == j
        if not m.any():
            continue
        cc = exp_closes[e]
        if len(cc) == 0:
            continue
        left = pd.DataFrame({"close_time": C[m]})
        got = pd.merge_asof(left.sort_values("close_time"),
                            cc.sort_values("close_time"),
                            on="close_time", direction="backward")
        F = got["close"].to_numpy(float)
        dte = (int(e.value) - cns[m].astype(np.int64)) / 8.64e13
        ok = np.isfinite(F) & (F > 0) & np.isfinite(P[m]) & (P[m] > 0) & (dte > 0)
        q = np.full(m.sum(), np.nan)
        q[ok] = np.log(F[ok] / P[m][ok]) * 365.0 / dte[ok]
        qb[np.flatnonzero(m)] = q
        front[np.flatnonzero(m)] = j
    return pd.DataFrame({"close_time": C, "qb": qb, "front": front})


def assign_mult(sym: np.ndarray, mom: np.ndarray, p20: float) -> np.ndarray:
    """Per-fill multiplier: 0.5 on every coin with mom < p20, else 1.0.

    NaN mom -> 1.0; mom == p20 (boundary tie) -> 1.0 (strictly below only).
    """
    vv = np.asarray(mom, dtype=float)
    m = np.ones(len(vv))
    flag = np.isfinite(vv) & (vv < p20)
    m[flag] = THROTTLE_MULT
    return m


def basis_at(c4_ns: np.ndarray, qb4: np.ndarray, q_ns: np.ndarray) -> np.ndarray:
    """Last 4h value with close strictly < each query (side='left' - 1)."""
    idx = np.searchsorted(c4_ns, q_ns, side="left") - 1
    out = np.full(len(q_ns), np.nan)
    ok = idx >= 0
    out[ok] = qb4[idx[ok]]
    return out


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if int(m.sum()) < 30:
        return float("nan")
    return float(st.spearmanr(x[m], y[m])[0])


def maxdd(cum: np.ndarray) -> float:
    return float(np.min(cum - np.maximum.accumulate(cum))) if len(cum) else 0.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- perp hourly (BTC) ----
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    hb = h[h.sym == "BTCUSDT"][["t", "close"]].sort_values("t").reset_index(drop=True)
    hb["close_time"] = pd.to_datetime(hb["t"], utc=True) + pd.Timedelta(hours=1)
    perp = pd.DataFrame({"close_time": hb["close_time"],
                         "perp_close": hb["close"].astype(float)})
    perp = perp[(perp["close_time"] < CUTOFF)].sort_values("close_time").reset_index(drop=True)
    assert len(perp) and bool((perp["close_time"] < CUTOFF).all())

    # ---- delivery legs (BTC only) ----
    cm = load_venue_closes("cm_BTCUSD_*_1h.parquet")
    um = load_venue_closes("um_BTCUSDT_*_1h.parquet")
    q_um = venue_hourly_qb(um, perp)
    q_cm = venue_hourly_qb(cm, perp)
    qb = q_um["qb"].to_numpy(float).copy()
    venue = np.full(len(qb), "none", dtype=object)
    venue[np.isfinite(qb)] = "um"
    fill = ~np.isfinite(qb)
    qb[fill] = q_cm["qb"].to_numpy(float)[fill]
    venue[fill & np.isfinite(q_cm["qb"].to_numpy(float))] = "cm"
    hourly = pd.DataFrame({"close_time": pd.DatetimeIndex(pd.to_datetime(perp["close_time"], utc=True)),
                           "qb": qb, "venue": venue})
    um_share = float((venue == "um").mean())
    cm_share = float((venue == "cm").mean())

    # ---- 4h series (value = hourly row with C == 4h close) ----
    c4 = pd.date_range(start=GRID_START, end=CUTOFF, freq="4h", tz="UTC")
    c4 = c4[c4 < CUTOFF]
    qb_by_c = dict(zip(pd.DatetimeIndex(hourly["close_time"]).asi8,
                       hourly["qb"].to_numpy(float)))
    c4n = c4.asi8
    qb4 = np.array([qb_by_c.get(t, np.nan) for t in c4n], dtype=float)
    c4_ns = c4n.astype(np.int64)

    # ---- mom on the 4h grid (bar opens) ----
    grid = pd.date_range(start=GRID_START, end=CUTOFF, freq="4h", tz="UTC")
    grid = grid[grid < CUTOFF]
    gns = grid.asi8
    b0 = basis_at(c4_ns, qb4, gns)
    b1 = basis_at(c4_ns, qb4, gns - np.int64(LAG24.total_seconds() * 1e9))
    grid_mom = b0 - b1

    # front-roll dates spanned by mom windows (descriptive)
    roll_mask = np.isfinite(b0)  # placeholder; rolls counted from front series below
    _ = roll_mask

    # ---- fills + mom ----
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    assert bool((d["T"] < CUTOFF).all()), "fills beyond market-data cutoff"
    is_r2 = (d["sym"].isin(MAJORS) & d["x1"].isin(R2) & d["size_dep"].notna()).to_numpy()
    univ = (d["sym"].isin(MAJORS) & d["x1"].isin(R2)).to_numpy()
    Tns = pd.DatetimeIndex(d["T"]).asi8
    mom_v = basis_at(c4_ns, qb4, Tns) - basis_at(
        c4_ns, qb4, Tns - np.int64(LAG24.total_seconds() * 1e9))
    d["mom"] = mom_v

    years = [((d["T"] >= a0) & (d["T"] < a0 + YEAR_LEN)).to_numpy() for a0 in ANCHORS]
    zv = d["mom"].to_numpy(float)
    yv = d["y_dep"].to_numpy(float)
    symv = d["sym"].to_numpy(dtype=object)
    sd_all = d["size_dep"].to_numpy(float)

    # ---- sequential cut-offs: p20 over grid bars strictly < anchor ----
    gns_all = grid.asi8
    seq_q, seq_ntrain = [], []
    for a0 in ANCHORS:
        pool = grid_mom[(gns_all < int(a0.value)) & np.isfinite(grid_mom)]
        seq_ntrain.append(int(len(pool)))
        seq_q.append(float(np.quantile(pool, 0.20)) if len(pool) >= MIN_TRAIN_BARS else float("nan"))

    size_seq = np.full(len(d), np.nan)
    for k in range(5):
        te = years[k] & is_r2
        q = seq_q[k]
        m = assign_mult(symv[te], zv[te], q) if np.isfinite(q) else np.ones(int(te.sum()))
        size_seq[te] = sd_all[te] * m
    res_seq = H5.score(d, size_seq, name="qb_mom_throttle_seq")

    # ---- LOYO cut-offs: p20 over grid bars inside the other 4 windows ----
    loyo = []
    for hh in range(5):
        other = np.zeros(len(grid), bool)
        for k in range(5):
            if k != hh:
                other |= (np.asarray(grid >= ANCHORS[k])
                          & np.asarray(grid < ANCHORS[k] + YEAR_LEN))
        pool = grid_mom[other & np.isfinite(grid_mom)]
        rec = {"heldout": str(ANCHORS[hh].date()), "n_train_bars": int(len(pool)),
               "p20": None, "gain": None, "pass": False}
        if len(pool) >= MIN_TRAIN_BARS:
            q = float(np.quantile(pool, 0.20))
            rec["p20"] = q
            te = years[hh] & is_r2
            sd = sd_all[te]
            sn = sd * assign_mult(symv[te], zv[te], q)
            sn = sn * sd.mean() / max(sn.mean(), 1e-12)
            yy = yv[te]
            rec["gain"] = round(float((sn * yy).sum() - (sd * yy).sum()), 4)
            rec["pass"] = bool(rec["gain"] > 0)
        loyo.append(rec)

    # ---- assemble results ----
    years_out = []
    for k, (a0, yr) in enumerate(zip(ANCHORS, res_seq["years"])):
        te = years[k] & is_r2
        q = seq_q[k]
        m = assign_mult(symv[te], zv[te], q) if np.isfinite(q) else np.ones(int(te.sum()))
        cov = float(np.isfinite(zv[te]).mean()) if int(te.sum()) else float("nan")
        thr_share = round(float((m == THROTTLE_MULT).mean()), 4) if int(te.sum()) else None
        sd = sd_all[te]
        yy = yv[te]
        sn = sd * m * sd.mean() / max((sd * m).mean(), 1e-12)
        raw_new = float((sd * m * yy).sum())
        raw_dep = float((sd * yy).sum())
        # yearly maxDD on the year's daily-sum paths (renorm sizes)
        day = d["T"][te].dt.floor("D").to_numpy()
        dep_daily = pd.Series(sd * yy).groupby(day).sum().sort_index()
        new_daily = pd.Series(sn * yy).groupby(day).sum().sort_index()
        dd_dep = maxdd(dep_daily.cumsum().to_numpy())
        dd_new = maxdd(new_daily.cumsum().to_numpy())
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
        wd_ok = bool(np.isfinite(wn) and np.isfinite(wd) and wn >= wd)
        dd_ok = bool(np.isfinite(dd_new) and np.isfinite(dd_dep) and dd_new >= dd_dep)
        years_out.append({
            "anchor": str(a0.date()), "n": int(te.sum()), "coverage": round(cov, 4),
            "p20": q, "n_train_bars": seq_ntrain[k],
            "thr_share": thr_share,
            "S_dep": yr["S_dep"], "S_new": yr["S_new"],
            "gain": gain, "gain_pass": bool(np.isfinite(gain) and gain > 0),
            "worst_day_dep": wd, "worst_day_new": wn, "wd_pass": wd_ok,
            "maxDD_dep": round(dd_dep, 4), "maxDD_new": round(dd_new, 4),
            "dd_pass": dd_ok, "tail_pass": bool(wd_ok and dd_ok),
            "S_raw_dep": round(raw_dep, 4), "S_raw_new": round(raw_new, 4),
            "retention_raw": round(raw_new / raw_dep, 4) if raw_dep > 0 else None,
            "per_coin": per_coin,
            "spearman_mom_ydep": round(spearman(zv[te], yy), 4),
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

    # save features (universe rows only; for audit + tests)
    feat = d.loc[univ, ["T", "sym", "x1", "y_dep", "size_dep", "mom"]].copy()
    mult = np.full(len(d), np.nan)
    for k in range(5):
        te = years[k] & is_r2
        q = seq_q[k]
        mult[te] = assign_mult(symv[te], zv[te], q) if np.isfinite(q) else np.ones(int(te.sum()))
    d["mult"] = mult
    feat["mult"] = d.loc[univ, "mult"].to_numpy()
    feat["year"] = pd.cut(pd.DatetimeIndex(pd.to_datetime(feat["T"], utc=True)).asi8,
                          bins=[int(a.value) for a in ANCHORS] + [int((ANCHORS[-1] + YEAR_LEN).value)],
                          labels=[str(a.date()) for a in ANCHORS]).astype(str)
    feat.to_parquet(OUT / "features_idea6.parquet")

    n_gain = sum(1 for y in years_out if y["gain_pass"])
    n_loyo = sum(1 for r in loyo if r["pass"])
    n_tail = sum(1 for y in years_out if y["tail_pass"])
    promising = bool(n_gain >= 4 and n_loyo >= 4 and n_tail >= 4)
    res = {
        "meta": {
            "fills": str(H5.FILLS), "table": str(H5.TABLE),
            "delivery": "data/raw/qbasis_20261003 BTC legs (cm 26 + um 25 contracts)",
            "perp": "research/tournament/ext/hourly_ext.parquet BTCUSDT hourly (no 1m)",
            "universe": "majors x R2(2.5,3,3.5,4,5), market-wide BTC basis-momentum throttle on all dips",
            "outcome": "y_dep (deployed TP, exact net)",
            "variant": "single pre-registered rule m=0.5 iff mom(T) < p20 else 1.0, all 5 majors",
            "mom": "mom(T)=basis(T)-basis(T-24h); basis(S)=last 4h annualised front qb with close<S strict; qb(C)=ln(F/P)*365/DTE, FRONT=nearest expiry E>C+7d, UM preferred else CM",
            "cutoffs": "p20 = 20th pct of mom over 4h grid bars strictly < anchor (sequential) resp. grid bars in other 4 year windows (LOYO)",
            "T_min": str(d.loc[is_r2, "T"].min()), "T_max": str(d.loc[is_r2, "T"].max()),
            "venue_share_hourly": {"um": round(um_share, 4), "cm": round(cm_share, 4)},
            "grid_bars": int(len(grid)),
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
        print(y["anchor"], "n", y["n"], "p20", round(y["p20"], 4),
              "thr", y["thr_share"], "gain", y["gain"], "pass", y["gain_pass"],
              "W", y["worst_day_dep"], "->", y["worst_day_new"],
              "DD", y["maxDD_dep"], "->", y["maxDD_new"], "tail", y["tail_pass"],
              "ret_raw", y["retention_raw"], "rho", y["spearman_mom_ydep"])
    for r in loyo:
        print("LOYO", r["heldout"], "p20", r["p20"], "gain", r["gain"], "pass", r["pass"])
    print("fullpath", path)


if __name__ == "__main__":
    main()
