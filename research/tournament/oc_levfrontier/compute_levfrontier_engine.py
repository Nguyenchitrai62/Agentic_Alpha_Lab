"""oc_levfrontier engine: ONLY the 6 missing BOT legs (kd=2.0 family on base/S5).

Mechanism = verbatim copy of oc_c2frontier/compute_frontier_engine.py
(= oc_chronos/run_engine.py = oc_b7c2/run_engine.py = v414 pipe v321,
corr-aware inv sizes, bear books, win_start=5, gate costs inside the engine)
with kd/G parameterised. Here EVERY row has G=2.0 (G2's gross cap binds),
bear True, F 2.5, risk_mult 1.0, sleeve_risk_budget 0.26*1*kd:

  G2K20      = kd 2.0, tilt 1 (v422 definition)
  G2K20_C2   = kd 2.0 + C2 tilt (frozen oc_chronos fits.json, risk=-ch_q10,
               hi 1.25/lo 0.75, missing -> 1; anchor-y fit for year y, all shifts)
  G2K20_B7   = kd 2.0 + B7 boost (frozen boost_mult_4shift.parquet mult_B7,
               1.5 in (tc,tc+7d] else 1.0, market-wide per shift)
  G2K20_B7C2 = kd 2.0 + PRODUCT m_B7*m_C2 uncapped (oc_b7c2 B7C2)

S5 (Bybit) = exact copy of oc_c2bybit S5: bybit_minutes() from
data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet; live0 = 2021-11-15 + shift;
standard index filtered to >= 2021-11-15 before shift; win_start=5.
Year 2021 on S5 is a SHORT window (labelled everywhere).

Caches: tmp/runs_<CFG>_<FRIC>.pkl with {shift: {cfg: {run, wins, mult}}}
(resume-safe per shift). HEAVY: run through heavy_slot (one heavy process).

Usage:
  python compute_levfrontier_engine.py --job G2K20_B7_base --shifts 0,1,2,3
  python compute_levfrontier_engine.py --job all --shifts 0,1,2,3
Jobs: G2K20_S5, G2K20_C2_S5, G2K20_B7_base, G2K20_B7_S5, G2K20_B7C2_base,
      G2K20_B7C2_S5, all.
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
from lev_rule import ANCH5, assign_c2, stack_mult  # noqa: E402

DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")
HEARTBEAT_S = 600
F_FLUSH = 2.5

# cfg -> (kd, tilt mode)
CONFIGS = {
    "G2K20": dict(kd=2.0, tilt="none"),
    "G2K20_C2": dict(kd=2.0, tilt="C2"),
    "G2K20_B7": dict(kd=2.0, tilt="B7"),
    "G2K20_B7C2": dict(kd=2.0, tilt="B7C2"),
}

JOBS = {
    "G2K20_S5": ("G2K20", "S5"),
    "G2K20_C2_S5": ("G2K20_C2", "S5"),
    "G2K20_B7_base": ("G2K20_B7", "base"),
    "G2K20_B7_S5": ("G2K20_B7", "S5"),
    "G2K20_B7C2_base": ("G2K20_B7C2", "base"),
    "G2K20_B7C2_S5": ("G2K20_B7C2", "S5"),
}

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


def run_shift(shift, cfg, fric, fits):
    """One phase; returns (shift, {cfg: {run, wins, mult}})."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    tag = f"{cfg}_{fric}_s{shift}"
    pod = pof._load(f"pod_lev_{cfg}_{fric}_{shift}",
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_lev_{cfg}_{fric}_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_lev_{cfg}_{fric}_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_lev_{cfg}_{fric}_{shift}", ROOT / "scripts/forward_v205.py")
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

    kd = CONFIGS[cfg]["kd"]
    mode = CONFIGS[cfg]["tilt"]
    need_stack = mode in ("B7", "B7C2", "C2")
    if need_stack:
        exact, t_ns, arr, feat = load_shift_stack(shift)
    else:
        exact, t_ns, arr, feat = {}, None, None, {}
    T_arr = idx + pd.Timedelta(hours=4)
    anch_ns = np.array([pd.Timestamp(a, tz="UTC").value for a in ANCH5])
    y_of_i = np.clip(np.searchsorted(anch_ns, T_arr.values.astype(np.int64),
                                     side="right") - 1, 0, 4)
    T_list = list(T_arr)

    t0 = time.time()
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    O, C, sg = prep["O"], prep["C"], prep["sig4"]
    base_size = kw["sleeve_fill_size"]
    msum = [0.0] * 5
    mcnt = [0] * 5
    miss_c2 = 0

    def tilt(i, a):
        nonlocal miss_c2
        y = int(y_of_i[i])
        if mode == "none":
            m = 1.0
        else:
            T = T_list[i]
            mb = b7_for(T, exact, t_ns, arr) if mode in ("B7", "B7C2") else 1.0
            if mode in ("C2", "B7C2"):
                q = feat.get((cols[a], pd.Timestamp(T)))
                if q is None or not np.isfinite(q):
                    miss_c2 += 1
                    mc = 1.0
                else:
                    f = fits[ANCH5[y]]
                    mc = assign_c2(-q, f["direction"], f["q20"], f["q80"])
            else:
                mc = 1.0
            if mode == "C2":
                m = mc
            elif mode == "B7":
                m = mb
            else:
                m = stack_mult(mb, mc)
        msum[y] += m
        mcnt[y] += 1
        return m

    def corr_size(i, a, r, f, base_size=base_size):
        m = f - 1
        n = 0
        for b in range(len(cols)):
            if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                continue
            n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - F_FLUSH * float(sg[i][b]))
        mult = 1.0 / (1 + n)
        return mult * kd * tilt(i, a) * base_size(i, a, r, f)

    kw["sleeve_fill_size"] = corr_size
    kw["risk_mult"] = lambda i, e: 1.0
    kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
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
    print(f"{tag} eq_end={run['eq'][-1]:.4f} miss_c2={miss_c2} "
          f"elapsed={(time.time() - t0) / 60:.1f}min", flush=True)
    del ev, opens, prep, books_bear
    gc.collect()
    return shift, {cfg: dict(run=run, wins=years, mult=mult, miss_c2=int(miss_c2))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", default="all",
                    help="one of " + ",".join(list(JOBS) + ["all"]))
    ap.add_argument("--shifts", default="0,1,2,3")
    args = ap.parse_args()
    if args.job == "all":
        jobs = list(JOBS)
    else:
        assert args.job in JOBS, args.job
        jobs = [args.job]
    shifts = [int(s) for s in args.shifts.split(",")]
    fits = json.loads((CH / "fits.json").read_text())
    TMP.mkdir(parents=True, exist_ok=True)

    hb = threading.Thread(target=heartbeat,
                          args=(f"levfrontier {args.job}",), daemon=True)
    hb.start()
    for job in jobs:
        cfg, fric = JOBS[job]
        cache_path = TMP / f"runs_{cfg}_{fric}.pkl"
        allres = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
        for shift in shifts:
            if shift in allres and cfg in allres[shift]:
                print(f"job {job} shift {shift}: cached, skip", flush=True)
                continue
            s, res = run_shift(shift, cfg, fric, fits)
            allres.setdefault(s, {}).update(res)
            cur = pickle.loads(cache_path.read_bytes()) if cache_path.exists() else {}
            cur.update(allres)
            cache_path.write_bytes(pickle.dumps(cur))
            print(f"job {job} shift {s} cached", flush=True)
    _stop_hb.set()
    print("DONE jobs", jobs, flush=True)


if __name__ == "__main__":
    main()
