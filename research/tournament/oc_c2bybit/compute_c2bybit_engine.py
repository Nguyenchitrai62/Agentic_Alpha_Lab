"""oc_c2bybit engine: REF vs C2 under base + frictions S1..S5.

Mechanism = verbatim copy of oc_chronos/run_engine.py (pipe v321,
corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
sleeve_gross_cap G=2.0, gate costs inside the engine) plus the friction knobs
EXACTLY as v421_audit/robust_v421.py (same defs as oc_k2bybit):

  base: win_start=5
  S1: MAKER 0.0004 / TAKER 0.0012 patched via eu.simulate.__globals__, restored
  S2: win_start=15, sleeve_start=16
  S3: win_start=30, sleeve_start=31
  S4: win_start=5, stop_slip=0.5
  S5: bybit_minutes() from data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet
      instead of pod.minutes(); live0 = 2021-11-15 + shift; standard index
      filtered to >= 2021-11-15 before shift (year 2021 = short window).

Variants: REF (tilt 1), C2 (1.25/0.75, frozen oc_chronos fits.json;
risk = -ch_q10; fits of anchor A applied to year A on all four shifts;
missing feature -> 1).

Caches: tmp/runs_<fric>.pkl (resume-safe per shift). HEAVY: run through
heavy_slot (sequential shifts, one heavy process).

Usage:
  python compute_c2bybit_engine.py --fric base --shifts 0,1,2,3 --rows REF,C2
  python compute_c2bybit_engine.py --fric all --shifts 0,1,2,3 --rows REF,C2
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
CH = ROOT / "research/tournament/oc_chronos"
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

sys.path.insert(0, str(HERE))
from tilt_rule import ANCH5, assign_mult  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600
FRICS = ("base", "S1", "S2", "S3", "S4", "S5")

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


def load_shift_chronos(shift):
    df = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                         columns=["sym", "shift", "T", "ch_q10"])
    df = df[df["shift"] == shift]
    out = {}
    for sym, t, q in zip(df["sym"], df["T"], df["ch_q10"]):
        out[(str(sym), pd.Timestamp(t))] = float(q)
    return out


def fric_extra(fric: str) -> dict:
    if fric == "base":
        return dict(win_start=5)
    if fric == "S1":
        return dict(win_start=5)
    if fric == "S2":
        return dict(win_start=15, sleeve_start=16)
    if fric == "S3":
        return dict(win_start=30, sleeve_start=31)
    if fric == "S4":
        return dict(win_start=5, stop_slip=0.5)
    if fric == "S5":
        return dict(win_start=5)
    raise ValueError(fric)


def run_shift(shift, variants, fric, fits):
    """One phase; returns {variant: {run, wins, mult}} (oc_chronos format)."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{fric}_s{shift}"
    pod = pof._load(f"pod_cb_{fric}_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_cb_{fric}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_cb_{fric}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_cb_{fric}_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    s5 = (fric == "S5")
    live0 = (S5_START if s5 else DEV0) + sh
    live1 = Y1 + sh
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

    chron = load_shift_chronos(shift)
    T_arr = idx + pd.Timedelta(hours=4)
    anch_ns = np.array([pd.Timestamp(a, tz="UTC").value for a in ANCH5])
    y_of_i = np.clip(np.searchsorted(anch_ns, T_arr.values.astype(np.int64),
                                     side="right") - 1, 0, 4)
    T_list = list(T_arr)

    out = {}
    for variant in variants:
        ex = dict(fric_extra(fric))  # fresh copy per variant (pop is mutating)
        ws = ex.pop("win_start", 5)
        t0 = time.time()
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]
        msum = [0.0] * 5
        mcnt = [0] * 5

        def tilt(i, a, variant=variant):
            y = int(y_of_i[i])
            if variant == "REF":
                m = 1.0
            else:
                f = fits[ANCH5[y]]
                q = chron.get((cols[a], T_list[i]))
                risk = -q if q is not None and np.isfinite(q) else float("nan")
                m = assign_mult(risk, f["direction"], f["q20"], f["q80"], 1.25, 0.75)
            msum[y] += m
            mcnt[y] += 1
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
        old_maker, old_taker = None, None
        try:
            if fric == "S1":
                old_maker = eu.simulate.__globals__["MAKER"]
                old_taker = eu.simulate.__globals__["TAKER"]
                eu.simulate.__globals__["MAKER"] = 0.0004
                eu.simulate.__globals__["TAKER"] = 0.0007 + 0.0005
            eu.simulate(books_bear, opens, prep, trade=trade, events=ev,
                        win_start=ws, **{**kw, **ex})
            # win_start consumed explicitly (same call shape as
            # oc_chronos/run_engine.py); remaining `ex` holds only
            # sleeve_start (S2/S3) or stop_slip (S4), merged over kw defaults.
        finally:
            if fric == "S1" and old_maker is not None:
                eu.simulate.__globals__["MAKER"] = old_maker
                eu.simulate.__globals__["TAKER"] = old_taker
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
            years.append(dict(nb=nb, wb=wb, nr=len(rr), wr=int(sum(r > 0 for r in rr))))
        mult = {str(y): dict(sized_mean=round(msum[y] / mcnt[y], 6) if mcnt[y] else None,
                             n_sized=int(mcnt[y])) for y in range(5)}
        out[variant] = dict(run=run, wins=years, mult=mult)
        print(f"{tag} {variant} eq_end={run['eq'][-1]:.4f} "
              f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        del ev
        gc.collect()
    del opens, prep, books_bear
    gc.collect()
    return shift, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fric", default="base",
                    help="base|S1|S2|S3|S4|S5|all")
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--rows", default="REF,C2")
    args = ap.parse_args()
    frics = list(FRICS) if args.fric == "all" else [args.fric]
    assert all(f in FRICS for f in frics), frics
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    assert set(variants) <= {"REF", "C2"}, variants
    fits = json.loads((CH / "fits.json").read_text())
    TMP.mkdir(parents=True, exist_ok=True)

    hb = threading.Thread(target=heartbeat,
                          args=(f"c2bybit {args.fric} {args.rows}",), daemon=True)
    hb.start()
    for fric in frics:
        cache_path = TMP / f"runs_{fric}.pkl"
        allres = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        for shift in shifts:
            need = [v for v in variants if v not in allres.get(shift, {})]
            if not need:
                print(f"fric {fric} shift {shift}: all cached, skip", flush=True)
                continue
            s, res = run_shift(shift, need, fric, fits)
            allres.setdefault(s, {}).update(res)
            cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
            cur.update(allres)
            cache_path.write_bytes(pickle.dumps(cur))
            print(f"fric {fric} shift {s} cached", flush=True)
    _stop_hb.set()
    print("DONE frics", frics, flush=True)


if __name__ == "__main__":
    main()
