"""oc_dipbe run: B1 base exits vs break-even exits on the SAME fills (paired).

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

import be_core as B

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
W = B.LIVE_B - B.LIVE_A + 1  # 223 live minutes


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


def xd_of(bt, x):
    if int(x) < 240:
        return (bt + pd.Timedelta(minutes=int(x))).date().isoformat()
    return (bt + pd.Timedelta(hours=4)).date().isoformat()


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
    fills_raw = {s: 0 for s in MAJORS}
    armed_total = 0
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
            low_win = La[base + B.LIVE_A:base + B.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + B.LIVE_A - 1:base + B.LIVE_B].astype(float)
                             for b in others])  # (4, W) closes at T+m-1
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec = B.n_vector(cmat, oo, ss)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            for k in B.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = B.find_fill(low_win, np.full(W, lv))
                if ib is None:
                    continue
                f = B.LIVE_A + ib
                nf = int(nvec[ib])
                w = float(B.size_mult(nf))
                r0, x0, h0 = B.outcome_base(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                r1, x1, h1, armed = B.outcome_be(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                if not (np.isfinite(r0) and np.isfinite(r1)):
                    continue  # paired: drop unless BOTH exits finite
                rows.append(dict(sym=sym, y=yi, k=k, arm="BASE", f=int(f),
                                 n=int(nf), w=w, ret=float(r0), x=int(x0),
                                 how=h0, xd=xd_of(bt, x0), fill=float(lv), t_bar=bt))
                rows.append(dict(sym=sym, y=yi, k=k, arm="BE", f=int(f),
                                 n=int(nf), w=w, ret=float(r1), x=int(x1),
                                 how=h1, armed=bool(armed), xd=xd_of(bt, x1),
                                 fill=float(lv), t_bar=bt))
                fills_raw[sym] += 1
                armed_total += int(armed)
            n_bar += 1
        print(f"{sym}: bars={n_bar} paired_fills={fills_raw[sym]}", flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    df = pd.DataFrame(rows)
    per_year, full = {}, {}
    for arm in ("BASE", "BE"):
        per_year[arm] = []
        for yi in range(5):
            sub = df[(df["arm"] == arm) & (df["y"] == yi)]
            n = len(sub)
            if n:
                w = sub["w"].to_numpy(float)
                wprime = w / w.mean()
                wy = wprime * sub["ret"].to_numpy(float)
                s_raw = float((w * sub["ret"].to_numpy(float)).sum())
                recs = list(zip(sub["xd"].tolist(), wy.tolist()))
                S, Wd, DD, nd = daily_path(recs)
                win = float((sub["ret"].to_numpy(float) > 0).mean())
                tmo = float((sub["how"].to_numpy() == "time").mean())
                mean = float(sub["ret"].to_numpy(float).mean())
            else:
                S, Wd, DD, nd, win, tmo, mean, s_raw = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0
            per_year[arm].append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                                  "mean": mean, "win_rate": win, "timeout_share": tmo,
                                  "sum": S, "sum_raw": s_raw, "worst_day": Wd,
                                  "max_dd": DD, "ndays": nd})
        sub = df[df["arm"] == arm]
        n = len(sub)
        if n:
            w = sub["w"].to_numpy(float)
            recs = list(zip(sub["xd"].tolist(), (w / w.mean() * sub["ret"].to_numpy(float)).tolist()))
            S, Wd, DD, nd = daily_path(recs)
            full[arm] = {"n": int(n), "mean": float(sub["ret"].mean()),
                         "win_rate": float((sub["ret"].to_numpy(float) > 0).mean()),
                         "timeout_share": float((sub["how"].to_numpy() == "time").mean()),
                         "sum": S, "worst_day": Wd, "max_dd": DD, "ndays": nd}
        else:
            full[arm] = {"n": 0, "mean": 0.0, "win_rate": 0.0, "timeout_share": 0.0,
                         "sum": 0.0, "worst_day": 0.0, "max_dd": 0.0, "ndays": 0}

    dd_pass, sum_pass = 0, 0
    for yi in range(5):
        a, e = per_year["BASE"][yi], per_year["BE"][yi]
        dd_ok = bool(np.isfinite(e["max_dd"]) and np.isfinite(a["max_dd"])
                     and e["max_dd"] <= a["max_dd"])
        if np.isfinite(e["sum"]) and np.isfinite(a["sum"]):
            sum_ok = bool(e["sum"] >= (0.97 * a["sum"] if a["sum"] > 0 else a["sum"]))
        else:
            sum_ok = False
        dd_pass += int(dd_ok)
        sum_pass += int(sum_ok)
    decision = {"years_dd_not_worse": int(dd_pass),
                "years_sum_ge_97pct": int(sum_pass),
                "promising": bool(dd_pass >= 4 and sum_pass >= 4)}
    chk = hashlib.sha256(
        np.round(df[["ret", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(B.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [B.LIVE_A, B.LIVE_B],
                       "maker": B.MAKER, "taker": B.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "fills": "B1 replica (static lv, strict low<lv, size 1/(1+n)); paired arms",
                       "be_rule": "trigger high>px*(1+0.6sg) STRICT; arm only if tb strictly before "
                                  "all base triggers; stop -> px*(1+maker+taker) on 5m-block closes "
                                  "for m>tb, exit next open taker; bl/tp unchanged, base priority",
                       "weights": "w=1/(1+n_fill); renorm per year-arm to mean 1 (primary)",
                       "daily": "exit-date UTC sums; maxDD of cumulative daily-sum path from 0",
                       "note": "fills kept only if BOTH exits finite (paired)"},
           "fills_per_coin_paired": fills_raw,
           "n_armed": int(armed_total),
           "n_rows": int(len(df)),
           "ledger_checksum": chk,
           "per_year": per_year, "full": full, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_rows", len(df), "armed", armed_total, "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
