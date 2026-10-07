"""oc_crash2020: G2 dip-sleeve stress replay through 2020-2021 crash windows.

Pre-registered in PLAN.md (read it first). Isolated dip-only sleeve: B1 sizes
(1/(1+n), kd 1.7), R2 depths, risk budget 0.442, G2 arm adds gross cap 2.0,
NOCAP arm is the budget-only reference. Exits = oc_dipexit D0 replica.
No book, no learned agents, no commits.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
KD = 1.7
U = 0.25 * 1.75 / 4 / 1.657  # engine fixed per-rung unit (SIZE/size_mult/S_REF)
BUDGET = 0.26 * 1.7  # G2 risk budget (k=1, kd=1.7)
GAP_ALLOW = 0.02
GCAP = 2.0
SETTLE_HOURS = (0, 8, 16)
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ORIGIN = pd.Timestamp("2020-01-01", tz="UTC")
LOAD_START = pd.Timestamp("2019-12-31", tz="UTC")
LOAD_END = pd.Timestamp("2021-07-03", tz="UTC")
WINDOWS = {
    "W1_covid0312": pd.Timestamp("2020-03-12", tz="UTC"),
    "W2_covid0316": pd.Timestamp("2020-03-16", tz="UTC"),
    "W3_jan21": pd.Timestamp("2021-01-21", tz="UTC"),
    "W4_may19": pd.Timestamp("2021-05-19", tz="UTC"),
    "W5_jun21": pd.Timestamp("2021-06-21", tz="UTC"),
}
SIM_DAYS = 10
PHASES = (0, 1, 2, 3)
ARMS = ("G2", "NOCAP")


# ---------------------------------------------------------------- core (pure)
def compute_sigma(opens: np.ndarray) -> np.ndarray:
    """4h sigma known at each bar open: rolling(360, min_periods=120).std.shift(1)."""
    return pd.Series(np.asarray(opens, dtype=float)).pct_change().rolling(
        360, min_periods=120).std(ddof=1).shift(1).to_numpy()


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """B1 correlation count per live minute (v399-exact). NaN -> not flushing."""
    W = close_others.shape[1]
    n = np.zeros(W, dtype=np.int64)
    for i in range(close_others.shape[0]):
        o, sg = float(open_others[i]), float(sigma_others[i])
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - DETECT_K * sg)
        if not np.isfinite(thr):
            continue
        c = close_others[i]
        n += (np.isfinite(c) & (c <= thr)).astype(np.int64)
    return n


def find_fill(low_win: np.ndarray, level: float):
    """First live-window index with low < level (STRICT). None if no fill."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_d0(Ha, La, Ca, Oa, f: int, lv: float, sg: float,
               o2: float, settle: bool):
    """D0 replica from lv. Returns (ret, x, how, gap_sigma).

    x = exit offset (0..239, 240 = next-bar open); how in
    {"tp","stop","backstop","time"}; gap_sigma = (level-fillpx)/(lv*sg) for
    stop/backstop exits (None otherwise); ret NaN when exit price missing.
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + 1.0 * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = int(np.argmax(ht)) if ht.any() else None
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = float(Oa[x])
        if not np.isfinite(ox):
            return (np.nan, x, "backstop", None)
        px = bl if ox > bl else ox  # min(bl, open): gap pays the open
        return (px / lv - 1 - MAKER - TAKER, x, "backstop", (bl - px) / (lv * sg))
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp", None)
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px, x = float(Oa[km + 1]), km + 1
        else:
            px, x = float(o2), 240
        if not np.isfinite(px):
            return (np.nan, x, "stop", None)
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop", (sl - px) / (lv * sg))
    x = 240
    if not np.isfinite(float(o2)):
        return (np.nan, x, "time", None)
    return (float(o2) / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0),
            x, "time", None)


def budget_ok(risk_open: float, w: float, sg: float) -> bool:
    """Engine risk-budget check for one candidate rung."""
    return risk_open + w * (M_SL * sg + GAP_ALLOW) <= BUDGET + 1e-12


def cap_apply(open_sum: float, w: float, cap: float | None) -> float:
    """Gross-cap room cut (engine hook). Returns kept weight (0 = skip)."""
    if cap is None:
        return w
    room = cap - open_sum
    if room <= 1e-12:
        return 0.0
    return min(w, room)


# ---------------------------------------------------------------- data
def load_1m(sym: str):
    if sym == "BTCUSDT":
        files = sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted((ROOT / "data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= LOAD_START) & (m["open_time"] <= LOAD_END)]
    idx = pd.date_range(LOAD_START, LOAD_END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    out = {k: m[k].to_numpy(dtype=np.float32) for k in ("open", "high", "low", "close")}
    del m, parts
    return idx, out


# ---------------------------------------------------------------- one run
def simulate_window(idx, D, bars, opens_bar, sig_bar, S, arm: str):
    """Dip-only replay for bars with open in [S, S+10d). Returns cell stats + ledger."""
    E = 1.0
    t_all, m_all = [], []
    fills = stops = tps = timeouts = gap_stops = 0
    gap_max = 0.0
    gap_list = []
    peak_gross = 0.0
    ledger = []
    end_S = S + pd.Timedelta(days=SIM_DAYS)
    for j in bars:
        T = bars[j]
        if not (S <= T < end_S):
            continue
        off = int((T - idx[0]).total_seconds() // 60)
        if off + 240 >= len(idx):
            continue
        settle = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
        E_open = E
        # candidate fills per (coin, rung)
        cands = []
        W = LIVE_B - LIVE_A + 1
        for ai, sym in enumerate(MAJORS):
            o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                continue
            low_win = D[sym]["low"][off + LIVE_A:off + LIVE_B + 1].astype(float)
            others = [s for s in MAJORS if s != sym]
            cmat = np.stack([D[b]["close"][off + LIVE_A - 1:off + LIVE_B].astype(float)
                             for b in others])
            oo = np.array([float(opens_bar[b][j]) for b in others])
            ss = np.array([float(sig_bar[b][j]) for b in others])
            nvec = n_vector(cmat, oo, ss)
            for r, k in enumerate(RUNGS):
                lv = o1 * (1 - k * sg)
                if not np.isfinite(lv) or lv <= 0:
                    continue
                ib = find_fill(low_win, lv)
                if ib is None:
                    continue
                f = LIVE_A + ib
                cands.append(dict(f=f, r=r, a=ai, sym=sym, lv=lv, sg=sg,
                                  n=int(nvec[ib])))
        cands.sort(key=lambda c: (c["f"], c["r"], c["a"]))
        taken = []  # dicts with x, w, sg, ret, how, lv, f, sym, r, gap
        for c in cands:
            w = U * KD / (1 + c["n"])
            risk_open = sum(t["w"] * (M_SL * t["sg"] + GAP_ALLOW)
                            for t in taken if t["x"] > c["f"])
            if not budget_ok(risk_open, w, c["sg"]):
                continue
            if arm == "G2":
                open_sum = sum(t["w"] for t in taken if t["x"] > c["f"])
                w = cap_apply(open_sum, w, GCAP)
                if w <= 0:
                    continue
            sym = c["sym"]
            Ha = D[sym]["high"][off:off + 240].astype(float)
            La = D[sym]["low"][off:off + 240].astype(float)
            Ca = D[sym]["close"][off:off + 240].astype(float)
            Oa = D[sym]["open"][off:off + 240].astype(float)
            o2m = D[sym]["open"][off + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            ret, x, how, gap = outcome_d0(Ha, La, Ca, Oa, c["f"], c["lv"], c["sg"], o2, settle)
            if not np.isfinite(ret):
                continue
            taken.append(dict(f=c["f"], r=c["r"], a=c["a"], sym=sym, lv=c["lv"],
                              sg=c["sg"], w=w, x=x, ret=ret, how=how, gap=gap, T=T))
        # bar accounting + 1m marks
        marks = np.zeros(240)
        gross = np.zeros(240)
        for t in taken:
            Ca = D[t["sym"]]["close"][off:off + 240].astype(float)
            end = min(t["x"], 240)
            seg = np.zeros(240)
            seg[t["f"]:end] = Ca[t["f"]:end] / t["lv"] - 1
            if t["x"] < 240:
                seg[t["x"]:] = t["ret"]
            marks += t["w"] * seg
            gseg = np.zeros(240)
            gseg[t["f"]:end] = t["w"]
            gross += gseg  # sum of open notionals (start-equity units x E_open)
            fills += 1
            if t["how"] in ("stop", "backstop"):
                stops += 1
            elif t["how"] == "tp":
                tps += 1
            else:
                timeouts += 1
            if t["gap"] is not None and t["gap"] > 1.0:
                gap_stops += 1
            if t["gap"] is not None and np.isfinite(t["gap"]):
                gap_max = max(gap_max, float(t["gap"]))
                if t["gap"] > 1.0:
                    gap_list.append(dict(t=str(T + pd.Timedelta(minutes=int(t["x"]))),
                                          sym=t["sym"], rung=RUNGS[t["r"]],
                                          gap=round(float(t["gap"]), 3)))
            ledger.append((t["sym"], str(T), RUNGS[t["r"]], t["f"],
                           round(t["w"], 9), round(float(t["ret"]), 9), t["how"]))
        pnl = float(sum(t["w"] * t["ret"] for t in taken))
        E = E_open * (1 + pnl)
        M = E_open * (1 + marks)
        for m in range(240):
            t_all.append(T + pd.Timedelta(minutes=m))
            m_all.append(float(M[m]))
        t_all.append(T + pd.Timedelta(hours=4))
        m_all.append(float(E))
        if len(taken):
            peak_gross = max(peak_gross, float(E_open * gross.max()))
    if not m_all:
        return None, ledger
    marr = np.array(m_all)
    i_min = int(np.argmin(marr))
    min_m = float(marr[i_min])
    peak = float(np.maximum.accumulate(np.concatenate([[1.0], marr]))[1:].max())
    run_peak = np.maximum.accumulate(np.concatenate([[1.0], marr]))[1:]
    dd = float(np.max(1 - marr / run_peak))
    trough_t = t_all[i_min]
    prior_peak = float(marr[:i_min + 1].max()) if i_min > 0 else 1.0
    rec = "never"
    for t, v in zip(t_all[i_min + 1:], marr[i_min + 1:]):
        if (t - trough_t).total_seconds() <= 7 * 86400 and v >= prior_peak:
            rec = round((t - trough_t).total_seconds() / 86400, 2)
            break
    cell = dict(equity_start=1.0, end_equity=round(E, 6),
                min_marked=round(min_m, 6),
                max_loss_pct=round(100 * (1 - min_m), 3),
                max_dd_pct=round(100 * dd, 3),
                peak_gross=round(peak_gross, 4),
                fills=fills, stops=stops, tps=tps, timeouts=timeouts,
                gap_stops=gap_stops, gap_max=round(gap_max, 3),
                worst_minute=str(trough_t), recovery_days_7d=rec)
    return cell, ledger


def main():
    print("loading 1m ...", flush=True)
    idx = None
    D = {}
    for sym in MAJORS:
        ii, d = load_1m(sym)
        if idx is None:
            idx = ii
        D[sym] = d
        print(f"  {sym} n={len(ii)}", flush=True)
    # per-phase bar grids + sigma
    grids = {}
    for s in PHASES:
        bts = pd.date_range(ORIGIN + pd.Timedelta(hours=s), LOAD_END, freq="4h")
        offs = ((bts - idx[0]).total_seconds() // 60).astype(int)
        ok = (offs >= 0) & (offs + 240 < len(idx))
        bts = bts[ok]
        ob, sg = {}, {}
        for sym in MAJORS:
            oo = D[sym]["open"][((bts - idx[0]).total_seconds() // 60).astype(int)].astype(float)
            ob[sym] = oo
            sg[sym] = compute_sigma(oo)
        grids[s] = (bts, ob, sg)
        print(f"phase {s}: {len(bts)} bars", flush=True)
    cells, ledgers = {}, []
    for wname, S in WINDOWS.items():
        for s in PHASES:
            bts, ob, sg = grids[s]
            js = [j for j, T in enumerate(bts)
                  if S <= T < S + pd.Timedelta(days=SIM_DAYS)]
            jj = {j: bts[j] for j in js}
            for arm in ARMS:
                cell, led = simulate_window(idx, D, jj, ob, sg, S, arm)
                cells[f"{wname}|s{s}|{arm}"] = cell
                ledgers.extend([(wname, s, arm) + tuple(r) for r in led])
                print(wname, f"s{s}", arm, cell, flush=True)
    chk = hashlib.sha256(repr(sorted(ledgers)).encode()).hexdigest()[:16]
    mix = {}
    for wname in WINDOWS:
        for arm in ARMS:
            cc = [cells[f"{wname}|s{s}|{arm}"] for s in PHASES]
            if any(c is None for c in cc):
                mix[f"{wname}|mix|{arm}"] = None
                continue
            mix[f"{wname}|mix|{arm}"] = {
                k: round(float(np.mean([c[k] for c in cc])), 3)
                for k in ("max_loss_pct", "max_dd_pct", "peak_gross", "end_equity")
            } | {"fills": int(sum(c["fills"] for c in cc)),
                 "stops": int(sum(c["stops"] for c in cc)),
                 "gap_stops": int(sum(c["gap_stops"] for c in cc))}
    out = {"config": {"coins": list(MAJORS), "rungs": list(RUNGS),
                       "live": [LIVE_A, LIVE_B], "maker": MAKER, "taker": TAKER,
                       "fund_long_settle": FUND, "settle_hours": list(SETTLE_HOURS),
                       "kd": KD, "unit": U, "budget": BUDGET, "gap_allow": GAP_ALLOW,
                       "gross_cap_G2": GCAP, "arms": list(ARMS),
                       "grid": "4h from 2020-01-01 00:00 UTC + phase h",
                       "windows": {k: str(v) for k, v in WINDOWS.items()},
                       "sim_days": SIM_DAYS, "phases": list(PHASES),
                       "equity_start_per_cell": 1.0,
                       "note": "dip-only; R2 agent size=1, scale=governor=1; "
                               "NOCAP=budget-only reference"},
             "cells": cells, "mix": mix, "ledger_checksum": chk,
             "n_ledger_rows": len(ledgers)}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("checksum", chk, "rows", len(ledgers), flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
