"""oc_stopentry engine: 4-phase G2 vs stop-entry book orders (V1/V2 + controls).

Mechanism = verbatim copy of oc_c2bybit/compute_c2bybit_engine.py base pipe
(v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
sleeve_gross_cap G=2.0, gate costs inside the engine, win_start=5) with ONE
difference: book entries run through the stop-patched simulate
(stop_patch.load(), asserted verbatim + STOP PATCH P0-P4):
  flat->open orders are stop-entries through P0 (taker) when routed, passive
  G2 limits (maker) otherwise; SL/TP/BE/tighten/validity/dip unchanged.

Variants (ONLY these, pre-registered):
  REF  = gate (stop_route=None -> bit-identical to G2).
  V1   = every new book entry is a stop-entry (5bps through P0, taker).
  V2   = stop-entry only when |w| > pre-anchor median for (anchor, coin)
         (stop_rule.py; 2021 all-passive by construction), passive otherwise.
  C_V1 = REF mechanism (all passive) with per-year constant book_size = c_y(V1)
         (exposure-matched, diagnostic, in-year, never picked).
  C_V2 = same with c_y(V2).
Stages: dev ([DEV0, DEV1)) for REF/V1/V2 then C_V1/C_V2 (c_y from dev runs);
  last ([DEV0, Y1)) for REF + dev4 pick ONLY (controls never run last).
Frics: base (win_start=5); S5 Bybit 1m (pick + REF only, live0 2021-11-15 + shift).

Caches: tmp/runs_<stage>_<fric>.pkl (resume-safe per shift). HEAVY: run through
heavy_slot (sequential shifts, one heavy process). Heartbeat every 600 s.

Usage:
  python compute_stopentry_engine.py --stage dev --fric base --shifts 0,1,2,3 --rows REF,V1,V2
  python compute_stopentry_engine.py --stage dev --fric base --shifts 0,1,2,3 --rows C_V1,C_V2
  python compute_stopentry_engine.py --stage last --fric base --shifts 0,1,2,3 --rows REF,V1
  python compute_stopentry_engine.py --stage dev --fric S5 --shifts 0,1,2,3 --rows REF,V1
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
import stop_patch  # noqa: E402
import stop_rule  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600
ALL_ROWS = ("REF", "V1", "V2", "C_V1", "C_V2")

_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bybit_minutes():
    out = {}
    for s in SYMS:
        m = pd.read_parquet(
            BYBIT_DIR / (f"{s}_1m.parquet"), columns=["open_time", "open", "high", "low", "close"]
        )
        m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
        out[s] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return out


def build_medians() -> dict[str, dict[str, float]]:
    """Pre-anchor |w| medians from standard-grid post-bear books (causal).

    Written to tmp/stop_meds.json BEFORE any engine run. Anchor 2021 is empty
    (books start 2021-09-24) -> all NaN -> V2 passive in 2021 (disclosed).
    """
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as _pof

    v221m = _pof._load("v221_med0", RD / "v221/v221_grid_hysteresis.py")
    eu0 = v221m.eu
    fw = _pof._load("fw_med0", ROOT / "scripts/forward_v205.py")
    books154, opens_std = eu0.er.v154_books()
    cols = list(books154.columns)
    std_books = fw.research_books_d2(eu0).reindex(books154.index).fillna(0.0)[cols]
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    meds = stop_rule.medians_from_bear(sb)
    (TMP / "stop_meds.json").write_text(json.dumps(meds, indent=1))
    print("medians frozen:", {a: m for a, m in meds.items()}, flush=True)
    return meds


def run_shift(shift, variants, stage, fric, meds, sext, ctrls):
    """One phase; returns {variant: {run, wins, fills}}."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof

    tag = f"{stage}_{fric}_s{shift}"
    pod = pof._load(
        f"pod_se_{stage}_{fric}_{shift}",
        ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py",
    )
    hist = pof._load(f"hist_se_{stage}_{fric}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_se_{stage}_{fric}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_se_{stage}_{fric}_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    sext.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()
    ) or {}
    sh = pd.Timedelta(hours=shift)
    last = stage == "last"
    s5 = fric == "S5"
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
    anch_ns = np.array([pd.Timestamp(a, tz="UTC").value for a in stop_rule.ANCH5])
    y_of_i = np.clip(
        np.searchsorted(anch_ns, T_arr.values.astype(np.int64), side="right") - 1, 0, 4
    )
    # signed post-bear weights on the shifted grid (ffilled) for the V2 gate
    w_grid = books_bear.to_numpy(dtype=float)
    route_v2 = stop_rule.route_matrix(w_grid, y_of_i, meds, cols)
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
                if b == a or not (
                    np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])
                ):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + n)
            return mult * 1.7 * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e: 1.0
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * 1.7
        kw["sleeve_gross_cap"] = 2.0

        if variant == "REF":
            sroute, bsize = None, None
        elif variant == "V1":
            mat = route_v1
            sroute = lambda i, a, _m=mat: bool(_m[i, a])  # noqa: E731
            bsize = None
        elif variant == "V2":
            mat = route_v2
            sroute = lambda i, a, _m=mat: bool(_m[i, a])  # noqa: E731
            bsize = None
        elif variant in ("C_V1", "C_V2"):
            src = "V1" if variant == "C_V1" else "V2"
            cy = ctrls[src]  # list of 5 per-year constants
            sroute = None  # controls stay passive limits

            def bsize(i, a, sgn, _cy=cy, _y=y_of_i):
                return float(_cy[int(_y[i])])

        else:
            raise ValueError(variant)

        ev = []
        sext.simulate(
            books_bear,
            opens,
            prep,
            trade=trade,
            win_start=5,
            events=ev,
            stop_route=sroute,
            stop_off=stop_rule.STOP_OFF,
            book_size=bsize,
            **kw,
        )
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(
            t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
            eq=(cap["eq"][lv] / base).tolist(),
            eq_min=(cap["eq_min"][lv] / base).tolist(),
        )
        years = []
        fills = []
        for y, a in enumerate(stop_rule.ANCH5):
            if not last and y == 4:
                years.append(dict(nb=0, wb=0, nr=0, wr=0))
                fills.append(dict(fg=0.0, nstop=0, nlim=0))
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
            fg = sum(abs(float(e.get("weight", 0.0))) for e in evy if e["kind"] == "book_fill")
            nstop = sum(1 for e in evy if e["kind"] == "book_fill" and e.get("entry_type") == "stop")
            nlim = sum(1 for e in evy if e["kind"] == "book_fill" and e.get("entry_type") != "stop")
            fills.append(dict(fg=float(fg), nstop=int(nstop), nlim=int(nlim)))
        out[variant] = dict(run=run, wins=years, fills=fills)
        print(
            f"{tag} {variant} eq_end={run['eq'][-1]:.4f} "
            f"elapsed={(time.time() - t0) / 60:.1f}min",
            flush=True,
        )
        del ev
        gc.collect()
    del opens, prep, books_bear
    gc.collect()
    return shift, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "last"], required=True)
    ap.add_argument("--fric", choices=["base", "S5"], default="base")
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--rows", default="REF,V1,V2")
    args = ap.parse_args()
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    assert set(variants) <= set(ALL_ROWS), variants
    if args.fric == "S5":
        assert args.stage == "dev", "S5 only scored on the dev window (pick + REF)"
    if any(v.startswith("C_") for v in variants):
        assert args.stage == "dev" and args.fric == "base", "controls run dev/base only"
    TMP.mkdir(parents=True, exist_ok=True)
    meds = json.loads((TMP / "stop_meds.json").read_text()) if (TMP / "stop_meds.json").exists() else build_medians()
    ctrls = {}
    if any(v.startswith("C_") for v in variants):
        p = TMP / "ctrl.json"
        assert p.exists(), f"missing {p} — run analyze to build c_y first"
        ctrls = {k: list(map(float, v)) for k, v in json.loads(p.read_text()).items()}
    sext = stop_patch.load()

    hb = threading.Thread(
        target=heartbeat, args=(f"stopentry {args.stage}/{args.fric} {args.rows}",), daemon=True
    )
    hb.start()
    cache_path = TMP / f"runs_{args.stage}_{args.fric}.pkl"
    allres = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
    for shift in shifts:
        need = [v for v in variants if v not in allres.get(shift, {})]
        if not need:
            print(f"stage {args.stage} fric {args.fric} shift {shift}: cached, skip", flush=True)
            continue
        s, res = run_shift(shift, need, args.stage, args.fric, meds, sext, ctrls)
        allres.setdefault(s, {}).update(res)
        cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        cur.update(allres)
        cache_path.write_bytes(pickle.dumps(cur))
        print(f"stage {args.stage} fric {args.fric} shift {s} cached", flush=True)
    _stop_hb.set()
    print("DONE", args.stage, args.fric, sorted(allres), flush=True)


if __name__ == "__main__":
    main()
