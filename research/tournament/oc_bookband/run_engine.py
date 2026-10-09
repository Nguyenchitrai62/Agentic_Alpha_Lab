"""oc_bookband engine: 4-phase G2 (v421 R2B1D17BFG2) with a no-trade band on book targets.

Frozen definitions in PLAN.md. REF = G2 bit-exact; NB10/NB25 replace ONLY the
bear-filtered book series with the band-filtered series F (p=0.10/0.25, trailing-90d
typical, flip bypass), then identical v421 wiring (pipe v321, kd=1.7 corr-inv,
budget 0.26*1.7, G=2.0, win_start=5, gate costs).

Usage (all heavy via the shared semaphore, one job at a time):
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_bookband --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_bookband/run_engine.py --validate
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_bookband --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_bookband/run_engine.py --stage dev --shifts 0,1,2,3 --rows REF,NB10,NB25
  (then, after the dev4 pick in analyze.py, scored-once last stage for REF + pick only)

Resume-safe caches: tmp/runs_dev.pkl, tmp/runs_last.pkl. Heartbeat every 600 s.
"""
from __future__ import annotations

import argparse
import gc
import importlib.util
import json
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
V421 = RD / "v421"
TMP = HERE / "tmp"
CACHE_DEV = TMP / "runs_dev.pkl"
CACHE_LAST = TMP / "runs_last.pkl"

sys.path.insert(0, str(HERE))
import bookband as bb  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
HEARTBEAT_S = 600
P_MAP = {"NB10": 0.10, "NB25": 0.25}

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validate_g2() -> None:
    runs = pickle.loads((V421 / "v421_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    exp = json.loads((V421 / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v388 = pof._load("v388_bb_val", RD / "v388/v388_bot_stop_distance.py")
    rm = pof._load("reset_bb_val", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    strat = "R2B1D17BFG2"
    got_r, got_dd = [], []
    for y in range(5):
        m = rm.year_reset(runs, strat, y)
        got_r.append(m["R"])
        got_dd.append(m["DD"])
    assert got_r == [r for r, _ in exp["years"]], (got_r, exp["years"])
    assert got_dd == [d for _, d in exp["years"]], (got_dd, exp["years"])
    R5 = round(float(np.prod([1 + r / 100 for r in got_r]) ** (1 / 5) - 1) * 100, 3)
    assert R5 == exp["R"] and min(got_r) == exp["W"] and max(got_dd) == exp["DD"], (R5, exp)
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, strat, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    assert full == exp["full_path_dd"], (full, exp["full_path_dd"])
    print(f"G2 validation OK: R {R5} / W {min(got_r)} / DD {max(got_dd)} / full {full}", flush=True)


def band_books(std_bear: pd.DataFrame, variant: str) -> pd.DataFrame:
    if variant == "REF":
        return std_bear
    p = P_MAP[variant]
    typ = bb.trailing_typical(std_bear)
    return bb.apply_band(std_bear, typ, p)


def run_shift(shift: int, variants: list[str], stage: str):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{stage}_s{shift}"
    pod = pof._load(f"pod_bb_{stage}_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_bb_{stage}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_bb_{stage}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_bb_{stage}_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}

    def _summ(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                   eq_max=(eq if eq_max is None else eq_max).copy(), stats=dict(stats))

    eu.summarize = _summ
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
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    std_bear = sb
    # precompute filtered standard-grid books per variant (causal on std grid)
    filt = {v: band_books(std_bear, v) for v in variants}
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"

    out = {}
    for variant in variants:
        t0 = time.time()
        books = filt[variant].reindex(idx, method="ffill").fillna(0.0)
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]

        def corr_size(i, a, r, f, base_size=base_size):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            return (1.0 / (1 + n)) * 1.7 * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7
        kw["sleeve_gross_cap"] = 2.0
        ev: list = []
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        years = []
        for y, a in enumerate(ANCH5):
            if not last and y == 4:
                years.append(dict(nb=0, wb=0, nfill=0))
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
            nf = sum(1 for e in evy if e["kind"] == "book_fill")
            years.append(dict(nb=nb, wb=wb, nfill=int(nf)))
        st = cap.get("stats", {})
        out[variant] = dict(run=run, wins=years,
                            stats={k: (float(v) if isinstance(v, float) else v) for k, v in st.items()})
        print(f"{tag} {variant} eq_end={run['eq'][-1]:.4f} elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        del ev, books
        gc.collect()
    del opens, prep
    gc.collect()
    return shift, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--stage", choices=["dev", "last"], default="dev")
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--rows", default="REF,NB10,NB25")
    args = ap.parse_args()
    validate_g2()
    if args.validate:
        print("validate-only done (no engine run).", flush=True)
        return
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    hb = threading.Thread(target=heartbeat, args=(f"run_engine {args.stage} {args.rows}",), daemon=True)
    hb.start()
    cache_path = CACHE_LAST if args.stage == "last" else CACHE_DEV
    TMP.mkdir(parents=True, exist_ok=True)
    allres = {}
    if cache_path.exists():
        allres = pickle.loads(cache_path.read_bytes())
        print("loaded cached runs:", {s: sorted(v) for s, v in allres.items()}, flush=True)
    for shift in shifts:
        need = [v for v in variants if v not in allres.get(shift, {})]
        if not need:
            print(f"shift {shift}: all cached, skip", flush=True)
            continue
        s, res = run_shift(shift, need, args.stage)
        allres.setdefault(s, {}).update(res)
        cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        cur.update(allres)
        cache_path.write_bytes(pickle.dumps(cur))
        print(f"shift {s} cached ({args.stage})", flush=True)
    _stop_hb.set()
    print("STAGE", args.stage, "DONE shifts", sorted(allres), flush=True)


if __name__ == "__main__":
    main()
