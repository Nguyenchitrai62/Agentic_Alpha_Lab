"""oc_carryhurdle: IDEAS11 #1 — quarterly carry entered only if annualised basis covers H x round-trip fees.

Frozen PLAN.md first. Light overlay only (no engine reruns, no 1m, hourly grid only).
Method = verbatim copy of oc_carrycompound/analyze_carrycompound.py overlay
(ONE compounding account A(t)=A(t-1)*(1+r_bot(t))+dU(t), f=0.25, causal hourly
marks, per-year reset to 1.0, spanning rebased to 0, v421 full-path DD formula)
applied to the frozen oc_cashcarry pair list filtered by the literal hurdle:

  C = 2*0.001 + 0.00055 + 0.0002 = 0.00275
  REF: ann_basis >= 0.04 (frozen)
  V1:  REF AND ann_basis >= 2.0*C = 0.0055
  V2:  REF AND ann_basis >= 1.5*C = 0.004125

Two BOT legs: G2 Binance (v421 R2B1D17BFG2) and G2 Bybit-S5 (runs_S5.pkl REF).

Protocol: Phase 0 reproduce gates (REF full-5y both venues). Phase 1 dev4-only
(anchors 2021-2024) for REF/V1/V2 both venues -> robust pick. Phase 2 recent
year (2025-09-24) scored ONCE only for pick + REF, both venues.

Usage: python research/tournament/oc_carryhurdle/analyze_carryhurdle.py
"""

from __future__ import annotations

import importlib.util
import json
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
CC = ROOT / "research/tournament/oc_cashcarry"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
S5_PKL = ROOT / "research/tournament/oc_k2bybit/tmp/runs_S5.pkl"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

COINS = ["BTC", "ETH"]
C_RT = 2 * 0.001 + 0.00055 + 0.0002  # 0.00275
T1 = 2.0 * C_RT  # 0.0055
T2 = 1.5 * C_RT  # 0.004125
F = 0.25
FEE_ENTRY_PAID = 0.001 + 0.00055
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_close_before(times_ns: np.ndarray, closes: np.ndarray,
                       ts_ns: np.ndarray) -> np.ndarray:
    """Close of the last bar with bar_time strictly before each query time."""
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def parse_expiry(fname: str) -> pd.Timestamp:
    m = re.search(r"_(\d{6})_1h\.parquet$", fname)
    assert m, fname
    s = m.group(1)
    return pd.Timestamp(f"20{s[:2]}-{s[2:4]}-{s[4:6]} 08:00", tz="UTC")


def recompute_skipped():
    """Re-run the frozen cashcarry entry rule to recover skipped contracts
    with hypothetical realised P&L (verbatim logic from analyze_cashcarry.py).
    4h + 1h only. Returns list of dicts."""
    out = []
    spots = {}
    for c in COINS:
        p = SDIR / f"{c}USDT_spot_4h.parquet"
        d = pd.read_parquet(p, columns=["open_time", "close", "close_time"])
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d["close_time"] = pd.to_datetime(d["close_time"], utc=True)
        spots[c] = d.sort_values("open_time").reset_index(drop=True)
    for coin in COINS:
        s = spots[coin]
        s_open, s_close_t = s["open_time"], s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        qmap = {}
        for f in sorted(QDIR.glob(f"um_{coin}USDT_*_1h.parquet")):
            d = pd.read_parquet(f, columns=["open_time", "close"])
            d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
            qmap[parse_expiry(f.name)] = d.sort_values("open_time").reset_index(drop=True)
        expiries = sorted(qmap)
        F_by_D = {}
        for D in expiries:
            q = qmap[D]
            qo = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
            qc = q["close"].to_numpy(dtype=float)
            sc = s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64)
            idx = np.searchsorted(qo, sc, side="left") - 1
            arr = np.full(len(s), np.nan)
            ok = idx >= 0
            arr[ok] = qc[idx[ok]]
            F_by_D[D] = arr
        for k, D in enumerate(expiries):
            Farr = F_by_D[D]
            if k > 0:
                cand = expiries[k - 1] - pd.Timedelta(days=7)
                pos = int(np.searchsorted(
                    s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    cand.value, side="left"))
            else:
                pos = 0
            both = np.where(~np.isnan(s_close) & ~np.isnan(Farr))[0]
            both = both[both >= pos]
            if len(both) == 0:
                continue
            ti = int(both[0])
            T_open, T_close = s_open.iloc[ti], s_close_t.iloc[ti]
            F_entry, S_entry = float(Farr[ti]), float(s_close[ti])
            dte = (D - T_close).total_seconds() / 86400.0
            if not (np.isfinite(F_entry) and np.isfinite(S_entry)) or dte <= 0:
                continue
            basis = float(np.log(F_entry / S_entry) * 365.0 / dte)
            si = int(np.searchsorted(
                s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                D.value, side="right"))
            if si >= len(s):
                out.append({"coin": coin, "delivery": str(D.date()),
                            "entry_open": str(T_open),
                            "ann_basis": round(basis, 6),
                            "dte_days": round(dte, 2),
                            "status": "incomplete_no_spot"})
                continue
            S_del = float(s_close[si])
            entered = bool(basis >= 0.04)
            gross = (S_del - S_entry) / S_entry + (F_entry - S_del) / F_entry
            hypo = float(gross - 0.00275)
            rec = {"coin": coin, "delivery": str(D.date()),
                   "entry_open": str(T_open), "ann_basis": round(basis, 6),
                   "dte_days": round(dte, 2),
                   "status": "entered" if entered else "skipped_basis",
                   "hypo_ret_alloc": round(hypo, 6),
                   "F_entry": F_entry, "S_entry": S_entry, "S_del": S_del}
            if not entered:
                out.append(rec)
    return [r for r in out if r["status"] == "skipped_basis"]


