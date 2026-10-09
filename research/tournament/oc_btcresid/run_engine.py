"""oc_btcresid engine: v421-G2 path with BTC-residual idiosyncratic book.

Mechanism = copy of oc_spillgate/run_engine.py (= v414 pipe v321, corr-aware inv
sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0,
win_start=5, gate costs inside the engine) plus a per-coin residual:
  V1: w_resid_c(T) = w_c(T) - beta_c[A(T)] * w_BTC(T) (raw beta, BTC leg -> 0).
  V2: same with beta clipped to [0,1].
  C1: w_REF(T) * m_C1[anchor year] (exposure-matched constant for V1).
  C2: w_REF(T) * m_C2[anchor year].
Dip tilt = 1.0 for ALL rows (book-side idea; dip sleeve untouched).
Betas from tmp/betas.json (causal: 4h closes <= T; norms pre-anchor + 7d embargo);
constants from tmp/controls.json (realised mean gross scale per year, computed
from post-bear standard-grid rows on first shift, then frozen).

Variants (ONLY these five, pre-registered): REF, V1, V2, C1, C2.
Stages: --stage dev runs [DEV0, DEV1); --stage last runs [DEV0, Y1) ONCE.

Usage:
  python run_engine.py --stage dev --shifts 0,1,2,3 --rows REF,V1,V2,C1,C2
Run through heavy_slot (one heavy job), nohup + log.
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
CACHE_DEV = TMP / "runs_dev.pkl"
CACHE_LAST = TMP / "runs_last.pkl"
sys.path.insert(0, str(HERE))

from resid_rule import ANCH5, COINS, anchor_of, beta_for_use, control_mult

ANCH = ANCH5
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
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


def load_betas():
    betas = json.loads((TMP / "betas.json").read_text())["betas"]
    return betas  # {anchor_date: {coin: beta}}


def load_controls():
    ctl = json.loads((TMP / "controls.json").read_text())
    m1 = {a: float(ctl[a]["m_c1"]) for a in ANCH}
    m2 = {a: float(ctl[a]["m_c2"]) for a in ANCH}
    return m1, m2, ctl


def controls_realised(sb: pd.DataFrame, betas: dict) -> dict:
    """Residual frames + per-year realised gross scales (standard grid).

    sb: post-bear book rows on the standard grid (NaN->0 already).
    Returns (sbb_v1, sbb_v2, sbb_c1, sbb_c2, ctl_dict).
    """
    cols = list(sb.columns)
    anch_ts = [pd.Timestamp(a, tz="UTC") for a in ANCH]
    anch_ns = np.array([a.value for a in anch_ts], dtype=np.int64)
    sb_ns = sb.index.values.astype("datetime64[ns]").astype(np.int64)
    ay = anchor_of(sb_ns, anch_ns)
    pre = np.asarray(sb.index < CUTOFF)

    sbb_v1 = sb.copy()
    sbb_v2 = sb.copy()
    wbtc = sb["BTCUSDT"].fillna(0.0).to_numpy(dtype=float)
    for y, a in enumerate(ANCH):
        m = (ay == y) & (~pre)
        if not int(m.sum()):
            continue
        by = betas[a]
        for c in cols:
            if c == "BTCUSDT":
                sbb_v1.loc[m, c] = 0.0
                sbb_v2.loc[m, c] = 0.0
                continue
            b1 = beta_for_use(float(by.get(c, float("nan"))), False)
            b2 = beta_for_use(float(by.get(c, float("nan"))), True)
            wc = sb[c].fillna(0.0).to_numpy(dtype=float)[m]
            wb = wbtc[m]
            sbb_v1.loc[m, c] = wc - b1 * wb
            sbb_v2.loc[m, c] = wc - b2 * wb

    gross_ref = sb.abs().sum(axis=1)
    gross_v1 = sbb_v1.abs().sum(axis=1)
    gross_v2 = sbb_v2.abs().sum(axis=1)
    ctl: dict[str, dict] = {}
    m1 = np.ones(len(sb))
    m2 = np.ones(len(sb))
    for y, a in enumerate(ANCH):
        mm = (ay == y)
        gr = float(gross_ref[mm].mean()) if int(mm.sum()) else float("nan")
        g1 = float(gross_v1[mm].mean()) if int(mm.sum()) else float("nan")
        g2 = float(gross_v2[mm].mean()) if int(mm.sum()) else float("nan")
        c1 = control_mult(g1, gr)
        c2 = control_mult(g2, gr)
        ctl[a] = {"m_c1": c1, "m_c2": c2, "n_bars": int(mm.sum()),
                  "gross_ref": gr, "gross_v1": g1, "gross_v2": g2}
        m1[mm] = c1
        m2[mm] = c2
    sbb_c1 = sb.mul(m1, axis=0)
    sbb_c2 = sb.mul(m2, axis=0)
    return sbb_v1, sbb_v2, sbb_c1, sbb_c2, ctl


def run_shift(shift, variants, stage, betas):
    """One phase; returns {variant: {run, wins, mult}} (run in v414 format)."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{stage}_s{shift}"
    pod = pof._load(f"pod_br_{stage}_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_br_{stage}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_br_{stage}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_br_{stage}_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
        stats={k: (float(v) if isinstance(v, float) else int(v))
               for k, v in dict(stats).items()}) or {}
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
    idx = prep["idx"]
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    # exact v421 bear construction
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear_arr_full = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear_arr_full] = sb.loc[bear_arr_full].where(sb.loc[bear_arr_full] <= 0, sb.loc[bear_arr_full] * 0.5)
    # residual frames + exposure-matched constants on the standard grid
    sbb_v1, sbb_v2, sbb_c1, sbb_c2, ctl = controls_realised(sb, betas)
    (TMP / "controls.json").write_text(json.dumps(ctl, indent=1))
    print(f"{tag}: controls m_c1=" + ",".join(f"{ctl[a]['m_c1']:.4f}" for a in ANCH)
          + " m_c2=" + ",".join(f"{ctl[a]['m_c2']:.4f}" for a in ANCH), flush=True)
    btc_zero = bool(((sbb_v1["BTCUSDT"].abs() > 1e-12) & (sbb_v1.index >= CUTOFF)).sum() == 0)
    print(f"{tag}: BTC leg zero after residual: {btc_zero}", flush=True)
    books_map = {
        "REF": sb.reindex(idx, method="ffill").fillna(0.0),
        "V1": sbb_v1.reindex(idx, method="ffill").fillna(0.0),
        "V2": sbb_v2.reindex(idx, method="ffill").fillna(0.0),
        "C1": sbb_c1.reindex(idx, method="ffill").fillna(0.0),
        "C2": sbb_c2.reindex(idx, method="ffill").fillna(0.0),
    }
    anch_ts = [pd.Timestamp(a, tz="UTC") for a in ANCH]
    anch_ns = np.array([a.value for a in anch_ts], dtype=np.int64)
    T_arr = idx + pd.Timedelta(hours=4)
    T_ns = T_arr.values.astype("datetime64[ns]").astype(np.int64)
    y_of_i = np.clip(np.searchsorted(anch_ns, T_ns, side="right") - 1, 0, 4)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"

    out = {}
    for variant in variants:
        t0 = time.time()
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]

        def tilt(i, a, variant=variant):
            return 1.0  # book-side idea; dip untouched

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
        books_in = books_map[variant]
        eu.simulate(books_in, opens, prep, trade=trade, win_start=5, events=ev, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        years = []
        for y, a in enumerate(ANCH):
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
        mult = {str(y): dict(scale=round(float(ctl[ANCH[y]][f"m_c{1 if variant in ('V1', 'C1') else 2}"]
                                                 if variant in ("V1", "V2", "C1", "C2") else 1.0), 6),
                             n_bars=int(ctl[ANCH[y]]["n_bars"]))
                for y in range(5)}
        out[variant] = dict(run=run, wins=years, mult=mult,
                            stats=dict(cap.get("stats", {})))
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
    ap.add_argument("--rows", default="REF,V1,V2,C1,C2")
    args = ap.parse_args()
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    betas = load_betas()

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
        s, res = run_shift(shift, need, args.stage, betas)
        allres.setdefault(s, {}).update(res)
        cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        cur.update(allres)
        cache_path.write_bytes(pickle.dumps(cur))
        print(f"shift {s} cached ({args.stage})", flush=True)
    _stop_hb.set()
    print("STAGE", args.stage, "DONE shifts", sorted(allres), flush=True)


if __name__ == "__main__":
    main()
