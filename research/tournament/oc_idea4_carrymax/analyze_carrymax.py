"""oc_idea4_carrymax: max-basis single-coin carry (IDEAS_20261007 section 4).

Frozen pre-reg (see REPORT.md section 0, written BEFORE this script ran):
  M1 max-coin only: per delivery keep only the higher entry ann_basis coin.
  M2 M1 + 4.5% re-entry floor (drop chosen trades with basis < 4.5%).
f = 0.25 of LIVE account equity at each entry, hold to delivery.

Method REUSED UNCHANGED from the audited oc_carrycompound block:
compounding account A(t) = A(t-1)*(1+r_bot(t)) + dU(t), r_bot from the
stored 4-phase G2 mix (UTA: BOT sizes on TOTAL equity), carry notional
N = f x A at each entry, causal hourly marks (last CLOSED hourly bar
strictly before t), per-year reset to 1.0 (reset_metric.year_reset
convention), spanning rebased at each anchor, v421 continuous full-path DD.
f = 0 short-circuits to base bit-exact. No fitting, no engine rerun,
4h+1h data only, one process, small RAM.

Selection: dev anchors 2021-2024 ONLY (robust criterion); the most recent
year (anchor 2025-09-24) is scored ONCE, for the chosen variant only.

  python research/tournament/oc_idea4_carrymax/analyze_carrymax.py
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
F = 0.25
FEE_ENTRY_PAID = 0.001 + 0.00055
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
DEV_YEARS = (0, 1, 2, 3)  # anchors 2021-2024; anchor 4 (2025) scored once
RECENT = 4


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


def build() -> dict:
    """Load frozen inputs and build causal per-trade mtm + base paths."""
    v388 = _load("v388_for_carrymax",
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

    # ---- frozen M1/M2 subsets on ENTRY-bar basis only (causal) ----
    by_del: dict[str, list[int]] = {}
    for k, t in enumerate(cc["trades"]):
        by_del.setdefault(t["delivery"], []).append(k)
    for d, ks in by_del.items():
        assert len(ks) <= 2, d
        if len(ks) == 2:
            b = [cc["trades"][k]["ann_basis"] for k in ks]
            assert abs(b[0] - b[1]) > 1e-12, f"tie at {d}"
    m1 = sorted(
        max(ks, key=lambda k: (cc["trades"][k]["ann_basis"],
                               cc["trades"][k]["coin"] == "BTC"))
        for ks in by_del.values()
    )
    assert len(m1) == len(by_del) == 18
    m2 = sorted(k for k in m1 if cc["trades"][k]["ann_basis"] >= 0.045 - 1e-12)
    assert len(m2) == 16, len(m2)
    assert set(m2) < set(m1)

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
                       "ann_basis": float(t["ann_basis"]),
                       "F_entry": float(t["F_entry"]),
                       "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "entry_ts": te,
                       "tc_ns": tc.value, "ts_ns": ts.value})

    Es, Ms = [], []
    for s in range(4):
        e1, m1e = v388.hourly(runs[s][strat], GRID0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1e.to_numpy(dtype=float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)

    for tr in trades:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        S = last_close_before(st, sc, gn)
        Fp = last_close_before(ft, fc, gn)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = ((S / tr["S_entry"] - 1.0)
                   + ((tr["F_entry"] - Fp) / tr["F_entry"]) - FEE_ENTRY_PAID)
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
        Fp = last_close_before(ft, fc, qa)[0]
        if np.isfinite(S) and np.isfinite(Fp) and tr["F_entry"] and tr["S_entry"]:
            return float((S / tr["S_entry"] - 1.0)
                         + ((tr["F_entry"] - Fp) / tr["F_entry"])
                         - FEE_ENTRY_PAID)
        return 0.0

    return {"ANCH": ANCH, "grid": grid, "gn": gn, "Es": Es, "Ms": Ms,
            "trades": trades, "mtm_at_anchor": mtm_at_anchor,
            "m1": m1, "m2": m2, "cc": cc}


def year_pass(B: dict, keep: list[int], years: tuple[int, ...],
              f: float) -> list[dict]:
    """Per-year reset pass (reset_metric.year_reset convention)."""
    ANCH, grid, gn = B["ANCH"], B["grid"], B["gn"]
    Es, Ms = B["Es"], B["Ms"]
    trades = B["trades"]
    out = []
    for y in years:
        a0 = ANCH[y]
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
            a_ns_all = np.array([a.value for a in ANCH])
            _ = a_ns_all
            mtm_a = {k: B["mtm_at_anchor"](trades[k], a0.value) for k in keep}
            rel = [k for k in keep
                   if trades[k]["tc_ns"] < a1.value
                   and trades[k]["ts_ns"] > a0.value]
            span = {k for k in rel if trades[k]["tc_ns"] <= a0.value}
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
        out.append({"anchor": str(ANCH[y].date()), "R": R, "DD": DD,
                    "end": round(float(A_arr[-1]), 6)})
    return out


def full_pass(B: dict, keep: list[int], f: float) -> dict:
    """Continuous full-path pass (v421 convention)."""
    grid, gn = B["grid"], B["gn"]
    Es, Ms = B["Es"], B["Ms"]
    trades = B["trades"]
    n = len(grid)
    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)
    if f == 0.0:
        A_c, M_c = Etot.copy(), Mtot.copy()
    else:
        A_c = np.empty(n)
        M_c = np.empty(n)
        g0_mtm = {k: B["mtm_at_anchor"](trades[k], gn[0]) for k in keep}
        rel_c = [k for k in keep if trades[k]["ts_ns"] > gn[0]]
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
    return {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}


def summ(years: list[dict]) -> dict:
    R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years])
                     ** (1 / len(years)) - 1) * 100, 3)
    return {"R": R5, "W": min(yy["R"] for yy in years),
            "DD": max(yy["DD"] for yy in years),
            "losing": sum(yy["R"] < 0 for yy in years)}


def main() -> None:
    B = build()
    ANCH = B["ANCH"]
    trades = B["trades"]
    m1, m2 = B["m1"], B["m2"]
    full33 = list(range(len(trades)))

    # ---- validation gate: f=0 -> v421 G2 to the digit ----
    y0 = year_pass(B, full33, tuple(range(5)), 0.0)
    f0 = dict(summ(y0), years=y0, full_path_dd=full_pass(B, full33, 0.0))
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    assert [yy["R"] for yy in y0] == [r for r, _ in exp["years"]], y0
    assert [yy["DD"] for yy in y0] == [d for _, d in exp["years"]], y0
    assert f0["R"] == exp["R"] and f0["W"] == exp["W"]
    assert f0["DD"] == exp["DD"], (f0, exp)
    assert f0["full_path_dd"]["full"] == exp["full_path_dd"], f0
    print("f=0 validation OK: reproduces v421_result G2 to the digit")

    # ---- validation gate 2: FULL33 f=0.25 -> oc_carrycompound to digit ----
    y33 = year_pass(B, full33, tuple(range(5)), F)
    c33 = dict(summ(y33), years=y33, full_path_dd=full_pass(B, full33, F))
    ref = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json")
                     .read_text())["rows"]["G2_f0.25"]
    assert c33["R"] == ref["R"] and c33["W"] == ref["W"]
    assert c33["DD"] == ref["DD"], (c33, ref)
    assert [yy["R"] for yy in y33] == [yy["R"] for yy in ref["years"]]
    assert [yy["DD"] for yy in y33] == [yy["DD"] for yy in ref["years"]]
    assert c33["full_path_dd"] == ref["full_path_dd"], c33
    print("FULL33 validation OK: reproduces oc_carrycompound "
          f"{ref['R']}/{ref['W']}/{ref['DD']}/full {ref['full_path_dd']['full']}")

    # ---- dev pass: anchors 2021-2024 ONLY for M1 vs M2 ----
    dev1 = year_pass(B, m1, DEV_YEARS, F)
    dev2 = year_pass(B, m2, DEV_YEARS, F)
    s1, s2 = summ(dev1), summ(dev2)

    def ok(s: dict) -> bool:
        return s["DD"] <= 20 and s["losing"] == 0

    def key(s: dict) -> tuple:
        return (ok(s), s["R"] >= 5, s["W"], s["R"])

    winner = "M1" if key(s1) >= key(s2) else "M2"
    print(f"dev M1: {s1} | dev M2: {s2} -> winner: {winner}")

    # ---- most recent year ONCE, winner only (POST-HOC) ----
    wkeep = m1 if winner == "M1" else m2
    yrecent = year_pass(B, wkeep, (RECENT,), F)[0]
    wyears = (dev1 if winner == "M1" else dev2) + [dict(
        yrecent, anchor=str(ANCH[RECENT].date()), post_hoc=True)]
    wfull = full_pass(B, wkeep, F)
    for yy in wyears[:4]:
        yy["post_hoc"] = False
    wsum = dict(summ(wyears), years=wyears, full_path_dd=wfull)

    # ---- UTA / concurrency bound (analytic, entry-equity units) ----
    conc: dict[str, dict] = {}
    for tag, keep in (("M1", m1), ("M2", m2)):
        ev: list[tuple[int, int]] = []
        for k in keep:
            ev.append((trades[k]["tc_ns"], 1))
            ev.append((trades[k]["ts_ns"], -1))
        ev.sort()
        cur = peak = 0
        for _, d in ev:
            cur += d
            peak = max(peak, cur)
        conc[tag] = {"n_trades_total": len(keep),
                     "peak_concurrent_pairs": peak,
                     "peak_spot_cash_x_equity_at_f025": round(0.25 * peak, 2),
                     "peak_carry_gross_x_equity_at_f025": round(0.50 * peak, 2)}

    out = {
        "meta": {
            "idea": "IDEAS_20261007 section 4: max-basis single-coin carry",
            "pre_reg": ("M1 max-coin only at f=0.25; M2 M1 with 4.5% "
                        "re-entry floor at f=0.25; no other variants"),
            "m1_trades": [(trades[k]["coin"], trades[k]["delivery"],
                           trades[k]["ann_basis"]) for k in m1],
            "m2_trades": [(trades[k]["coin"], trades[k]["delivery"],
                           trades[k]["ann_basis"]) for k in m2],
            "dropped_vs_baseline": sorted(
                (trades[k]["coin"], trades[k]["delivery"])
                for k in full33 if k not in m1),
            "m2_floor_drops": sorted(
                (trades[k]["coin"], trades[k]["delivery"])
                for k in m1 if k not in m2),
            "g2_src": ("research/parallel/rounds/parallel-20260906-r2/v421/"
                       "v421_runs.pkl strat R2B1D17BFG2"),
            "carry_src": ("research/tournament/oc_cashcarry/results.json "
                          "(33 entered frozen; fees spot 0.001/side + fut "
                          "0.00055/0.0002)"),
            "metric": ("reset_metric.year_reset per anchor year (fresh 1.0) + "
                       "v421 continuous full-path DD"),
            "gate_costs": ("maker 0.0002, taker 0.00055; delivery quarterlies "
                           "pay NO funding; 0.00275/alloc fee drag inside "
                           "ret_alloc; BOT leg costs from stored engine path"),
            "selection": ("dev anchors 2021-2024 only, robust criterion "
                          "(DD<=20, no losing dev year, prefer dev4 mean>=5, "
                          "then highest dev4 WORST year); 2025 scored once "
                          "for the winner only, labelled POST-HOC"),
            "sizing": "f=0.25 x live account equity A at each entry",
        },
        "baseline_G2_f0": f0,
        "baseline_FULL33_f025": c33,
        "dev_M1_f025": dict(s1, years=dev1),
        "dev_M2_f025": dict(s2, years=dev2),
        "choice": {"winner": winner,
                   "dev_M1": s1, "dev_M2": s2,
                   "reason": ("robust criterion on dev 2021-2024: "
                              f"M1 {s1} vs M2 {s2}")},
        f"chosen_{winner}_f025": wsum,
        "concurrency": conc,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"chosen {winner}: 5y {wsum['R']}/{wsum['W']}/{wsum['DD']} "
          f"full {wfull} (2025 POST-HOC {yrecent})")
    print(f"concurrency: {conc}")


if __name__ == "__main__":
    main()
