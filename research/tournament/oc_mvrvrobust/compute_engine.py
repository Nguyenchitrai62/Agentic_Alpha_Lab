"""oc_mvrvrobust engine: frozen M1 robustness (jitters, A1M1, LOEO, frictions S1-S5).

PLAN-fixed (see PLAN.md). Mechanism copied from v426/v426_book_brake.py via
oc_lit_position/compute_engine.py: multiplier on STANDARD book rows with
bear-filtered weight > 0, AFTER the bear filter, BEFORE shifted-clock ffill.
Rows before 2021-09-24 not gated. Base = G2 (rule inv, k 1.0, kd 1.7,
bear True, G 2.0). Gate costs: maker 0.0002, taker 0.00055, longs 0.0001/8h,
win_start=5, stop-first.

Rows (base friction):
  G2, M1 (frozen thr 2.0/win 365), J_T175, J_T225, J_W270, J_W450,
  A1M1 (M1 gate then Amihud A1 tilt, labelled post-hoc),
  LOEO_E2/E3/E4 (M1 with that merged episode forced to mult 1).
Frictions (M1 vs G2, v421-audit family as in robust_d13.py):
  S1 cost stress MAKER 0.0004/TAKER 0.0012 (globals patch), win_start 5;
  S2 win_start 15/sleeve_start 16; S3 30/31; S4 stop_slip 0.5;
  S5 Bybit 1m from 2021-11-15 (same-window G2 vs M1).
Step 1 validates cached G2+M1 (5.41/6.192 dev4 etc); else stops.
HEAVY: run through heavy_slot (Pool(2)).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_mvrvrobust_eng --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_mvrvrobust/compute_engine.py
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
XS_DIR = HERE.parent / "oc_lit_xs"
sys.path.insert(0, str(HERE))
from signals_mvrv import gate_mults

ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
S5_START = pd.Timestamp("2021-11-15", tz="UTC")
EXP_G2 = dict(R=5.41, W=2.588, DD=16.91, FULL=16.82)
EXP_M1_DEV4 = 6.192
BASE_CFG = dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0)
BASE_ROWS = ["G2", "M1", "J_T175", "J_T225", "J_W270", "J_W450",
             "A1M1", "LOEO_E2", "LOEO_E3", "LOEO_E4"]
FRIC_ROWS = ["G2_S1", "G2_S2", "G2_S3", "G2_S4", "G2_S5",
             "M1_S1", "M1_S2", "M1_S3", "M1_S4", "M1_S5"]
ALL_ROWS = BASE_ROWS + FRIC_ROWS
JITTER_CFG = {"J_T175": (1.75, 365), "J_T225": (2.25, 365),
              "J_W270": (2.0, 270), "J_W450": (2.0, 450)}
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_mvrvrobust", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_mvrvrobust", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1
_xs = _load("xs_signal_mvrvrobust", XS_DIR / "xs_signal.py")


def _episodes():
    ev = json.loads((HERE / "events.json").read_text())["episodes"]
    tot = sum(e["nbars"] for e in ev)
    out = {}
    for e in ev:
        if e["nbars"] / tot >= 0.05:
            out[f"LOEO_E{e['episode']}"] = (pd.Timestamp(e["start"]), pd.Timestamp(e["end"]))
    return out


def build_base_books(sb: pd.DataFrame):
    """Gated books on STANDARD index for BASE_ROWS. Returns (dict, info)."""
    T = sb.index
    Tts = pd.to_datetime(T, utc=True)
    gated_ok = np.asarray(Tts >= CUTOFF)
    cols = list(sb.columns)
    sbv = sb.to_numpy(float)
    is_long = sbv > 0
    is_nz = sbv != 0
    out = {}
    info = {}

    def apply_long(mvec):
        g = sb.copy()
        mvec = np.where(gated_ok, mvec, 1.0)
        adj = is_long & (mvec[:, None] != 1.0)
        g[:] = np.where(adj, sbv * mvec[:, None], sbv)
        return g, mvec

    # M1 frozen
    z, m = gate_mults(T, 2.0, 365)
    out["M1"], mv = apply_long(m)
    info["M1_gated"] = int(((mv != 1.0) & is_long.any(axis=1)).sum())
    # jitters
    for name, (thr, win) in JITTER_CFG.items():
        zj, mj = gate_mults(T, thr, win)
        out[name], mvj = apply_long(mj)
        info[f"{name}_gated_bars"] = int((mvj != 1.0).sum())
    # A1M1: M1 gate then A1 tilt (both legs)
    frames, _ = _xs.tilt_frames(T, cols)
    a1 = frames["A1"]
    a1.loc[Tts < CUTOFF] = 1.0
    a1v = a1.to_numpy(float)
    g = sb.copy()
    m1v = np.where(gated_ok, m, 1.0)
    comb = np.where(is_long, m1v[:, None] * a1v, np.where(is_nz, a1v, 1.0))
    g[:] = np.where(is_nz, sbv * comb, sbv)
    out["A1M1"] = g
    # LOEO rows
    for name, (s, e) in _episodes().items():
        mask = np.asarray((Tts >= s) & (Tts <= e))
        mlo = np.where(mask, 1.0, np.where(gated_ok, m, 1.0))
        g = sb.copy()
        adj = is_long & (mlo[:, None] != 1.0)
        g[:] = np.where(adj, sbv * mlo[:, None], sbv)
        out[name] = g
        info[f"{name}_removed_bars"] = int(mask.sum())
    return out, info


def bybit_minutes():
    out = {}
    d = ROOT / "data" / "raw" / "bybit_linear_1m_20261004"
    for s in SYMS:
        m = pd.read_parquet(d / f"{s}_1m.parquet",
                            columns=["open_time", "open", "high", "low", "close"])
        m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
        out[s] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return out


def simulate_one(eu, v221, v216, hist, pof, books_fwd, opens, prep, idx, cols,
                 shift, extra, maker_taker=None):
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
    cap = {}
    eu.summarize = lambda idx_, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx_, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    old = None
    try:
        if maker_taker is not None:
            old = (eu.simulate.__globals__["MAKER"], eu.simulate.__globals__["TAKER"])
            eu.simulate.__globals__["MAKER"], eu.simulate.__globals__["TAKER"] = maker_taker
        eu.simulate(books_fwd, opens, prep, trade=trade, events=[], **kw, **extra)
    finally:
        if old is not None:
            eu.simulate.__globals__["MAKER"], eu.simulate.__globals__["TAKER"] = old
    return cap


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podmv_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histmv_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_mv_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwmv_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    # --- Binance block (base rows + S1..S4) ---
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    base_books, ginfo = build_base_books(sb)
    fwd = {"G2": sb.reindex(idx, method="ffill").fillna(0.0)}
    for name, g in base_books.items():
        fwd[name] = g.reindex(idx, method="ffill").fillna(0.0)
    # friction book variants share base books (G2/M1); only sim kwargs change
    fwd["G2_S1"] = fwd["G2"]
    fwd["M1_S1"] = fwd["M1"]
    fwd["G2_S2"] = fwd["G2"]
    fwd["M1_S2"] = fwd["M1"]
    fwd["G2_S3"] = fwd["G2"]
    fwd["M1_S3"] = fwd["M1"]
    fwd["G2_S4"] = fwd["G2"]
    fwd["M1_S4"] = fwd["M1"]
    hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
    FRIC_EXTRA = {
        "G2_S1": (dict(win_start=5), (0.0004, 0.0012)),
        "M1_S1": (dict(win_start=5), (0.0004, 0.0012)),
        "G2_S2": (dict(win_start=15, sleeve_start=16), None),
        "M1_S2": (dict(win_start=15, sleeve_start=16), None),
        "G2_S3": (dict(win_start=30, sleeve_start=31), None),
        "M1_S3": (dict(win_start=30, sleeve_start=31), None),
        "G2_S4": (dict(win_start=5, stop_slip=0.5), None),
        "M1_S4": (dict(win_start=5, stop_slip=0.5), None),
    }
    out = {}
    seq = BASE_ROWS + [r for r in FRIC_ROWS if not r.endswith("_S5")]
    for name in seq:
        extra, mt = (dict(win_start=5), None) if name in BASE_ROWS else FRIC_EXTRA[name]
        cap = simulate_one(eu, v221, v216, hist, pof, fwd[name], opens, prep,
                           idx, cols, shift, extra, mt)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    # --- Bybit S5 block (truncated window, same for G2/M1) ---
    M5 = bybit_minutes()
    std_idx5 = books154.index[books154.index >= S5_START] + sh
    opens5, prep5 = pof.prep_idx(M5, std_idx5, shift, list(books154.columns))
    del M5
    idx5, cols5 = prep5["idx"], list(prep5["cols"])
    live0_5 = S5_START + sh
    eu.v110.START, eu.v110.END = live0_5, live1
    fwd5 = {k: fwd[k].reindex(idx5, method="ffill").fillna(0.0) for k in ("G2", "M1")}
    for name, src in (("G2_S5", "G2"), ("M1_S5", "M1")):
        cap = simulate_one(eu, v221, v216, hist, pof, fwd5[src], opens5, prep5,
                           idx5, cols5, shift, dict(win_start=5), None)
        lv = np.asarray((cap["idx"] >= live0_5) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    print(shift, "gate_info", ginfo, flush=True)
    return shift, out


def stats(runs, row, ys):
    yy = [rm.year_reset(runs, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy),
                DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


def main():
    runs_cached = pickle.loads((LIT / "engine_runs.pkl").read_bytes())
    got_g2 = stats(runs_cached, "G2", list(range(5)))
    got_m1 = stats(runs_cached, "M1", list(range(4)))
    e, mn = v388.mix(runs_cached, "G2", Y1 + pd.Timedelta(hours=12))
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    print("cached G2:", got_g2, "full", full, flush=True)
    print("cached M1 dev4:", got_m1, flush=True)
    assert (got_g2["R"], got_g2["W"], got_g2["DD"], full) == (
        EXP_G2["R"], EXP_G2["W"], EXP_G2["DD"], EXP_G2["FULL"]), got_g2
    assert got_m1["R"] == EXP_M1_DEV4, got_m1
    print("G2+M1 reproduction OK", flush=True)

    cache = HERE / "engine_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
        assert set(runs[0].keys()) == set(ALL_ROWS), sorted(runs[0].keys())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
    g1 = Y1 + pd.Timedelta(hours=12)
    out = {"version": "oc_mvrvrobust_engine",
           "rows": {r: stats(runs, r, list(range(5))) for r in ALL_ROWS
                    if not r.endswith("_S5")},
           "dev4": {r: stats(runs, r, list(range(4))) for r in ALL_ROWS
                    if not r.endswith("_S5")}}
    for r in list(out["rows"]):
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(
            100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, out["rows"][r], "full", out["rows"][r]["full_path_dd"], flush=True)
    # S5: same-window comparison only (truncated live window)
    out["s5_note"] = ("S5 runs on the truncated 2021-11-15..2026-09-23 window; "
                      "year_reset year-0 is partial; compare M1_S5 vs G2_S5 only.")
    out["s5"] = {r: stats(runs, r, list(range(5))) for r in ("G2_S5", "M1_S5")}
    print("S5", out["s5"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "engine_results.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
