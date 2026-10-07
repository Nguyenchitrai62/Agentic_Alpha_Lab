"""oc_velocity run: B1 (size only) vs B1+velocity-guard exact comparison.

One process, one coin's H/L in RAM at a time; all-five-coins 1m opens/closes
held as float32 arrays; bar opens/sigmas precomputed per coin. Guard trigger
uses BTC closes only (see PLAN.md frozen definitions).
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

import velocity as V

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
W = V.LIVE_B - V.LIVE_A + 1  # 223 live minutes
QUERY_DATES = ("2024-01-03", "2024-08-05", "2022-06-13", "2022-11-09", "2025-10-10")


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
    guard_bars = {}  # bt_iso -> dict(T, mstar, removed_n, removed_rs)
    fills_raw = {"B1": {s: 0 for s in MAJORS}, "GUARD": {s: 0 for s in MAJORS}}
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
            # guard minute from BTC closes of this bar (minutes 0..239)
            btc_c = C["BTCUSDT"][base:base + 240].astype(float)
            sg_btc = float(sig_bar["BTCUSDT"][j])
            g = V.guard_minute(btc_c, sg_btc)
            low_win = La[base + V.LIVE_A:base + V.LIVE_B + 1].astype(float)
            cmat = np.stack([C[b][base + V.LIVE_A - 1:base + V.LIVE_B].astype(float)
                             for b in others])
            oo = np.array([opens_bar[b][j] for b in others], dtype=float)
            ss = np.array([sig_bar[b][j] for b in others], dtype=float)
            nvec = V.n_vector(cmat, oo, ss)
            Ha_b = Ha[base:base + 240].astype(float)
            La_b = La[base:base + 240].astype(float)
            Ca_b = Ca[base:base + 240].astype(float)
            Oa_b = Oa[base:base + 240].astype(float)
            bar_had_fill = False
            for k in V.RUNGS:
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = V.find_fill(low_win, np.full(W, lv))
                if ib is None:
                    continue
                f = V.LIVE_A + ib
                nf = int(nvec[ib])
                ret, x, _ = V.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                if not np.isfinite(ret):
                    continue
                bar_had_fill = True
                xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat() if int(x) < 240 else \
                    (bt + pd.Timedelta(hours=4)).date().isoformat()
                rec = dict(sym=sym, y=yi, k=k, f=int(f), n=int(nf),
                           w=float(V.size_mult(nf)), ret=float(ret), x=int(x),
                           xd=xd, fill=float(lv), t_bar=bt, g=-1 if g is None else int(g))
                rows.append({**rec, "arm": "B1"})
                fills_raw["B1"][sym] += 1
                kept = (g is None) or (int(f) < int(g))
                if kept:
                    rows.append({**rec, "arm": "GUARD"})
                    fills_raw["GUARD"][sym] += 1
                else:
                    key = bt.isoformat()
                    e = guard_bars.get(key)
                    if e is None:
                        e = {"T": bt.isoformat(), "mstar": int(g), "removed": []}
                        guard_bars[key] = e
                    e["removed"].append((float(rec["w"] * rec["ret"]), float(rec["ret"]),
                                         sym, float(k), int(f)))
            n_bar += 1
        print(f"{sym}: bars={n_bar} fills B1={fills_raw['B1'][sym]} GUARD={fills_raw['GUARD'][sym]}",
              flush=True)
        del H, L, Ha, La, Oa_b, Ca_b, La_b, Ha_b

    df = pd.DataFrame(rows)
    per_year, removed_year = {}, {}
    for arm in ("B1", "GUARD"):
        per_year[arm] = []
        for yi in range(5):
            sub = df[(df["arm"] == arm) & (df["y"] == yi)]
            n = len(sub)
            if n:
                wy = sub["w"].to_numpy(float) * sub["ret"].to_numpy(float)
                recs = list(zip(sub["xd"].tolist(), wy.tolist()))
                S, Wd, DD, nd = daily_path(recs)
                win = float((sub["ret"].to_numpy(float) > 0).mean())
                mean = float(sub["ret"].to_numpy(float).mean())
                s_raw = S
            else:
                S, Wd, DD, nd, win, mean, s_raw = 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0
            per_year[arm].append({"year": ANCHORS[yi].date().isoformat(), "n": int(n),
                                  "mean": mean, "win_rate": win, "sum": S,
                                  "worst_day": Wd, "max_dd": DD, "ndays": nd})
    # removed stats per year: B1 fills not kept
    b1 = df[df["arm"] == "B1"]
    gu = df[df["arm"] == "GUARD"]
    for yi in range(5):
        sb = b1[b1["y"] == yi]
        sg_ = gu[gu["y"] == yi]
        # key on (sym,k,t_bar,f) to diff
        gkeys = set(zip(sg_["sym"], sg_["k"], sg_["t_bar"].astype(str), sg_["f"])) if len(sg_) else set()
        rem = sb[~sb.apply(lambda r: (r["sym"], r["k"], str(r["t_bar"]), r["f"]) in gkeys, axis=1)] \
            if len(sb) else sb
        n = len(rem)
        if n:
            rs = float((rem["w"].to_numpy(float) * rem["ret"].to_numpy(float)).sum())
            removed_year[str(yi)] = {"n": int(n),
                                     "mean": float(rem["ret"].mean()),
                                     "win_rate": float((rem["ret"].to_numpy(float) > 0).mean()),
                                     "sum_wy": rs}
        else:
            removed_year[str(yi)] = {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum_wy": 0.0}

    full = {}
    for arm in ("B1", "GUARD"):
        sub = df[df["arm"] == arm]
        n = len(sub)
        if n:
            recs = list(zip(sub["xd"].tolist(),
                            (sub["w"].to_numpy(float) * sub["ret"].to_numpy(float)).tolist()))
            S, Wd, DD, nd = daily_path(recs)
            full[arm] = {"n": int(n), "mean": float(sub["ret"].mean()),
                         "win_rate": float((sub["ret"].to_numpy(float) > 0).mean()),
                         "sum": S, "worst_day": Wd, "max_dd": DD, "ndays": nd}
        else:
            full[arm] = {"n": 0, "mean": 0.0, "win_rate": 0.0, "sum": 0.0,
                         "worst_day": 0.0, "max_dd": 0.0, "ndays": 0}

    # decision: DD not worse + sum >= 95% of B1, per year
    dd_pass, sum_pass = 0, 0
    per_year_check = []
    for yi in range(5):
        dd_ok = bool(per_year["GUARD"][yi]["max_dd"] <= per_year["B1"][yi]["max_dd"])
        s_b1 = per_year["B1"][yi]["sum"]
        s_g = per_year["GUARD"][yi]["sum"]
        sum_ok = bool(np.isfinite(s_b1) and np.isfinite(s_g) and s_g >= 0.95 * s_b1)
        dd_pass += int(dd_ok)
        sum_pass += int(sum_ok)
        per_year_check.append({"year": per_year["B1"][yi]["year"], "dd_pass": dd_ok,
                               "sum_pass": sum_ok})
    decision = {"years_dd_not_worse": int(dd_pass),
                "years_sum_ge95": int(sum_pass),
                "promising": bool(dd_pass >= 4 and sum_pass >= 4)}

    # guard events: rank by removed count desc, then removed RS asc, then earliest T
    evts = []
    for key, e in guard_bars.items():
        rs = float(sum(v[0] for v in e["removed"]))
        rets = [v[1] for v in e["removed"]]
        evts.append({"T": e["T"], "mstar": e["mstar"], "removed_n": len(e["removed"]),
                     "removed_rs": rs,
                     "removed_mean": float(np.mean(rets)) if rets else 0.0,
                     "removed_win": float(np.mean([1 if r > 0 else 0 for r in rets])) if rets else 0.0})
    evts.sort(key=lambda e: (-e["removed_n"], e["removed_rs"], e["T"]))
    top10 = evts[:10]
    # query dates: any fired bar whose [T,T+4h) intersects calendar day D
    fired_days = {}
    for key, e in guard_bars.items():
        pass
    # rebuild fired-bar set: need ALL fired bars, not only those with removals.
    # Recompute cheaply? Instead derive from df guard column g != "" grouped by t_bar
    fired = set(df[df["g"] != -1]["t_bar"].astype(str).tolist()) if len(df) else set()
    fired_ts = [pd.Timestamp(t) for t in fired]
    query = {}
    for d in QUERY_DATES:
        day0 = pd.Timestamp(d, tz="UTC")
        day1 = day0 + pd.Timedelta(days=1)
        hit = any((t < day1 and t + pd.Timedelta(hours=4) > day0) for t in fired_ts)
        query[d] = bool(hit)

    chk = hashlib.sha256(
        np.round(df[["ret", "w", "fill"]].to_numpy(), 9).tobytes()).hexdigest()[:16] if len(df) else "empty"
    out = {"config": {"coins": list(MAJORS), "rungs": list(V.RUNGS),
                       "bars": "open in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC",
                       "live": [V.LIVE_A, V.LIVE_B],
                       "maker": V.MAKER, "taker": V.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "n": "other majors C(T+m-1) <= O(T)*(1-2.5*sg(T)), oc_b1deeper-exact",
                       "guard": "BTC close(m-1) <= max(close(m-16..m-1))*(1-3.0*sg_BTC(T)); "
                                "cancel resting bids from m* onward; kept iff f < m*",
                       "size": "1/(1+n_fill) both arms, NO renormalisation (subset sums)",
                       "exits": "D0 replica from fill px lv (TP=px*(1+sg), sl 4sg, bl 8sg, timeout next open)",
                       "daily": "exit-date UTC sums of w*y; maxDD of cumulative daily-sum path from 0",
                       "note": "fills with non-finite exit nets dropped per arm; NaN closes never trigger"},
           "fills_per_coin_raw": fills_raw,
           "n_fills": int(len(df)),
           "n_fired_bars": int(len(fired)),
           "n_guard_events_with_removals": int(len(evts)),
           "ledger_checksum": chk,
           "per_year": per_year, "removed_per_year": removed_year,
           "full": full, "per_year_check": per_year_check,
           "decision": decision, "top10_events": top10,
           "query_dates_fired": query}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_rows", len(df), "fired", len(fired), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
