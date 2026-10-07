"""oc_idea3_carrytier: tiered carry sizing by locked basis (IDEAS_20261007 §3).

Pre-registered variants (frozen in REPORT.md BEFORE this ran; no others):
  T1: per-coin f by locked ann. basis: 4-6% -> 0.125, 6-10% -> 0.25, >10% -> 0.375.
  T2: T1 capped at f=0.25 per coin (oc_utamargin account-check: 0.25 is the
      largest additive f cleared on one UTA; 0.50 blocks + borrows USDT).

Method: verbatim oc_carrycompound accounting (ONE compounding account
A(t)=A(t-1)*(1+r_bot(t))+dU(t), r_bot from stored 4-phase G2 mix, UTA sizes
on TOTAL equity; carry notional N_k=f_k x A at each entry, held to delivery;
causal hourly marks = last CLOSED hourly bar strictly before t, 0 before
entry-close, locked to frozen ret_alloc; spanning carry rebased to 0 at each
anchor; per-year reset to 1.0 = reset_metric.year_reset arithmetic; full-path
DD continuous from grid start, v421 formula max(marked/close)). Frozen
oc_cashcarry trades reused verbatim (signal/fees/deliveries untouched; basis
annualised from <=entry closes only; 2 incomplete contracts excluded, no P&L
imputed). Only the per-trade f_k differs by tier. Fees: spot 0.001/side +
fut 0.00055 entry + 0.0002 delivery (drag 0.00275/alloc; same frozen numbers
as oc_cashcarry; delivery futures pay NO funding so the AGENTS.md perp-funding
gate rule is irrelevant here — stated like oc_cashcarry). Gate BOT costs
(maker 0.02% / taker 0.055%, longs pay 0.01%/8h) apply to the BOOK legs inside
the stored G2 path, untouched.

Selection: compare T1 vs T2 ONLY on dev years 2021-2024 (robust criterion:
DD<=20 and no losing dev year; prefer dev4 mean>=5, then highest dev4 WORST
year; ties -> higher mean). Most recent year 2025-09-24..2026-09-23 scored
ONCE for the chosen variant only. All years POST-HOC (frozen trades already
saw all years). Baseline gate: f=0 must reproduce v421_result G2 (5.41) and
flat f=0.25 must reproduce oc_carrycompound (5.634/DD16.75/full16.66) exactly,
else STOP.

Run: .venv/Scripts/python.exe research/tournament/oc_idea3_carrytier/analyze_carrytier.py
Writes results.json. 4h+1h hourly grid only (~44k rows), no 1m, no engine reruns.
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
CCMP = ROOT / "research/tournament/oc_carrycompound"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

COINS = ["BTC", "ETH"]
FEE_ENTRY_PAID = 0.001 + 0.00055
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)

# Tier buckets (pre-frozen §3): [0.04,0.06)->0.125, (0.06,0.10]->0.25, >0.10->0.375.
# Boundary: b < 0.06 -> 0.125 else b <= 0.10 -> 0.25 else 0.375.


def tier_f(ann_basis: float) -> float:
    if ann_basis < 0.04 - 1e-12:
        return 0.0
    if ann_basis < 0.06:
        return 0.125
    if ann_basis <= 0.10:
        return 0.25
    return 0.375


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


def main() -> None:
    v388 = _load("v388_for_carrytier", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    assert len(ANCH) == 5
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

    ccmp = json.loads((CCMP / "results.json").read_text())

    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all())
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
        fk = tier_f(float(t["ann_basis"]))
        assert fk > 0, t  # all 33 entered trades clear 4%; skipped ones never enter
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "ann_basis": float(t["ann_basis"]),
                       "F_entry": float(t["F_entry"]),
                       "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "f_T1": fk, "f_T2": min(fk, 0.25),
                       "tc_ns": tc.value, "ts_ns": ts.value})

    # tier census (frozen buckets, no fitting)
    census = {}
    for k in ("f_T1", "f_T2"):
        vals = [tr[k] for tr in trades]
        census[k] = {f: vals.count(f) for f in sorted(set(vals))}

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

    def run_year(y: int, fkey):
        """One anchor-year reset pass. fkey: float (flat f) or 'T1'/'T2' tier key."""
        a0 = ANCH[y]
        a1 = a0 + YEAR
        seg = (grid > a0) & (grid <= a1)
        idx = np.where(np.asarray(seg))[0]
        le = gn <= a0.value
        b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
        E4 = [Es[s][idx] / b[s] for s in range(4)]
        M4 = [Ms[s][idx] / b[s] for s in range(4)]
        es = np.mean(E4, axis=0)
        ms = np.mean(M4, axis=0)
        if fkey == 0.0:
            return es, ms
        es_prev = np.concatenate([[1.0], es[:-1]])
        g = es / es_prev
        hh = ms / es_prev
        mtm_a = anchor_mtm[y]
        rel = [k for k, tr in enumerate(trades)
               if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
        span = {k for k in rel if trades[k]["tc_ns"] <= a0.value}
        if isinstance(fkey, float):
            fk = {k: fkey for k in rel}
        else:
            fk = {k: trades[k]["f_" + fkey] for k in rel}
        N = {k: fk[k] * 1.0 for k in span}
        mtm_seg = {k: trades[k]["mtm"][idx] - mtm_a[k] for k in rel}
        A_prev, U_prev = 1.0, 0.0
        A_arr = np.empty(len(idx))
        M_arr = np.empty(len(idx))
        tc_map: dict[int, list[int]] = {}
        for k in rel:
            if k in span:
                continue
            pos = int(np.searchsorted(gn[idx], trades[k]["tc_ns"], side="right"))
            if 0 <= pos < len(idx):
                tc_map.setdefault(pos, []).append(k)
        U_open: dict[int, float] = dict(N)
        for i in range(len(idx)):
            for k in tc_map.get(i, []):
                U_open[k] = fk[k] * A_prev
            U_i = 0.0
            for k, nk in U_open.items():
                U_i += nk * mtm_seg[k][i]
            dU = U_i - U_prev
            A_arr[i] = A_prev * g[i] + dU
            M_arr[i] = A_prev * hh[i] + dU
            A_prev, U_prev = A_arr[i], U_i
        return A_arr, M_arr

    def year_stats(A_arr, M_arr, anchor):
        pk = np.maximum.accumulate(A_arr)
        R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
        DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
        return {"anchor": str(anchor.date()), "R": R, "DD": DD,
                "end": round(float(A_arr[-1]), 6)}

    def summarize(year_list):
        rr = [yy["R"] for yy in year_list]
        R = round(float(np.prod([1 + v / 100 for v in rr]) ** (1 / len(rr)) - 1) * 100, 3)
        return {"R": R, "W": min(rr), "DD": max(yy["DD"] for yy in year_list),
                "losing": sum(v < 0 for v in rr)}

    # ---- PHASE A: baseline reproduction over all 5 years (else STOP) ----
    base = {}
    for f in (0.0, 0.25):
        yl = [year_stats(*run_year(y, f), ANCH[y]) for y in range(5)]
        base[f] = dict(summarize(yl), years=yl)
    exp = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    g0 = base[0.0]
    assert [yy["R"] for yy in g0["years"]] == [r for r, _ in exp["years"]], g0
    assert [yy["DD"] for yy in g0["years"]] == [d for _, d in exp["years"]], g0
    assert g0["R"] == exp["R"] and g0["W"] == exp["W"] and g0["DD"] == exp["DD"]
    print("f=0 reproduces v421_result G2 to the digit: R=5.41 W=2.588 DD=16.91")
    c25 = base[0.25]
    e25 = ccmp["rows"]["G2_f0.25"]
    assert c25["R"] == e25["R"] == 5.634, (c25, e25)
    assert c25["W"] == e25["W"] == 2.778
    assert c25["DD"] == e25["DD"] == 16.75
    assert [yy["R"] for yy in c25["years"]] == [yy["R"] for yy in e25["years"]]
    assert [yy["DD"] for yy in c25["years"]] == [yy["DD"] for yy in e25["years"]]
    print("flat f=0.25 reproduces oc_carrycompound to the digit: 5.634/DD16.75")

    # ---- PHASE B: dev4 (2021-2024) for T1/T2 only; robust selection ----
    dev = {}
    for key in ("T1", "T2"):
        yl = [year_stats(*run_year(y, key), ANCH[y]) for y in range(4)]
        dev[key] = dict(summarize(yl), years=yl)

    def eligible(d):
        return d["DD"] <= 20 and d["losing"] == 0

    e1, e2 = eligible(dev["T1"]), eligible(dev["T2"])
    if e1 and not e2:
        winner = "T1"
    elif e2 and not e1:
        winner = "T2"
    elif e1 and e2:
        m1, m2 = dev["T1"]["R"], dev["T2"]["R"]
        if (m1 >= 5) != (m2 >= 5):
            winner = "T1" if m1 >= 5 else "T2"
        elif dev["T1"]["W"] != dev["T2"]["W"]:
            winner = "T1" if dev["T1"]["W"] > dev["T2"]["W"] else "T2"
        else:
            winner = "T1" if m1 >= m2 else "T2"
    else:
        # neither eligible: pick highest dev4 WORST year (ties -> higher mean), still report
        winner = ("T1" if (dev["T1"]["W"], dev["T1"]["R"])
                  >= (dev["T2"]["W"], dev["T2"]["R"]) else "T2")
    print(f"dev4 T1={dev['T1']} T2={dev['T2']} -> winner={winner} (dev-only)")

    # ---- PHASE C: score 2025 ONCE for the winner only ----
    y4 = year_stats(*run_year(4, winner), ANCH[4])
    wyears = dev[winner]["years"] + [y4]
    wsum = summarize(wyears)

    # ---- continuous full-path pass (v421 convention) for f=0 + winner ----
    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)

    def full_path(fkey):
        if fkey == 0.0:
            A_c, M_c = Etot.copy(), Mtot.copy()
        else:
            A_c = np.empty(n)
            M_c = np.empty(n)
            g0_mtm = np.array([mtm_at_anchor(tr, gn[0]) for tr in trades])
            rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
            span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
            if isinstance(fkey, float):
                fk = {k: fkey for k in rel_c}
                N_c = {k: fkey * float(Etot[0]) for k in span_c}
            else:
                fk = {k: trades[k]["f_" + fkey] for k in rel_c}
                N_c = {k: trades[k]["f_" + fkey] * float(Etot[0]) for k in span_c}
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
                    U_open_c[k] = fk[k] * A_prev
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

    full0 = full_path(0.0)
    assert full0["full"] == exp["full_path_dd"] == 16.82, full0
    full_flat = full_path(0.25)
    assert full_flat["full"] == ccmp["rows"]["G2_f0.25"]["full_path_dd"]["full"] == 16.66
    full_w = full_path(winner)

    # ---- UTA account-check (indexed, oc_utamargin envelope) ----
    # max simultaneous open pairs + max indexed spot cost per variant
    overlap = {}
    for key in ("T1", "T2", "flat0.25"):
        if key == "flat0.25":
            fk = {k: 0.25 for k in range(len(trades))}
        else:
            fk = {k: trades[k]["f_" + key] for k in range(len(trades))}
        # sweep entry/settlement events on hourly grid
        open_f = np.zeros(n)
        for k, tr in enumerate(trades):
            m = (gn >= tr["tc_ns"]) & (gn < tr["ts_ns"])
            open_f[m] += fk[k]
        overlap[key] = {"max_pairs": int(max(
            sum(1 for tr in trades if tr["tc_ns"] <= t < tr["ts_ns"]) for t in gn[::24])),
            "max_indexed_spot_cost": round(float(open_f.max()), 4)}
    out = {
        "meta": {
            "idea": "IDEAS_20261007 §3 tiered carry sizing by locked basis",
            "variants": ["T1", "T2"],
            "tiers": {"[0.04,0.06)": 0.125, "[0.06,0.10]": 0.25, ">0.10": 0.375,
                      "T2_cap": 0.25},
            "tier_census_T1": census["f_T1"],
            "tier_census_T2": census["f_T2"],
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
            "carry_src": "research/tournament/oc_cashcarry/results.json (33 entered frozen; fees spot 0.001/side + fut 0.00055/0.0002; 2 incomplete excluded)",
            "grid": [str(grid[0]), str(grid[-1])],
            "metric": "reset_metric.year_reset per anchor year (fresh 1.0) + v421 continuous full-path DD; f=0 reproduces v421_result to the digit; flat f=0.25 reproduces oc_carrycompound to the digit",
            "assumption": ("ONE account: A(t)=A(t-1)*(1+r_bot(t))+dU(t) with r_bot from the stored "
                           "4-phase G2 mix (UTA: BOT sizes on TOTAL equity A(t-1)); carry notional N_k=f_k x A "
                           "at each entry (f_k tiered per trade), held to delivery; carry marks causal hourly closes (lower bound); "
                           "spanning carry rebased to 0 at each reset"),
            "gate_costs": "BOT legs inside stored G2 path already carry gate costs (maker 0.02% / taker 0.055%, longs pay 0.01%/8h); carry leg frozen fee drag 0.00275/alloc, no perp funding (delivery quarterlies)",
            "selection": "dev years 2021-2024 ONLY, robust criterion (DD<=20 + no losing dev year; prefer dev4 mean>=5 then highest dev4 WORST; ties higher mean); 2025 scored ONCE for winner only; ALL years POST-HOC (frozen trades already saw all years)",
            "winner_dev_only": winner,
            "labels": "all rows POST-HOC where years were already seen",
        },
        "baseline_repro": {
            "G2_f0.0": dict(base[0.0], full_path_dd=full0),
            "G2_flat_f0.25": dict(base[0.25], full_path_dd=full_flat),
        },
        "dev4": {
            "T1": dev["T1"],
            "T2": dev["T2"],
        },
        "year2025_winner_only": {
            "winner": winner,
            winner: y4,
        },
        "winner_full": {
            "variant": winner,
            "years": wyears,
            **wsum,
            "full_path_dd": full_w,
        },
        "account_check": {
            "overlap_indexed": overlap,
            "uta_envelope": "oc_utamargin: f=0.25 additive OK (0 blocked hrs, spot cost peak 95.8% Eq); f=0.50 NOT cleared (1 blocked hr + spot cost 179.9% Eq, must borrow). T2 capped at 0.25 stays inside the cleared envelope; T1 peak indexed cost above must split capital if it exceeds ~1.0.",
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"dev4": dev, "winner": winner, "y2025": y4,
                      "winner_full": {**wsum, "full": full_w}}, indent=1))


if __name__ == "__main__":
    main()
