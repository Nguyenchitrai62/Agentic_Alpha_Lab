"""oc_booktrim engine: REF vs BT08 (book x0.8) vs BT06 (book x0.6), base + S5.

Mechanism = verbatim copy of oc_c2bybit/compute_c2bybit_engine.py base/S5 paths
(pipe v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
sleeve_gross_cap G=2.0, gate costs inside the engine) with NO tilt; the only
change across variants is trade["book_mult"] (REF omits the key = 1.0).

Stages (selection discipline, see PLAN.md):
  dev:  [DEV0, DEV1) for REF/BT08/BT06 on base+S5 -> robust pick on dev4 base.
  last: [DEV0, Y1) ONCE for the pick + REF on base+S5.
Caches: tmp/runs_dev_<fric>.pkl / tmp/runs_last_<fric>.pkl (resume-safe per
shift). Each entry: {run, wins, decomp}. HEAVY: run through heavy_slot
(sequential shifts, one heavy process).

Usage:
  python compute_booktrim_engine.py --stage dev --fric base --shifts 0,1,2,3 --rows REF,BT08,BT06
  python compute_booktrim_engine.py --stage last --fric base --shifts 0,1,2,3 --rows REF,BT08
"""
from __future__ import annotations

import argparse
import gc
import importlib.util
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
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = [f"{y}-09-24" for y in (2021, 2022, 2023, 2024, 2025)]
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
EXIT_KINDS = set(RUNG_KINDS)
HEARTBEAT_S = 600
BOOK_MULT = {"BT08": 0.8, "BT06": 0.6}  # REF omits the key (= 1.0)
G_CAP = 2.0
NEAR_GAP = 0.5  # near-cap = C_before >= G - 0.5 = 1.5

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive",
              flush=True)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bybit_minutes():
    out = {}
    for s in SYMS:
        m = pd.read_parquet(BYBIT_DIR / (f"{s}_1m.parquet"),
                            columns=["open_time", "open", "high", "low", "close"])
        m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
        out[s] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return out


def pair_rungs(ev):
    """Consecutive (rung_fill, exit) pairs -> arrays (fill_ns, exit_ns, w).

    The engine appends each rung's fill immediately followed by its own exit
    (engine_user.py lines ~808-813), so pairs are consecutive in the list.
    """
    fns, xns, ws = [], [], []
    i, n = 0, len(ev)
    while i < n:
        e = ev[i]
        if e["kind"] == "rung_fill":
            assert i + 1 < n and ev[i + 1]["kind"] in EXIT_KINDS, \
                f"unpaired rung_fill at {e['t']} {e['symbol']}"
            x = ev[i + 1]
            fns.append(pd.Timestamp(e["t"]).value)
            xns.append(pd.Timestamp(x["t"]).value)
            ws.append(float(e["weight"]))
            i += 2
        else:
            i += 1
    return (np.array(fns, dtype=np.int64), np.array(xns, dtype=np.int64),
            np.array(ws, dtype=float))


def cap_sweep(fns, xns, ws, G=G_CAP, near_gap=NEAR_GAP):
    """Per-fill concurrency: C_before, near/over counts, max concurrent."""
    o = np.argsort(fns, kind="stable")
    fns, xns, ws = fns[o], xns[o], ws[o]
    n = len(ws)
    if n == 0:
        return dict(fills_total=0, near=0, over=0, max_concurrent=0.0,
                    c_before=np.zeros(0), order=o)
    # C_before[i] = sum of w[j], j != i, with fill_j <= fill_i < exit_j
    cb = np.zeros(n)
    for i in range(n):
        m = (fns <= fns[i]) & (xns > fns[i])
        m[i] = False
        cb[i] = ws[m].sum()
    near = int(((cb >= G - near_gap)).sum())
    over = int(((cb + ws > G + 1e-9)).sum())
    maxc = float(np.max(cb + ws)) if n else 0.0
    return dict(fills_total=n, near=near, over=over, max_concurrent=maxc,
                c_before=cb, order=o)


def year_of(t_ns, bounds_ns):
    """Anchor-year index for timestamp ns, or None outside [A0, A4+365d+8h)."""
    for y in range(5):
        if bounds_ns[y][0] <= t_ns < bounds_ns[y][1]:
            return y
    return None


