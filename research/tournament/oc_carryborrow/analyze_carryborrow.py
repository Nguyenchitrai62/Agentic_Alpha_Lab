"""oc_carryborrow: is f=0.5 worth it once the USDT borrow cost is charged?

Assignment: docs/opencode/OPENCODE_W_oc_carryborrow.md. Read-only inputs,
no engine reruns, one process, 4h+1h data only (no 1m), small RAM
(hourly grid ~44k rows). LIGHT, post-hoc labelled (all years seen).

Exactly two variants, fixed now:
  f = 0.25 (no borrow, = oc_carrycompound bit-exact)
  f = 0.5  where the spot notional above 0.25 x equity is borrowed at a
           constant APR (main 10 %/yr; stress row 15 %/yr), interest
           charged hourly on borrowed notional while held.
G2 base (v421/v422 runs) only, plus the S1 cost-friction row
(BOT S1 + carry fees stressed exactly as in oc_carryfric2).

Method (account-realistic compounding, reused UNCHANGED from
oc_carrycompound/analyze_carrycompound.py and oc_carryfric2):
  One account A(t) = A(t-1)*(1+r_bot(t)) + dU(t) - borrow(t), where r_bot
  is the stored 4-phase G2 hourly return applied to the WHOLE equity
  A(t-1) (UTA: BOT sizes on total equity, carry included); dU is the
  frozen oc_cashcarry pair MtM change on notional N_k = f x A at each
  entry, held to delivery (fees spot 0.001/side + fut 0.00055/0.0002;
  S1 stressed spot 0.0015/side + fut taker 0.0012 entry, delivery
  0.0002 unchanged, drag 0.0044 vs 0.00275); marks causal hourly:
  last CLOSED hourly bar strictly before t (0 before entry-close; locked to
  frozen ret_alloc from settlement-close; carry leg close-marked, DD
  lower bound). Borrow: per pair B_k = max(0, N_k - 0.25 x A_entry)
  = 0.25 x A_entry for f=0.5 (0 for f=0.25); spanning positions at a
  reset use 0.25 x 1.0; hourly interest B_k * APR/8760 charged for each
  hourly step while held (grid time strictly after entry-close and
  strictly before settlement bar). Marked-for-DD path:
  M(t) = A(t-1)*(ms_base(t)/es_base(t-1)) + dU(t) - borrow(t).
  Per-year reset to 1.0 with spanning carry rebased to 0 at each anchor;
  full-path DD continuous from grid start with the v421 formula.
  f=0.25 short-circuits the borrow leg so it reproduces oc_carrycompound
  bit-exact (asserted in-script, also in tests).

  python research/tournament/oc_carryborrow/analyze_carryborrow.py
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
V422 = RD / "v422/v422_runs.pkl"
V421A = RD / "v421_audit"
V421_RES = RD / "v421/v421_result.json"
CCMP = ROOT / "research/tournament/oc_carrycompound/results.json"
CFR2 = ROOT / "research/tournament/oc_carryfric2/results.json"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

COINS = ["BTC", "ETH"]
F_ROWS = [0.25, 0.5]
APR_MAIN = 0.10
APR_STRESS = 0.15
HRS_YR = 365.0 * 24.0
FEE_ENTRY_PAID = 0.001 + 0.00055
S1_ENTRY_PAID = 0.0015 + 0.0012
S1_EXTRA_DRAG = (2 * 0.0015 + 0.0012 + 0.0002) - 0.00275
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
    v388 = _load("v388_for_borrow", RD / "v388/v388_bot_stop_distance.py")
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
    assert min(stressed_ret) > 0, min(stressed_ret)

    def build_mtm(fee_entry_paid: float, ret_of) -> tuple[list[np.ndarray], np.ndarray]:
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

    # ---- stored G2 runs: v421/v422 twins + audit base/S1 (no engine reruns) ----
    r21 = pickle.loads(V421.read_bytes())
    r22 = pickle.loads(V422.read_bytes())
    assert set(r21) == {0, 1, 2, 3} and set(r22) == {0, 1, 2, 3}
    d_base = pickle.loads((V421A / "runs_G2_base.pkl").read_bytes())
    d_s1 = pickle.loads((V421A / "runs_G2_S1.pkl").read_bytes())
    assert set(d_base) == {0, 1, 2, 3} and set(d_s1) == {0, 1, 2, 3}
    base_eq = {}
    for s in range(4):
        e1, m1 = v388.hourly(r21[s]["R2B1D17BFG2"], GRID0, g1)
        e2, m2 = v388.hourly(r22[s]["R2B1D17BFG2"], GRID0, g1)
        e3, m3 = v388.hourly(d_base[s], GRID0, g1)
        assert (e1.index == grid).all()
        assert bool((e1.values == e2.values).all()), f"v421/v422 twin differ s={s}"
        assert bool((e1.values == e3.values).all()), f"v421/audit base differ s={s}"
        assert bool((m1.values == m3.values).all()), f"v421/audit marks differ s={s}"
    print("v421/v422/audit-base twin check OK")
    Es_base, Ms_base, Es_s1, Ms_s1 = [], [], [], []
    for s in range(4):
        e1, m1 = v388.hourly(d_base[s], GRID0, g1)
        Es_base.append(e1.to_numpy(dtype=float))
        Ms_base.append(m1.to_numpy(dtype=float))
        e2, m2 = v388.hourly(d_s1[s], GRID0, g1)
        Es_s1.append(e2.to_numpy(dtype=float))
        Ms_s1.append(m2.to_numpy(dtype=float))
    base_eq["base"] = (np.stack(Es_base), np.stack(Ms_base))
    base_eq["S1"] = (np.stack(Es_s1), np.stack(Ms_s1))

    def run_year(Es, Ms, mtms, anch_mtm, f: float, apr: float | None):
        years = []
        borrow_paid_year = []
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
            es_prev = np.concatenate([[1.0], es[:-1]])
            g = es / es_prev
            hh = ms / es_prev
            mtm_a = anch_mtm[y]
            rel = [k for k, tr in enumerate(trades)
                   if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
            span = {k for k in rel if trades[k]["tc_ns"] <= a0.value}
            mtm_seg = {k: mtms[k][idx] - mtm_a[k] for k in rel}
            tc_map: dict[int, list[int]] = {}
            for k in rel:
                if k in span:
                    continue
                pos = int(np.searchsorted(gn[idx], trades[k]["tc_ns"], side="right"))
                if 0 <= pos < len(idx):
                    tc_map.setdefault(pos, []).append(k)
            U_open: dict[int, float] = {k: f * 1.0 for k in span}
            B_open: dict[int, float] = {}
            if apr is not None:
                B_open = {k: 0.25 * 1.0 for k in span}
            hr = (apr / HRS_YR) if apr is not None else 0.0
            gi = gn[idx]
            A_prev, U_prev = 1.0, 0.0
            A_arr = np.empty(len(idx))
            M_arr = np.empty(len(idx))
            cum_b = 0.0
            for i in range(len(idx)):
                for k in tc_map.get(i, []):
                    U_open[k] = f * A_prev
                    if apr is not None:
                        B_open[k] = 0.25 * A_prev
                U_i = 0.0
                for k, nk in U_open.items():
                    U_i += nk * mtm_seg[k][i]
                dU = U_i - U_prev
                bstep = 0.0
                if apr is not None:
                    tnow = gi[i]
                    for k, bk in B_open.items():
                        if tnow > trades[k]["tc_ns"] and tnow < trades[k]["ts_ns"]:
                            bstep += bk * hr
                A_i = A_prev * g[i] + dU - bstep
                M_i = A_prev * hh[i] + dU - bstep
                A_arr[i] = A_i
                M_arr[i] = M_i
                A_prev, U_prev = A_i, U_i
                cum_b += bstep
            pk = np.maximum.accumulate(A_arr)
            R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
            DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
            years.append({"anchor": str(a0.date()), "R": R, "DD": DD,
                          "end": round(float(A_arr[-1]), 6)})
            borrow_paid_year.append(round(float(cum_b), 6))
        R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years])
                         ** (1 / 5) - 1) * 100, 3)
        return (years, R5, min(yy["R"] for yy in years),
                max(yy["DD"] for yy in years),
                sum(yy["R"] < 0 for yy in years), borrow_paid_year)

    def run_full(Es, Ms, mtms, g0_mtm, f: float, apr: float | None):
        Etot = Es.mean(axis=0)
        Mtot = Ms.mean(axis=0)
        A_c = np.empty(n)
        M_c = np.empty(n)
        rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
        span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
        N_c: dict[int, float] = {k: f * float(Etot[0]) for k in span_c}
        B_c: dict[int, float] = {}
        if apr is not None:
            B_c = {k: 0.25 * float(Etot[0]) for k in span_c}
        hr = (apr / HRS_YR) if apr is not None else 0.0
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
        B_open_c: dict[int, float] = dict(B_c)
        cum_b = 0.0
        for i in range(1, n):
            for k in tc_pos.get(i, []):
                U_open_c[k] = f * A_prev
                if apr is not None:
                    B_open_c[k] = 0.25 * A_prev
            U_i = 0.0
            for k, nk in U_open_c.items():
                U_i += nk * mtm_r[k][i]
            dU = U_i - U_prev
            bstep = 0.0
            if apr is not None:
                tnow = gn[i]
                for k, bk in B_open_c.items():
                    if tnow > trades[k]["tc_ns"] and tnow < trades[k]["ts_ns"]:
                        bstep += bk * hr
            g = Etot[i] / Etot[i - 1]
            hh = Mtot[i] / Etot[i - 1]
            A_c[i] = A_prev * g + dU - bstep
            M_c[i] = A_prev * hh + dU - bstep
            A_prev, U_prev = A_c[i], U_i
            cum_b += bstep
        segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
        esf, msf = A_c[segf], M_c[segf]
        dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
        dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
        return {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}, round(float(cum_b), 6)

    def g0_of(mtms_kind: str, fee_here: float, ret_here) -> np.ndarray:
        qa0 = np.array([gn[0]])
        out = []
        for tr, r in zip(trades, ret_here):
            if qa0[0] <= tr["tc_ns"]:
                out.append(0.0)
            elif qa0[0] >= tr["ts_ns"]:
                out.append(float(r))
            else:
                st0, sc0 = spot[tr["coin"]]
                ft0, fc0 = qmap[(tr["coin"], tr["delivery"])]
                s0 = last_close_before(st0, sc0, qa0)[0]
                f0 = last_close_before(ft0, fc0, qa0)[0]
                if np.isfinite(s0) and np.isfinite(f0):
                    out.append(float((s0 / tr["S_entry"] - 1.0)
                                     + ((tr["F_entry"] - f0) / tr["F_entry"])
                                     - fee_here))
                else:
                    out.append(0.0)
        return np.array(out)

    ret_base = [t["ret_alloc"] for t in trades]
    g0_base = g0_of("base", FEE_ENTRY_PAID, ret_base)
    g0_s1 = g0_of("s1", S1_ENTRY_PAID, stressed_ret)

    combos = []
    for scen in ("base", "S1"):
        Es, Ms = base_eq[scen]
        mtms = mtm_s1 if scen == "S1" else mtm_base
        anch_mtm = anch_s1 if scen == "S1" else anch_base
        g0 = g0_s1 if scen == "S1" else g0_base
        for f in F_ROWS:
            aprs: list[float | None] = [None] if f == 0.25 else [APR_MAIN, APR_STRESS]
            for apr in aprs:
                years, R5, W, DDmax, losing, bpaid = run_year(Es, Ms, mtms, anch_mtm, f, apr)
                full, bfull = run_full(Es, Ms, mtms, g0, f, apr)
                label = f"f={f}" + ("" if apr is None else f"_apr{int(apr*100)}")
                combos.append({"scen": scen, "f": f,
                               "borrow_apr": apr, "label": label,
                               "years": years, "R_5y": R5, "W": W,
                               "DD_maxyearly": DDmax, "full_path_dd": full,
                               "losing_years": losing,
                               "borrow_paid_year_acct": bpaid,
                               "borrow_paid_full_acct": bfull})

    # ---- validation: f=0.25 must reproduce oc_carrycompound exactly ----
    cmp_rows = json.loads(CCMP.read_text())["rows"]
    ref25 = cmp_rows["G2_f0.25"]
    got25 = next(c for c in combos if c["scen"] == "base" and c["f"] == 0.25)
    assert [yy["R"] for yy in got25["years"]] == [yy["R"] for yy in ref25["years"]], got25
    assert [yy["DD"] for yy in got25["years"]] == [yy["DD"] for yy in ref25["years"]], got25
    assert got25["R_5y"] == ref25["R"] and got25["W"] == ref25["W"], (got25, ref25)
    assert got25["DD_maxyearly"] == ref25["DD"], (got25, ref25)
    assert got25["full_path_dd"]["full"] == ref25["full_path_dd"]["full"], got25
    exp_g2 = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    assert got25["full_path_dd"]["full"] is not None
    print("f=0.25 validation OK: reproduces oc_carrycompound to the digit")

    # ---- validation: S1 f=0.25 must reproduce oc_carryfric2 G2/S1/f=0.25 ----
    fr2 = json.loads(CFR2.read_text())["combos"]
    ref_s1 = next(c for c in fr2 if (c["row"], c["scen"], c["f"]) == ("G2", "S1", 0.25))
    got_s1 = next(c for c in combos if c["scen"] == "S1" and c["f"] == 0.25)
    assert [yy["R"] for yy in got_s1["years"]] == [yy["R"] for yy in ref_s1["years"]], got_s1
    assert [yy["DD"] for yy in got_s1["years"]] == [yy["DD"] for yy in ref_s1["years"]], got_s1
    assert got_s1["R_5y"] == ref_s1["R_5y"] and got_s1["W"] == ref_s1["W"]
    assert got_s1["DD_maxyearly"] == ref_s1["DD_maxyearly"]
    assert got_s1["full_path_dd"]["full"] == ref_s1["full_path_dd"]["full"]
    print("S1 f=0.25 validation OK: reproduces oc_carryfric2 G2/S1/0.25 to the digit")

    def gain(v, ref):
        return round(v - ref, 3)

    table = {}
    for c in combos:
        ref = got25 if c["scen"] == "base" else got_s1
        table[c["label"] + "/" + c["scen"]] = {
            "R_5y": c["R_5y"], "W": c["W"], "DDmax": c["DD_maxyearly"],
            "full": c["full_path_dd"]["full"], "losing": c["losing_years"],
            "gain_vs_f025_pp": gain(c["R_5y"], ref["R_5y"]),
        }

    out = {
        "meta": {
            "variants": ["f=0.25 (no borrow, = oc_carrycompound)", "f=0.5 (extra 0.25 spot borrowed)"],
            "borrow": ("extra spot notional above 0.25x equity borrowed at constant APR "
                       "(main 10 %/yr; stress 15 %/yr), hourly rate APR/8760 on borrowed "
                       "notional while held (grid time strictly after entry-close, strictly "
                       "before settlement)"),
            "scens": ["base (v421/v422 G2 runs; twins asserted equal; base carry fees)",
                      "S1 (v421_audit G2 S1 BOT + S1 carry fees stressed as in oc_carryfric2)"],
            "g2_src": ("research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl + "
                       "v422/v422_runs.pkl (twins) + v421_audit/runs_G2_{base,S1}.pkl strat R2B1D17BFG2"),
            "carry_src": "research/tournament/oc_cashcarry/results.json (33 entered frozen; fees spot 0.001/side + fut 0.00055/0.0002; S1 drag 0.0044)",
            "grid": [str(grid[0]), str(grid[-1])],
            "metric": "reset_metric.year_reset per anchor year (fresh 1.0) + v421 continuous full-path DD; f=0.25 reproduces oc_carrycompound to the digit",
            "assumption": ("ONE account (method reused UNCHANGED from oc_carrycompound): "
                           "A(t)=A(t-1)*(1+r_bot(t))+dU(t)-borrow(t) with r_bot from the stored "
                           "4-phase G2 mix (UTA: BOT sizes on TOTAL/WHOLE equity A(t-1)); carry notional N=f x A "
                           "at each entry, held to delivery; borrowed B=0.25 x A at each entry for f=0.5; "
                           "carry marks causal hourly closes (lower bound, no intra-hour low); "
                           "spanning carry rebased to 0 at each reset"),
            "sizing": "f x account equity A at each entry (compounds intra-year); year resets to 1.0",
            "post_hoc": True,
            "reporting_only": True,
            "data_cap": "2026-09-24T00:00:00Z",
        },
        "combos": combos,
        "gain_table": table,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for c in combos:
        print(f"{c['scen']} {c['label']}: R5={c['R_5y']} W={c['W']} "
              f"DDmax={c['DD_maxyearly']} fullDD={c['full_path_dd']['full']} "
              f"losing={c['losing_years']} borrow_full={c['borrow_paid_full_acct']}")


if __name__ == "__main__":
    main()
