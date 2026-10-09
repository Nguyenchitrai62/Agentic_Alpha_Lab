"""oc_vrprobust carry base: account-realistic G2+carry(f=0.25) hourly paths.

Copied construction from research/tournament/oc_carrycompound/
analyze_carrycompound.py (read-only source, never edited): one account
A(t) = A(t-1)*(1+r_bot(t)) + dU(t), carry notional N = f x A at each entry,
held to delivery; mtm per alloc from oc_cashcarry trades net of fees;
hourly S/F marks causal (last CLOSED hourly bar strictly before t).
Exposes builders returning yearly-reset (g, hh, idx) pairs and full-path
arrays for the G2+carry base used as the overlay bed in D1.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
CC = ROOT / "research/tournament/oc_cashcarry"
V421 = RD / "v421/v421_runs.pkl"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

COINS = ["BTC", "ETH"]
FEE_ENTRY_PAID = 0.001 + 0.00055
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
STRAT = "R2B1D17BFG2"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_close_before(times_ns, closes, ts_ns):
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def load_grid():
    v388 = _load("v388_for_carrybase", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(GRID0, g1, freq="1h")
    return v388, grid


def load_g2_base(grid):
    """Per-phase G2 hourly equities -> Es, Ms (4, n)."""
    v388 = _load("v388_for_carrybase2", RD / "v388/v388_bot_stop_distance.py")
    runs = pickle.loads(V421.read_bytes())
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][STRAT], GRID0, grid[-1])
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    return np.stack(Es), np.stack(Ms)


_AUX: dict = {}


def load_carry_trades(grid):
    """Carry trades with hourly mtm (alloc units) on grid (copy of compound)."""
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)
    cc = json.loads((CC / "results.json").read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13
    assert cc["n_incomplete"] == 2

    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all())
    spot = {}
    for coin in COINS:
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))
    qmap = {}
    for t in cc["trades"]:
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
    trades = []
    for t in cc["trades"]:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        assert (s4o == te).any(), t
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64),
                                 D.value, side="right"))
        assert si < len(s4), t
        ts = s4c.iloc[si]
        assert ts > tc, t
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "F_entry": float(t["F_entry"]),
                       "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "tc_ns": tc.value, "ts_ns": ts.value})
    for tr in trades:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        S = last_close_before(st, sc, gn)
        F = last_close_before(ft, fc, gn)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = ((S / tr["S_entry"] - 1.0)
                   + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID)
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
    _AUX["spot"] = spot
    _AUX["qmap"] = qmap
    return trades


def year_base_g_hh(Es, Ms, grid, trades, f, a0):
    """Yearly-reset G2+carry(f) base: returns idx, g, hh (base returns)."""
    a1 = a0 + YEAR
    seg = (grid > a0) & (grid <= a1)
    idx = np.where(np.asarray(seg))[0]
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    le = gn <= a0.value
    b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
    es = np.mean([Es[s][idx] / b[s] for s in range(4)], axis=0)
    ms = np.mean([Ms[s][idx] / b[s] for s in range(4)], axis=0)
    if f == 0.0:
        return idx, es / np.concatenate([[1.0], es[:-1]]), ms / np.concatenate([[1.0], es[:-1]]), es, ms
    mtm_a = np.array([mtm_at_anchor(tr, a0.value, grid) for tr in trades])
    rel = [k for k, tr in enumerate(trades)
           if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
    span = {k for k in rel if trades[k]["tc_ns"] <= a0.value}
    mtm_seg = {k: trades[k]["mtm"][idx] - mtm_a[k] for k in rel}
    tc_map: dict[int, list[int]] = {}
    for k in rel:
        if k in span:
            continue
        pos = int(np.searchsorted(gn[idx], trades[k]["tc_ns"], side="right"))
        if 0 <= pos < len(idx):
            tc_map.setdefault(pos, []).append(k)
    es_prev = np.concatenate([[1.0], es[:-1]])
    g = es / es_prev
    hh = ms / es_prev
    U_open: dict[int, float] = {k: f * 1.0 for k in span}
    A_prev, U_prev = 1.0, 0.0
    A_arr = np.empty(len(idx))
    M_arr = np.empty(len(idx))
    for i in range(len(idx)):
        for k in tc_map.get(i, []):
            U_open[k] = f * A_prev
        U_i = sum(nk * mtm_seg[k][i] for k, nk in U_open.items())
        dU = U_i - U_prev
        A_arr[i] = A_prev * g[i] + dU
        M_arr[i] = A_prev * hh[i] + dU
        A_prev, U_prev = A_arr[i], U_i
    # re-express as base paths so the VRP sleeve can layer identically:
    A_prev0 = np.concatenate([[1.0], A_arr[:-1]])
    gb = A_arr / A_prev0
    hb = M_arr / A_prev0
    return idx, gb, hb, A_arr, M_arr


def mtm_at_anchor(tr, a_ns, grid=None):
    # verbatim copy of oc_carrycompound's mtm_at_anchor (bar-close semantics)
    if a_ns <= tr["tc_ns"]:
        return 0.0
    if a_ns >= tr["ts_ns"]:
        return float(tr["ret_alloc"])
    spot, qmap = _AUX["spot"], _AUX["qmap"]
    st, sc = spot[tr["coin"]]
    ft, fc = qmap[(tr["coin"], tr["delivery"])]
    qa = np.array([a_ns])
    S = last_close_before(st, sc, qa)[0]
    F = last_close_before(ft, fc, qa)[0]
    if np.isfinite(S) and np.isfinite(F) and tr["F_entry"] and tr["S_entry"]:
        return float((S / tr["S_entry"] - 1.0)
                     + ((tr["F_entry"] - F) / tr["F_entry"])
                     - FEE_ENTRY_PAID)
    return 0.0


def full_base(Es, Ms, grid, trades, f):
    """Continuous full-path G2+carry(f) account from grid start."""
    n = len(grid)
    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)
    if f == 0.0:
        return Etot.copy(), Mtot.copy()
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
    span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
    N_c = {k: f * float(Etot[0]) for k in span_c}
    g0_mtm = np.array([mtm_at_anchor(tr, gn[0], grid) for tr in trades])
    mtm_r = {k: trades[k]["mtm"] - g0_mtm[k] for k in rel_c}
    tc_pos: dict[int, list[int]] = {}
    for k in rel_c:
        if k in span_c:
            continue
        pos = int(np.searchsorted(gn, trades[k]["tc_ns"], side="right"))
        if 0 <= pos < n:
            tc_pos.setdefault(pos, []).append(k)
    A_c = np.empty(n)
    M_c = np.empty(n)
    A_c[0], M_c[0] = float(Etot[0]), float(Mtot[0])
    A_prev = float(Etot[0])
    U_prev = 0.0
    U_open_c: dict[int, float] = dict(N_c)
    for i in range(1, n):
        for k in tc_pos.get(i, []):
            U_open_c[k] = f * A_prev
        U_i = sum(nk * mtm_r[k][i] for k, nk in U_open_c.items())
        dU = U_i - U_prev
        A_c[i] = A_prev * Etot[i] / Etot[i - 1] + dU
        M_c[i] = A_prev * Mtot[i] / Etot[i - 1] + dU
        A_prev, U_prev = A_c[i], U_i
    return A_c, M_c
