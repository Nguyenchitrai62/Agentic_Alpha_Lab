"""oc_fundclock engine: v421-G2 path with funding-clock flatten (W1/W2).

Mechanism = copy of oc_vpinveto/run_engine.py (= v414 pipe v321, corr-aware inv
sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0,
win_start=5, gate costs inside the engine) plus a per-(T,sym) funding-clock gate:
  W1/W2: book longs x0.5 on gated rows (after bear filter, before ffill, v426 style).
  W1: dip multiplier 0 on holding bars starting at a flagged settlement (covers
      [S,S+30m]; causal post-leg of the +-30min window; exits unchanged).
  W2: dip untouched (tilt 1 everywhere).
Gates from tmp/gates_wide.parquet (causal: premium <= S-1h; norms pre-anchor + 7d).

Variants (ONLY these three, pre-registered): REF, W1, W2.
Stages: --stage dev runs [DEV0, DEV1); --stage last runs [DEV0, Y1) ONCE.

Usage:
  python run_engine.py --stage dev --shifts 0,1,2,3 --rows REF,W1,W2
Run through heavy_slot (one heavy job), nohup + log.
"""
from __future__ import annotations

import argparse
import gc
import importlib.util
import pickle
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
TMP = HERE / "tmp"
CACHE_DEV = TMP / "runs_dev.pkl"
CACHE_LAST = TMP / "runs_last.pkl"

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_gate_std() -> pd.DataFrame:
    """Gate DataFrame on settlement grid (T -> sym bool)."""
    g = pd.read_parquet(TMP / "gates_wide.parquet")
    g.index = pd.to_datetime(g.index, utc=True)
    return g.sort_index()


