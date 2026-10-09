"""oc_cboostctrl engine: G2 path with B7 boost vs exposure-matched controls.

Mechanism = exact copy of oc_cascadeboost/run_engine.py (= oc_chronos/run_engine.py
= v414 pipe v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine) plus a
per-(holding bar) multiplier mult_row(i) on the corr-aware dip sizes; budget
unchanged, book leg byte-identical to G2.

Rows (ONLY these, pre-registered):
  REF    = G2 unchanged (mult 1.0).
  B7     = cascade boost (read-only oc_cascadeboost/boost_mult_4shift.parquet
           mult_B7: 1.5 in 7d window else 1.0; market-wide per shift).
  CTRL_C = constant per-year mult c_y (tmp/ctrlC_{stage}.json from B7's own run).
  R00..R19 = random 7-day x1.5 windows (tmp/ctrlR_starts.pkl frozen starts).
Missing mult -> 1.0. G2 dip gross cap 2.0 and every other G2 limit bind.

Stages: --stage dev runs [DEV0, DEV1); --stage last runs [DEV0, Y1) ONCE.
Run through heavy_slot (one heavy job at a time).
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
B7PQ = ROOT / "research/tournament/oc_cascadeboost/boost_mult_4shift.parquet"
TMP = HERE / "tmp"
CACHE_DEV = TMP / "runs_dev.pkl"
CACHE_LAST = TMP / "runs_last.pkl"

sys.path.insert(0, str(HERE))
from ctrl_rule import ANCH5, BOOST, N_DAYS, N_SEEDS, NS_DAY  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600
R_ROWS = [f"R{j:02d}" for j in range(N_SEEDS)]
ALLOWED = {"REF", "B7", "CTRL_C"} | set(R_ROWS)
SPAN = int(N_DAYS) * NS_DAY

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


def load_b7_mult(shift):
    """{T: mult_B7} + sorted t_ns for causal ffill fallback."""
    d = pd.read_parquet(B7PQ, columns=["shift", "T", "mult_B7"])
    d = d[d["shift"] == shift].sort_values("T")
    t = pd.to_datetime(d["T"], utc=True)
    exact = {pd.Timestamp(tt): float(a) for tt, a in zip(t, d["mult_B7"])}
    t_ns = t.values.astype("datetime64[ns]").astype(np.int64)
    arr = d["mult_B7"].to_numpy(dtype=float)
    return exact, t_ns, arr


def load_ctrlR_shift(shift):
    """{j: sorted combined start-ns array} for this shift (all years)."""
    with open(TMP / "ctrlR_starts.pkl", "rb") as f:
        blob = pickle.load(f)
    starts = blob["starts"]
    out = {}
    for j in range(N_SEEDS):
        acc = []
        for y in range(5):
            acc.extend(starts[(y, shift, j)])
        out[j] = np.array(sorted(acc), dtype=np.int64)
    return out


def r_mult(T_ns: int, ts: np.ndarray) -> float:
    if ts.size == 0:
        return 1.0
    pos = int(np.searchsorted(ts, np.int64(T_ns), side="left")) - 1
    if pos < 0:
        return 1.0
    return 1.5 if (np.int64(T_ns) - ts[pos] <= SPAN) else 1.0


def run_shift(shift, variants, stage):
    """One phase; returns {variant: {run, wins, mult}} (run in v414 format)."""
    assert BOOST == 1.5
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{stage}_s{shift}"
    pod = pof._load(f"pod_cc_{stage}_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_cc_{stage}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_cc_{stage}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_cc_{stage}_{shift}", ROOT / "scripts/forward_v205.py")
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
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"

    exact, t_ns, arr = load_b7_mult(shift)
    ctrlR = load_ctrlR_shift(shift) if any(v in R_ROWS for v in variants) else {}
    ctrlC = None
    if "CTRL_C" in variants:
        cpath = TMP / ("ctrlC_last.json" if last else "ctrlC_dev.json")
        ctrlC = json.loads(cpath.read_text())
    T_arr = idx + pd.Timedelta(hours=4)
    T_ns = T_arr.values.astype("datetime64[ns]").astype(np.int64)
    anch_ns = np.array([pd.Timestamp(a, tz="UTC").value for a in ANCH5])
    y_of_i = np.clip(np.searchsorted(anch_ns, T_ns, side="right") - 1, 0, 4)
    T_list = list(T_arr)

    def mult_b7(t):
        hit = exact.get(pd.Timestamp(t))
        if hit is not None:
            return float(hit)
        q = pd.Timestamp(t)
        if q.tzinfo is None:
            q = q.tz_localize("UTC")
        pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
        return float(arr[pos]) if pos >= 0 else 1.0

    out = {}
    for variant in variants:
        t0 = time.time()
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size = kw["sleeve_fill_size"]
        msum = [0.0] * 5
        mcnt = [0] * 5
        if variant in R_ROWS:
            ts = ctrlR[int(variant[1:])]

        def tilt(i, a, variant=variant):
            y = int(y_of_i[i])
            if variant == "REF":
                m = 1.0
            elif variant == "B7":
                m = mult_b7(T_list[i])
            elif variant == "CTRL_C":
                m = float(ctrlC.get(str(y), {"c": 1.0})["c"])
            else:
                m = r_mult(int(T_ns[i]), ts)
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
            ts216 = v216.v213.trade_stats(evy)
            nb, wb = 0, 0
            for _k, v in (ts216.items() if isinstance(ts216, dict) else []):
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
    del opens, prep, books
    gc.collect()
    return shift, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "last"], required=True)
    ap.add_argument("--shifts", default="0,1,2,3")
    ap.add_argument("--rows", required=True)
    args = ap.parse_args()
    shifts = [int(s) for s in args.shifts.split(",")]
    variants = [r.strip() for r in args.rows.split(",") if r.strip()]
    assert set(variants) <= ALLOWED and variants, variants

    hb = threading.Thread(target=heartbeat, args=(f"run_engine {args.stage} {args.rows}",), daemon=True)
    hb.start()
    TMP.mkdir(exist_ok=True)
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
