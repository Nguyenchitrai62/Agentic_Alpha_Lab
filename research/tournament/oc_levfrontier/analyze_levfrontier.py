"""oc_levfrontier scoring (CPU-only, hourly, no 1m reads, no engine reruns here).

Method = verbatim copy of research/tournament/oc_c2carry/analyze_c2carry.py
generalized to 16 BOT legs (8 configs x Binance/Bybit-S5), each with f=0.0 and
f=0.25 compounding on TOTAL equity (ONE account UTA), plus the oc_c2carry
stationary block bootstrap per row (mean block 10 d, 4000 draws, seed 0).

BOT legs (flat runs {t,eq,eq_min} per shift for the hourly grid):
  L00 G2 base/S5, L01 G2+C2 base/S5, L02 G2+B7 base/S5, L03 G2+B7xC2 base/S5,
  L10 G2K20 base/S5, L11 G2K20+C2 base/S5, L12 G2K20+B7 base/S5, L13 G2K20+B7C2 base/S5.
Reused legs are read from frozen caches (asserted to the digit); new legs
(L10_S5, L11_S5, L12_base/S5, L13_base/S5) are read from tmp/runs_*_*.pkl
written by compute_levfrontier_engine.py.

BOT per-year R/DD use the same hourly-grid year_pass as oc_c2carry (which
reproduces v421 / oc_chronos / oc_cascadeboost / oc_b7c2 / oc_c2frontier to the
digit); a reset_metric.year_reset cross-check is asserted for the reused rows.
Full-path DD is the v421 continuous formula on the grid; worst marked episode
is peak/trough/depth on dd(t)=1-M(t)/peak(E)(t) from the same continuous
account (BOT marks are 1m-marked via eq_min; carry marks are close-marked, so
carry DD is a lower bound). Wins are pooled from the stored engine wins dicts.

Usage: python research/tournament/oc_levfrontier/analyze_levfrontier.py
Writes tmp/levfrontier_table.json + results.json. See PLAN.md (pre-registered).
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
TMP = HERE / "tmp"
CC = ROOT / "research/tournament/oc_cashcarry"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
V422 = RD / "v422/v422_runs.pkl"
V422_RES = RD / "v422/v422_result.json"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
CH_LAST = ROOT / "research/tournament/oc_chronos/tmp/runs_last.pkl"
C2B = ROOT / "research/tournament/oc_c2bybit/tmp/runs_base.pkl"
S5C2 = ROOT / "research/tournament/oc_c2bybit/tmp/runs_S5.pkl"
S5K2 = ROOT / "research/tournament/oc_k2bybit/tmp/runs_S5.pkl"
CB_LAST = ROOT / "research/tournament/oc_cascadeboost/tmp/runs_last.pkl"
CBB_BASE = ROOT / "research/tournament/oc_cboostbybit/tmp/runs_base.pkl"
CBB_S5 = ROOT / "research/tournament/oc_cboostbybit/tmp/runs_S5.pkl"
B7C2_LAST = ROOT / "research/tournament/oc_b7c2/tmp/runs_last.pkl"
B7C2_S5 = ROOT / "research/tournament/oc_b7c2/tmp/runs_S5.pkl"
G2K20C2_BASE = ROOT / "research/tournament/oc_c2frontier/tmp/runs_G2K20_C2_base.pkl"
C2C_RES = ROOT / "research/tournament/oc_c2carry/results.json"

COINS = ["BTC", "ETH"]
F_ROWS = [0.0, 0.25]
FEE_ENTRY_PAID = 0.001 + 0.00055
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
S5_LIVE0 = pd.Timestamp("2021-11-15", tz="UTC")

BOOT_MEAN_BLOCK = 10.0
BOOT_N = 4000
BOOT_LEN = 365
BOOT_SEED = 0


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_close_before(times_ns: np.ndarray, closes: np.ndarray,
                       ts_ns: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def stationary_indices(n, length, rng, p):
    out = np.empty(length, dtype=np.int64)
    k = 0
    while k < length:
        start = int(rng.integers(0, n))
        L = int(rng.geometric(p))
        L = min(L, length - k)
        idx = (start + np.arange(L)) % n
        out[k:k + L] = idx
        k += L
    return out


def bootstrap_row(r, l, seed=BOOT_SEED, n_paths=BOOT_N,
                  length=BOOT_LEN, mean_block=BOOT_MEAN_BLOCK):
    rng = np.random.default_rng(seed)
    n = len(r)
    p = 1.0 / mean_block
    I = np.empty((n_paths, length), dtype=np.int64)
    for b in range(n_paths):
        I[b] = stationary_indices(n, length, rng, p)
    R = r[I]
    L = l[I]
    P = np.cumprod(1.0 + R, axis=1)
    Pprev = np.concatenate([np.ones((n_paths, 1)), P[:, :-1]], axis=1)
    Mk = np.minimum(P, Pprev * L)
    peak = np.maximum.accumulate(
        np.concatenate([np.ones((n_paths, 1)), P], axis=1), axis=1)[:, 1:]
    dd_m = np.max(1.0 - Mk / peak, axis=1)
    R12 = P[:, -1] - 1.0
    m = (1.0 + np.clip(R12, -0.999999, None)) ** (1.0 / 12.0) - 1.0
    return {
        "m_med_pc": round(100 * float(np.median(m)), 3),
        "p_m_ge_5pc": round(100 * float(np.mean(m >= 0.05)), 2),
        "p_dd_gt_20pc": round(100 * float(np.mean(dd_m > 0.20)), 2),
        "p_losing_pc": round(100 * float(np.mean(R12 < 0)), 2),
    }


def worst_episode(grid, A_c, M_c):
    segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
    esf, msf = A_c[segf], M_c[segf]
    idx = grid[segf]
    pk = np.maximum.accumulate(esf)
    dd = 1 - msf / pk
    i_dd = int(np.argmax(dd))
    i_pk = int(np.argmax(esf[:i_dd + 1])) if i_dd > 0 else 0
    return {"peak": str(idx[i_pk]), "trough": str(idx[i_dd]),
            "depth_pct": round(100 * float(dd[i_dd]), 2)}


def main() -> None:
    v388 = _load("v388_for_lev", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_for_lev", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)

    # ---- BOT legs (frozen caches + 6 new) ----
    v421 = pickle.loads(V421.read_bytes())
    v422 = pickle.loads(V422.read_bytes())
    ch_last = pickle.loads(CH_LAST.read_bytes())
    c2b = pickle.loads(C2B.read_bytes())
    s5c2 = pickle.loads(S5C2.read_bytes())
    s5k2 = pickle.loads(S5K2.read_bytes())
    cb_last = pickle.loads(CB_LAST.read_bytes())
    cbb_base = pickle.loads(CBB_BASE.read_bytes())
    cbb_s5 = pickle.loads(CBB_S5.read_bytes())
    b7c2_last = pickle.loads(B7C2_LAST.read_bytes())
    b7c2_s5 = pickle.loads(B7C2_S5.read_bytes())
    g2k20c2_base = pickle.loads(G2K20C2_BASE.read_bytes())
    new = {}
    for cfg, fric in (("G2K20", "S5"), ("G2K20_C2", "S5"),
                      ("G2K20_B7", "base"), ("G2K20_B7", "S5"),
                      ("G2K20_B7C2", "base"), ("G2K20_B7C2", "S5")):
        p = TMP / f"runs_{cfg}_{fric}.pkl"
        assert p.exists(), f"missing {p} — run compute_levfrontier_engine.py first"
        new[(cfg, fric)] = pickle.loads(p.read_bytes())

    legs = {
        "L00_bin": {s: v421[s]["R2B1D17BFG2"] for s in range(4)},
        "L00_by": {s: s5c2[s]["REF"]["run"] for s in range(4)},
        "L01_bin": {s: ch_last[s]["C2"]["run"] for s in range(4)},
        "L01_by": {s: s5c2[s]["C2"]["run"] for s in range(4)},
        "L02_bin": {s: cb_last[s]["B7"]["run"] if "B7" in cb_last[s] else cbb_base[s]["B7"]["run"] for s in range(4)},
        "L02_by": {s: cbb_s5[s]["B7"]["run"] for s in range(4)},
        "L03_bin": {s: b7c2_last[s]["B7C2"]["run"] for s in range(4)},
        "L03_by": {s: b7c2_s5[s]["B7C2"]["run"] for s in range(4)},
        "L10_bin": {s: v422[s]["G2K20"] for s in range(4)},
        "L10_by": {s: new[("G2K20", "S5")][s]["G2K20"]["run"] for s in range(4)},
        "L11_bin": {s: g2k20c2_base[s]["G2K20_C2"]["run"] for s in range(4)},
        "L11_by": {s: new[("G2K20_C2", "S5")][s]["G2K20_C2"]["run"] for s in range(4)},
        "L12_bin": {s: new[("G2K20_B7", "base")][s]["G2K20_B7"]["run"] for s in range(4)},
        "L12_by": {s: new[("G2K20_B7", "S5")][s]["G2K20_B7"]["run"] for s in range(4)},
        "L13_bin": {s: new[("G2K20_B7C2", "base")][s]["G2K20_B7C2"]["run"] for s in range(4)},
        "L13_by": {s: new[("G2K20_B7C2", "S5")][s]["G2K20_B7C2"]["run"] for s in range(4)},
    }
    # wins pools (same keys; v421/v422 have no wins dicts -> wins=None there)
    wins_src = {
        "L00_bin": None, "L00_by": None,
        "L01_bin": {s: ch_last[s]["C2"]["wins"] for s in range(4)},
        "L01_by": None,
        "L02_bin": None, "L02_by": None,
        "L03_bin": {s: b7c2_last[s]["B7C2"]["wins"] for s in range(4)},
        "L03_by": {s: b7c2_s5[s]["B7C2"]["wins"] for s in range(4)},
        "L10_bin": None, "L10_by": {s: new[("G2K20", "S5")][s]["G2K20"]["wins"] for s in range(4)},
        "L11_bin": None, "L11_by": {s: new[("G2K20_C2", "S5")][s]["G2K20_C2"]["wins"] for s in range(4)},
        "L12_bin": {s: new[("G2K20_B7", "base")][s]["G2K20_B7"]["wins"] for s in range(4)},
        "L12_by": {s: new[("G2K20_B7", "S5")][s]["G2K20_B7"]["wins"] for s in range(4)},
        "L13_bin": {s: new[("G2K20_B7C2", "base")][s]["G2K20_B7C2"]["wins"] for s in range(4)},
        "L13_by": {s: new[("G2K20_B7C2", "S5")][s]["G2K20_B7C2"]["wins"] for s in range(4)},
    }
    # sanity: S5 REF identical across K2/C2/B7 files (same engine)
    for s in range(4):
        a = np.asarray(s5k2[s]["REF"]["run"]["eq"], dtype=float)
        b = np.asarray(s5c2[s]["REF"]["run"]["eq"], dtype=float)
        assert a.shape == b.shape and bool((a == b).all()), s
    print("S5 REF identical across K2/C2 files", flush=True)

    # ---- carry trades (verbatim from analyze_carrycompound.py) ----
    cc = json.loads((CC / "results.json").read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13
    assert cc["n_incomplete"] == 2

    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all()), "hourly data reaches beyond the cap"
    spot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for coin in COINS:
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))

    qmap: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
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

    def mtm_at_anchor(tr, a_ns: int) -> float:
        if a_ns <= tr["tc_ns"]:
            return 0.0
        if a_ns >= tr["ts_ns"]:
            return float(tr["ret_alloc"])
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

    a_ns_all = np.array([a.value for a in ANCH])
    anchor_mtm = np.array([[mtm_at_anchor(tr, a) for tr in trades]
                           for a in a_ns_all])

    # ---- per-leg base hourly equities on the grid ----
    base = {}
    for leg, runs in legs.items():
        Es, Ms = [], []
        for s in range(4):
            e1, m1 = v388.hourly(runs[s], GRID0, g1)
            assert (e1.index == grid).all()
            Es.append(e1.to_numpy(dtype=float))
            Ms.append(m1.to_numpy(dtype=float))
        base[leg] = (np.stack(Es), np.stack(Ms))

    def year_pass(Es, Ms, f):
        years = []
        Ac_list, Mc_list = [], []
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            seg = (grid > a0) & (grid <= a1)
            idx = np.where(np.asarray(seg))[0]
            le = gn <= a0.value
            b = np.array([float(Es[s][le][-1]) if le.any() else 1.0
                          for s in range(4)])
            E4 = [Es[s][idx] / b[s] for s in range(4)]
            M4 = [Ms[s][idx] / b[s] for s in range(4)]
            es = np.mean(E4, axis=0)
            ms = np.mean(M4, axis=0)
            if f == 0.0:
                A_arr, M_arr = es, ms
            else:
                es_prev = np.concatenate([[1.0], es[:-1]])
                g = es / es_prev
                hh = ms / es_prev
                mtm_a = anchor_mtm[y]
                rel = [k for k, tr in enumerate(trades)
                       if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
                span = {k for k in rel if trades[k]["tc_ns"] <= a0.value}
                N = {k: f * 1.0 for k in span}
                mtm_seg = {k: trades[k]["mtm"][idx] - mtm_a[k] for k in rel}
                A_prev, U_prev = 1.0, 0.0
                A_arr = np.empty(len(idx))
                M_arr = np.empty(len(idx))
                tc_map: dict[int, list[int]] = {}
                for k in rel:
                    if k in span:
                        continue
                    pos = int(np.searchsorted(gn[idx], trades[k]["tc_ns"],
                                              side="right"))
                    if 0 <= pos < len(idx):
                        tc_map.setdefault(pos, []).append(k)
                U_open: dict[int, float] = dict(N)
                for i in range(len(idx)):
                    for k in tc_map.get(i, []):
                        U_open[k] = f * A_prev
                    U_i = 0.0
                    for k, nk in U_open.items():
                        U_i += nk * mtm_seg[k][i]
                    dU = U_i - U_prev
                    A_i = A_prev * g[i] + dU
                    M_i = A_prev * hh[i] + dU
                    A_arr[i] = A_i
                    M_arr[i] = M_i
                    A_prev, U_prev = A_i, U_i
            pk = np.maximum.accumulate(A_arr)
            R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
            DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
            years.append({"anchor": str(a0.date()), "R": R, "DD": DD,
                          "end": round(float(A_arr[-1]), 6)})
            Ac_list.append(A_arr)
            Mc_list.append(M_arr)
        R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years])
                         ** (1 / 5) - 1) * 100, 3)
        return years, R5, Ac_list, Mc_list

    def full_pass(Es, Ms, f):
        Etot = Es.mean(axis=0)
        Mtot = Ms.mean(axis=0)
        if f == 0.0:
            A_c, M_c = Etot.copy(), Mtot.copy()
        else:
            A_c = np.empty(n)
            M_c = np.empty(n)
            g0_mtm = np.array([mtm_at_anchor(tr, gn[0]) for tr in trades])
            rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
            span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
            N_c: dict[int, float] = {k: f * float(Etot[0]) for k in span_c}
            mtm_r = {k: trades[k]["mtm"] - g0_mtm[k] for k in rel_c}
            tc_pos: dict[int, list[int]] = {}
            for k in rel_c:
                if k in span_c:
                    continue
                pos = int(np.searchsorted(gn, trades[k]["tc_ns"], side="right"))
                if 0 <= pos < n:
                    tc_pos.setdefault(pos, []).append(k)
            A_c[0], M_c[0] = float(Etot[0]), float(Mtot[0])
            A_prev = float(Etot[0])
            U_prev = 0.0
            U_open_c: dict[int, float] = dict(N_c)
            for i in range(1, n):
                for k in tc_pos.get(i, []):
                    U_open_c[k] = f * A_prev
                U_i = 0.0
                for k, nk in U_open_c.items():
                    U_i += nk * mtm_r[k][i]
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
        return A_c, M_c, {"marked": dd_m, "close": dd_c,
                          "full": max(dd_m, dd_c)}

    LABELS = {
        "L00_bin": ("G2", "binance", 1.7, "none"), "L00_by": ("G2", "bybit_S5", 1.7, "none"),
        "L01_bin": ("G2+C2", "binance", 1.7, "C2"), "L01_by": ("G2+C2", "bybit_S5", 1.7, "C2"),
        "L02_bin": ("G2+B7", "binance", 1.7, "B7"), "L02_by": ("G2+B7", "bybit_S5", 1.7, "B7"),
        "L03_bin": ("G2+B7xC2", "binance", 1.7, "B7xC2"), "L03_by": ("G2+B7xC2", "bybit_S5", 1.7, "B7xC2"),
        "L10_bin": ("G2K20", "binance", 2.0, "none"), "L10_by": ("G2K20", "bybit_S5", 2.0, "none"),
        "L11_bin": ("G2K20+C2", "binance", 2.0, "C2"), "L11_by": ("G2K20+C2", "bybit_S5", 2.0, "C2"),
        "L12_bin": ("G2K20+B7", "binance", 2.0, "B7"), "L12_by": ("G2K20+B7", "bybit_S5", 2.0, "B7"),
        "L13_bin": ("G2K20+B7xC2", "binance", 2.0, "B7xC2"), "L13_by": ("G2K20+B7xC2", "bybit_S5", 2.0, "B7xC2"),
    }

    rows = {}
    for leg in sorted(legs):
        Es, Ms = base[leg]
        bot, venue, kd, overlay = LABELS[leg]
        for f in F_ROWS:
            years, R5, _, _ = year_pass(Es, Ms, f)
            A_c, M_c, full = full_pass(Es, Ms, f)
            ep = worst_episode(grid, A_c, M_c)
            e_s = pd.Series(A_c, index=grid)
            m_s = pd.Series(M_c, index=grid)
            D0 = S5_LIVE0 if venue == "bybit_S5" else pd.Timestamp(
                "2021-09-24", tz="UTC")
            D = pd.date_range(D0, pd.Timestamp("2026-09-23", tz="UTC"),
                              freq="1D")
            E = e_s.reindex(D, method="ffill").fillna(1.0).to_numpy(float)
            M = pd.Series(index=D, dtype=float)
            M.iloc[0] = float(E[0])
            mh = pd.concat([m_s, e_s], axis=1).min(axis=1)
            for d in range(1, len(D)):
                seg = mh[(mh.index > D[d - 1]) & (mh.index <= D[d])]
                M.iloc[d] = float(seg.min()) if len(seg) else float(E[d])
            M = M.fillna(pd.Series(E, index=D)).to_numpy(float)
            r = E[1:] / E[:-1] - 1.0
            l = M[1:] / E[:-1]
            boot = bootstrap_row(r, l)
            dev = [yy["R"] for yy in years[:4]]
            key = f"{leg}{'_carry' if f else ''}"
            wpool = wins_src.get(leg)
            if wpool is not None:
                wins = []
                for y in range(5):
                    nb = sum(wpool[s][y]["nb"] for s in range(4))
                    wb = sum(wpool[s][y]["wb"] for s in range(4))
                    nr = sum(wpool[s][y]["nr"] for s in range(4))
                    wr = sum(wpool[s][y]["wr"] for s in range(4))
                    wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                                     book_win=round(wb / nb, 4) if nb else None,
                                     rung_win=round(wr / nr, 4) if nr else None,
                                     all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
            else:
                wins = None
            rows[key] = {
                "leg": leg, "bot": bot, "venue": venue, "kd": kd,
                "overlay": overlay, "f": f,
                "years": years,
                "dev4": {"R": [years[y]["R"] for y in range(4)],
                         "DD": [years[y]["DD"] for y in range(4)],
                         "mean": round(float(np.prod([1 + years[y]["R"] / 100 for y in range(4)]) ** (1 / 4) - 1) * 100, 3),
                         "W": min(dev), "DDmax": max(years[y]["DD"] for y in range(4)),
                         "losing": sum(v < 0 for v in dev)},
                "R5y": R5,
                "W5y": min(yy["R"] for yy in years),
                "DDmax": max(yy["DD"] for yy in years),
                "losing": sum(yy["R"] < 0 for yy in years),
                "full_path_dd": full,
                "worst_marked_episode": ep,
                "recent": years[-1],
                "bootstrap": boot,
                "wins": wins,
            }
            print(f"{key}: 5y={R5} W={rows[key]['W5y']} "
                  f"DD={rows[key]['DDmax']} full={full['full']} "
                  f"boot={boot}", flush=True)

    # ---- reproduction gates (STOP if failed) ----
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    g = rows["L00_bin"]
    assert [yy["R"] for yy in g["years"]] == [r for r, _ in exp["years"]], g
    assert [yy["DD"] for yy in g["years"]] == [d for _, d in exp["years"]], g
    assert g["R5y"] == exp["R"] and g["W5y"] == exp["W"]
    assert g["DDmax"] == exp["DD"], (g, exp)
    assert g["full_path_dd"]["full"] == exp["full_path_dd"], g
    print("gate G2 base OK", flush=True)
    exp22 = json.loads(V422_RES.read_text())["rows"]["G2K20"]
    g10 = rows["L10_bin"]
    assert [yy["R"] for yy in g10["years"]] == [r for r, _ in exp22["years"]], g10
    assert [yy["DD"] for yy in g10["years"]] == [d for _, d in exp22["years"]], g10
    assert g10["R5y"] == exp22["R"] and g10["W5y"] == exp22["W"]
    assert g10["full_path_dd"]["full"] == exp22["full_path_dd"], g10
    print("gate G2K20 base OK", flush=True)
    c2c = json.loads(C2C_RES.read_text())["rows"]
    assert rows["L00_bin_carry"]["R5y"] == c2c["G2_carry_binance"]["R5y"], rows["L00_bin_carry"]
    assert rows["L00_bin_carry"]["full_path_dd"]["full"] == c2c["G2_carry_binance"]["full_path_dd"]["full"]
    assert rows["L00_by_carry"]["R5y"] == c2c["G2_carry_bybit_S5"]["R5y"]
    assert rows["L00_by_carry"]["full_path_dd"]["full"] == c2c["G2_carry_bybit_S5"]["full_path_dd"]["full"]
    assert rows["L01_bin"]["R5y"] == c2c["C2_binance"]["R5y"], (rows["L01_bin"], c2c["C2_binance"])
    assert rows["L01_by"]["R5y"] == c2c["C2_bybit_S5"]["R5y"]
    print("gate oc_c2carry method (G2+carry both venues, C2 both venues) OK", flush=True)
    # reset_metric cross-check on reused rows (must match frozen tables to the digit)
    for leg, rr_src, rkey in (
            ("L01_bin", {s: {"C2": c2b[s]["C2"]["run"]} for s in range(4)}, "C2"),
            ("L01_by", {s: {"C2": s5c2[s]["C2"]["run"]} for s in range(4)}, "C2"),
            ("L02_bin", {s: {"B7": cbb_base[s]["B7"]["run"]} for s in range(4)}, "B7"),
            ("L02_by", {s: {"B7": cbb_s5[s]["B7"]["run"]} for s in range(4)}, "B7"),
            ("L03_bin", {s: {"B7C2": b7c2_last[s]["B7C2"]["run"]} for s in range(4)}, "B7C2"),
            ("L03_by", {s: {"B7C2": b7c2_s5[s]["B7C2"]["run"]} for s in range(4)}, "B7C2"),
            ("L00_by", {s: {"REF": s5c2[s]["REF"]["run"]} for s in range(4)}, "REF")):
        got = [rm.year_reset(rr_src, rkey, y) for y in range(5)]
        gr = [x["R"] for x in got]
        gd = [x["DD"] for x in got]
        assert gr == [yy["R"] for yy in rows[leg]["years"]], (leg, gr, rows[leg]["years"])
        assert gd == [yy["DD"] for yy in rows[leg]["years"]], (leg, gd)
    print("gate reset_metric cross-check on reused rows OK", flush=True)

    out = {
        "meta": {
            "assignment": "docs/opencode/OPENCODE_W_oc_levfrontier.md",
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
            "g2k20_src": "research/parallel/rounds/parallel-20260906-r2/v422/v422_runs.pkl strat G2K20",
            "c2_src": "research/tournament/oc_chronos/tmp/runs_last.pkl C2 + oc_c2bybit runs_base.pkl/runs_S5.pkl C2",
            "b7_src": "research/tournament/oc_cascadeboost/tmp/runs_last.pkl B7 + oc_cboostbybit runs_base.pkl/runs_S5.pkl B7",
            "b7c2_src": "research/tournament/oc_b7c2/tmp/runs_last.pkl B7C2 + tmp/runs_S5.pkl B7C2_S5 (uncapped product)",
            "g2k20c2_base_src": "research/tournament/oc_c2frontier/tmp/runs_G2K20_C2_base.pkl",
            "new_src": "tmp/runs_G2K20_S5.pkl, runs_G2K20_C2_S5.pkl, runs_G2K20_B7_base.pkl, runs_G2K20_B7_S5.pkl, runs_G2K20_B7C2_base.pkl, runs_G2K20_B7C2_S5.pkl (this study, kd=2.0, G=2.0)",
            "s5_note": "Bybit live from 2021-11-15; y2021 SHORT, labelled; REF_S5 identical across K2/C2 files",
            "carry_src": "research/tournament/oc_cashcarry/results.json (33 entered frozen; fees spot 0.001/side + fut 0.00055/0.0002)",
            "grid": [str(grid[0]), str(grid[-1])],
            "metric": "hourly-grid year_pass (== reset_metric to the digit on reused rows) + v421 continuous full-path DD; f=0 reproduces frozen tables; f=0.25 == oc_c2carry method",
            "assumption": "ONE account: A(t)=A(t-1)*(1+r_bot(t))+dU(t) with r_bot from the stored 4-phase mix of THAT BOT leg (UTA); carry notional N=f x A at each entry; carry marks causal hourly closes (lower bound); spanning carry rebased to 0 at each reset; carry leg venue-independent",
            "sizing": "f x account equity A at each entry (compounds intra-year); year resets to 1.0; every BOT row has G=2.0 gross cap",
            "bootstrap": "stationary Politis-Romano, mean block 10 d, 4000 paths x 365 d, seed 0, circular; daily close E + daily marked low M (00:00 UTC causal ffill); Binance 2021-09-24..2026-09-23, Bybit 2021-11-15..2026-09-23; carry close-marked so DD is a lower bound",
            "labels": "C2 dev nearly clean (Chronos-Bolt 2024-11, UPPER BOUND small caveat); B7 contaminated (idea post-dates delay replica incl. post-release year; ~70% extra exposure per oc_cboostctrl); post-release year 2025-09-24..2026-09-23 is a LABELLED DIAGNOSTIC for every row containing C2 or B7; S5 y2021 SHORT; carry post-hoc",
            "costs": "maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0 (inside engine); carry fees frozen",
            "selection": "robust pick on dev4 ON BYBIT WITH CARRY f=0.25 among full-path DD<=20 and no losing dev year: prefer mean>=5, then highest WORST, ties->mean; Y4 never used",
        },
        "rows": rows,
    }
    (TMP / "levfrontier_table.json").write_text(json.dumps(out, indent=1))
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/levfrontier_table.json + results.json", flush=True)


if __name__ == "__main__":
    main()