def run_shift(shift, variants, stage, gate_grid: pd.DataFrame,
              gate_ns: np.ndarray):
    """One phase; returns {variant: {run, wins, mult}} (run in v414 format)."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{stage}_s{shift}"
    pod = pof._load(f"pod_fc_{stage}_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_fc_{stage}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_fc_{stage}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_fc_{stage}_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    last = (stage == "last")
    live0 = DEV0 + sh
    live1 = (Y1 if last else DEV1) + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    std_idx = books154.index if last else books154.index[books154.index <= DEV1 + pd.Timedelta(hours=4)]
    cols = list(books154.columns)
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, std_idx + sh, shift, cols)
    del M
    gc.collect()
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    # exact v421 bear construction
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear_arr_full = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear_arr_full] = sb.loc[bear_arr_full].where(sb.loc[bear_arr_full] <= 0, sb.loc[bear_arr_full] * 0.5)
    # funding-clock gate on the standard grid (causal asof: latest gate T <= book T)
    std_ns = sb.index.values.astype("datetime64[ns]").astype(np.int64)
    pos = np.searchsorted(gate_ns, std_ns, side="right") - 1
    gate_std = pd.DataFrame(False, index=sb.index, columns=sb.columns)
    sval = gate_grid.reindex(columns=gate_std.columns).to_numpy()
    for j, sym in enumerate(gate_std.columns):
        ok = pos >= 0
        gate_std.iloc[:, j] = np.where(ok, sval[np.clip(pos, 0, len(sval) - 1), j], False)
    # rows before 2021-09-24 never gated (frozen)
    gate_std.loc[gate_std.index < pd.Timestamp("2021-09-24", tz="UTC")] = False
    n_gate = int((gate_std & (sb > 0)).to_numpy().sum())
    print(f"{tag}: gated long rows {n_gate}", flush=True)
    sbb = sb.where(~(gate_std & (sb > 0)), sb * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    books_gate = sbb.reindex(idx, method="ffill").fillna(0.0)
    # gate per decision index i (holding-bar open T[i]=idx[i]+4h; W1 dip skips
    # bars STARTING at a flagged settlement: exact causal post-leg)
    T_arr = idx + pd.Timedelta(hours=4)
    T_ns = T_arr.values.astype("datetime64[ns]").astype(np.int64)
    ipos = np.searchsorted(gate_ns, T_ns, side="right") - 1
    # exact-match only for dip (bar starts at S): T_ns == gate time
    # NOTE: sval above is in gate_std (books) column order; use a gate_grid-ordered
    # array here so coin j maps to the right coin (plumbing fix, no mechanism change).
    gsym = list(gate_grid.columns)
    sval_g = gate_grid.to_numpy()
    gate_i = np.zeros((len(idx), len(cols)), dtype=bool)
    for k, c in enumerate(cols):
        if c not in gsym:
            continue
        j = gsym.index(c)
        # exact start match: gate time == T_ns
        gt = gate_ns[np.clip(ipos, 0, len(gate_ns) - 1)]
        exact = (ipos >= 0) & (gt == T_ns) & sval_g[np.clip(ipos, 0, len(sval_g) - 1), j]
        gate_i[:, k] = exact
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"

    out = {}
    for variant in variants:
        t0 = time.time()
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]
        msum = [0.0] * 5
        mcnt = [0] * 5
        gsum = [0] * 5
        anch_ns = np.array([pd.Timestamp(a, tz="UTC").value for a in ANCH5])
        y_of_i = np.clip(np.searchsorted(anch_ns, T_ns, side="right") - 1, 0, 4)

        def tilt(i, a, variant=variant):
            y = int(y_of_i[i])
            if variant == "W1":
                m = 0.0 if bool(gate_i[i, a]) else 1.0
            else:
                m = 1.0
            msum[y] += m
            mcnt[y] += 1
            gsum[y] += int(bool(gate_i[i, a]))
            return m

        def corr_size(i, a, r, f, base_size=base_size):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + n)
            return mult * 1.7 * tilt(i, a) * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7
        kw["sleeve_gross_cap"] = 2.0

        ev = []
        books_in = books_bear if variant == "REF" else books_gate
        eu.simulate(books_in, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        years = []
        for y, a in enumerate(ANCH5):
            if not last and y == 4:
                years.append(dict(nb=0, wb=0, nr=0, wr=0))
                continue
            a0 = pd.Timestamp(a, tz="UTC") + sh
            a1 = min(a0 + pd.Timedelta(days=365), live1)
            evy = [e for e in ev if a0 <= pd.Timestamp(e["t"]) < a1 + pd.Timedelta(hours=8)]
            ts = v216.v213.trade_stats(evy)
            nb, wb = 0, 0
            for _k, v in (ts.items() if isinstance(ts, dict) else []):
                if isinstance(v, dict) and v.get("trades"):
                    nb += int(v["trades"])
                    wb += int(round(float(v.get("win_rate") or 0.0) * int(v["trades"])))
            rr = [float(e["ret"]) for e in evy if e["kind"] in RUNG_KINDS and "ret" in e]
            years.append(dict(nb=nb, wb=wb, nr=len(rr), wr=int(sum(r > 0 for r in rr))))
        mult = {str(y): dict(sized_mean=round(msum[y] / mcnt[y], 6) if mcnt[y] else None,
                             n_sized=int(mcnt[y]),
                             gated_share=round(gsum[y] / mcnt[y], 6) if mcnt[y] else None)
                for y in range(5)}
        out[variant] = dict(run=run, wins=years, mult=mult)
        print(f"{tag} {variant} eq_end={run['eq'][-1]:.4f} "
              f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        del ev
        gc.collect()
    del opens, prep, books
    gc.collect()
    return shift, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "last"], required=True)
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--rows", default="REF,W1,W2")
    args = ap.parse_args()
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    gate_grid = load_gate_std()
    gate_ns = gate_grid.index.values.astype("datetime64[ns]").astype(np.int64)
    order = np.argsort(gate_ns)
    gate_grid = gate_grid.iloc[order]
    gate_ns = gate_ns[order]

    hb = threading.Thread(target=heartbeat, args=(f"run_engine {args.stage} {args.rows}",), daemon=True)
    hb.start()
    cache_path = CACHE_LAST if args.stage == "last" else CACHE_DEV
    allres = {}
    if cache_path.exists():
        allres = pickle.loads(cache_path.read_bytes())
        print("loaded cached runs:", {s: sorted(v) for s, v in allres.items()}, flush=True)
    for shift in shifts:
        need = [v for v in variants if v not in allres.get(shift, {})]
        if not need:
            print(f"shift {shift}: all cached, skip", flush=True)
            continue
        s, res = run_shift(shift, need, args.stage, gate_grid, gate_ns)
        allres.setdefault(s, {}).update(res)
        cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        cur.update(allres)
        cache_path.write_bytes(pickle.dumps(cur))
        print(f"shift {s} cached ({args.stage})", flush=True)
    _stop_hb.set()
    print("STAGE", args.stage, "DONE shifts", sorted(allres), flush=True)


if __name__ == "__main__":
    main()
