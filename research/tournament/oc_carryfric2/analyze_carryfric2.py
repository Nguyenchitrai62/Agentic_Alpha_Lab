"""oc_carryfric2: friction table with the ACCOUNT-REALISTIC (compounding) carry overlay.

Assignment: docs/opencode/OPENCODE_W_oc_carryfric2.md. Read-only inputs,
no engine reruns, one process, 4h+1h data only (no 1m).

Question: recompute the friction table for G2 (R2B1D17BFG2) and D13BF
(v424 R2B1D13BF) with the oc_carrycompound method at f in {0, 0.25}
(S1 carry fees stressed as in oc_carryfric): per scenario 5y mean,
worst year, max yearly DD, full-path DD; reproduce f = 0 exactly.
Plain answers: under which frictions does G2 + carry keep >= 5.0 %/mo,
and does D13BF + carry keep DD < 15 under any friction.

Method (ACCOUNT-REALISTIC, same assumption as oc_carrycompound):
  One account with equity A(t) = BOT capital + carry pair value. The BOT is
  assumed to size on TOTAL equity in a UTA, so the BOT's hourly RETURN
  r_bot(t) = es_base(t)/es_base(t-1) - 1 (from the stored 4-phase mix,
  as a rate) applies to the WHOLE account equity A(t-1) -- NOT to the BOT
  leg alone. Plus the carry pair's hourly MtM change on its notional:
    A(t) = A(t-1)*(1+r_bot(t)) + dU(t),
    dU(t) = sum_k N_k * (mtm_k(t) - mtm_k(t-1)),
  where each entered pair's notional N_k = f x A at its entry hour (last
  hourly close before the entry-close; spanning positions at a reset use
  f x 1.0), held to delivery, mtm per alloc from oc_cashcarry (entry-paid
  fee 0.001+0.00055 while open, frozen ret_alloc net of 0.00275 from
  settlement; S1 stressed as in oc_carryfric: entry-paid 0.0015+0.0012,
  realized ret_alloc - 0.00165, drag 0.0044; all 33 pairs stay net
  positive, min checked in-script). Hourly S/F marks causal:
  last CLOSED hourly bar strictly before t; 0 before entry-close. Marked-for-DD path:
    M(t) = A(t-1)*(ms_base(t)/es_base(t-1)) + dU(t)
  (carry leg close-marked, labelled lower bound; at f=0 M == base ms
  exactly). Per anchor year the account resets to 1.0 (same reset metric
  as research/diagnostics/r2_decompose5/reset_metric.py year_reset);
  spanning carry is rebased to 0 at each anchor (fresh user buys at market).
  Full-path DD uses the continuous account from the grid start with the
  v421 formula (max of marked/close DD), so f=0 reproduces the stored
  reference rows exactly. f=0 short-circuits to the base paths bit-exact
  (no cumprod drift).

  python research/tournament/oc_carryfric2/analyze_carryfric2.py
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
V421A = RD / "v421_audit"
D13R = ROOT / "research/diagnostics/oc_d13robust"
V421_RES = RD / "v421/v421_result.json"
V424_RES = RD / "v424/v424_result.json"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

ROWS = ("G2", "D13BF")
SCENS = ("base", "S1", "S2", "S3", "S4", "S5")
F_ROWS = [0.0, 0.25]
COINS = ["BTC", "ETH"]
FEE_ENTRY_PAID = 0.001 + 0.00055
FEE_FULL_DRAG = 0.00275
# S1 carry stress (labelled, exactly as oc_carryfric): spot 0.0015/side,
# fut taker 0.0012 at entry, delivery 0.0002 unchanged.
S1_ENTRY_PAID = 0.0015 + 0.0012
S1_EXTRA_DRAG = (2 * 0.0015 + 0.0012 + 0.0002) - FEE_FULL_DRAG
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


def main() -> None:
    v388 = _load("v388_for_fric2",
                 RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)

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

    stressed_ret = [tr["ret_alloc"] - S1_EXTRA_DRAG for tr in trades]
    min_stressed = min(stressed_ret)
    assert min_stressed > 0, min_stressed

    def build_mtm(fee_entry_paid: float, ret_of) -> tuple[list[np.ndarray], np.ndarray]:
        """Per-trade hourly mtm (alloc units) on the grid + value at each anchor."""
        mtms = []
        for tr, r in zip(trades, ret_of):
            st, sc = spot[tr["coin"]]
            ft, fc = qmap[(tr["coin"], tr["delivery"])]
            S = last_close_before(st, sc, gn)
            F = last_close_before(ft, fc, gn)
            with np.errstate(divide="ignore", invalid="ignore"):
                mtm = ((S / tr["S_entry"] - 1.0)
                       + ((tr["F_entry"] - F) / tr["F_entry"]) - fee_entry_paid)
            mtm[~np.isfinite(mtm)] = np.nan
            mtm = pd.Series(mtm, index=grid).ffill().to_numpy()
            v = np.zeros(n)
            open_m = gn > tr["tc_ns"]
            settled_m = gn >= tr["ts_ns"]
            hold_m = open_m & ~settled_m
            v[hold_m] = mtm[hold_m]
            v[hold_m & ~np.isfinite(mtm)] = 0.0
            v[settled_m] = r
            mtms.append(v)

        def mtm_at_anchor(tr_idx: int, a_ns: int, ret: float) -> float:
            tr = trades[tr_idx]
            if a_ns <= tr["tc_ns"]:
                return 0.0
            if a_ns >= tr["ts_ns"]:
                return float(ret)
            st, sc = spot[tr["coin"]]
            ft, fc = qmap[(tr["coin"], tr["delivery"])]
            qa = np.array([a_ns])
            S = last_close_before(st, sc, qa)[0]
            F = last_close_before(ft, fc, qa)[0]
            if np.isfinite(S) and np.isfinite(F) and tr["F_entry"] and tr["S_entry"]:
                return float((S / tr["S_entry"] - 1.0)
                             + ((tr["F_entry"] - F) / tr["F_entry"])
                             - fee_entry_paid)
            return 0.0

        a_ns_all = np.array([a.value for a in ANCH])
        anchor_mtm = np.array([[mtm_at_anchor(k, a, ret_of[k])
                                for k in range(len(trades))]
                               for a in a_ns_all])
        return mtms, anchor_mtm

    mtm_base, anch_base = build_mtm(FEE_ENTRY_PAID,
                                    [tr["ret_alloc"] for tr in trades])
    mtm_s1, anch_s1 = build_mtm(S1_ENTRY_PAID, stressed_ret)

    # ---- stored friction runs (no engine reruns) ----
    base_eq: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for row in ROWS:
        for scen in SCENS:
            if row == "G2":
                d = pickle.loads((V421A / f"runs_G2_{scen}.pkl").read_bytes())
            else:
                d = pickle.loads((D13R / f"runs_D13BF_{scen}.pkl").read_bytes())
            assert set(d) == {0, 1, 2, 3}, (row, scen)
            Es, Ms = [], []
            for s in range(4):
                e1, m1 = v388.hourly(d[s], GRID0, g1)
                assert (e1.index == grid).all()
                Es.append(e1.to_numpy(dtype=float))
                Ms.append(m1.to_numpy(dtype=float))
            base_eq[f"{row}/{scen}"] = (np.stack(Es), np.stack(Ms))

    # ---- reference aggregates for the f=0 exact check ----
    rob_g2 = json.loads((V421A / "robust.json").read_text())
    rob_d13 = json.loads((D13R / "results.json").read_text())

    def ref_of(row: str, scen: str):
        if row == "G2":
            src = rob_g2["baseline"]["G2"] if scen == "base" else rob_g2["configs"][scen]
            return ([(y["R"], y["DD"]) for y in src["years"]],
                    src["mean5y"], src["maxDD"], src["fullDD"])
        src = rob_d13["baseline"] if scen == "base" else rob_d13["configs"][scen]
        return ([(y["R"], y["DD"]) for y in src["years"]],
                src["mean5y"], src["maxDD"], src["fullDD"])

    combos = []
    for row in ROWS:
        for scen in SCENS:
            Es, Ms = base_eq[f"{row}/{scen}"]
            stressed = scen == "S1"
            mtms = mtm_s1 if stressed else mtm_base
            anch_mtm = anch_s1 if stressed else anch_base
            Etot = Es.mean(axis=0)
            Mtot = Ms.mean(axis=0)
            # continuous full-path pass inputs (shared across f):
            # carry value at the grid start (rebased to 0 there).
            fee_here = S1_ENTRY_PAID if stressed else FEE_ENTRY_PAID
            ret_here = stressed_ret if stressed else [t["ret_alloc"] for t in trades]
            g0_list = []
            qa0 = np.array([gn[0]])
            for tr, r in zip(trades, ret_here):
                if qa0[0] <= tr["tc_ns"]:
                    g0_list.append(0.0)
                elif qa0[0] >= tr["ts_ns"]:
                    g0_list.append(float(r))
                else:
                    st0, sc0 = spot[tr["coin"]]
                    ft0, fc0 = qmap[(tr["coin"], tr["delivery"])]
                    s0 = last_close_before(st0, sc0, qa0)[0]
                    f0 = last_close_before(ft0, fc0, qa0)[0]
                    if np.isfinite(s0) and np.isfinite(f0):
                        g0_list.append(float((s0 / tr["S_entry"] - 1.0)
                                             + ((tr["F_entry"] - f0) / tr["F_entry"])
                                             - fee_here))
                    else:
                        g0_list.append(0.0)
            g0_mtm = np.array(g0_list)
            for f in F_ROWS:
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
                        mtm_a = anch_mtm[y]
                        rel = [k for k, tr in enumerate(trades)
                               if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
                        span = {k for k in rel if trades[k]["tc_ns"] <= a0.value}
                        mtm_seg = {k: mtms[k][idx] - mtm_a[k] for k in rel}
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
                        U_open: dict[int, float] = {k: f * 1.0 for k in span}
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
                W = min(yy["R"] for yy in years)
                DDmax = max(yy["DD"] for yy in years)
                # continuous full-path pass (v421 convention)
                if f == 0.0:
                    A_c, M_c = Etot.copy(), Mtot.copy()
                else:
                    A_c = np.empty(n)
                    M_c = np.empty(n)
                    rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
                    span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
                    N_c: dict[int, float] = {k: f * float(Etot[0]) for k in span_c}
                    mtm_r = {k: mtms[k] - g0_mtm[k] for k in rel_c}
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
                full = {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}
                combos.append({"row": row, "scen": scen, "f": f, "years": years,
                               "R_5y": R5, "W": W, "DD_maxyearly": DDmax,
                               "full_path_dd": full,
                               "losing_years": sum(yy["R"] < 0 for yy in years),
                               "dd_lt_15": bool(DDmax < 15.0),
                               "r_ge_5": bool(R5 >= 5.0)})

    # ---- validation: f=0 must reproduce the stored reference rows exactly ----
    for c in combos:
        if c["f"] != 0.0:
            continue
        ry, rmean, rdd, rfull = ref_of(c["row"], c["scen"])
        assert [yy["R"] for yy in c["years"]] == [r for r, _ in ry], c
        assert [yy["DD"] for yy in c["years"]] == [d for _, d in ry], c
        assert c["R_5y"] == rmean and c["W"] == min(r for r, _ in ry), c
        assert c["DD_maxyearly"] == rdd, (c, rdd)
        assert c["full_path_dd"]["full"] == rfull, (c, rfull)
    # headline cross-checks against the official result files
    exp_g2 = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    g0 = next(c for c in combos if (c["row"], c["scen"], c["f"]) == ("G2", "base", 0.0))
    assert g0["R_5y"] == exp_g2["R"] and g0["W"] == exp_g2["W"]
    assert g0["DD_maxyearly"] == exp_g2["DD"]
    assert g0["full_path_dd"]["full"] == exp_g2["full_path_dd"]
    exp_d13 = json.loads(V424_RES.read_text())["rows"]["R2B1D13BF"]
    d0 = next(c for c in combos if (c["row"], c["scen"], c["f"]) == ("D13BF", "base", 0.0))
    assert d0["R_5y"] == exp_d13["R"] and d0["W"] == exp_d13["W"]
    assert d0["DD_maxyearly"] == exp_d13["DD"]
    assert d0["full_path_dd"]["full"] == exp_d13["full_path_dd"]
    print("f=0 validation OK: all 12 base rows reproduce stored references to the digit")

    out = {
        "meta": {
            "rows": list(ROWS), "scens": list(SCENS), "f_rows": list(F_ROWS),
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421_audit/runs_G2_{base,S1..S5}.pkl",
            "d13bf_src": "research/diagnostics/oc_d13robust/runs_D13BF_{base,S1..S5}.pkl",
            "carry_src": "research/tournament/oc_cashcarry/results.json (33 entered frozen; fees spot 0.001/side + fut 0.00055/0.0002)",
            "grid": [str(grid[0]), str(grid[-1])],
            "metric": "reset_metric.year_reset per anchor year (fresh 1.0) + v421 continuous full-path DD; f=0 reproduces stored references to the digit",
            "assumption": ("ONE account (method reused UNCHANGED from oc_carrycompound): "
                           "A(t)=A(t-1)*(1+r_bot(t))+dU(t) with r_bot from the stored "
                           "4-phase mix (UTA: BOT sizes on TOTAL equity A(t-1)); carry notional N=f x A "
                           "at each entry, held to delivery; carry marks causal hourly closes (lower bound, "
                           "no intra-hour low); spanning carry rebased to 0 at each reset; "
                           "S1 carry fees stressed as in oc_carryfric (spot 0.0015/side + fut 0.0012 entry, "
                           "delivery 0.0002 unchanged, drag 0.0044)"),
            "sizing": "f x account equity A at each entry (compounds intra-year); year resets to 1.0",
            "friction_defs": ("exactly as oc_d13robust/ROBUST.md: S1 cost stress MAKER 0.0004/TAKER 0.0012, "
                              "S2 latency 15/16, S3 latency 30/31, S4 stop slip 50%, S5 Bybit prices from 2021-11-15"),
            "post_hoc": True,
            "reporting_only": True,
            "data_cap": "2026-09-24T00:00:00Z",
        },
        "combos": combos,
        "checks": {
            "s1_min_stressed_ret_alloc": round(float(min_stressed), 6),
            "carry_fee_entry_paid_base": float(FEE_ENTRY_PAID),
            "carry_fee_entry_paid_S1": float(S1_ENTRY_PAID),
            "carry_extra_drag_S1": float(S1_EXTRA_DRAG),
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for c in combos:
        print(f"{c['row']} {c['scen']} f={c['f']}: R5={c['R_5y']} W={c['W']} "
              f"DDmax={c['DD_maxyearly']} fullDD={c['full_path_dd']['full']} "
              f"losing={c['losing_years']}")


if __name__ == "__main__":
    main()
