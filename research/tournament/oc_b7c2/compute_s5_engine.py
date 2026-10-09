"""oc_b7c2 S5 engine: REF / B7 / B7C2 / B7C2_cap on BYBIT prices.

Mechanism = verbatim copy of oc_c2bybit/compute_c2bybit_engine.py (pipe v321,
corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
sleeve_gross_cap G=2.0, gate costs inside the engine) with the S5 price switch
EXACTLY as oc_k2bybit/oc_c2bybit:

  S5: bybit_minutes() from data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet
      instead of pod.minutes(); live0 = 2021-11-15 + shift; standard index
      filtered to >= 2021-11-15 before shift (year 2021 = SHORT window, labelled).

Dip mult per sizing (i,a):
  REF      -> 1.0
  B7       -> m_B7(T,shift) (1.5 in 7d window else 1.0; frozen boost parquet)
  B7C2     -> m_B7 * m_C2
  B7C2_cap -> min(m_B7 * m_C2, 1.5)
m_C2 = assign_c2(-ch_q10(sym,T), dir_y, q20_y, q80_y); missing/NaN -> 1.0
(frozen oc_chronos fits.json; fits of anchor y for year y on all shifts).

Caches: tmp/runs_S5.pkl (resume-safe per shift). HEAVY: run through heavy_slot.

Usage:
  python compute_s5_engine.py --shifts 0,1,2,3 --rows REF,B7,B7C2,B7C2_cap
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
TMP = HERE / "tmp"
CB = ROOT / "research/tournament/oc_cascadeboost"
CH = ROOT / "research/tournament/oc_chronos"
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

sys.path.insert(0, str(HERE))
from stack_rule import ANCH5, assign_c2, stack_mult, stack_mult_cap  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600

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


def load_shift_stack(shift):
    d = pd.read_parquet(CB / "boost_mult_4shift.parquet",
                        columns=["shift", "T", "mult_B7"])
    d = d[d["shift"] == shift].sort_values("T")
    t = pd.to_datetime(d["T"], utc=True)
    exact = {pd.Timestamp(tt): float(a) for tt, a in zip(t, d["mult_B7"])}
    t_ns = t.values.astype("datetime64[ns]").astype(np.int64)
    arr = d["mult_B7"].to_numpy(dtype=float)
    c = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                        columns=["sym", "shift", "T", "ch_q10"])
    c = c[c["shift"] == shift]
    feat = {}
    for sym, tt, q in zip(c["sym"], c["T"], c["ch_q10"]):
        feat[(str(sym), pd.Timestamp(tt))] = float(q)
    return exact, t_ns, arr, feat


def b7_for(t, exact, t_ns, arr):
    hit = exact.get(pd.Timestamp(t))
    if hit is not None:
        return hit
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return 1.0
    return float(arr[pos])


def fric_extra(fric: str) -> dict:
    # S5 only in this file (kept as a function for the friction-constant test).
    assert fric == "S5", fric
    return dict(win_start=5)


def run_shift(shift, variants, fits):
    """One S5 phase; returns {variant: {run, wins, mult}}."""
    assert set(variants) <= {"REF", "B7", "B7C2", "B7C2_cap"} and variants, variants
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"S5_s{shift}"
    pod = pof._load(f"pod_b7c2s5_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_b7c2s5_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_b7c2s5_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_b7c2s5_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0 = S5_START + sh
    live1 = Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    std_idx = books154.index[books154.index >= S5_START] + sh
    M = bybit_minutes()
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

    exact, t_ns, arr, feat = load_shift_stack(shift)
    T_arr = idx + pd.Timedelta(hours=4)
    anch_ns = np.array([pd.Timestamp(a, tz="UTC").value for a in ANCH5])
    y_of_i = np.clip(np.searchsorted(anch_ns, T_arr.values.astype(np.int64),
                                     side="right") - 1, 0, 4)
    T_list = list(T_arr)

    out = {}
    for variant in variants:
        ex = dict(fric_extra("S5"))
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
            elif variant == "B7":
                m = b7_for(T_list[i], exact, t_ns, arr)
            else:
                T = T_list[i]
                mb = b7_for(T, exact, t_ns, arr)
                q = feat.get((cols[a], pd.Timestamp(T)))
                if q is None or not np.isfinite(q):
                    mc = 1.0
                else:
                    f = fits[ANCH5[y]]
                    mc = assign_c2(-q, f["direction"], f["q20"], f["q80"])
                m = stack_mult(mb, mc) if variant == "B7C2" else stack_mult_cap(mb, mc)
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
        eu.simulate(books_bear, opens, prep, trade=trade, events=ev,
                    win_start=ws, **{**kw, **ex})
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
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--rows", default="REF,B7,B7C2,B7C2_cap")
    args = ap.parse_args()
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    assert set(variants) <= {"REF", "B7", "B7C2", "B7C2_cap"} and variants, variants
    fits = json.loads((CH / "fits.json").read_text())
    TMP.mkdir(parents=True, exist_ok=True)

    hb = threading.Thread(target=heartbeat, args=("b7c2_s5 " + args.rows,), daemon=True)
    hb.start()
    cache_path = TMP / "runs_S5.pkl"
    allres = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
    for shift in shifts:
        need = [v for v in variants if v not in allres.get(shift, {})]
        if not need:
            print(f"S5 shift {shift}: all cached, skip", flush=True)
            continue
        s, res = run_shift(shift, need, fits)
        allres.setdefault(s, {}).update(res)
        cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        cur.update(allres)
        cache_path.write_bytes(pickle.dumps(cur))
        print(f"S5 shift {s} cached", flush=True)
    _stop_hb.set()
    print("DONE S5 shifts", sorted(allres), flush=True)


if __name__ == "__main__":
    main()
