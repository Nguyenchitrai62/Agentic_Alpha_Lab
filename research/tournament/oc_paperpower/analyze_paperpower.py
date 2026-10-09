"""oc_paperpower: how much paper evidence do the go-live gates need?

Assignment: docs/opencode/OPENCODE_W_oc_paperpower.md. Pre-registered in PLAN.md.
Read-only inputs, no engine reruns, one process, 4h+1h data only (no 1m).

Research return process: G2 + carry hourly equity (4-phase), built EXACTLY as
research/tournament/oc_carrycompound/analyze_carrycompound.py (f = 0.25) ->
daily returns over 2021-09-24 .. 2026-09-23. Stationary block bootstrap
(fixed 10-day blocks exactly as scripts/prospective_scorecard.py, 5000 paths,
seed 0) under S_good / S_half / S_zero / S_neg; horizons 56/84/182/364 days.
PASS = (cumret >= p20 of S_good at same horizon) AND (maxDD <= 15%);
STOP = (maxDD > 20%) OR (cumret < p5). Sensitivity: 30-day blocks.

  python research/tournament/oc_paperpower/analyze_paperpower.py
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

COINS = ["BTC", "ETH"]
F_TARGET = 0.25
FEE_ENTRY_PAID = 0.001 + 0.00055
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)

# Pre-registered power settings
HORIZONS = {"8w": 56, "12w": 84, "26w": 182, "52w": 364}
BLOCK_MAIN = 10
BLOCK_SENS = 30
N_PATHS = 5000
SEED = 0
DAYS_PER_MONTH = 30.4167
D0 = pd.Timestamp("2021-09-24", tz="UTC")
D1 = pd.Timestamp("2026-09-23", tz="UTC")


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


def build_hourly_equity():
    """Rebuild the oc_carrycompound continuous full-path equities bit-exact.

    Returns dict with grid, Etot/Mtot (f=0 base mix) and A_c/M_c for f=0.25,
    plus the per-year reset rows for f=0 and f=0.25 (for validation/report).
    """
    v388 = _load("v388_for_paperpower", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)

    runs = pickle.loads(V421.read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    strat = "R2B1D17BFG2"

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

    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][strat], GRID0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)

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

    # per-year reset pass (validation + context table), f in {0, 0.25}
    rows: dict[float, dict] = {}
    for f in (0.0, F_TARGET):
        years = []
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
        R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years])
                         ** (1 / 5) - 1) * 100, 3)
        rows[f] = {"years": years, "R": R5,
                   "W": min(yy["R"] for yy in years),
                   "DD": max(yy["DD"] for yy in years),
                   "losing": sum(yy["R"] < 0 for yy in years)}

    # continuous full-path pass (v421 convention)
    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)
    full: dict[float, dict] = {}
    A_by_f: dict[float, np.ndarray] = {}
    M_by_f: dict[float, np.ndarray] = {}
    for f in (0.0, F_TARGET):
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
        A_by_f[f], M_by_f[f] = A_c, M_c
        segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
        esf, msf = A_c[segf], M_c[segf]
        dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
        dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
        full[f] = {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}

    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    got = rows[0.0]
    assert [yy["R"] for yy in got["years"]] == [r for r, _ in exp["years"]], got
    assert [yy["DD"] for yy in got["years"]] == [d for _, d in exp["years"]], got
    assert got["R"] == exp["R"] and got["W"] == exp["W"]
    assert got["DD"] == exp["DD"], (got, exp)
    assert full[0.0]["full"] == exp["full_path_dd"], full[0.0]
    print("f=0 validation OK: reproduces v421_result G2 to the digit")
    return {"grid": grid, "A": A_by_f[F_TARGET], "M": M_by_f[F_TARGET],
            "rows": rows, "full": full, "ANCH": ANCH}


def to_daily(grid, A_c):
    """Causal daily-last equity over [2021-09-24, 2026-09-23].

    Grid starts 2021-09-24 04:00 UTC so the 2021-09-24 00:00 mark has no
    prior point: seed E[2021-09-24] with the first hourly value A_c[0]
    (same-day 04:00 close), ffill afterwards. Returns 1825 daily returns
    (2021-09-25..2026-09-23).
    """
    s = pd.Series(np.asarray(A_c, dtype=float), index=pd.DatetimeIndex(grid))
    days = pd.date_range(D0, D1, freq="1D", tz="UTC")
    assert len(days) == 1826, len(days)
    E = s.reindex(days, method="ffill")
    E.iloc[0] = float(np.asarray(A_c, dtype=float)[0])
    assert E.notna().all(), "daily ffill hit NaN"
    E = E.to_numpy(dtype=float)
    r = E[1:] / E[:-1] - 1.0
    assert len(r) == 1825, len(r)
    assert np.all(np.isfinite(r)), "non-finite daily return"
    return days, E, r


def simulate(daily: np.ndarray, horizon: int, block: int, n_paths: int,
             seed: int, rng=None):
    """Fixed-block bootstrap paths (prospective_scorecard convention).

    Returns (C, DD): cumulative return and daily-close maxDD per path.
    Non-circular starts uniform in [0, N-block), concatenated, truncated.
    """
    rng = np.random.default_rng(seed) if rng is None else rng
    N = len(daily)
    assert 1 <= block <= N and horizon >= 1
    nblocks = int((horizon + block - 1) // block)
    starts = rng.integers(0, N - block, size=(n_paths, nblocks))
    offs = np.arange(block)[None, None, :]
    idx = (starts[:, :, None] + offs).reshape(n_paths, nblocks * block)[:, :horizon]
    R = daily[idx]
    P = np.cumprod(1.0 + R, axis=1)
    C = P[:, -1] - 1.0
    full = np.concatenate([np.ones((n_paths, 1)), P], axis=1)
    peak = np.maximum.accumulate(full, axis=1)[:, 1:]
    DD = np.max(1.0 - P / peak, axis=1)
    return C, DD


def run_power(r: np.ndarray):
    mu = float(np.mean(r))
    mu_neg = float((1 - 0.01) ** (1 / DAYS_PER_MONTH) - 1)
    scen = {
        "S_good": r,
        "S_half": r - mu / 2.0,
        "S_zero": r - mu,
        "S_neg": r - mu + mu_neg,
    }
    out: dict[str, dict] = {}
    for bkey, block in (("block10", BLOCK_MAIN), ("block30", BLOCK_SENS)):
        btab: dict[str, dict] = {}
        for hkey, H in HORIZONS.items():
            # reference thresholds from S_good with a dedicated stream
            Cg, DDg = simulate(scen["S_good"], H, block, N_PATHS, SEED)
            p20 = float(np.quantile(Cg, 0.20))
            p5 = float(np.quantile(Cg, 0.05))
            rows = {}
            for skey, vec in scen.items():
                if skey == "S_good":
                    C, DD = Cg, DDg
                else:
                    C, DD = simulate(vec, H, block, N_PATHS, SEED)
                passed = (C >= p20) & (DD <= 0.15)
                stopped = (DD > 0.20) | (C < p5)
                rows[skey] = {
                    "pass_rate": round(float(passed.mean()), 4),
                    "stop_rate": round(float(stopped.mean()), 4),
                    "median_cumret_pct": round(100 * float(np.median(C)), 3),
                    "median_dd_pct": round(100 * float(np.median(DD)), 3),
                }
            btab[hkey] = {"days": H, "p20_cumret_pct": round(100 * p20, 3),
                          "p5_cumret_pct": round(100 * p5, 3), "rows": rows}
        out[bkey] = btab
    return out, {"mu_daily": mu, "mu_neg_daily": mu_neg,
                 "vol_daily": float(np.std(r, ddof=1)),
                 "min_daily": float(np.min(r)), "max_daily": float(np.max(r))}


def main() -> None:
    eq = build_hourly_equity()
    days, E, r = to_daily(eq["grid"], eq["A"])
    tab, dstat = run_power(r)
    g0, g1 = eq["rows"][0.0], eq["rows"][F_TARGET]
    add = round(g1["R"] - g0["R"], 3)

    rec = None
    for hkey in ("8w", "12w", "26w", "52w"):
        if tab["block10"][hkey]["rows"]["S_zero"]["pass_rate"] <= 0.20:
            rec = hkey
            break
    out = {
        "meta": {
            "research_process": "G2 (R2B1D17BFG2 4-phase) + carry f=0.25 continuous "
                                "full-path close equity, built exactly as "
                                "oc_carrycompound/analyze_carrycompound.py",
            "daily": "causal daily-last over 2021-09-24..2026-09-23 (1825 returns); "
                     "descriptive, no selection",
            "bootstrap": f"fixed {BLOCK_MAIN}-day blocks (sensitivity {BLOCK_SENS}d), "
                         f"{N_PATHS} paths/scenario/horizon, seed {SEED}; "
                         "starts uniform [0,N-block) non-circular, "
                         "prospective_scorecard convention",
            "horizons_days": dict(HORIZONS),
            "gates": "PASS=(cumret>=p20 of S_good same horizon) AND (maxDD<=15%); "
                     "STOP=(maxDD>20%) OR (cumret<p5). Divergence/cycle_error not simulated.",
            "dd_note": "daily-close DD only (lower bound vs official 1m-marked DD)",
            "caveat": "bootstrap preserves <=" + str(BLOCK_MAIN) +
                      "-day dependence only; ignores annual regime persistence "
                      f"(sensitivity {BLOCK_SENS}d included)",
            "g2_validation": "f=0 reproduces v421_result R2B1D17BFG2 to the digit",
        },
        "g2_baseline": {"R": g0["R"], "W": g0["W"], "DD": g0["DD"],
                        "full_path_dd": eq["full"][0.0],
                        "years": g0["years"]},
        "g2_carry_f025": {"R": g1["R"], "W": g1["W"], "DD": g1["DD"],
                          "full_path_dd": eq["full"][F_TARGET],
                          "years": g1["years"],
                          "carry_add_pp_per_month": add},
        "daily_stats": {**dstat,
                        "n": len(r),
                        "start": str(days[0].date()),
                        "end": str(days[-1].date())},
        "power": tab,
        "recommendation": {
            "rule": "shortest horizon with S_zero PASS <= 20% (block10)",
            "horizon": rec,
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: {h: {s: v["pass_rate"]
                              for s, v in tab["block10"][h]["rows"].items()}
                          for h in HORIZONS} for k in ("block10",)}, indent=1))
    print("S_zero PASS<=20% first at:", rec)
    print("wrote", HERE / "results.json")


if __name__ == "__main__":
    main()
