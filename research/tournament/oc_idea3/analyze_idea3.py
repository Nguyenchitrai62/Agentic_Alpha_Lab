"""oc_idea3 analysis: pre-bar intraday-RV skip (IDEAS.md #3).

Frozen PLAN.md definitions. LIGHT: majors 1m only, one coin at a time, < 1 GB.
Causality: RV15(c,T) uses only minutes [T, T+15] (offsets 0..15), strictly
before the first fillable minute 16; sigma_4h uses 4h opens up to T (v293).

  .venv/Scripts/python.exe research/tournament/oc_idea3/analyze_idea3.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OC = ROOT / "research/tournament/oc_idea3"
FILLS = ROOT / "research/tournament/ext/fills_U_ext.parquet"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR = pd.Timedelta(days=365)
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24", tz="UTC")
Q = 0.80
MIN_TRAIN = 500
MIN_N = 10


def load_1m(sym: str) -> pd.DataFrame:
    if sym == "BTCUSDT":
        files = sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted((ROOT / "data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    m = m[(m.index >= START) & (m.index < END)]
    full = pd.date_range(START, END - pd.Timedelta(minutes=1), freq="1min", tz="UTC")
    m = m.reindex(full)
    for c in ("open", "high", "low", "close"):
        m[c] = m[c].astype("float32")
    return m


def rv15_for_coin(m: pd.DataFrame) -> pd.DataFrame:
    """RV15 per 4h bar: (max high[0..15] - min low[0..15]) / (O * sigma)."""
    full = m.index
    n = len(full)
    nb = n // 240
    bar_t = full[: nb * 240: 240]
    opens = m["open"].to_numpy(dtype=float)[: nb * 240: 240]
    sigma = pd.Series(opens).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy(dtype=float)
    H = m["high"].to_numpy(dtype=float)
    L = m["low"].to_numpy(dtype=float)
    rv = np.full(nb, np.nan)
    for j in range(nb):
        s = j * 240
        hw = H[s: s + 16]
        lw = L[s: s + 16]
        o = opens[j]
        sg = sigma[j]
        if len(hw) < 16 or len(lw) < 16:
            continue
        if not (np.all(np.isfinite(hw)) and np.all(np.isfinite(lw))):
            continue
        if not (np.isfinite(o) and np.isfinite(sg) and sg > 0 and o > 0):
            continue
        rv[j] = float((float(hw.max()) - float(lw.min())) / (float(o) * float(sg)))
    return pd.DataFrame({"T": bar_t, "O": opens, "sigma": sigma, "RV15": rv})


def year_stats(y: np.ndarray, mask: np.ndarray):
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "mean_bps": None, "win": None, "min_bps": None}
    yy = y[mask]
    return {"n": n, "mean_bps": round(float(yy.mean()) * 1e4, 2),
            "win": round(float((yy > 0).mean()), 4),
            "min_bps": round(float(yy.min()) * 1e4, 2)}


def main() -> None:
    t0 = time.time()
    OC.mkdir(parents=True, exist_ok=True)

    # --- per-coin RV15 (one coin at a time) ---
    rv_parts = []
    for sym in MAJORS:
        c0 = time.time()
        px = load_1m(sym)
        r = rv15_for_coin(px)
        r["sym"] = sym
        rv_parts.append(r)
        del px
        print(f"{sym}: bars {len(r)}, RV15 valid {int(np.isfinite(r['RV15']).sum())} "
              f"in {time.time() - c0:.0f}s", flush=True)
    rv = pd.concat(rv_parts, ignore_index=True)
    rv["T"] = pd.to_datetime(rv["T"], utc=True)
    rv.to_parquet(OC / "rv15.parquet")
    print(f"rv15 rows {len(rv)}, valid {int(np.isfinite(rv['RV15']).sum())}", flush=True)

    # --- thresholds (feature quantiles only, no outcomes) ---
    seq_q = []
    for a in ANCHORS:
        w = rv[(rv["T"] >= a - YEAR) & (rv["T"] < a) & np.isfinite(rv["RV15"].to_numpy())]
        q = float(w["RV15"].quantile(Q)) if len(w) >= MIN_TRAIN else float("nan")
        seq_q.append({"anchor": str(a.date()), "q80": q, "n_train": int(len(w))})
    loyo_q = []
    for h, a in enumerate(ANCHORS):
        keep = np.zeros(len(rv), bool)
        for k, b in enumerate(ANCHORS):
            if k == h:
                continue
            keep |= ((rv["T"] >= b) & (rv["T"] < b + YEAR)).to_numpy()
        w = rv[keep & np.isfinite(rv["RV15"].to_numpy())]
        q = float(w["RV15"].quantile(Q)) if len(w) >= MIN_TRAIN else float("nan")
        loyo_q.append({"heldout": str(a.date()), "q80": q, "n_train": int(len(w))})

    # --- fills join ---
    f = pd.read_parquet(FILLS)
    f["T"] = pd.to_datetime(f["t_fill"], utc=True) - pd.to_timedelta(f["f"], unit="min")
    d = f[f["sym"].isin(MAJORS) & f["x1"].isin(R2)].copy().reset_index(drop=True)
    d = d[d["T"] < END].reset_index(drop=True)
    d = d.merge(rv[["T", "sym", "RV15"]], on=["T", "sym"], how="left")
    assert len(d) == 6876, f"majors-R2 rows {len(d)} != 6876"

    y = d["y1.0"].to_numpy(dtype=float)
    rv15v = d["RV15"].to_numpy(dtype=float)
    ymasks = [((d["T"] >= a) & (d["T"] < a + YEAR)).to_numpy() for a in ANCHORS]

    # --- sequential screen ---
    years = []
    spreads_seq = []
    for k, a in enumerate(ANCHORS):
        m = ymasks[k]
        q = seq_q[k]["q80"]
        sk = np.isfinite(rv15v) & np.isfinite([q] * len(d)) & (rv15v > q) if np.isfinite(q) else np.zeros(len(d), bool)
        sk = sk & m
        mi, mo = m & sk, m & ~sk
        si, so = year_stats(y, mi), year_stats(y, mo)
        if mi.sum() >= MIN_N and mo.sum() >= MIN_N:
            spread = round(float(y[mi].mean() - y[mo].mean()) * 1e4, 2)
        else:
            spread = None
        spreads_seq.append(spread)
        day = d["T"][m].dt.floor("D").to_numpy()
        s_full = pd.Series(y[m]).groupby(day).sum()
        keep = ~sk[m]
        s_skip = pd.Series(y[m][keep]).groupby(day[keep]).sum() if keep.sum() else pd.Series(dtype=float)
        S_full = round(float(y[m].sum()), 6)
        S_skip = round(float(y[m & ~sk].sum()), 6)
        cut = round((S_full - S_skip) / S_full, 4) if S_full > 0 else None
        wd_full = round(float(s_full.min()), 6) if len(s_full) else None
        wd_skip = round(float(s_skip.min()), 6) if len(s_skip) else None
        tail = bool(wd_skip is not None and wd_full is not None and wd_skip > wd_full)
        per_coin = {}
        for c in MAJORS:
            mc = m & (d["sym"] == c).to_numpy()
            mcs, mck = mc & sk, mc & ~sk
            if int(mcs.sum()) >= MIN_N and int(mck.sum()) >= MIN_N:
                per_coin[c] = {"n_skip": int(mcs.sum()), "n_keep": int(mck.sum()),
                               "spread_bps": round(float(y[mcs].mean() - y[mck].mean()) * 1e4, 2)}
            else:
                per_coin[c] = {"n_skip": int(mcs.sum()), "n_keep": int(mck.sum()), "spread_bps": None}
        years.append({"year": str(a.date()), "q80": q, "n": int(m.sum()),
                      "n_skip": int(sk.sum()), "n_keep": int(m.sum()) - int(sk.sum()),
                      "kept_share": round(float((m & ~sk).sum() / max(m.sum(), 1)), 4),
                      "skip": si, "keep": so, "spread_bps": spread,
                      "S_full": S_full, "S_skip": S_skip, "cut_frac": cut,
                      "worst_day_full": wd_full, "worst_day_skip": wd_skip,
                      "tail_improves": tail, "per_coin": per_coin})
    d["SKIP_seq"] = np.zeros(len(d), bool)
    for k, a in enumerate(ANCHORS):
        q = seq_q[k]["q80"]
        if np.isfinite(q):
            flag = np.isfinite(rv15v) & (rv15v > q)
            d.loc[ymasks[k] & flag, "SKIP_seq"] = True

    # --- LOYO screen ---
    loyo = []
    spreads_loyo = []
    for h, a in enumerate(ANCHORS):
        held = ymasks[h]
        q = loyo_q[h]["q80"]
        if np.isfinite(q):
            sk = np.isfinite(rv15v) & (rv15v > q) & held
        else:
            sk = np.zeros(len(d), bool)
        mi, mo = held & sk, held & ~sk
        if mi.sum() >= MIN_N and mo.sum() >= MIN_N:
            spread = round(float(y[mi].mean() - y[mo].mean()) * 1e4, 2)
        else:
            spread = None
        spreads_loyo.append(spread)
        loyo.append({"heldout": str(a.date()), "q80": q, "n_skip": int(sk.sum()),
                     "n_keep": int(held.sum()) - int(sk.sum()), "spread_bps": spread,
                     "negative": bool(spread is not None and spread < 0)})

    neg_seq = sum(1 for s in spreads_seq if s is not None and s < 0)
    neg_loyo = sum(1 for s in spreads_loyo if s is not None and s < 0)
    ntail = sum(1 for w in years if w["tail_improves"])
    promising = bool(neg_seq >= 4 and neg_loyo >= 4 and ntail >= 4)

    sk_all = d["SKIP_seq"].to_numpy(bool)
    mi_all = sk_all & np.isfinite(y)
    mo_all = ~sk_all & np.isfinite(y)
    out = {
        "meta": {"fills": str(FILLS), "n_majors_r2": int(len(d)),
                 "T_min": str(d["T"].min()), "T_max": str(d["T"].max()),
                 "outcome": "y1.0", "unit": "bps in tables (x1e4)",
                 "rv15": "(max high[0..15] - min low[0..15]) / (O * sigma_4h); "
                         "sigma = pct_change().rolling(360).std(ddof=1).shift(1) on 4h opens",
                 "threshold": "q80 of RV15 over prior-year (coin,bar) T in [A-365d, A); "
                              "LOYO q80 over other-4 anchor years; SKIP iff RV15 > q80",
                 "min_n": MIN_N, "min_train": MIN_TRAIN,
                 "rv15_rows": int(len(rv)), "rv15_valid": int(np.isfinite(rv["RV15"]).sum()),
                 "rule": "PROMISING iff spread_seq<0 in >=4/5 AND spread_loyo<0 in >=4/5 "
                         "AND worst-day improves in >=4/5"},
        "thresholds_seq": seq_q, "thresholds_loyo": loyo_q,
        "years": years, "loyo": loyo,
        "decision": {"spread_seq_negative": f"{neg_seq}/5",
                     "spread_loyo_negative": f"{neg_loyo}/5",
                     "tail_improves": f"{ntail}/5",
                     "promising": promising},
        "overall": {
            "n_skip": int(mi_all.sum()), "n_keep": int(mo_all.sum()),
            "mean_skip_bps": round(float(y[mi_all].mean()) * 1e4, 2) if mi_all.sum() else None,
            "mean_keep_bps": round(float(y[mo_all].mean()) * 1e4, 2) if mo_all.sum() else None,
            "spread_bps": round(float(y[mi_all].mean() - y[mo_all].mean()) * 1e4, 2) if mi_all.sum() and mo_all.sum() else None,
            "coverage": round(float(np.isfinite(rv15v).mean()), 4)},
    }
    (OC / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["decision"], indent=1))
    for w, s in zip(years, spreads_seq):
        print(w["year"], "q80", round(w["q80"], 3) if w["q80"] == w["q80"] else None,
              "n_skip", w["n_skip"], "spread", s, "cut", w["cut_frac"], "tail", w["tail_improves"])
    print("runtime_s", round(time.time() - t0, 1))


if __name__ == "__main__":
    main()
