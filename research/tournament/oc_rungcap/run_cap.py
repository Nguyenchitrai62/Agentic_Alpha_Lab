"""oc_rungcap run: B1 base (oc_b1deeper-exact) vs per-coin fill cap (first 3 per bar).

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

import b1core as D

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
W = D.LIVE_B - D.LIVE_A + 1  # 223 live minutes


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

    rows = []
    fills_per_coin = {s: 0 for s in MAJORS}
    for ai, sym in enumerate(MAJORS):
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
            low_win = La[base + D.LIVE_A:base + D.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + D.LIVE_A - 1:base + D.LIVE_B].astype(float)
                             for b in others])  # (4, W) closes at T+m-1
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec = D.n_vector(cmat, oo, ss)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            for k in D.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = D.find_fill(low_win, np.full(W, lv))
                if ib is not None:
                    f = D.LIVE_A + ib
                    nf = int(nvec[ib])
                    ret, x, _ = D.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                    if np.isfinite(ret):
                        xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat() if int(x) < 240 else \
                            (bt + pd.Timedelta(hours=4)).date().isoformat()
                        rows.append(dict(sym=sym, y=yi, k=k, f=int(f),
                                         n=int(nf), w=float(D.size_mult(nf)),
                                         ret=float(ret), x=int(x), xd=xd,
                                         fill=float(lv), t_bar=bt))
                        fills_per_coin[sym] += 1
            n_bar += 1
        print(f"{sym}: bars={n_bar} base_fills={fills_per_coin[sym]}", flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    df = pd.DataFrame(rows)
    # --- apply per-(coin, bar) cap: keep first 3 by (f, k) ---
    df["keep"] = True
    if len(df):
        grp = df.groupby(["sym", "t_bar"], sort=False)
        keep_idx = []
        for _, g in grp:
            mask = D.cap_keep_mask(g["f"].tolist(), g["k"].tolist(), D.CAP_KEEP)
            keep_idx.extend(g.index[np.array(mask)].tolist())
        keep_set = set(keep_idx)
        df["keep"] = df.index.map(lambda i: i in keep_set)
    base = df
    cap = df[df["keep"]].copy()
    removed = df[~df["keep"]].copy()

    def score(sub):
        per_year, full = [], {}
        for yi in range(5):
            s = sub[sub["y"] == yi]
            n = len(s)
            if n:
                wy = s["w"].to_numpy(float) * s["ret"].to_numpy(float)
                recs = list(zip(s["xd"].tolist(), wy.tolist()))
                S, Wd, DD, nd = daily_path(recs)
                win = float((s["ret"].to_numpy(float) > 0).mean())
                mean = float(s["ret"].to_numpy(float).mean())
                s_raw = float(wy.sum())
            else:
                S, Wd, DD, nd, win, mean, s_raw = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0
            per_year.append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                             "mean": mean, "win_rate": win, "sum": S,
                             "worst_day": Wd, "max_dd": DD, "ndays": nd})
        n = len(sub)
        if n:
            wy = sub["w"].to_numpy(float) * sub["ret"].to_numpy(float)
            recs = list(zip(sub["xd"].tolist(), wy.tolist()))
            S, Wd, DD, nd = daily_path(recs)
            full = {"n": int(n), "mean": float(sub["ret"].mean()),
                    "win_rate": float((sub["ret"].to_numpy(float) > 0).mean()),
                    "sum": S, "worst_day": Wd, "max_dd": DD, "ndays": nd}
        else:
            full = {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum": 0.0,
                    "worst_day": 0.0, "max_dd": 0.0, "ndays": 0}
        return per_year, full

    # side row: renormalised sums (w' per year-arm to mean 1)
    def score_renorm(sub):
        out = []
        for yi in range(5):
            s = sub[sub["y"] == yi]
            if len(s):
                w = s["w"].to_numpy(float)
                wy = w / w.mean() * s["ret"].to_numpy(float)
                S, _, _, _ = daily_path(list(zip(s["xd"].tolist(), wy.tolist())))
            else:
                S = 0.0
            out.append(S)
        return out

    per_base, full_base = score(base)
    per_cap, full_cap = score(cap)
    ren_base = score_renorm(base)
    ren_cap = score_renorm(cap)

    per_removed = []
    for yi in range(5):
        s = removed[removed["y"] == yi]
        n = len(s)
        if n:
            wy = float((s["w"].to_numpy(float) * s["ret"].to_numpy(float)).sum())
            per_removed.append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                                "mean": float(s["ret"].mean()),
                                "win_rate": float((s["ret"].to_numpy(float) > 0).mean()),
                                "wy_sum": wy})
        else:
            per_removed.append({"year": ANCHORS[yi].date().isoformat(), "n": 0,
                                "mean": 0.0, "win_rate": 0.0, "wy_sum": 0.0})

    dd_pass, sum_pass = 0, 0
    per_year_out = []
    for yi in range(5):
        b, c = per_base[yi], per_cap[yi]
        if np.isfinite(b["max_dd"]) and np.isfinite(c["max_dd"]) and c["max_dd"] <= b["max_dd"]:
            dp = True
        else:
            dp = False
        if np.isfinite(b["sum"]) and np.isfinite(c["sum"]):
            if b["sum"] <= 0:
                sp = bool(c["sum"] >= b["sum"])
            else:
                sp = bool(c["sum"] >= 0.97 * b["sum"])
        else:
            sp = False
        dd_pass += int(dp)
        sum_pass += int(sp)
        per_year_out.append({"year": b["year"], "base": b, "cap": c,
                             "removed": per_removed[yi],
                             "sum_renorm_base": ren_base[yi],
                             "sum_renorm_cap": ren_cap[yi],
                             "pass_dd": dp, "pass_sum97": sp})
    decision = {"years_dd_not_worse": int(dd_pass),
                "years_sum_ge97": int(sum_pass),
                "promising": bool(dd_pass >= 4 and sum_pass >= 4)}
    chk = hashlib.sha256(
        np.round(df[["ret", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(D.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [D.LIVE_A, D.LIVE_B],
                       "maker": D.MAKER, "taker": D.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "n": "other majors C(T+m-1) <= O(T)*(1-2.5*sg(T)), oc_b1deeper-exact",
                       "base": "B1 static bid at lv, strict low<lv fill, size 1/(1+n), D0 exits from lv",
                       "cap": "per (coin,bar) keep first 3 fills by (f ASC, k ASC), cancel rest",
                       "scoring": "PRIMARY raw w*y daily sums by exit date UTC; maxDD of cumsum path from 0; renorm side row",
                       "note": "fills with non-finite exit nets dropped identically in base and cap"},
           "fills_per_coin_base": fills_per_coin,
           "n_base": int(len(base)), "n_cap": int(len(cap)), "n_removed": int(len(removed)),
           "ledger_checksum": chk,
           "per_year": per_year_out,
           "full": {"base": full_base, "cap": full_cap,
                    "removed_mean": float(removed["ret"].mean()) if len(removed) else 0.0,
                    "removed_win": float((removed["ret"].to_numpy(float) > 0).mean()) if len(removed) else 0.0,
                    "removed_wy_sum": float((removed["w"].to_numpy(float) * removed["ret"].to_numpy(float)).sum()) if len(removed) else 0.0},
           "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    base.to_parquet(HERE / "fills_base.parquet", index=False)
    print("n_base", len(base), "n_cap", len(cap), "n_removed", len(removed), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