def main() -> None:
    print("oc_carryhurdle: start", flush=True)
    v388 = _load("v388_for_hurdle", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    DEV_ANCH = ANCH[:4]
    REC_ANCH = ANCH[4]
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)

    runs_bin = pickle.loads(V421.read_bytes())
    assert set(runs_bin) == {0, 1, 2, 3}
    s5 = pickle.loads(S5_PKL.read_bytes())
    legs_runs = {
        "binance": {s: runs_bin[s]["R2B1D17BFG2"] for s in range(4)},
        "bybit_S5": {s: s5[s]["REF"]["run"] for s in range(4)},
    }

    cc = json.loads((CC / "results.json").read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13
    assert cc["n_incomplete"] == 2
    assert abs(C_RT - cc["meta"]["fees"]["pair_drag"]) < 1e-12

    # ---- variant trade lists (frozen literal rule) ----
    all_tr = cc["trades"]
    ref_tr = list(all_tr)
    v1_tr = [t for t in all_tr if float(t["ann_basis"]) >= T1]
    v2_tr = [t for t in all_tr if float(t["ann_basis"]) >= T2]
    v1_skip = [t for t in all_tr if float(t["ann_basis"]) < T1]
    v2_skip = [t for t in all_tr if float(t["ann_basis"]) < T2]
    print(f"REF={len(ref_tr)} V1={len(v1_tr)} V2={len(v2_tr)} "
          f"V1_extra_skip={len(v1_skip)} V2_extra_skip={len(v2_skip)}", flush=True)

    # ---- skipped-contract context (hypothetical P&L, static, not a score) ----
    skipped = recompute_skipped()
    print(f"recomputed frozen-skipped contracts: {len(skipped)}", flush=True)
    assert len(skipped) == 13, skipped

    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all()), "hourly data reaches beyond the cap"
    spot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for coin in COINS:
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))

    qmap: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for t in all_tr:
        key = (t["coin"], t["delivery"])
        if key in qmap:
            continue
        y, m, dd = t["delivery"].split("-")
        code = f"{y[2:]}{m}{dd}"
        (f,) = sorted(QDIR.glob(f"um_{t['coin']}USDT_{code}_1h.parquet"))
        q = pd.read_parquet(f, columns=["open_time", "close"])
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype(
            "datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])

    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)

    def prep(trades_in):
        out = []
        for t in trades_in:
            te = pd.Timestamp(t["entry_open"], tz="UTC")
            tc = te + pd.Timedelta(hours=4)
            assert (s4o == te).any(), t
            D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
            si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64),
                                     D.value, side="right"))
            assert si < len(s4), t
            ts = s4c.iloc[si]
            assert ts > tc, t
            out.append({"coin": t["coin"], "delivery": t["delivery"],
                        "F_entry": float(t["F_entry"]),
                        "S_entry": float(t["S_entry"]),
                        "ret_alloc": float(t["ret_alloc"]),
                        "ann_basis": float(t["ann_basis"]),
                        "tc_ns": tc.value, "ts_ns": ts.value})
        for tr in out:
            st, sc = spot[tr["coin"]]
            ft, fc = qmap[(tr["coin"], tr["delivery"])]
            S = last_close_before(st, sc, gn)
            Ff = last_close_before(ft, fc, gn)
            with np.errstate(divide="ignore", invalid="ignore"):
                mtm = ((S / tr["S_entry"] - 1.0)
                       + ((tr["F_entry"] - Ff) / tr["F_entry"]) - FEE_ENTRY_PAID)
            mtm[~np.isfinite(mtm)] = np.nan
            mtm = pd.Series(mtm, index=grid).ffill().to_numpy()
            v = np.zeros(n)
            open_m = gn > tr["tc_ns"]
            settled_m = gn >= tr["ts_ns"]
            hold_m = open_m & ~settled_m
            v[hold_m] = mtm[hold_m]
            v[hold_m & ~np.isfinite(mtm)] = 0.0
            v[settled_m] = tr["ret_alloc"]
            tr["mtm"] = v
        return out

    variants = {"REF": prep(ref_tr), "V1": prep(v1_tr), "V2": prep(v2_tr)}

    def mtm_at_anchor(tr, a_ns: int) -> float:
        if a_ns <= tr["tc_ns"]:
            return 0.0
        if a_ns >= tr["ts_ns"]:
            return float(tr["ret_alloc"])
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        qa = np.array([a_ns])
        S = last_close_before(st, sc, qa)[0]
        Ff = last_close_before(ft, fc, qa)[0]
        if np.isfinite(S) and np.isfinite(Ff) and tr["F_entry"] and tr["S_entry"]:
            return float((S / tr["S_entry"] - 1.0)
                         + ((tr["F_entry"] - Ff) / tr["F_entry"])
                         - FEE_ENTRY_PAID)
        return 0.0

    base = {}
    for leg, runs in legs_runs.items():
        Es, Ms = [], []
        for s in range(4):
            e1, m1 = v388.hourly(runs[s], GRID0, g1)
            assert (e1.index == grid).all()
            Es.append(e1.to_numpy(dtype=float))
            Ms.append(m1.to_numpy(dtype=float))
        base[leg] = (np.stack(Es), np.stack(Ms))

    def year_row(Es, Ms, trades_in, a0):
        a1 = a0 + YEAR
        seg = (grid > a0) & (grid <= a1)
        idx = np.where(np.asarray(seg))[0]
        le = gn <= a0.value
        b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
        E4 = [Es[s][idx] / b[s] for s in range(4)]
        M4 = [Ms[s][idx] / b[s] for s in range(4)]
        es = np.mean(E4, axis=0)
        ms = np.mean(M4, axis=0)
        ypos = list(ANCH).index(a0)
        a_ns_all = np.array([a.value for a in ANCH])
        mtm_a = np.array([mtm_at_anchor(tr, a0.value) for tr in trades_in])
        rel = [k for k, tr in enumerate(trades_in)
               if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
        span = {k for k in rel if trades_in[k]["tc_ns"] <= a0.value}
        _ = (ypos, a_ns_all)
        N = {k: F * 1.0 for k in span}
        mtm_seg = {k: trades_in[k]["mtm"][idx] - mtm_a[k] for k in rel}
        es_prev = np.concatenate([[1.0], es[:-1]])
        g = es / es_prev
        hh = ms / es_prev
        A_prev, U_prev = 1.0, 0.0
        A_arr = np.empty(len(idx))
        M_arr = np.empty(len(idx))
        tc_map: dict[int, list[int]] = {}
        for k in rel:
            if k in span:
                continue
            pos = int(np.searchsorted(gn[idx], trades_in[k]["tc_ns"], side="right"))
            if 0 <= pos < len(idx):
                tc_map.setdefault(pos, []).append(k)
        U_open: dict[int, float] = dict(N)
        for i in range(len(idx)):
            for k in tc_map.get(i, []):
                U_open[k] = F * A_prev
            U_i = sum(nk * mtm_seg[k][i] for k, nk in U_open.items())
            dU = U_i - U_prev
            A_arr[i] = A_prev * g[i] + dU
            M_arr[i] = A_prev * hh[i] + dU
            A_prev, U_prev = A_arr[i], U_i
        pk = np.maximum.accumulate(A_arr)
        R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
        DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
        return {"anchor": str(a0.date()), "R": R, "DD": DD,
                "end": round(float(A_arr[-1]), 6)}

    def full_dd(Es, Ms, trades_in):
        Etot = Es.mean(axis=0)
        Mtot = Ms.mean(axis=0)
        A_c = np.empty(n)
        M_c = np.empty(n)
        g0_mtm = np.array([mtm_at_anchor(tr, gn[0]) for tr in trades_in])
        rel_c = [k for k, tr in enumerate(trades_in) if tr["ts_ns"] > gn[0]]
        span_c = {k for k in rel_c if trades_in[k]["tc_ns"] <= gn[0]}
        N_c: dict[int, float] = {k: F * float(Etot[0]) for k in span_c}
        mtm_r = {k: trades_in[k]["mtm"] - g0_mtm[k] for k in rel_c}
        tc_pos: dict[int, list[int]] = {}
        for k in rel_c:
            if k in span_c:
                continue
            pos = int(np.searchsorted(gn, trades_in[k]["tc_ns"], side="right"))
            if 0 <= pos < n:
                tc_pos.setdefault(pos, []).append(k)
        A_c[0], M_c[0] = float(Etot[0]), float(Mtot[0])
        A_prev = float(Etot[0])
        U_prev = 0.0
        U_open_c: dict[int, float] = dict(N_c)
        for i in range(1, n):
            for k in tc_pos.get(i, []):
                U_open_c[k] = F * A_prev
            U_i = sum(nk * mtm_r[k][i] for k, nk in U_open_c.items())
            dU = U_i - U_prev
            g = Etot[i] / Etot[i - 1]
            hh = Mtot[i] / Etot[i - 1]
            A_c[i] = A_prev * g + dU
            M_c[i] = A_prev * hh + dU
            A_prev, U_prev = A_c[i], U_i
        segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
        esf, msf = A_c[segf], M_c[segf]
        dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
        dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
        return {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}

    def geom_mean(Rs):
        return round(float(np.prod([1 + r / 100 for r in Rs]) ** (1 / len(Rs)) - 1) * 100, 3)

    # ---- Phase 0: reproduction gates (labelled, required) ----
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    Es_b, Ms_b = base["binance"]
    ref5_bin = [year_row(Es_b, Ms_b, variants["REF"], a) for a in ANCH]
    assert [y["R"] for y in ref5_bin] == [2.778, 3.353, 6.59, 10.956, 4.698], ref5_bin
    assert [y["DD"] for y in ref5_bin] == [10.86, 16.75, 15.69, 8.2, 12.66], ref5_bin
    assert geom_mean([y["R"] for y in ref5_bin]) == 5.634, ref5_bin
    assert max(y["DD"] for y in ref5_bin) == 16.75
    assert full_dd(Es_b, Ms_b, variants["REF"])["full"] == 16.66
    # f=0 reproduces G2
    Es0, Ms0 = base["binance"]
    e_trivial: list = []
    r0 = [year_row(Es0, Ms0, e_trivial, a) for a in ANCH]
    assert [y["R"] for y in r0] == [r for r, _ in exp["years"]], r0
    assert [y["DD"] for y in r0] == [d for _, d in exp["years"]], r0
    print("gate Binance REF (5.634/16.75/16.66) + f=0 G2 OK", flush=True)

    Es_y, Ms_y = base["bybit_S5"]
    ref5_by = [year_row(Es_y, Ms_y, variants["REF"], a) for a in ANCH]
    assert [y["R"] for y in ref5_by] == [2.321, 2.808, 5.484, 10.656, 4.493], ref5_by
    assert [y["DD"] for y in ref5_by] == [12.36, 17.95, 16.67, 9.15, 12.13], ref5_by
    assert geom_mean([y["R"] for y in ref5_by]) == 5.111, ref5_by
    assert full_dd(Es_y, Ms_y, variants["REF"])["full"] == 17.93
    print("gate Bybit-S5 REF (5.111/17.95/17.93) OK", flush=True)

    # ---- Phase 1: dev4 only for REF/V1/V2 (selection universe) ----
    dev: dict[str, dict[str, list]] = {}
    for leg in ("binance", "bybit_S5"):
        Es, Ms = base[leg]
        dev[leg] = {}
        for var in ("REF", "V1", "V2"):
            dev[leg][var] = [year_row(Es, Ms, variants[var], a) for a in DEV_ANCH]
            print(f"dev4 {leg} {var}: {dev[leg][var]}", flush=True)

    def dev_stats(rows):
        Rs = [y["R"] for y in rows]
        return {"mean": geom_mean(Rs), "worst": min(Rs),
                "DD": max(y["DD"] for y in rows),
                "losing": sum(r < 0 for r in Rs)}

    # Robust pick on dev4 (both venues must satisfy; Binance is primary per
    # assignment order — pick must pass on BOTH venues to be adoptable).
    pick = None
    for var in ("V1", "V2"):
        ok = True
        for leg in ("binance", "bybit_S5"):
            s = dev_stats(dev[leg][var])
            if not (s["DD"] <= 20 and s["losing"] == 0):
                ok = False
        if ok:
            pick = var if pick is None else pick
    # tie-break frozen in PLAN: V1 (more conservative) if both eligible & equal
    s1 = dev_stats(dev["binance"]["V1"])
    s2 = dev_stats(dev["binance"]["V2"])
    if s1 == s2:
        pick = "V1"
    else:
        # robust rule on Binance dev4, then check Bybit eligibility
        cands = []
        for var in ("V1", "V2"):
            s = dev_stats(dev["binance"][var])
            if s["DD"] <= 20 and s["losing"] == 0:
                cands.append((var, s))
        if cands:
            has5 = [c for c in cands if c[1]["mean"] >= 5.0]
            pool = has5 if has5 else cands
            pool.sort(key=lambda c: (c[1]["worst"], c[1]["mean"]), reverse=True)
            pick = pool[0][0]
        else:
            pick = "V1"
    print(f"robust pick on dev4: {pick}", flush=True)

    # ---- Phase 2: recent year scored ONCE, only for pick + REF ----
    recent: dict[str, dict[str, dict]] = {}
    for leg in ("binance", "bybit_S5"):
        Es, Ms = base[leg]
        recent[leg] = {}
        for var in (pick, "REF"):
            if var in recent[leg]:
                continue
            recent[leg][var] = year_row(Es, Ms, variants[var], REC_ANCH)
            print(f"recent {leg} {var}: {recent[leg][var]} (POST-RELEASE, scored once)",
                  flush=True)

    full: dict[str, dict[str, dict]] = {}
    for leg in ("binance", "bybit_S5"):
        Es, Ms = base[leg]
        full[leg] = {}
        for var in (pick, "REF"):
            if var in full[leg]:
                continue
            full[leg][var] = full_dd(Es, Ms, variants[var])

    def five_stats(leg, var):
        rows = dev[leg][var] + [recent[leg][var]]
        Rs = [y["R"] for y in rows]
        return {"mean": geom_mean(Rs), "worst": min(Rs),
                "DD": max(y["DD"] for y in rows),
                "losing": sum(r < 0 for r in Rs)}

    out = {
        "meta": {
            "carry_src": "research/tournament/oc_cashcarry/results.json (33 entered frozen, threshold 0.04)",
            "overlay": "ONE compounding account A(t)=A(t-1)*(1+r_bot(t))+dU(t), f=0.25, causal hourly marks, per-year reset, spanning rebased, v421 full-path DD (verbatim oc_carrycompound)",
            "hurdle": f"C=0.00275; V1 ann_basis>=2.0*C=0.0055 (literal); V2 ann_basis>=1.5*C=0.004125 (literal); ANDed with frozen 0.04",
            "variants": ["REF", "V1", "V2"],
            "dev_universe": [str(a.date()) for a in DEV_ANCH],
            "recent_post_release": str(REC_ANCH.date()),
            "pick": pick,
            "labels": "dev4 rows = selection universe; recent/5y/full rows ONLY for pick+REF (post-release, scored once); Bybit y2021 SHORT (live from 2021-11-15)",
        },
        "hurdle_counts": {
            "REF_n": len(ref_tr), "V1_n": len(v1_tr), "V2_n": len(v2_tr),
            "V1_extra_skipped": v1_skip, "V2_extra_skipped": v2_skip,
        },
        "frozen_skipped_hypothetical": skipped,
        "dev4": {leg: {var: {"years": dev[leg][var], **dev_stats(dev[leg][var])}
                        for var in ("REF", "V1", "V2")}
                 for leg in ("binance", "bybit_S5")},
        "recent_once": {leg: {var: recent[leg][var] for var in recent[leg]}
                        for leg in ("binance", "bybit_S5")},
        "five": {leg: {var: {"years": dev[leg][var] + [recent[leg][var]],
                             **five_stats(leg, var),
                             "full_path_dd": full[leg][var]}
                       for var in recent[leg]}
                 for leg in ("binance", "bybit_S5")},
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"wrote results.json; pick={pick}", flush=True)


if __name__ == "__main__":
    main()
