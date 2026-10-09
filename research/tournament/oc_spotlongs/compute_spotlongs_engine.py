"""oc_spotlongs engine: 4-phase G2 vs spot-margin book longs (V0/V1/V2).

Mechanism = verbatim copy of oc_c2bybit/compute_c2bybit_engine.py base pipe
(v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
sleeve_gross_cap G=2.0, gate costs inside the engine, win_start=5) with ONE
difference: book legs run through the spot-patched simulate
(spot_patch.load(), asserted verbatim + SPOT PATCH P0-P4):
  book long funding 0 for spot-routed (coin, bar), USDT borrow borrow_apr on
  the spot-routed long leg where leveraged, dip sleeve untouched (perp).

Variants (ONLY these, pre-registered):
  V0 = gate (spot_route=None, borrow 0 -> bit-identical to G2 REF).
  V1 = all book longs spot-routed, borrow APR 10%.
  V2 = gated spot-route (F7 > pre-anchor median, spot_rule.py), borrow 10%.
Stages: dev ([DEV0, DEV1)) for V0/V1/V2; last ([DEV0, Y1)) for the pick only.
Frics: base (win_start=5); S5 Bybit 1m (pick only, live0 2021-11-15 + shift).
Stress APR 15% and CTRL are CPU overlays in analyze_spotlongs.py (same fills).

Caches: tmp/runs_<stage>_<fric>.pkl (resume-safe per shift). HEAVY: run through
heavy_slot (sequential shifts, one heavy process). Heartbeat every 600 s.

Usage:
  python compute_spotlongs_engine.py --stage dev --fric base --shifts 0,1,2,3 --rows V0,V1,V2
  python compute_spotlongs_engine.py --stage last --fric base --shifts 0,1,2,3 --rows V1
  python compute_spotlongs_engine.py --stage dev --fric S5 --shifts 0,1,2,3 --rows V1
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
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

sys.path.insert(0, str(HERE))
import spot_rule  # noqa: E402
import spot_patch  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600
BORROW_APR = 0.10

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


def run_shift(shift, variants, stage, fric, fund, meds, sext):
    """One phase; returns {variant: {run, wins, bars_lite, stats}}."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{stage}_{fric}_s{shift}"
    pod = pof._load(f"pod_sl_{stage}_{fric}_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_sl_{stage}_{fric}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_sl_{stage}_{fric}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_sl_{stage}_{fric}_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    sext.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    last = (stage == "last")
    s5 = (fric == "S5")
    live0 = (S5_START if s5 else DEV0) + sh
    live1 = (Y1 if last else DEV1) + sh
    sext.v110.START, sext.v110.END = live0, live1
    books154, _opens_std = sext.er.v154_books()
    if last:
        std_idx = books154.index
    else:
        std_idx = books154.index[books154.index <= DEV1 + pd.Timedelta(hours=4)]
    if s5:
        std_idx = std_idx[std_idx >= S5_START]
        M = bybit_minutes()
    else:
        M = pod.minutes()
    opens, prep = pof.prep_idx(M, std_idx + sh, shift, list(books154.columns))
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

    T_arr = idx + pd.Timedelta(hours=4)
    anch_ns = np.array([pd.Timestamp(a, tz="UTC").value for a in spot_rule.ANCH5])
    y_of_i = np.clip(np.searchsorted(anch_ns, T_arr.values.astype(np.int64),
                                     side="right") - 1, 0, 4)
    T_list = list(T_arr)
    route_v2 = spot_rule.route_matrix(T_list, cols, y_of_i, meds, fund)
    route_v1 = np.ones_like(route_v2)

    out = {}
    for variant in variants:
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

        if variant == "V0":
            route, apr = None, 0.0
        elif variant == "V1":
            mat = route_v1
            route = lambda i, a, _m=mat: bool(_m[i, a])
            apr = BORROW_APR
        elif variant == "V2":
            mat = route_v2
            route = lambda i, a, _m=mat: bool(_m[i, a])
            apr = BORROW_APR
        else:
            raise ValueError(variant)

        ev, bars = [], []
        sext.simulate(books_bear, opens, prep, trade=trade, win_start=5,
                      events=ev, bars=bars, spot_route=route, borrow_apr=apr, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        # bars[] holds one entry per simulated (live, finite) bar with
        # b["t"] = holding-bar open T; live decisions idx in [live0, live1)
        # <=> T in [live0+4h, live1+4h).
        b0, b1 = live0 + pd.Timedelta(hours=4), live1 + pd.Timedelta(hours=4)
        bars_lite = [dict(t=str(b["t"]), equity=float(b["equity"]),
                          borrow=float(b.get("borrow", 0.0)),
                          funding_saved=float(b.get("funding_saved", 0.0)))
                     for b in bars
                     if b0 <= pd.Timestamp(b["t"]) < b1]
        years = []
        for y, a in enumerate(spot_rule.ANCH5):
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
        out[variant] = dict(run=run, wins=years, bars_lite=bars_lite)
        print(f"{tag} {variant} eq_end={run['eq'][-1]:.4f} "
              f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
        del ev, bars
        gc.collect()
    del opens, prep, books_bear
    gc.collect()
    return shift, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "last"], required=True)
    ap.add_argument("--fric", choices=["base", "S5"], default="base")
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--rows", default="V0,V1,V2")
    args = ap.parse_args()
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    assert set(variants) <= {"V0", "V1", "V2"}, variants
    if args.fric == "S5":
        assert args.stage == "dev", "S5 only scored on the dev window (pick)"
    TMP.mkdir(parents=True, exist_ok=True)
    print("loading funding panel + medians (causal, pre-anchor -7d)...", flush=True)
    fund = spot_rule.load_funding()
    meds = spot_rule.medians(fund)
    (TMP / "funding_meds.json").write_text(json.dumps(meds, indent=1))
    print("medians frozen:", {a: {s: round(v, 8) for s, v in m.items()}
                              for a, m in meds.items()}, flush=True)
    sext = spot_patch.load()

    hb = threading.Thread(target=heartbeat,
                          args=(f"spotlongs {args.stage}/{args.fric} {args.rows}",),
                          daemon=True)
    hb.start()
    cache_path = TMP / f"runs_{args.stage}_{args.fric}.pkl"
    allres = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
    for shift in shifts:
        need = [v for v in variants if v not in allres.get(shift, {})]
        if not need:
            print(f"stage {args.stage} fric {args.fric} shift {shift}: cached, skip",
                  flush=True)
            continue
        s, res = run_shift(shift, need, args.stage, args.fric, fund, meds, sext)
        allres.setdefault(s, {}).update(res)
        cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        cur.update(allres)
        cache_path.write_bytes(pickle.dumps(cur))
        print(f"stage {args.stage} fric {args.fric} shift {s} cached", flush=True)
    _stop_hb.set()
    print("DONE", args.stage, args.fric, sorted(allres), flush=True)


if __name__ == "__main__":
    main()
