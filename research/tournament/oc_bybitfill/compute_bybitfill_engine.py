"""oc_bybitfill engine: REF vs TPm3 vs RUNp3 on Bybit S5 (+ Binance base side row).

Mechanism = G2 (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0) via
phase_offset_full.pipe_setup("v321", ..., agents=True) plus corr-aware dip sizes,
exactly as oc_c2bybit/compute_c2bybit_engine.py, except the price offsets go through
engine_patch.simulate (vendored engine_user + dip_rung_mult/dip_tp_mult):
  REF   = (1.0, 1.0)
  TPm3  = (1.0, 0.9997)
  RUNp3 = (1.0003, 0.9997)
Frictions: base (Binance, win_start=5) and S5 (Bybit 1m from 2021-11-15,
win_start=5; 2021 = short window, labelled). Gate costs inside the engine
(maker 0.0002 / taker 0.00055 / longs 0.0001 per 8h; strict trade-through;
stop-first, inherited harness).

Caches: tmp/runs_<ROW>.pkl (resume-safe per shift), ROW in
REF_base/TPm3_base/RUNp3_base/REF_S5/TPm3_S5/RUNp3_S5. HEAVY: run through
heavy_slot (sequential shifts, one heavy process).

Usage:
  python compute_bybitfill_engine.py --row REF_S5 --shifts 0,1,2,3
  python compute_bybitfill_engine.py --row all --shifts 0,1,2,3
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
V421 = RD / "v421"
TMP = HERE / "tmp"
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

sys.path.insert(0, str(HERE))
from engine_patch import RUNG_MULT, TP_MULT  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ROWS = ("REF_base", "TPm3_base", "RUNp3_base", "REF_S5", "TPm3_S5", "RUNp3_S5")


def _parse_row(row: str):
    variant, fric = row.split("_", 1)
    assert variant in ("REF", "TPm3", "RUNp3"), row
    assert fric in ("base", "S5"), row
    return variant, fric


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


def run_shift(shift, rows):
    """One phase; returns {row: {run, wins}} (oc_chronos/oc_c2bybit format)."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"pod_bf_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_bf_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_bf_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_bf_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    eup = _load("eup_bf_engine_patch", HERE / "engine_patch.py")
    cap = {}

    def _cap(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy())
        return {}

    # The vendored simulate looks up module-global `summarize` and `v110` in its
    # own namespace: patch those (eu.summarize patch alone would NOT affect it).
    eup.simulate.__globals__["summarize"] = _cap
    sh = pd.Timedelta(hours=shift)
    out = {}
    for row in rows:
        variant, fric = _parse_row(row)
        s5 = (fric == "S5")
        live0 = (S5_START if s5 else DEV0) + sh
        live1 = Y1 + sh
        eup.simulate.__globals__["v110"].START, eup.simulate.__globals__["v110"].END = live0, live1
        eu.v110.START, eu.v110.END = live0, live1
        books154, _opens_std = eu.er.v154_books()
        if s5:
            std_idx = books154.index[books154.index >= S5_START] + sh
            M = bybit_minutes()
        else:
            std_idx = books154.index + sh
            M = pod.minutes()
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

        t0 = time.time()
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
            mult = 1.0 / (1 + n)
            return mult * 1.7 * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7
        kw["sleeve_gross_cap"] = 2.0

        ev = []
        eup.simulate(books_bear, opens, prep, trade=trade, events=ev,
                     win_start=5,
                     dip_rung_mult=RUNG_MULT[variant], dip_tp_mult=TP_MULT[variant],
                     **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        years = []
        for y, a in enumerate(ANCH5):
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
            rtp = sum(1 for e in evy if e["kind"] == "rung_tp")
            rsl = sum(1 for e in evy if e["kind"] == "rung_sl")
            rto = sum(1 for e in evy if e["kind"] == "rung_timeout")
            years.append(dict(nb=nb, wb=wb, nr=len(rr), wr=int(sum(r > 0 for r in rr)),
                              ntp=int(rtp), nsl=int(rsl), nto=int(rto)))
        out[row] = dict(run=run, wins=years)
        print(f"s{shift} {row} eq_end={run['eq'][-1]:.4f} "
              f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        del ev, opens, prep, books_bear
        gc.collect()
    return shift, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--row", default="REF_S5",
                    help="one of REF_base|TPm3_base|RUNp3_base|REF_S5|TPm3_S5|RUNp3_S5|all")
    ap.add_argument("--shifts", default="0,1,2,3")
    args = ap.parse_args()
    rows = list(ROWS) if args.row == "all" else [args.row]
    assert all(r in ROWS for r in rows), rows
    shifts = [int(s) for s in args.shifts.split(",")]
    TMP.mkdir(parents=True, exist_ok=True)

    hb = threading.Thread(target=heartbeat,
                          args=(f"bybitfill {args.row}",), daemon=True)
    hb.start()
    for row in rows:
        cache_path = TMP / f"runs_{row}.pkl"
        allres = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        for shift in shifts:
            if shift in allres and row in allres[shift]:
                print(f"row {row} shift {shift}: cached, skip", flush=True)
                continue
            s, res = run_shift(shift, [row])
            allres.setdefault(s, {}).update(res)
            cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
            cur.update(allres)
            cache_path.write_bytes(pickle.dumps(cur))
            print(f"row {row} shift {s} cached", flush=True)
    _stop_hb.set()
    print("DONE rows", rows, flush=True)


if __name__ == "__main__":
    main()
