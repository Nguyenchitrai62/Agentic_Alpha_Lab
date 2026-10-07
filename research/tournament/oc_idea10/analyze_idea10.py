"""oc_idea10 analysis: 1h-confirmation filter on 4h dip bids (IDEAS.md #10).

Gate (frozen in PLAN.md): for coin c at 4h bar open T,
  state(c,T) = (open_T - minLow6) / (open_T * sigma_ret),
  open_T = hourly open at T, minLow6 = min low over the six hourly bars
  t in {T-6h..T-1h} (strictly < T), sigma_ret = v293 360-bar std of 4h-open
  returns ending at the bar before T. KEEP = state > 1.0 strict, NaN -> 0.
Outcome y1.0 only, unit rung size, equal-exposure rescale for the filter.

Reads research/tournament/ext/fills_U_ext.parquet + hourly_ext.parquet.
Writes results.json. LIGHT: one coin at a time, one process, RAM < 1 GB.

  .venv/Scripts/python.exe research/tournament/oc_idea10/analyze_idea10.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OC = ROOT / "research/tournament/oc_idea10"
FILLS = ROOT / "research/tournament/ext/fills_U_ext.parquet"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR = pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
THRESH = 1.0
LOOKBACK = 6
MIN_N = 10  # fixed in PLAN.md


def sigma_on_grid(grid: pd.DataFrame) -> pd.Series:
    """v293 sigma: pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1)."""
    o = grid["open"].to_numpy(dtype=float)
    s = pd.Series(o).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1)
    tns = pd.to_datetime(grid["t"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    return pd.Series(s.to_numpy(), index=tns)


def compute_state_for_coin(hc: pd.DataFrame) -> dict:
    """Return dicts keyed by grid T: open_T, sigma_ret, minLow6, state.

    hc: hourly rows for one coin, columns t/open/low, t tz-aware UTC sorted.
    Causal: only rows with t <= T are read for state(T).
    """
    hc = hc.sort_values("t").reset_index(drop=True)
    tns = pd.to_datetime(hc["t"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    open_by_t = dict(zip(tns, hc["open"].to_numpy(dtype=float)))
    low_by_t = dict(zip(tns, hc["low"].to_numpy(dtype=float)))
    # 4h grid opens: hour % 4 == 0
    hh = pd.to_datetime(hc["t"], utc=True)
    gmask = (hh.dt.hour % 4 == 0) & (hh.dt.minute == 0) & (hh.dt.second == 0)
    grid = hc.loc[gmask, ["t", "open"]].copy().sort_values("t").reset_index(drop=True)
    sig = sigma_on_grid(grid)
    sig_by_t = dict(zip(sig.index.to_numpy(dtype=np.int64),
                        sig.to_numpy(dtype=float)))
    H = np.int64(3_600_000_000_000)
    return {"open_by_t": open_by_t, "low_by_t": low_by_t,
            "sig_by_t": sig_by_t, "H": int(H)}


def gate_for_T(open_by_t: dict, low_by_t: dict, sig_by_t: dict, H: int, Tns: int):
    oT = open_by_t.get(Tns, np.nan)
    sg = sig_by_t.get(Tns, np.nan)
    lows = [low_by_t.get(Tns - k * H, np.nan) for k in range(1, LOOKBACK + 1)]
    if not np.isfinite(oT) or not np.isfinite(sg) or sg <= 0:
        return np.nan, oT, sg, np.nan
    arr = np.asarray(lows, dtype=float)
    if not np.all(np.isfinite(arr)):
        return np.nan, oT, sg, np.nan
    ml = float(arr.min())
    st = float((oT - ml) / (oT * sg)) if oT != 0 else np.nan
    return st, oT, sg, ml


def year_stats(y: np.ndarray, mask: np.ndarray):
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "mean_bps": None, "win": None, "min_bps": None}
    yy = y[mask]
    return {"n": n, "mean_bps": round(float(yy.mean()) * 1e4, 2),
            "win": round(float((yy > 0).mean()), 4),
            "min_bps": round(float(yy.min()) * 1e4, 2)}


def maxdd_of_daily(daily: pd.Series) -> float | None:
    if len(daily) == 0:
        return None
    cs = daily.sort_index().cumsum()
    peak = cs.cummax()
    dd = (cs - peak).min()
    return round(float(dd), 6)


def main() -> None:
    f = pd.read_parquet(FILLS)
    f["T"] = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    d = d[d["T"] < CUTOFF].reset_index(drop=True)

    h = pd.read_parquet(HOURLY)
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[h["t"] < CUTOFF].copy()

    # per-coin lookup tables (one coin at a time, LIGHT)
    coin_tab = {}
    for sym in MAJORS:
        hc = h[h["sym"] == sym][["t", "open", "low"]].copy()
        coin_tab[sym] = compute_state_for_coin(hc)

    Tns_all = pd.to_datetime(d["T"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    states = np.full(len(d), np.nan)
    opens = np.full(len(d), np.nan)
    sigmas = np.full(len(d), np.nan)
    minlows = np.full(len(d), np.nan)
    for i, (sym, Tns) in enumerate(zip(d["sym"].to_numpy(), Tns_all)):
        tab = coin_tab[sym]
        st, oT, sg, ml = gate_for_T(tab["open_by_t"], tab["low_by_t"],
                                    tab["sig_by_t"], tab["H"], int(Tns))
        states[i] = st
        opens[i] = oT
        sigmas[i] = sg
        minlows[i] = ml
    d["state"] = states
    d["open_T"] = opens
    d["sigma_ret"] = sigmas
    d["minLow6"] = minlows
    d["KEEP"] = (np.isfinite(states) & (states > THRESH))

    y = d["y1.0"].to_numpy(dtype=float)
    keep = d["KEEP"].to_numpy(bool)
    ymasks = [((d["T"] >= a) & (d["T"] < a + YEAR)).to_numpy() for a in ANCHORS]

    years = []
    spreads = []
    for k, a in enumerate(ANCHORS):
        m = ymasks[k]
        mk, md = m & keep, m & ~keep
        sk, sd = year_stats(y, mk), year_stats(y, md)
        sf = year_stats(y, m)
        n_full, n_kept = int(m.sum()), int(mk.sum())
        if mk.sum() >= MIN_N and md.sum() >= MIN_N:
            spread = round(float(y[mk].mean() - y[m].mean()) * 1e4, 2)
        else:
            spread = None
        spreads.append(spread)
        S_full = round(float(y[m].sum()), 6)
        S_kept = round(float(y[mk].sum()), 6)
        if n_kept > 0:
            fac = n_full / n_kept
            S_kept_eq = round(float(y[mk].sum() * fac), 6)
            gain_eq = round(float(S_kept_eq - S_full), 6)
        else:
            fac, S_kept_eq, gain_eq = None, None, None
        if S_full > 0:
            cut_raw = round((S_full - S_kept) / S_full, 4)
        else:
            cut_raw = None
        day = d["T"][m].dt.floor("D").to_numpy()
        s_full = pd.Series(y[m]).groupby(day).sum().sort_index()
        if mk.sum():
            dayk = d["T"][mk].dt.floor("D").to_numpy()
            s_kept_raw = pd.Series(y[mk]).groupby(dayk).sum().sort_index()
            s_kept_eq = s_kept_raw * fac if fac else s_kept_raw
        else:
            s_kept_raw = pd.Series(dtype=float)
            s_kept_eq = pd.Series(dtype=float)
        wd_full = round(float(s_full.min()), 6) if len(s_full) else None
        wd_kept_eq = round(float(s_kept_eq.min()), 6) if len(s_kept_eq) else None
        tail = bool(wd_kept_eq is not None and wd_full is not None
                    and wd_kept_eq > wd_full)
        dd_full = maxdd_of_daily(s_full)
        dd_kept_eq = maxdd_of_daily(s_kept_eq)
        # state distribution context
        st_y = states[m]
        st_fin = st_y[np.isfinite(st_y)]
        years.append({
            "year": str(a.date()), "n_full": n_full, "n_kept": int(mk.sum()),
            "n_drop": int(md.sum()),
            "kept_share": round(float(mk.sum() / m.sum()), 4) if m.sum() else None,
            "full": sf, "kept": sk, "dropped": sd, "spread_bps": spread,
            "S_full": S_full, "S_kept": S_kept, "S_kept_eq": S_kept_eq,
            "gain_eq": gain_eq, "cut_raw_frac": cut_raw,
            "worst_day_full": wd_full, "worst_day_kept_eq": wd_kept_eq,
            "tail_improves": tail, "maxDD_full": dd_full,
            "maxDD_kept_eq": dd_kept_eq,
            "state_q50": round(float(np.median(st_fin)), 4) if len(st_fin) else None,
            "state_share_gt1": round(float((st_fin > THRESH).mean()), 4) if len(st_fin) else None,
            "state_coverage": round(float(np.isfinite(st_y).mean()), 4),
        })

    loyo = []
    for hh in range(5):
        trm = np.zeros(len(d), bool)
        for k in range(5):
            if k != hh:
                trm |= ymasks[k]
        tri_k, tri_d = trm & keep, trm & ~keep
        held = ymasks[hh]
        hi_k, hi_d = held & keep, held & ~keep
        if (tri_k.sum() >= MIN_N and trm.sum() - tri_k.sum() >= MIN_N
                and hi_k.sum() >= MIN_N and hi_d.sum() >= MIN_N):
            pooled = round(float(y[tri_k].mean() - y[trm].mean()) * 1e4, 2)
            hs = spreads[hh]
            agree = bool(hs is not None and pooled != 0 and hs != 0
                         and np.sign(hs) == np.sign(pooled))
        else:
            pooled, agree = None, False
        loyo.append({"heldout": str(ANCHORS[hh].date()),
                     "held_spread_bps": spreads[hh],
                     "pooled_other4_bps": pooled, "sign_agrees": agree})

    def sgn(x):
        if x is None or x == 0:
            return 0
        return 1 if x > 0 else -1

    pos = sum(1 for s in spreads if sgn(s) > 0)
    agr = sum(1 for L in loyo if L["sign_agrees"])
    tails = sum(1 for w in years if w["tail_improves"])
    promising = bool(pos >= 4 and agr >= 4 and tails >= 4)

    mk_all = keep & np.isfinite(y)
    md_all = (~keep) & np.isfinite(y)
    out = {
        "meta": {"fills": str(FILLS), "hourly": str(HOURLY),
                 "n_majors_r2": int(len(d)),
                 "T_min": str(d["T"].min()), "T_max": str(d["T"].max()),
                 "outcome": "y1.0", "unit": "bps in tables (x1e4)",
                 "gate": "KEEP = state > 1.0 strict, state=(open_T-minLow6)/(open_T*sigma_ret), six 1h bars t<T, sigma=v293 rolling360/min120/shift1",
                 "threshold": THRESH, "lookback_1h": LOOKBACK, "min_n": MIN_N,
                 "cutoff": "2026-09-24 00:00 UTC",
                 "rule": "PROMISING iff spread>0 in >=4/5 AND LOYO agree in >=4/5 AND worst_day_kept_eq>worst_day_full in >=4/5"},
        "years": years, "loyo": loyo,
        "decision": {"pos_spread_count": f"{pos}/5", "loyo_agree_count": f"{agr}/5",
                     "tail_improve_count": f"{tails}/5", "promising": promising},
        "overall": {
            "n_kept": int(mk_all.sum()), "n_drop": int(md_all.sum()),
            "kept_share": round(float(mk_all.sum() / len(d)), 4),
            "mean_full_bps": round(float(y[np.isfinite(y)].mean()) * 1e4, 2),
            "mean_kept_bps": round(float(y[mk_all].mean()) * 1e4, 2) if mk_all.sum() else None,
            "mean_drop_bps": round(float(y[md_all].mean()) * 1e4, 2) if md_all.sum() else None,
            "spread_bps": round(float(y[mk_all].mean() - y[np.isfinite(y)].mean()) * 1e4, 2) if mk_all.sum() else None,
            "state_coverage": round(float(np.isfinite(states).mean()), 4)},
    }
    (OC / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["decision"], indent=1))
    for w in years:
        print(w["year"], "kept", w["n_kept"], "/", w["n_full"],
              "spread", w["spread_bps"], "tail", w["tail_improves"])


if __name__ == "__main__":
    main()
