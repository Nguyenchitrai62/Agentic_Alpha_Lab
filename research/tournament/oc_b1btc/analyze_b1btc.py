"""oc_b1btc: BTC-weighted correlation count for B1 (idea #20).

Frozen PLAN.md definitions. LIGHT: one process, < 1 GB, BTC 1m one yearly
file at a time. n per fill REUSED from oc_manual3 n_per_fill.parquet
(v399-exact); btc_det recomputed EXACTLY as v399 for the BTC leg only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5

OUT = ROOT / "research" / "tournament" / "oc_b1btc"
NFILE = ROOT / "research" / "tournament" / "oc_manual3" / "n_per_fill.parquet"
B1SHAPE = ROOT / "research" / "tournament" / "oc_b1shape" / "fills_n.parquet"
MAJORS = list(H5.MAJORS)
R2 = tuple(H5.R2)
ANCHORS = list(H5.ANCHORS)
DEV_END = H5.DEV_END
YEAR_D = pd.Timedelta(days=365)

BTC_DIR = ROOT / "data" / "raw" / "btc_intraday_20260924"


def btc_det_row(O: float, C: float, sg: float, own_is_btc: bool) -> int:
    """Exact v399 BTC-leg detection for one fill (pure helper, unit-tested)."""
    if own_is_btc:
        return 0
    if not (np.isfinite(O) and np.isfinite(C) and np.isfinite(sg)):
        return 0
    if sg <= 0:
        return 0
    return int(float(C) <= float(O) * (1 - 2.5 * float(sg)))


def maxdd_of_cumsum(cum: np.ndarray) -> float:
    """Max peak-to-trough decline of a cumsum path from 0 (native units)."""
    if len(cum) == 0:
        return 0.0
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[:-1]
    return float(np.maximum(0.0, np.max(peak - cum)))


def compute_btc_leg(Tuniq: pd.DatetimeIndex, need_min: set):
    """BTC O(T)/sig(T)/close-by-minute, one yearly 1m file at a time."""
    G = pd.date_range("2020-06-01", "2026-09-24", freq="4h", tz="UTC")
    G = G[G < DEV_END]
    open_at: dict[int, float] = {}
    close_by: dict[int, float] = {}
    for fp in sorted(BTC_DIR.glob("klines_1m_20*.parquet")):
        df = pd.read_parquet(fp, columns=["open_time", "open", "close"])
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df = df[(df["open_time"] >= pd.Timestamp("2020-06-01", tz="UTC"))
                & (df["open_time"] < DEV_END)]
        if df.empty:
            del df
            continue
        df = df.drop_duplicates("open_time").set_index("open_time").sort_index()
        hit_g = df.index.intersection(G)
        if len(hit_g):
            o = df["open"].reindex(hit_g)
            for ts, v in zip(hit_g, o.to_numpy(float)):
                if np.isfinite(v):
                    open_at[int(ts.value)] = float(v)
        want = need_min.intersection(set(df.index))
        if want:
            idx = pd.DatetimeIndex(sorted(want))
            c = df["close"].reindex(idx)
            arr = c.to_numpy(float)
            for ts, v in zip(idx, arr):
                if np.isfinite(v):
                    close_by[int(ts.value)] = float(v)
        del df
    o = pd.Series({pd.Timestamp(v, tz="UTC"): open_at[v] for v in open_at})
    o = o.reindex(G).astype(float)
    sig = o.pct_change().rolling(360, min_periods=120).std()
    sig_T = {int(t.value): (float(sig.loc[t]) if t in sig.index and np.isfinite(sig.loc[t]) else np.nan)
             for t in Tuniq}
    open_T = {int(t.value): float(open_at.get(int(t.value), np.nan)) for t in Tuniq}
    return sig_T, open_T, close_by


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    d["t_fill"] = pd.to_datetime(d["t_fill"], utc=True)
    is_test = (d["sym"].isin(MAJORS) & d["k"].isin(R2) & d["size_dep"].notna()
               & (d["T"] >= ANCHORS[0]) & (d["T"] < ANCHORS[-1] + YEAR_D))
    test = d[is_test].copy().reset_index(drop=True)
    assert len(test) == 5498, f"TEST rows {len(test)} != 5498"

    # --- reuse stored n (v399-exact) ---
    ndf = pd.read_parquet(NFILE)
    ndf["T"] = pd.to_datetime(ndf["T"], utc=True)
    ndf["t_fill"] = pd.to_datetime(ndf["t_fill"], utc=True)
    key = ["sym", "x1", "T", "t_fill", "f"]
    assert test.set_index(key).index.is_unique
    assert ndf.set_index(key).index.is_unique
    m = test.merge(ndf[key + ["n"]], on=key, how="left", validate="one_to_one")
    assert int(m["n"].notna().sum()) == len(m), "n join incomplete"
    m["n"] = m["n"].to_numpy(int)
    assert bool(m["n"].between(0, 4).all())

    # --- exact BTC leg (BTC 1m only) ---
    Tuniq = pd.DatetimeIndex(sorted(m["T"].unique()))
    need_min: set = set()
    for t in Tuniq:
        base = pd.Timestamp(t)
        need_min.update(pd.date_range(base, base + pd.Timedelta(minutes=239), freq="min"))
    sig_T, open_T, close_by = compute_btc_leg(Tuniq, need_min)
    Tn = m["T"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    fn = m["f"].to_numpy(int)
    Mns = (m["T"] + pd.to_timedelta(m["f"] - 1, unit="min")).to_numpy(
        dtype="datetime64[ns]").astype(np.int64)
    Tns = Tn
    ocol = np.array([open_T.get(int(v), np.nan) for v in Tns], float)
    scol = np.array([sig_T.get(int(v), np.nan) for v in Tns], float)
    ccol = np.full(len(m), np.nan)
    get = close_by.get
    for i in range(len(m)):
        if int(fn[i]) <= 0:
            ccol[i] = np.nan
            continue
        t0, mm = int(Tns[i]), int(Mns[i])
        v = get(mm, None)
        if v is None or not np.isfinite(v):
            mm -= 60_000_000_000
            while mm >= t0:
                v = get(mm, None)
                if v is not None and np.isfinite(v):
                    break
                mm -= 60_000_000_000
            else:
                v = np.nan
        ccol[i] = v if v is not None else np.nan
    print(f"BTC leg cov: open {np.isfinite(ocol).mean():.3f} "
          f"sig {np.isfinite(scol).mean():.3f} close {np.isfinite(ccol).mean():.3f}",
          flush=True)
    del sig_T, open_T, close_by
    own_btc = (m["sym"].to_numpy() == "BTCUSDT")
    btc_det = np.zeros(len(m), dtype=int)
    for i in range(len(m)):
        btc_det[i] = btc_det_row(ocol[i], ccol[i], scol[i], bool(own_btc[i]))
    m["btc_det"] = btc_det
    m["n_btc"] = np.where(own_btc, m["n"].to_numpy(int),
                          m["n"].to_numpy(int) + btc_det)
    assert bool(m["n_btc"].between(0, 5).all())
    assert bool((m.loc[own_btc, "btc_det"] == 0).all())
    viol = int(((~own_btc) & (m["btc_det"].to_numpy() == 1)
                & (m["n"].to_numpy() == 0)).sum())
    # btc_det==1 with n==0 is impossible under exact consistency
    # (BTC counted in n); report, do not fail the run on it.
    print(f"consistency: non-BTC btc_det=1 & n=0 rows = {viol}", flush=True)

    # --- descriptive agreement vs oc_b1shape btc_det (no-ffill variant) ---
    agree = None
    try:
        b = pd.read_parquet(B1SHAPE)
        b["Tbar"] = pd.to_datetime(b["Tbar"], utc=True)
        b["t_fill"] = pd.to_datetime(b["t_fill"], utc=True)
        bkey = m[["sym", "x1", "T", "t_fill", "f"]].merge(
            b[["sym", "k", "Tbar", "t_fill", "f", "btc_det"]].rename(
                columns={"Tbar": "T", "k": "x1", "btc_det": "btc_det_b1shape"}),
            on=["sym", "x1", "T", "t_fill", "f"], how="left", validate="one_to_one")
        assert int(bkey["btc_det_b1shape"].notna().sum()) == len(m)
        agree = float((bkey["btc_det_b1shape"].to_numpy(int)
                       == m["btc_det"].to_numpy(int)).mean())
        print(f"btc_det agreement exact vs b1shape: {agree:.4f}", flush=True)
    except Exception as e:  # descriptive only; never fail scoring
        print(f"b1shape cross-check skipped: {e}", flush=True)

    # --- per-year B1 vs B1-BTC (equal-exposure renormalised) ---
    m["w_a_raw"] = 1.0 / (1.0 + m["n"].to_numpy(float))
    m["w_b_raw"] = 1.0 / (1.0 + m["n_btc"].to_numpy(float))
    years = []
    for k, a0 in enumerate(ANCHORS):
        a0 = pd.Timestamp(a0)
        te = ((m["T"] >= a0) & (m["T"] < a0 + YEAR_D)).to_numpy()
        idx = np.where(te)[0]
        sd = m["size_dep"].to_numpy()[te]
        yd = m["y_dep"].to_numpy()[te]
        wa_raw = m["w_a_raw"].to_numpy()[te]
        wb_raw = m["w_b_raw"].to_numpy()[te]
        ra = sd * wa_raw
        rb = sd * wb_raw
        sa = ra * sd.mean() / max(ra.mean(), 1e-12)
        sb = rb * sd.mean() / max(rb.mean(), 1e-12)
        day = m["T"][te].dt.floor("D").to_numpy()
        da = pd.Series(sa * yd).groupby(day).sum().sort_index()
        db = pd.Series(sb * yd).groupby(day).sum().sort_index()
        Sa, Sb = float((sa * yd).sum()), float((sb * yd).sum())
        Wa, Wb = float(da.min()), float(db.min())
        DDa = maxdd_of_cumsum(da.cumsum().to_numpy())
        DDb = maxdd_of_cumsum(db.cumsum().to_numpy())
        gain = Sb - Sa
        # win-rate split (descriptive): y_dep > 0 fractions
        sub = m[te]
        yv = sub["y_dep"].to_numpy(float)
        nb = sub["btc_det"].to_numpy(int)
        nn = sub["n"].to_numpy(int)
        syms = sub["sym"].to_numpy()
        nb_mask = (syms != "BTCUSDT") & (nb == 1)
        ao_mask = (syms != "BTCUSDT") & (nb == 0) & (nn >= 1)
        is_mask = (syms != "BTCUSDT") & (nn == 0)
        bo_mask = (syms == "BTCUSDT")

        def wr(mm):
            if int(mm.sum()) == 0:
                return {"n": 0, "win_rate": None, "mean_bps": None}
            yy = yv[mm]
            return {"n": int(mm.sum()),
                    "win_rate": round(float((yy > 0).mean()), 4),
                    "mean_bps": round(float(yy.mean() * 1e4), 1)}

        n_dist = pd.Series(nn).value_counts().sort_index()
        btc_share = float(nb_mask.mean()) if len(sub) else float("nan")
        years.append({
            "anchor": str(a0.date()), "n": int(te.sum()),
            "S_a": round(Sa, 4), "S_b": round(Sb, 4),
            "gain": round(gain, 4), "gain_pass": bool(gain > 0),
            "W_a": round(Wa, 4), "W_b": round(Wb, 4),
            "DD_a": round(DDa, 4), "DD_b": round(DDb, 4),
            "dd_pass": bool(DDb <= DDa),
            "buckets": {
                "btc_flush": wr(nb_mask), "alt_only": wr(ao_mask),
                "isolated": wr(is_mask), "btc_own": wr(bo_mask)},
            "btc_det_share": round(btc_share, 4),
            "n_dist": {str(kk): int(vv) for kk, vv in n_dist.items()},
        })
    gains = np.array([y["gain"] for y in years], float)
    loyo = []
    for h in range(5):
        others = [gains[k] for k in range(5) if k != h]
        lg = float(np.mean(others))
        loyo.append({"heldout": years[h]["anchor"], "loyo_gain": round(lg, 4),
                     "pass": bool(lg > 0)})
    n_gain = sum(1 for y in years if y["gain_pass"])
    n_loyo = sum(1 for r in loyo if r["pass"])
    n_dd = sum(1 for y in years if y["dd_pass"])
    promising = bool(n_gain >= 4 and n_loyo >= 4 and n_dd >= 4)
    res = {
        "meta": {
            "fills": str(H5.FILLS), "table": str(H5.TABLE),
            "n_source": "REUSED oc_manual3 n_per_fill.parquet (v399-exact 2.5-sigma); joined on (sym,x1,T,t_fill,f)",
            "btc_det_source": "recomputed EXACTLY as v399 for the BTC leg only from data/raw/btc_intraday_20260924/klines_1m_20*.parquet, one yearly file at a time; O = 1m open at T (no ffill), C = 1m close at T+f-1 with within-bar ffill, sig = 4h-open rolling(360,min120).std; minutes < 2026-09-24 00:00 UTC only",
            "btc_det_agreement_vs_b1shape": agree,
            "btc_det_n0_violations": viol,
            "universe": "majors x R2(2.5,3,3.5,4,5) TEST with size_dep non-NaN, outcome y_dep (deployed TP, exact net)",
            "arms": "B1: size_dep/(1+n); B1-BTC: size_dep/(1+n_btc), n_btc = n+btc_det (non-BTC) else n",
            "renorm": "per-year mean-match to size_dep: s = raw*mean(sd)/mean(raw)",
            "maxDD": "max peak-to-trough decline of cumsum of calendar-day sums from 0 (native units)",
            "loyo": "LOYO_gain(h) = mean gain over the other 4 years (no fitted params; stability check)",
            "rule": "PROMISING iff gain>0 in >=4/5 years AND LOYO_gain>0 in >=4/5 AND DD_b<=DD_a in >=4/5",
            "T_min": str(m["T"].min()), "T_max": str(m["T"].max()),
            "test_rows": int(len(m)),
        },
        "years": years,
        "loyo": loyo,
        "decision": {
            "gain": f"{n_gain}/5", "loyo_gain": f"{n_loyo}/5",
            "dd_not_worse": f"{n_dd}/5", "promising": promising},
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    m[["sym", "x1", "T", "t_fill", "f", "size_dep", "y_dep",
       "n", "btc_det", "n_btc"]].to_parquet(OUT / "n_btc_per_fill.parquet")
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y["anchor"], "n", y["n"], "S", y["S_a"], "->", y["S_b"],
              "gain", y["gain"], y["gain_pass"], "W", y["W_a"], "->", y["W_b"],
              "DD", y["DD_a"], "->", y["DD_b"], y["dd_pass"],
              "buckets", {k: (v["n"], v["win_rate"], v["mean_bps"])
                          for k, v in y["buckets"].items()})
    for r in loyo:
        print("LOYO", r["heldout"], r["loyo_gain"], r["pass"])


if __name__ == "__main__":
    main()
