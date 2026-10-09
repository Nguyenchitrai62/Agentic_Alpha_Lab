"""oc_k2carry: account-realistic profile of G2+carry vs K2+carry (Binance + Bybit S5).

Descriptive only, no selection. CPU-only, hourly grid, no 1m reads, no engine
reruns (all runs cached). Method = verbatim copy of
research/tournament/oc_carrycompound/analyze_carrycompound.py generalized to
4 BOT legs (G2/K2 x Binance/Bybit-S5), each with f=0.0 and f=0.25 compounding
on TOTAL equity, plus a stationary block bootstrap per row (mean block 10 d,
4000 draws, seed 0) like research/tournament/oc_mcdd/mcdd_bootstrap.py.

ONE account: A(t)=A(t-1)*(1+r_bot(t))+dU(t), r_bot from the stored 4-phase mix
of THAT BOT leg (UTA: BOT sizes on TOTAL equity); carry notional N=f x A at
each entry, held to delivery; carry marks causal hourly closes (lower bound).
Per-year reset to 1.0; spanning carry rebased to 0 at each anchor.
Full-path DD continuous from grid start, v421 formula.

Usage: python research/tournament/oc_k2carry/analyze_k2carry.py
Writes results.json in this folder. See PLAN.md (pre-registered).
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
V421_RES = RD / "v421/v421_result.json"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
KH_LAST = ROOT / "research/tournament/oc_kronoshidden/tmp/runs_last.pkl"
K2B_TABLE = ROOT / "research/tournament/oc_k2bybit/tmp/k2bybit_table.json"
S5_PKL = ROOT / "research/tournament/oc_k2bybit/tmp/runs_S5.pkl"

COINS = ["BTC", "ETH"]
F_ROWS = [0.0, 0.25]
FEE_ENTRY_PAID = 0.001 + 0.00055
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
S5_LIVE0 = pd.Timestamp("2021-11-15", tz="UTC")

# bootstrap (per assignment; like oc_mcdd but 10-day blocks, 4000 draws)
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
    """Close of the last bar with bar_time strictly before each query time."""
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


def main() -> None:
    v388 = _load("v388_for_k2carry", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)

    # ---- BOT legs (frozen caches, no reruns) ----
    v421 = pickle.loads(V421.read_bytes())
    kh_last = pickle.loads(KH_LAST.read_bytes())
    s5 = pickle.loads(S5_PKL.read_bytes())
    legs = {
        "G2_bin": {s: v421[s]["R2B1D17BFG2"] for s in range(4)},
        "K2_bin": {s: kh_last[s]["K2"]["run"] for s in range(4)},
        "G2_by": {s: s5[s]["REF"]["run"] for s in range(4)},
        "K2_by": {s: s5[s]["K2"]["run"] for s in range(4)},
    }
    # sanity: K2_bin prefix equals dev cache is checked in tests; S5 live start
    assert len(legs["G2_bin"][0]["eq"]) == n - (len(grid) - 10944), (
        len(legs["G2_bin"][0]["eq"]), n)

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

    rows = {}
    for leg in ("G2_bin", "K2_bin", "G2_by", "K2_by"):
        Es, Ms = base[leg]
        for f in F_ROWS:
            years, R5, _, _ = year_pass(Es, Ms, f)
            A_c, M_c, full = full_pass(Es, Ms, f)
            # daily series for bootstrap (causal 00:00 UTC ffill)
            e_s = pd.Series(A_c, index=grid)
            m_s = pd.Series(M_c, index=grid)
            D0 = S5_LIVE0 if leg.endswith("_by") else pd.Timestamp(
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
            tag = {"G2_bin": "G2", "K2_bin": "K2",
                   "G2_by": "G2", "K2_by": "K2"}[leg]
            venue = "binance" if leg.endswith("_bin") else "bybit_S5"
            key = f"{tag}{'_carry' if f else ''}_{venue}"
            rows[key] = {
                "bot": tag, "venue": venue, "f": f,
                "years": years, "R5y": R5,
                "W5y": min(yy["R"] for yy in years),
                "DDmax": max(yy["DD"] for yy in years),
                "losing": sum(yy["R"] < 0 for yy in years),
                "full_path_dd": full,
                "recent": years[-1],
                "bootstrap": boot,
            }
            print(f"{key}: 5y={R5} W={rows[key]['W5y']} "
                  f"DD={rows[key]['DDmax']} full={full['full']} "
                  f"boot={boot}", flush=True)

    # ---- reproduction gates (STOP if failed) ----
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    g = rows["G2_binance"]
    assert [yy["R"] for yy in g["years"]] == [r for r, _ in exp["years"]], g
    assert [yy["DD"] for yy in g["years"]] == [d for _, d in exp["years"]], g
    assert g["R5y"] == exp["R"] and g["W5y"] == exp["W"]
    assert g["DDmax"] == exp["DD"], (g, exp)
    assert g["full_path_dd"]["full"] == exp["full_path_dd"], g
    gc = rows["G2_carry_binance"]
    assert gc["R5y"] == 5.634, gc
    assert gc["DDmax"] == 16.75, gc
    assert gc["full_path_dd"]["full"] == 16.66, gc
    print("gate G2 + G2+carry (5.634/16.75/16.66) OK", flush=True)

    kh_tab = json.loads(K2B_TABLE.read_text())["table"]
    for leg, kk in (("K2_binance", "K2_base"), ("G2_bybit_S5", "REF_S5"),
                    ("K2_bybit_S5", "K2_S5")):
        er = kh_tab[kk]["years_R"]
        ed = kh_tab[kk]["years_DD"]
        got = rows[leg if leg != "K2_binance" else "K2_binance"]
        assert [yy["R"] for yy in got["years"]] == er, (leg, got)
        assert [yy["DD"] for yy in got["years"]] == ed, (leg, got)
        assert got["full_path_dd"]["full"] == kh_tab[kk]["full_path_dd"], leg
    print("gate K2_bin + S5 REF/K2 OK", flush=True)

    out = {
        "meta": {
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
            "k2_bin_src": "research/tournament/oc_kronoshidden/tmp/runs_last.pkl K2 (prefix == runs_dev.pkl K2)",
            "s5_src": "research/tournament/oc_k2bybit/tmp/runs_S5.pkl REF/K2 (Bybit live from 2021-11-15; y2021 SHORT)",
            "carry_src": "research/tournament/oc_cashcarry/results.json (33 entered frozen; fees spot 0.001/side + fut 0.00055/0.0002)",
            "grid": [str(grid[0]), str(grid[-1])],
            "metric": "reset_metric.year_reset per anchor year (fresh 1.0) + v421 continuous full-path DD; f=0 reproduces v421 / oc_kronoshidden / oc_k2bybit to the digit",
            "assumption": ("ONE account: A(t)=A(t-1)*(1+r_bot(t))+dU(t) with r_bot from the stored "
                           "4-phase mix of THAT BOT leg (UTA: BOT sizes on TOTAL equity A(t-1)); carry notional N=f x A "
                           "at each entry, held to delivery; carry marks causal hourly closes (lower bound); "
                           "spanning carry rebased to 0 at each reset; carry leg venue-independent (same MtM on both venues)"),
            "sizing": "f x account equity A at each entry (compounds intra-year); year resets to 1.0",
            "bootstrap": ("stationary Politis-Romano, mean block 10 d, 4000 paths x 365 d, seed 0, circular; "
                          "daily close E + daily marked low M from the continuous account (00:00 UTC causal ffill); "
                          "Binance universe 2021-09-24..2026-09-23, Bybit universe 2021-11-15..2026-09-23 (live only); "
                          "carry close-marked so DD is a lower bound; assumes ~stationary daily returns"),
            "labels": "recent = anchor 2025-09-24 year (clean BUT already scored once for base K2 -> labelled re-score); S5 y2021 SHORT (Bybit from 2021-11-15)",
            "selection": "NONE (descriptive)",
        },
        "rows": rows,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
