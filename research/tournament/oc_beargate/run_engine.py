"""oc_beargate engine: v421-G2 path with bear-gated dip-size tilts.

Mechanism = copy of oc_chronos/run_engine.py (= v414 pipe v321,
corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine) plus a
per-(coin, holding bar) gated multiplier tilt(i, a) on top of the corr-aware
dip sizes; budget unchanged.

Bear state (exact v421 definition, v421_gross_cap.py:70):
  btc = _opens_std["BTCUSDT"].reindex(books154.index)
  bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
evaluated at the holding-bar open T as the latest standard-grid index r <= T
(ffill; causal). Same bear array the books use (books_bear ffill).

Variants (ONLY these three, pre-registered):
  REF     = G2 unchanged (tilt 1).
  C2_B    = Chronos C2 base mult (frozen oc_chronos fits.json; risk = -ch_q10;
            hi/lo 1.25/0.75) when not bear, else 1.0.
  GARCH_B = V_GARCH base mult (frozen oc_voltilt fits.json V_GARCH;
            risk = risk_GARCH; hi/lo 1.25/0.75) when not bear, else 1.0.
Fits of anchor A applied to year A on all four shifts; missing feature -> 1
(then gate keeps 1).

Stages (selection discipline): --stage dev runs [DEV0, DEV1) only (REF first;
must reproduce v421 G2 years 0..3, else STOP).
--stage last runs [DEV0, Y1) for all three rows ONCE.

Usage:
  python run_engine.py --stage dev --shifts 0,1,2,3 --rows REF,C2_B,GARCH_B
  python run_engine.py --stage last --shifts 0,1,2,3 --rows REF,C2_B,GARCH_B
Run through heavy_slot (one heavy job).
"""
from __future__ import annotations

import argparse
import bisect
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
CH = ROOT / "research/tournament/oc_chronos"
VT = ROOT / "research/tournament/oc_voltilt"

sys.path.insert(0, str(HERE))
from tilt_rule import ANCH5, assign_mult, gate_mult  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
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


def load_shift_feat(shift):
    """{(sym, T): (ch_q10, risk_GARCH)} for one phase shift (frozen tables)."""
    c = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                        columns=["sym", "shift", "T", "ch_q10"])
    c = c[c["shift"] == shift]
    v = pd.read_parquet(VT / "vol_features_4shift.parquet",
                        columns=["sym", "shift", "T", "risk_GARCH"])
    v = v[v["shift"] == shift]
    vg = {}
    for sym, t, g in zip(v["sym"], v["T"], v["risk_GARCH"]):
        vg[(str(sym), pd.Timestamp(t))] = float(g)
    out = {}
    for sym, t, q in zip(c["sym"], c["T"], c["ch_q10"]):
        key = (str(sym), pd.Timestamp(t))
        out[key] = (float(q), vg.get(key))
    # rows present only in vol table (early T before Chronos P=512 gate):
    # GARCH leg still needs them; add with ch_q10=None
    for key, g in vg.items():
        if key not in out:
            out[key] = (None, g)
    return out


def build_bear_std(books_idx, opens_btc):
    """Exact v421 bear series on the standard grid (v421_gross_cap.py:69-70).

    btc = opens_btc.reindex(books_idx);
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).
    Returns (idx_ns sorted int64, bear bool array, bear Series).
    """
    btc = opens_btc.reindex(books_idx)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    bear = np.asarray(bear, dtype=bool)
    idx_ns = books_idx.values.astype("datetime64[ns]").astype(np.int64)
    order = np.argsort(idx_ns)
    return idx_ns[order], bear[order], pd.Series(bear, index=books_idx)


def bear_state_at(idx_ns, bear_arr, t):
    """Latest bear state at standard-grid index <= T (ffill, causal)."""
    ts = pd.Timestamp(t)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    pos = bisect.bisect_right(idx_ns, int(ts.value)) - 1
    if pos < 0:
        return False
    return bool(bear_arr[pos])


def run_shift(shift, variants, stage, fits_c2, fits_g):
    """One phase; returns {variant: {run, wins, mult}} (run in v414 format)."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{stage}_s{shift}"
    pod = pof._load(f"pod_bg_{stage}_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_bg_{stage}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_bg_{stage}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_bg_{stage}_{shift}", ROOT / "scripts/forward_v205.py")
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
    # exact v421 bear construction (v421_gross_cap.py:69-72)
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear_arr_full = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear_arr_full] = sb.loc[bear_arr_full].where(sb.loc[bear_arr_full] <= 0, sb.loc[bear_arr_full] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"

    # bear lookup built on the FULL standard grid (causal ffill <= T)
    bidx_ns, bval, _ = build_bear_std(books154.index, _opens_std["BTCUSDT"])

    feat = load_shift_feat(shift)
    T_arr = idx + pd.Timedelta(hours=4)
    anch_ns = np.array([pd.Timestamp(a, tz="UTC").value for a in ANCH5])
    y_of_i = np.clip(np.searchsorted(anch_ns, T_arr.values.astype(np.int64),
                                     side="right") - 1, 0, 4)
    if not last:
        assert int(y_of_i.max()) <= 4, y_of_i.max()
    T_list = list(T_arr)
    # precompute bear per decision index i (holding-bar open T[i], causal ffill)
    T_ns = T_arr.values.astype("datetime64[ns]").astype(np.int64)
    pos = np.searchsorted(bidx_ns, T_ns, side="right") - 1
    bear_i = np.where(pos >= 0, bval[np.clip(pos, 0, len(bval) - 1)], False)
    bear_i = np.where(pos >= 0, bear_i, False).astype(bool)

    def base_mult(variant, y, key):
        if variant == "C2_B":
            f = fits_c2[ANCH5[y]]
            q, _g = feat.get(key, (None, None))
            risk = -q if q is not None and np.isfinite(q) else float("nan")
            return assign_mult(risk, f["direction"], f["q20"], f["q80"], 1.25, 0.75)
        f = fits_g[ANCH5[y]]
        _q, g = feat.get(key, (None, None))
        risk = float(g) if g is not None and np.isfinite(g) else float("nan")
        return assign_mult(risk, f["direction"], f["q20"], f["q80"], 1.25, 0.75)

    out = {}
    for variant in variants:
        t0 = time.time()
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]
        msum = [0.0] * 5
        mcnt = [0] * 5
        bsum = [0] * 5

        def tilt(i, a, variant=variant):
            y = int(y_of_i[i])
            if variant == "REF":
                m = 1.0
            else:
                m0 = base_mult(variant, y, (cols[a], T_list[i]))
                m = gate_mult(m0, bool(bear_i[i]))
            msum[y] += m
            mcnt[y] += 1
            bsum[y] += int(bool(bear_i[i]))
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
        eu.simulate(books_bear, opens, prep, trade=trade, win_start=5, events=ev, **kw)
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
                             bear_share=round(bsum[y] / mcnt[y], 6) if mcnt[y] else None)
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
    ap.add_argument("--rows", default="REF,C2_B,GARCH_B")
    args = ap.parse_args()
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    fits_c2 = json.loads((CH / "fits.json").read_text())
    fits_g = json.loads((VT / "fits.json").read_text())["V_GARCH"]

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
        s, res = run_shift(shift, need, args.stage, fits_c2, fits_g)
        allres.setdefault(s, {}).update(res)
        cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        cur.update(allres)
        cache_path.write_bytes(pickle.dumps(cur))
        print(f"shift {s} cached ({args.stage})", flush=True)
    _stop_hb.set()
    print("STAGE", args.stage, "DONE shifts", sorted(allres), flush=True)


if __name__ == "__main__":
    main()
