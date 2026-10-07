"""oc_carrycompound: ACCOUNT-REALISTIC carry overlay (compounding inside the BOT).

Assignment: docs/opencode/OPENCODE_W_oc_carrycompound.md. Read-only inputs,
no engine reruns, one process, 4h+1h data only (no 1m), small RAM
(hourly grid ~44k rows).

Question: two existing overlays disagree -- oc_carrycombo (G2+carry f=0.25:
5.413 %/mo; carry P&L accumulated as absolute cash next to the BOT's own
equity path, so it does NOT compound inside the BOT) and oc_carryfric /
oc_carryd13 (5.533; carry sized at f x year-start equity, added per year).
Which lift is real for one account?

Method (ACCOUNT-REALISTIC, stated assumption):
  One account with equity A(t) = BOT capital + carry pair value. The BOT is
  assumed to size on TOTAL equity in a UTA, so the BOT's hourly RETURN
  r_bot(t) = es_base(t)/es_base(t-1) - 1 (from the stored 4-phase G2 equity,
  as a rate) applies to the WHOLE account equity A(t-1) -- NOT to the BOT
  leg alone. Plus the carry pair's hourly MtM change on its notional:
    A(t) = A(t-1)*(1+r_bot(t)) + dU(t),
    dU(t) = sum_k N_k * (mtm_k(t) - mtm_k(t-1)),
  where each entered pair's notional N_k = f x A at its entry hour (last
  hourly close before the entry-close; spanning positions at a reset use
  f x 1.0), held to delivery, mtm per alloc from oc_cashcarry (entry-paid
  fee 0.001+0.00055 while open, frozen ret_alloc net of 0.00275 from
  settlement; hourly S/F marks causal: last CLOSED hourly bar strictly
  before t; 0 before entry-close). Marked-for-DD path:
    M(t) = A(t-1)*(ms_base(t)/es_base(t-1)) + dU(t)
  (carry leg close-marked, labelled lower bound; at f=0 M == base ms
  exactly). Per anchor year the account resets to 1.0 (same reset metric
  as research/diagnostics/r2_decompose5/reset_metric.py year_reset);
  spanning carry is rebased to 0 at each anchor (fresh user buys at market).
  Full-path DD uses the continuous account from the grid start with the
  v421 formula (max of marked/close DD), so f=0 reproduces v421_result G2
  exactly. f=0 short-circuits to the base paths bit-exact (no cumprod drift).

  python research/tournament/oc_carrycompound/analyze_carrycompound.py
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
F_ROWS = [0.0, 0.25]
FEE_ENTRY_PAID = 0.001 + 0.00055
FEE_FULL_DRAG = 0.00275
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
    v388 = _load("v388_for_compound",
                 RD / "v388/v388_bot_stop_distance.py")
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

    # ---- base per-phase hourly equities on the grid ----
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][strat], GRID0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)

    # ---- per-trade hourly mtm (alloc units) on the grid ----
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

    # ---- per-year reset pass with compounding ----
    rows: dict[float, dict] = {}
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
                mtm_a = anchor_mtm[y]
                # relevant trades overlapping this year
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

    # ---- continuous full-path pass (v421 convention) ----
    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)
    full: dict[float, dict] = {}
    for f in F_ROWS:
        if f == 0.0:
            A_c, M_c = Etot.copy(), Mtot.copy()
        else:
            A_c = np.empty(n)
            M_c = np.empty(n)
            g0_mtm = np.array([mtm_at_anchor(tr, gn[0]) for tr in trades])
            rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
            span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
            # fixed grid-start notionals for spanning
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
            # U at i=0 is 0 by rebase; dU from 0
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
        full[f] = {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}

    # ---- validation: f=0 must reproduce v421_result G2 exactly ----
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    got = rows[0.0]
    assert [yy["R"] for yy in got["years"]] == [r for r, _ in exp["years"]], got
    assert [yy["DD"] for yy in got["years"]] == [d for _, d in exp["years"]], got
    assert got["R"] == exp["R"] and got["W"] == exp["W"]
    assert got["DD"] == exp["DD"], (got, exp)
    assert full[0.0]["full"] == exp["full_path_dd"], full[0.0]
    print("f=0 validation OK: reproduces v421_result G2 to the digit")

    add = round(rows[0.25]["R"] - rows[0.0]["R"], 3)
    out = {
        "meta": {
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
            "carry_src": "research/tournament/oc_cashcarry/results.json (33 entered frozen; fees spot 0.001/side + fut 0.00055/0.0002)",
            "grid": [str(grid[0]), str(grid[-1])],
            "metric": "reset_metric.year_reset per anchor year (fresh 1.0) + v421 continuous full-path DD; f=0 reproduces v421_result to the digit",
            "assumption": ("ONE account: A(t)=A(t-1)*(1+r_bot(t))+dU(t) with r_bot from the stored "
                           "4-phase G2 mix (UTA: BOT sizes on TOTAL equity A(t-1)); carry notional N=f x A "
                           "at each entry, held to delivery; carry marks causal hourly closes (lower bound, "
                           "no intra-hour low); spanning carry rebased to 0 at each reset"),
            "sizing": "f x account equity A at each entry (compounds intra-year); year resets to 1.0",
            "f_rows": list(F_ROWS),
        },
        "rows": {
            f"G2_f{f}": dict(rows[f], full_path_dd=full[f]) for f in F_ROWS
        },
        "carry_add_pp_per_month": add,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for f in F_ROWS:
        print(f"G2_f{f}:", rows[f], full[f])
    print(f"carry add at f=0.25: {add:+.3f} pp/mo")


if __name__ == "__main__":
    main()