def run_shift(shift, variants, stage, fric):
    """One phase; returns {variant: {run, wins, decomp}}."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{stage}_{fric}_s{shift}"
    pod = pof._load(f"pod_bt_{stage}_{fric}_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_bt_{stage}_{fric}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_bt_{stage}_{fric}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_bt_{stage}_{fric}_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    last = (stage == "last")
    s5 = (fric == "S5")
    live0 = (S5_START if s5 else DEV0) + sh
    live1 = (Y1 if last else DEV1) + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    if last:
        std_idx = books154.index[books154.index >= S5_START] + sh if s5 else books154.index + sh
        M = bybit_minutes() if s5 else pod.minutes()
    else:
        base_idx = books154.index[books154.index <= DEV1 + pd.Timedelta(hours=4)]
        if s5:
            base_idx = base_idx[base_idx >= S5_START]
        std_idx = base_idx + sh
        M = bybit_minutes() if s5 else pod.minutes()
    opens, prep = pof.prep_idx(M, std_idx, shift, list(books154.columns))
    del M
    gc.collect()
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"

    # year bounds per shift: [a0, a1 + 8h) with a0 = ANCH[y] + sh
    bounds = []
    for a in ANCH5:
        a0 = pd.Timestamp(a, tz="UTC") + sh
        a1 = min(a0 + pd.Timedelta(days=365), live1)
        bounds.append((a0.value, (a1 + pd.Timedelta(hours=8)).value))

    out = {}
    for variant in variants:
        t0 = time.time()
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        if variant in BOOK_MULT:
            trade["book_mult"] = BOOK_MULT[variant]
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]

        def corr_size(i, a, r, f, base_size=base_size):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + n)
            return mult * 1.7 * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7
        kw["sleeve_gross_cap"] = 2.0

        ev, att = [], []
        eu.simulate(books_bear, opens, prep, trade=trade, events=ev,
                    attrib=att, win_start=5, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        # wins per year (same collection as oc_chronos / oc_c2bybit)
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
        # decomposition: attrib sums + rung intervals per year
        book_y = [0.0] * 5
        dip_y = [0.0] * 5
        for t, bpnl, spnl in att:
            yy = year_of(pd.Timestamp(t).value, bounds)
            if yy is not None:
                book_y[yy] += float(np.asarray(bpnl, dtype=float).sum())
                dip_y[yy] += float(spnl)
        fns, xns, ws = pair_rungs(ev)
        fills_y = [0] * 5
        wsum_y = [0.0] * 5
        near_y = [0] * 5
        over_y = [0] * 5
        maxconc = 0.0
        if len(ws):
            cs = cap_sweep(fns, xns, ws)
            cb = cs["c_before"]
            oo = cs["order"]
            fns_o = fns[oo]
            maxconc = cs["max_concurrent"]
            for k in range(len(ws)):
                yy = year_of(int(fns_o[k]), bounds)
                if yy is None:
                    continue
                fills_y[yy] += 1
                wsum_y[yy] += float(ws[oo[k]])
                if float(cb[k]) >= G_CAP - NEAR_GAP:
                    near_y[yy] += 1
                if float(cb[k]) + float(ws[oo[k]]) > G_CAP + 1e-9:
                    over_y[yy] += 1
        decomp = dict(book=book_y, dip=dip_y, fills=fills_y, wsum=wsum_y,
                      near=near_y, over=over_y, max_concurrent=maxconc,
                      rungs=int(len(ws)))
        out[variant] = dict(run=run, wins=years, decomp=decomp)
        print(f"{tag} {variant} eq_end={run['eq'][-1]:.4f} "
              f"rungs={len(ws)} maxconc={maxconc:.3f} "
              f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        del ev, att
        gc.collect()
    del opens, prep, books_bear
    gc.collect()
    return shift, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "last"], required=True)
    ap.add_argument("--fric", choices=["base", "S5"], required=True)
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--rows", default="REF,BT08,BT06")
    args = ap.parse_args()
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    assert set(variants) <= {"REF", "BT08", "BT06"}, variants
    if args.stage == "last":
        assert set(variants) <= {"REF", "BT08", "BT06"}
    TMP.mkdir(parents=True, exist_ok=True)
    cache_path = TMP / f"runs_{args.stage}_{args.fric}.pkl"

    hb = threading.Thread(target=heartbeat,
                          args=(f"booktrim {args.stage} {args.fric} {args.rows}",),
                          daemon=True)
    hb.start()
    import pickle
    allres = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
    for shift in shifts:
        need = [v for v in variants if v not in allres.get(shift, {})]
        if not need:
            print(f"{args.stage} {args.fric} shift {shift}: all cached, skip", flush=True)
            continue
        s, res = run_shift(shift, need, args.stage, args.fric)
        allres.setdefault(s, {}).update(res)
        cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        cur.update(allres)
        cache_path.write_bytes(pickle.dumps(cur))
        print(f"{args.stage} {args.fric} shift {s} cached", flush=True)
    _stop_hb.set()
    print("DONE", args.stage, args.fric, flush=True)


if __name__ == "__main__":
    main()
