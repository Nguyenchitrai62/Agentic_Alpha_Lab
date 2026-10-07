"""oc_lowvolrung run: baseline ladder vs baseline + gated extra-2.0 rung.

One process, one coin's H/L in RAM at a time; all-five-coins 1m opens/closes
held as float32 arrays; bar opens/sigmas precomputed per coin. See PLAN.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import core as K

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
W = K.LIVE_B - K.LIVE_A + 1  # 223 live minutes


def load_oc(sym: str):
    """Full-length 1m open + close as float32 (+ minute index)."""
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    idx = pd.date_range(START, END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m, parts
    return idx, O, C


def load_hl(sym: str, idx):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "high", "low"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    m = m.set_index("open_time").reindex(idx)
    H = m["high"].to_numpy(dtype=np.float32)
    L = m["low"].to_numpy(dtype=np.float32)
    del m, parts
    return H, L


def year_of(t0):
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def daily_path(recs):
    """recs: list of (exit_date_iso, w_y). Returns (S, worst_day, maxDD, ndays)."""
    if not recs:
        return 0.0, 0.0, 0.0, 0
    daily = {}
    for d, v in recs:
        daily[d] = daily.get(d, 0.0) + v
    days = sorted(daily)
    cum, peak, dd = 0.0, 0.0, 0.0
    for d in days:
        cum += daily[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return float(sum(daily.values())), float(min(daily.values())), float(-dd), len(days)


def main():
    idx, O, C = {}, {}, {}
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        idx[sym], O[sym], C[sym] = ii, o, c
        print(f"loaded OC {sym}", flush=True)
    base_idx = idx[MAJORS[0]]
    n_all = len(base_idx)
    nb = (n_all - 1) // 240
    t0 = base_idx[:nb * 240:240]
    opens_bar, sig_bar = {}, {}
    for sym in MAJORS:
        ob = O[sym][:nb * 240:240].astype(float)
        sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
        opens_bar[sym], sig_bar[sym] = ob, sg
    del ob, sg

    # Walk-forward lowest-tercile cut-offs per coin per anchor year.
    t0s = pd.DatetimeIndex(t0)
    cutoffs, armed_bars = {}, {}
    for sym in MAJORS:
        cutoffs[sym], armed_bars[sym] = [], []
        for yi, A in enumerate(ANCHORS):
            mask = (t0s < A) & np.isfinite(sig_bar[sym])
            hist = sig_bar[sym][mask]
            q = K.lowvol_cutoff(hist)
            cutoffs[sym].append(float(q))
    for sym in MAJORS:
        print(f"cutoffs {sym}: " + ", ".join(f"{c:.6f}" for c in cutoffs[sym]), flush=True)

    rows = []
    fills_raw = {"BASE": {s: 0 for s in MAJORS}, "EXTRA": {s: 0 for s in MAJORS}}
    armed_count = {s: [0, 0, 0, 0, 0] for s in MAJORS}
    elig_count = {s: [0, 0, 0, 0, 0] for s in MAJORS}
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        Oa, Ca, La, Ha = O[sym], C[sym], L, H
        others = [s for s in MAJORS if s != sym]
        n_bar = 0
        for j in range(nb):
            bt = t0[j]
            if not (TRADE_START <= bt < YEAR_END):
                continue
            o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                continue
            base = j * 240
            if base + 240 >= n_all:
                continue
            o2m = Oa[base + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            yi = year_of(bt)
            elig_count[sym][yi] += 1
            armed = bool(sg <= cutoffs[sym][yi])
            if armed:
                armed_count[sym][yi] += 1
            cmat = np.stack([C[b][base + K.LIVE_A - 1:base + K.LIVE_B].astype(float)
                             for b in others])  # (4, W) closes at T+m-1
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec = K.n_vector(cmat, oo, ss)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            low_win = La[base + K.LIVE_A:base + K.LIVE_B + 1].astype(float)

            def do_rung(k, arm):
                ib = K.find_fill(low_win, o1 * (1 - k * sg))
                if ib is None:
                    return
                f = K.LIVE_A + ib
                nf = int(nvec[ib])
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    return
                ret, x, _ = K.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                if np.isfinite(ret):
                    xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat() if int(x) < 240 else \
                        (bt + pd.Timedelta(hours=4)).date().isoformat()
                    rows.append(dict(sym=sym, y=yi, k=k, arm=arm, f=int(f),
                                     n=int(nf), w=float(K.size_mult(nf)),
                                     ret=float(ret), x=int(x), xd=xd,
                                     fill=float(lv), t_bar=bt))
                    fills_raw[arm][sym] += 1

            for k in K.BASE_RUNGS:
                do_rung(k, "BASE")
            if armed:
                do_rung(K.EXTRA_K, "EXTRA")
            n_bar += 1
        print(f"{sym}: bars={n_bar} fills BASE={fills_raw['BASE'][sym]} "
              f"EXTRA={fills_raw['EXTRA'][sym]} armed={armed_count[sym]}", flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    df = pd.DataFrame(rows)
    # Per-year ladders with RAW weights (PLAN 7-8).
    per_year, full = {"base": [], "with": []}, {}
    for yi in range(5):
        for lad, arms in (("base", ["BASE"]), ("with", ["BASE", "EXTRA"])):
            sub = df[(df["y"] == yi) & (df["arm"].isin(arms))]
            if len(sub):
                wy = sub["w"].to_numpy(float) * sub["ret"].to_numpy(float)
                recs = list(zip(sub["xd"].tolist(), wy.tolist()))
                S, Wd, DD, nd = daily_path(recs)
            else:
                S, Wd, DD, nd = 0.0, 0.0, 0.0, 0
            per_year[lad].append({"year": ANCHORS[yi].date().isoformat(),
                                  "n": int(len(sub)), "sum": S,
                                  "worst_day": Wd, "max_dd": DD, "ndays": nd})
    for lad, arms in (("base", ["BASE"]), ("with", ["BASE", "EXTRA"])):
        sub = df[df["arm"].isin(arms)]
        if len(sub):
            wy = sub["w"].to_numpy(float) * sub["ret"].to_numpy(float)
            recs = list(zip(sub["xd"].tolist(), wy.tolist()))
            S, Wd, DD, nd = daily_path(recs)
        else:
            S, Wd, DD, nd = 0.0, 0.0, 0.0, 0
        full[lad] = {"n": int(len(sub)), "sum": S, "worst_day": Wd,
                     "max_dd": DD, "ndays": nd}

    # Extra-rung standalone stats per year (raw weights).
    extra = []
    for yi in range(5):
        sub = df[(df["arm"] == "EXTRA") & (df["y"] == yi)]
        n = len(sub)
        if n:
            r = sub["ret"].to_numpy(float)
            w = sub["w"].to_numpy(float)
            extra.append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                          "mean": float(r.mean()),
                          "win_rate": float((r > 0).mean()),
                          "sum": float((w * r).sum())})
        else:
            extra.append({"year": ANCHORS[yi].date().isoformat(), "n": 0,
                          "mean": 0.0, "win_rate": 0.0, "sum": 0.0})

    # LOO descriptive (no selection): sums excluding each year.
    loo = []
    for drop in range(5):
        sb = sum(per_year["base"][yi]["sum"] for yi in range(5) if yi != drop)
        sw = sum(per_year["with"][yi]["sum"] for yi in range(5) if yi != drop)
        loo.append({"drop_year": ANCHORS[drop].date().isoformat(),
                    "base_sum": sb, "with_sum": sw, "with_higher": bool(sw > sb)})

    sum_pass = sum(1 for yi in range(5)
                   if per_year["with"][yi]["sum"] > per_year["base"][yi]["sum"])
    dd_pass = sum(1 for yi in range(5)
                  if per_year["with"][yi]["max_dd"] <= per_year["base"][yi]["max_dd"])
    decision = {"years_sum_higher": int(sum_pass),
                "years_dd_not_worse": int(dd_pass),
                "promising": bool(sum_pass >= 4 and dd_pass >= 4)}
    chk = hashlib.sha256(
        np.round(df[["ret", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "base_rungs": list(K.BASE_RUNGS),
                       "extra_k": K.EXTRA_K,
                       "gate": "extra armed iff sigma_c(T) <= walk-forward lowest-tercile cutoff q(c,Y) from finite sigma with T < anchor",
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [K.LIVE_A, K.LIVE_B],
                       "maker": K.MAKER, "taker": K.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "n": "other majors C(T+m-1) <= O(T)*(1-2.5*sg(T)), oc_b1deeper-exact",
                       "size": "raw w=1/(1+n_fill) both ladders; no renormalisation",
                       "exits": "D0 replica from fill px (TP=px*(1+sg), sl 4sg, bl 8sg, timeout next open)",
                       "daily": "exit-date UTC sums; maxDD of cumulative daily-sum path from 0",
                       "note": "fills with non-finite exit nets dropped"},
           "cutoffs": {s: {ANCHORS[yi].date().isoformat(): cutoffs[s][yi] for yi in range(5)}
                       for s in MAJORS},
           "armed_bars": {s: {ANCHORS[yi].date().isoformat(): int(armed_count[s][yi])
                              for yi in range(5)} for s in MAJORS},
           "eligible_bars": {s: {ANCHORS[yi].date().isoformat(): int(elig_count[s][yi])
                                 for yi in range(5)} for s in MAJORS},
           "fills_per_coin_raw": fills_raw,
           "n_fills": int(len(df)),
           "ledger_checksum": chk,
           "per_year": per_year, "full": full, "extra": extra,
           "loo": loo, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_fills", len(df), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
