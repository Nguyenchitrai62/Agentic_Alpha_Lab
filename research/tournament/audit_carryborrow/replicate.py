"""Blind audit replication for oc_carryborrow f=0.5 + borrow.

Independent re-implementation from the header spec in
research/tournament/oc_carryborrow/analyze_carryborrow.py (spec only, no
REPORT/results read) + method reused from oc_carrycompound (allowed overlay).

Spec:
  ONE account A(t)=A(t-1)*(1+r_bot(t))+dU(t)-borrow(t), r_bot from stored
  4-phase G2 hourly returns applied to WHOLE equity; dU = frozen oc_cashcarry
  pair MtM change on notional N_k = f x A at each entry, held to delivery;
  fees base spot 0.001/side + fut 0.00055 entry / 0.0002 delivery (drag
  0.00275); S1 stressed spot 0.0015/side + fut taker 0.0012 entry, delivery
  0.0002 unchanged (drag 0.0044, extra 0.00165); marks causal hourly: last
  CLOSED hourly bar strictly before t (0 before entry-close; locked to frozen
  ret_alloc from settlement-close). Borrow: per pair B_k = max(0, N_k - 0.25 x
  A_entry) = 0.25 x A_entry for f=0.5 (0 for f=0.25); spanning at reset use
  0.25 x 1.0; hourly interest B_k * APR/8760 charged for each hourly step
  while held (grid time strictly after entry-close, strictly before
  settlement). M(t) = A(t-1)*(ms_base/es_base_prev) + dU - borrow.
  Per-year reset to 1.0, spanning rebased to 0; full-path continuous v421.
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
CCMP = ROOT / "research/tournament/oc_carrycompound/results.json"
V421 = RD / "v421/v421_runs.pkl"
V421A = RD / "v421_audit"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

COINS = ["BTC", "ETH"]
APR_MAIN = 0.10
APR_STRESS = 0.15
HRS_YR = 365.0 * 24.0
FEE_BASE = 0.001 + 0.00055
FEE_S1 = 0.0015 + 0.0012
S1_EXTRA = (2 * 0.0015 + 0.0012 + 0.0002) - 0.00275
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_close_before(times_ns: np.ndarray, closes: np.ndarray, ts_ns: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def main() -> None:
    v388 = _load("v388_audit_rep", RD / "v388/v388_bot_stop_distance.py")
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
    assert bool((h["t"] < CAP).all())
    spot = {}
    for coin in COINS:
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (
            d["t"].values.astype("datetime64[ns]").astype(np.int64),
            d["close"].to_numpy(dtype=float),
        )

    qmap = {}
    for t in cc["trades"]:
        key = (t["coin"], t["delivery"])
        if key in qmap:
            continue
        y, m, dd = t["delivery"].split("-")
        code = f"{y[2:]}{m}{dd}"
        (fpath,) = sorted(QDIR.glob(f"um_{t['coin']}USDT_{code}_1h.parquet"))
        q = pd.read_parquet(fpath, columns=["open_time", "close"])
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])

    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet", columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trades = []
    for t in cc["trades"]:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        assert (s4o == te).any(), t
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64), D.value, side="right"))
        assert si < len(s4), t
        ts = s4c.iloc[si]
        assert ts > tc, t
        trades.append({
            "coin": t["coin"], "delivery": t["delivery"],
            "F_entry": float(t["F_entry"]), "S_entry": float(t["S_entry"]),
            "ret_alloc": float(t["ret_alloc"]),
            "tc_ns": tc.value, "ts_ns": ts.value,
        })

    ret_s1 = [tr["ret_alloc"] - S1_EXTRA for tr in trades]
    assert min(ret_s1) > 0

    def build(fee_paid, rets):
        mtms = []
        for tr, r in zip(trades, rets):
            st, sc = spot[tr["coin"]]
            ft, fc = qmap[(tr["coin"], tr["delivery"])]
            S = last_close_before(st, sc, gn)
            F = last_close_before(ft, fc, gn)
            with np.errstate(divide="ignore", invalid="ignore"):
                mtm = (S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"]) - fee_paid
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

        def at_anchor(k, a_ns, ret):
            tr = trades[k]
            if a_ns <= tr["tc_ns"]:
                return 0.0
            if a_ns >= tr["ts_ns"]:
                return float(ret)
            st, sc = spot[tr["coin"]]
            ft, fc = qmap[(tr["coin"], tr["delivery"])]
            qa = np.array([a_ns])
            S = last_close_before(st, sc, qa)[0]
            F = last_close_before(ft, fc, qa)[0]
            if np.isfinite(S) and np.isfinite(F):
                return float((S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"]) - fee_paid)
            return 0.0

        a_all = np.array([a.value for a in ANCH])
        anch = np.array([[at_anchor(k, a, rets[k]) for k in range(len(trades))] for a in a_all])
        return mtms, anch

    ret_base = [t["ret_alloc"] for t in trades]
    mtm_base, anch_base = build(FEE_BASE, ret_base)
    mtm_s1, anch_s1 = build(FEE_S1, ret_s1)

    r21 = pickle.loads(V421.read_bytes())
    assert set(r21) == {0, 1, 2, 3}
    d_s1 = pickle.loads((V421A / "runs_G2_S1.pkl").read_bytes())
    assert set(d_s1) == {0, 1, 2, 3}
    d_base = pickle.loads((V421A / "runs_G2_base.pkl").read_bytes())
    # twin check base == v421 (allowed G2 runs)
    for s in range(4):
        e1, m1 = v388.hourly(r21[s]["R2B1D17BFG2"], GRID0, g1)
        e3, m3 = v388.hourly(d_base[s], GRID0, g1)
        assert (e1.index == grid).all()
        assert bool((e1.values == e3.values).all()), f"base twin differ s={s}"
    print("twin check OK: v421 == audit base")

    Es_base, Ms_base, Es_s1, Ms_s1 = [], [], [], []
    for s in range(4):
        e1, m1 = v388.hourly(d_base[s], GRID0, g1)
        Es_base.append(e1.to_numpy(dtype=float))
        Ms_base.append(m1.to_numpy(dtype=float))
        e2, m2 = v388.hourly(d_s1[s], GRID0, g1)
        Es_s1.append(e2.to_numpy(dtype=float))
        Ms_s1.append(m2.to_numpy(dtype=float))
    Es_base = np.stack(Es_base)
    Ms_base = np.stack(Ms_base)
    Es_s1 = np.stack(Es_s1)
    Ms_s1 = np.stack(Ms_s1)

    def run_year(Es, Ms, mtms, anch_mtm, f, apr):
        years = []
        bpaid = []
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            seg = (grid > a0) & (grid <= a1)
            idx = np.where(np.asarray(seg))[0]
            le = gn <= a0.value
            b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            E4 = [Es[s][idx] / b[s] for s in range(4)]
            M4 = [Ms[s][idx] / b[s] for s in range(4)]
            es = np.mean(E4, axis=0)
            ms = np.mean(M4, axis=0)
            es_prev = np.concatenate([[1.0], es[:-1]])
            g = es / es_prev
            hh = ms / es_prev
            mtm_a = anch_mtm[y]
            rel = [k for k, tr in enumerate(trades) if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
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
            B_open: dict[int, float] = {k: 0.25 * 1.0 for k in span} if apr is not None else {}
            hr = (apr / HRS_YR) if apr is not None else 0.0
            gi = gn[idx]
            A_prev, U_prev = 1.0, 0.0
            A_arr = np.empty(len(idx))
            M_arr = np.empty(len(idx))
            cum = 0.0
            for i in range(len(idx)):
                for k in tc_map.get(i, []):
                    U_open[k] = f * A_prev
                    if apr is not None:
                        B_open[k] = 0.25 * A_prev
                U_i = sum(nk * mtm_seg[k][i] for k, nk in U_open.items())
                dU = U_i - U_prev
                bstep = 0.0
                if apr is not None:
                    tnow = gi[i]
                    for k, bk in B_open.items():
                        if tnow > trades[k]["tc_ns"] and tnow < trades[k]["ts_ns"]:
                            bstep += bk * hr
                A_arr[i] = A_prev * g[i] + dU - bstep
                M_arr[i] = A_prev * hh[i] + dU - bstep
                A_prev, U_prev = A_arr[i], U_i
                cum += bstep
            pk = np.maximum.accumulate(A_arr)
            R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
            DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
            years.append({"anchor": str(a0.date()), "R": R, "DD": DD, "end": round(float(A_arr[-1]), 6)})
            bpaid.append(round(float(cum), 6))
        R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years]) ** (1 / 5) - 1) * 100, 3)
        return years, R5, min(yy["R"] for yy in years), max(yy["DD"] for yy in years), sum(yy["R"] < 0 for yy in years), bpaid

    def run_full(Es, Ms, mtms, g0_mtm, f, apr):
        Etot = Es.mean(axis=0)
        Mtot = Ms.mean(axis=0)
        rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
        span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
        N_c = {k: f * float(Etot[0]) for k in span_c}
        B_c = {k: 0.25 * float(Etot[0]) for k in span_c} if apr is not None else {}
        hr = (apr / HRS_YR) if apr is not None else 0.0
        mtm_r = {k: mtms[k] - g0_mtm[k] for k in rel_c}
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
        A_prev, U_prev = float(Etot[0]), 0.0
        Uo = dict(N_c)
        Bo = dict(B_c)
        for i in range(1, n):
            for k in tc_pos.get(i, []):
                Uo[k] = f * A_prev
                if apr is not None:
                    Bo[k] = 0.25 * A_prev
            U_i = sum(nk * mtm_r[k][i] for k, nk in Uo.items())
            dU = U_i - U_prev
            bstep = 0.0
            if apr is not None:
                tnow = gn[i]
                for k, bk in Bo.items():
                    if tnow > trades[k]["tc_ns"] and tnow < trades[k]["ts_ns"]:
                        bstep += bk * hr
            g = Etot[i] / Etot[i - 1]
            hh = Mtot[i] / Etot[i - 1]
            A_c[i] = A_prev * g + dU - bstep
            M_c[i] = A_prev * hh + dU - bstep
            A_prev, U_prev = A_c[i], U_i
        segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
        esf, msf = A_c[segf], M_c[segf]
        dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
        dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
        return {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}

    def g0_of(fee_here, rets):
        qa0 = np.array([gn[0]])
        out = []
        for tr, r in zip(trades, rets):
            if qa0[0] <= tr["tc_ns"]:
                out.append(0.0)
            elif qa0[0] >= tr["ts_ns"]:
                out.append(float(r))
            else:
                st0, sc0 = spot[tr["coin"]]
                ft0, fc0 = qmap[(tr["coin"], tr["delivery"])]
                s0 = last_close_before(st0, sc0, qa0)[0]
                f0 = last_close_before(ft0, fc0, qa0)[0]
                out.append(float((s0 / tr["S_entry"] - 1.0) + ((tr["F_entry"] - f0) / tr["F_entry"]) - fee_here))
        return np.array(out)

    g0_base = g0_of(FEE_BASE, ret_base)
    g0_s1 = g0_of(FEE_S1, ret_s1)

    combos = []
    for scen, Es, Ms, mtms, anch in (("base", Es_base, Ms_base, mtm_base, anch_base),
                                     ("S1", Es_s1, Ms_s1, mtm_s1, anch_s1)):
        g0 = g0_base if scen == "base" else g0_s1
        for f, apr in ([(0.25, None)] if scen in ("base", "S1") else []) + ([(0.5, APR_MAIN), (0.5, APR_STRESS)] if True else []):
            # compute f=0.25 (validation) + f=0.5 rows
            years, R5, W, DDmax, losing, bpaid = run_year(Es, Ms, mtms, anch, f, apr)
            full = run_full(Es, Ms, mtms, g0, f, apr)
            label = f"f={f}" + ("" if apr is None else f"_apr{int(apr*100)}")
            combos.append({"scen": scen, "f": f, "borrow_apr": apr, "label": label,
                           "years": years, "R_5y": R5, "W": W, "DD_maxyearly": DDmax,
                           "full_path_dd": full, "losing_years": losing,
                           "borrow_paid_year_acct": bpaid})

    # validation: base f=0.25 must reproduce oc_carrycompound to the digit
    cmp_rows = json.loads(CCMP.read_text())["rows"]
    ref25 = cmp_rows["G2_f0.25"]
    got25 = next(c for c in combos if c["scen"] == "base" and c["f"] == 0.25)
    assert [yy["R"] for yy in got25["years"]] == [yy["R"] for yy in ref25["years"]], got25
    assert [yy["DD"] for yy in got25["years"]] == [yy["DD"] for yy in ref25["years"]], got25
    assert got25["R_5y"] == ref25["R"] and got25["W"] == ref25["W"]
    assert got25["DD_maxyearly"] == ref25["DD"]
    assert got25["full_path_dd"]["full"] == ref25["full_path_dd"]["full"]
    print("f=0.25 validation OK vs oc_carrycompound")

    out = {
        "meta": {
            "g2_src": "v421/v421_runs.pkl + v421_audit/runs_G2_{base,S1}.pkl strat R2B1D17BFG2 via v388.hourly",
            "carry_src": "oc_cashcarry/results.json (33 entered)",
            "fees": {"base_entry_paid": FEE_BASE, "s1_entry_paid": FEE_S1, "s1_extra_drag": S1_EXTRA},
            "borrow": "extra 0.25x equity at APR/8760 hourly while held (strictly inside tc..ts)",
            "grid": [str(grid[0]), str(grid[-1])],
        },
        "combos": combos,
    }
    (HERE / "replication.json").write_text(json.dumps(out, indent=1))
    for c in combos:
        print(f"{c['scen']} {c['label']}: R5={c['R_5y']} W={c['W']} DDmax={c['DD_maxyearly']} full={c['full_path_dd']['full']} losing={c['losing_years']}")


if __name__ == "__main__":
    main()
