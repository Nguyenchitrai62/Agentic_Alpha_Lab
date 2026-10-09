"""oc_mvrvmech engine: frozen G2/M1 mechanism check (FULL + BOOKONLY + DIPONLY).

PLAN-fixed (see PLAN.md). Mechanism copied from oc_mvrvrobust/compute_engine.py:
multiplier on STANDARD book rows with bear-filtered weight > 0, AFTER the bear
filter, BEFORE shifted-clock ffill. Base = G2 (rule inv, k 1.0, kd 1.7,
bear True, G 2.0). Gate costs: maker 0.0002, taker 0.00055, longs 0.0001/8h,
win_start=5, stop-first.

Rows (base friction only):
  FULL: G2_full, M1_full (trade mode, sleeve True)
  BOOKONLY: G2_book, M1_book (sleeve=False, as oc_bookattrib/run_bookonly.py)
  DIPONLY: Dip_only (books=0, sleeve=True; serves both G2/M1 labels)
Each with events/attrib/bars capture. Step 1 validates cached G2+M1 FULL
(5.41/6.192 dev4 etc) bit-exact; else stops.
HEAVY: run through heavy_slot (Pool(2)).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_mvrvmech_eng --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_mvrvmech/compute_mech.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pickle
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parents[1] / "parallel" / "rounds" / "parallel-20260906-r2"
ROOT = HERE.parents[2]
LIT = HERE.parent / "oc_lit_position"
MVRV = HERE.parent / "oc_mvrvrobust"
sys.path.insert(0, str(HERE))
from signals_mvrv import gate_mults

ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
EXP_G2 = dict(R=5.41, W=2.588, DD=16.91, FULL=16.82)
EXP_M1_DEV4 = 6.192
BASE_CFG = dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0)
ROWS = ["G2_full", "M1_full", "G2_book", "M1_book", "Dip_only"]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_mvrvmech", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_mvrvmech", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1


def build_m1_book(sb: pd.DataFrame):
    """M1-gated books on STANDARD index. Returns (m1_df, gated_count)."""
    T = sb.index
    Tts = pd.to_datetime(T, utc=True)
    gated_ok = np.asarray(Tts >= CUTOFF)
    sbv = sb.to_numpy(float)
    is_long = sbv > 0
    z, m = gate_mults(T, 2.0, 365)
    mvec = np.where(gated_ok, m, 1.0)
    g = sb.copy()
    adj = is_long & (mvec[:, None] != 1.0)
    g[:] = np.where(adj, sbv * mvec[:, None], sbv)
    return g, int(((mvec != 1.0) & is_long.any(axis=1)).sum())


def simulate_cfg(eu, v221, v216, hist, pof, books_fwd, opens, prep, idx, cols,
                 shift, sleeve_on: bool):
    import copy
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    O, C, sg = prep["O"], prep["C"], prep["sig4"]
    base_size, rule = kw["sleeve_fill_size"], BASE_CFG["rule"]
    kd = BASE_CFG.get("kd", 1.0)

    def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd):
        mm = f - 1
        n = 0
        for b in range(len(cols)):
            if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, mm, b]) and np.isfinite(sg[i][b])):
                continue
            n += float(C[i, mm, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
        mult = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
        return mult * kd * base_size(i, a, r, f)
    kw["sleeve_fill_size"] = corr_size
    kw["risk_mult"] = lambda i, e: 1.0
    kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * kd
    kw["sleeve_gross_cap"] = BASE_CFG["G"]
    kw["sleeve"] = bool(sleeve_on)
    cap = {}
    eu.summarize = lambda idx_, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx_, eq=eq.copy(), eq_min=eq_min.copy(),
        eq_max=(eq.copy() if eq_max is None else eq_max.copy()),
        stats=dict(stats)) or {}
    events, attrib, bars = [], [], []
    eu.simulate(books_fwd, opens, prep, trade=trade, events=events,
                attrib=attrib, bars=bars, win_start=5, **kw)
    return cap, events, attrib, bars


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podmech_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histmech_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_mech_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwmech_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    m1_std, gated = build_m1_book(sb)
    print(shift, "M1 gated standard bars:", gated, flush=True)
    fwd_g2 = sb.reindex(idx, method="ffill").fillna(0.0)
    fwd_m1 = m1_std.reindex(idx, method="ffill").fillna(0.0)
    fwd_zero = pd.DataFrame(0.0, index=idx, columns=cols)
    hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
    cfgs = [("G2_full", fwd_g2, True), ("M1_full", fwd_m1, True),
            ("G2_book", fwd_g2, False), ("M1_book", fwd_m1, False),
            ("Dip_only", fwd_zero, True)]
    out = {}
    for name, fwd, sleeve_on in cfgs:
        cap, events, attrib, bars = simulate_cfg(
            eu, v221, v216, hist, pof, fwd, opens, prep, idx, cols, shift, sleeve_on)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        t8 = cap["idx"][lv] + pd.Timedelta(hours=8)
        entry = dict(
            t=[str(x) for x in t8],
            eq=(cap["eq"][lv] / base).tolist(),
            eq_min=(cap["eq_min"][lv] / base).tolist(),
            eq_end=float(cap["eq"][lv][-1] / base),
            stats={k: (round(float(v), 6) if isinstance(v, float) else v)
                   for k, v in cap["stats"].items()},
            n_events=len(events),
            n_bars_live=int(lv.sum()),
        )
        # slim attrib: per live bar (t, book_sum, sleeve)
        a_idx = [a[0] for a in attrib]
        # attrib t = idx+4h; live mask on decision idx
        a_live = np.asarray([(pd.Timestamp(t) - pd.Timedelta(hours=4) >= live0) and
                             (pd.Timestamp(t) - pd.Timedelta(hours=4) < live1) for t in a_idx])
        entry["attrib"] = dict(
            t=[str(t) for t, k in zip(a_idx, a_live) if k],
            book=[float(np.asarray(a[1]).sum()) for a, k in zip(attrib, a_live) if k],
            sleeve=[float(a[2]) for a, k in zip(attrib, a_live) if k],
        )
        # slim bars: governor, scale, equity, |target| per live bar
        b_live = np.asarray([(b["t"] >= live0) and (b["t"] < live1) for b in bars])
        entry["bars"] = dict(
            t=[str(b["t"]) for b, k in zip(bars, b_live) if k],
            g=[float(b["governor"]) for b, k in zip(bars, b_live) if k],
            scale=[float(b["scale"]) for b, k in zip(bars, b_live) if k],
            equity=[float(b["equity"]) for b, k in zip(bars, b_live) if k],
            abs_tgt=[float(np.abs(np.asarray(b["target"])).sum()) for b, k in zip(bars, b_live) if k],
        )
        # events: keep all (needed for E2/E3/E4 trade tape + rung counts)
        entry["events"] = [
            {k: (str(v) if k == "t" else (float(v) if isinstance(v, (np.floating, np.integer)) else v))
             for k, v in e.items()} for e in events
        ]
        out[name] = entry
        print(shift, name, round(entry["eq_end"], 3), "ev", len(events), flush=True)
    return shift, out


def stats_of(runs, row, ys):
    runs_slim = {s: {row: {"t": runs[s][row]["t"], "eq": runs[s][row]["eq"],
                            "eq_min": runs[s][row]["eq_min"]}} for s in runs}
    yy = [rm.year_reset(runs_slim, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy),
                DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


def main():
    runs_cached = pickle.loads((MVRV / "engine_runs.pkl").read_bytes())
    got_g2 = stats_of(runs_cached, "G2", list(range(5)))
    got_m1 = stats_of(runs_cached, "M1", list(range(4)))
    e, mn = v388.mix(runs_cached, "G2", Y1 + pd.Timedelta(hours=12))
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    print("cached G2:", got_g2, "full", full, flush=True)
    print("cached M1 dev4:", got_m1, flush=True)
    assert (got_g2["R"], got_g2["W"], got_g2["DD"], full) == (
        EXP_G2["R"], EXP_G2["W"], EXP_G2["DD"], EXP_G2["FULL"]), got_g2
    assert got_m1["R"] == EXP_M1_DEV4, got_m1
    print("G2+M1 reproduction reference OK", flush=True)

    cache = HERE / "engine_mech.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
        assert set(runs[0].keys()) == set(ROWS), sorted(runs[0].keys())
        print("loaded cached engine_mech.pkl", flush=True)
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
        print("wrote engine_mech.pkl", flush=True)
    # bit-exact check of FULL legs vs cached MVRV runs
    for row_new, row_old in (("G2_full", "G2"), ("M1_full", "M1")):
        for s in range(4):
            a = np.asarray(runs[s][row_new]["eq"], float)
            b = np.asarray(runs_cached[s][row_old]["eq"], float)
            assert a.shape == b.shape and np.array_equal(a, b), (row_new, s)
            am = np.asarray(runs[s][row_new]["eq_min"], float)
            bm = np.asarray(runs_cached[s][row_old]["eq_min"], float)
            assert am.shape == bm.shape and np.array_equal(am, bm), (row_new, s)
    print("FULL G2/M1 bit-exact vs oc_mvrvrobust cache", flush=True)
    # Dip_only sanity: books were zero so gate is a no-op (single run serves both labels)
    g1 = Y1 + pd.Timedelta(hours=12)
    out = {"version": "oc_mvrvmech_engine",
           "rows": {r: stats_of(runs, r, list(range(5))) for r in ROWS},
           "dev4": {r: stats_of(runs, r, list(range(4))) for r in ROWS}}
    for r in ROWS:
        e, mn = v388.mix({s: {r: {"t": runs[s][r]["t"], "eq": runs[s][r]["eq"],
                                  "eq_min": runs[s][r]["eq_min"]}} for s in runs}, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(
            100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, out["rows"][r], "full", out["rows"][r]["full_path_dd"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "tmp" / "mech_years.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
