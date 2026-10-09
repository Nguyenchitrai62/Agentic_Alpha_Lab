"""oc_lit_position Leg1: H6/H8 book gates on G2 (4-phase engine).

PLAN-fixed (see PLAN.md). Mechanism copied from v426/v426_book_brake.py:
STANDARD book rows (sb index) with bear-filtered weight > 0 get a multiplier,
applied AFTER the bear-book filter and BEFORE the shifted-clock forward fill.
Shorts/flats/NaN-z unchanged. Rows before 2021-09-24 are not gated.

  G2      = R2B1D17BFG2 (rule inv, k 1.0, kd 1.7, bear True, G 2.0), no gate
  O1      = G2 + per-coin longs x0.5 when H6 z > 2.0
  M1      = G2 + all longs x0.5 when BTC MVRV-z > 2.0
  M2      = G2 + all longs x0.5 when z > 2.0, x1.1 when z < 0.0
  O2book  = G2 + per-coin longs x0.5 when H6 z > 1.5 (+ dip skip in sleeve;
            RUN ONLY IF dip_results.json says promising, else skipped)
  CTRL_*  = per-year constant long multiplier = variant realised mean over long
            rows in that anchor year (exposure-matched, no timing)

Step 1 validates the cached G2 (5.41 / 2.588 / 16.91 / 16.82); else stops.
HEAVY: run through heavy_slot (Pool(2), same as v426).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_lit_position_eng --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_lit_position/compute_engine.py
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
sys.path.insert(0, str(HERE))
from signals import (BOOK_MULT, M2_GREED_MULT, O1_THRESH, O2_THRESH,
                     h6_d7_z, h6_mults, h8_asof_z, h8_mults, load_mvrv_daily,
                     load_oi, MAJORS)

ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
EXP_R, EXP_W, EXP_DD, EXP_FULL = 5.41, 2.588, 16.91, 16.82

BASE_CFG = dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_litpos", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_litpos", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1

_MVRV = None


def mvrv():
    global _MVRV
    if _MVRV is None:
        _MVRV = load_mvrv_daily()
    return _MVRV


def gate_frames(sb: pd.DataFrame):
    """Per-row gated books on the STANDARD index. Returns (dict name->df, info)."""
    T = sb.index
    Tts = pd.to_datetime(T, utc=True)
    gated_ok = np.asarray(Tts >= CUTOFF)
    cols = list(sb.columns)
    cix = {c: i for i, c in enumerate(cols)}
    Tns = Tts.values.astype("datetime64[ns]").astype(np.int64)

    # H6 per-coin mults
    m_o1 = np.ones(len(T))
    m_o2 = np.ones(len(T))
    per_coin_o1_share = {}
    per_coin_o2_share = {}
    for sym in MAJORS:
        if sym not in cix:
            continue
        oi_t, oi_v = load_oi(sym)
        _, z = h6_d7_z(Tns, oi_t, oi_v)
        z = np.where(gated_ok, z, np.nan)
        m1c = h6_mults(z, O1_THRESH)
        m2c = h6_mults(z, O2_THRESH)
        # per-coin series -> will be applied cell-wise below; store for info
        per_coin_o1_share[sym] = {
            "eligible": int(np.isfinite(z).sum()),
            "fired": int((np.isfinite(z) & (z > O1_THRESH)).sum())}
        per_coin_o2_share[sym] = {
            "eligible": int(np.isfinite(z).sum()),
            "fired": int((np.isfinite(z) & (z > O2_THRESH)).sum())}
        # stash per-column mult vectors
        if "m_o1_mat" not in locals():
            m_o1_mat = np.ones((len(T), len(cols)))
            m_o2_mat = np.ones((len(T), len(cols)))
        m_o1_mat[:, cix[sym]] = m1c
        m_o2_mat[:, cix[sym]] = m2c
    if "m_o1_mat" not in locals():
        m_o1_mat = np.ones((len(T), len(cols)))
        m_o2_mat = np.ones((len(T), len(cols)))

    # H8 shared mults (broadcast to all coins)
    d = mvrv()
    zh8 = h8_asof_z(d, Tts)
    zh8 = np.where(gated_ok, zh8, np.nan)
    m_m1 = h8_mults(zh8, "M1")
    m_m2 = h8_mults(zh8, "M2")
    m_m1_mat = np.broadcast_to(m_m1[:, None], (len(T), len(cols))).copy()
    m_m2_mat = np.broadcast_to(m_m2[:, None], (len(T), len(cols))).copy()

    variants = {"O1": m_o1_mat, "O2book": m_o2_mat, "M1": m_m1_mat, "M2": m_m2_mat}

    # exposure-matched controls (per-year mean over long rows)
    sbv = sb.to_numpy(float)
    is_long = sbv > 0
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    ctrls = {}
    ctrl_means = {}
    for name, mat in variants.items():
        cm = np.ones((len(T), len(cols)))
        means = []
        for k in range(5):
            sel = np.asarray((Tts >= bounds[k]) & (Tts < bounds[k + 1]))
            denom = int(is_long[sel].sum())
            if denom:
                mu = float(mat[sel][is_long[sel]].mean())
            else:
                mu = 1.0
            means.append(round(mu, 6))
            cm[sel] = mu
        ctrls[f"CTRL_{name}"] = cm
        ctrl_means[name] = means

    out = {}
    for name, mat in {**variants, **ctrls}.items():
        g = sb.copy()
        adj = is_long & (mat < 1.0) if name in variants and name != "M2" else (
            is_long & (mat != 1.0) if name == "M2" else is_long & (np.abs(mat - 1.0) > 1e-12))
        # M2 has both <1 and >1 mults; CTRL has constant !=1 possible; gate all long cells
        if name.startswith("CTRL"):
            adj = is_long & (np.abs(mat - 1.0) > 1e-12)
            # constant applies to every long cell of that year (even where realised mean==1 -> no-op)
            g[:] = np.where(is_long, sbv * mat, sbv)
        else:
            g[:] = np.where(adj, sbv * mat, sbv)
        out[name] = g
    info = dict(
        o1_coverage=per_coin_o1_share, o2_coverage=per_coin_o2_share,
        h8_eligible=int(np.isfinite(zh8).sum()),
        h8_fire_m1=int((np.isfinite(zh8) & (zh8 > 2.0)).sum()),
        h8_fire_m2_hi=int((np.isfinite(zh8) & (zh8 > 2.0)).sum()),
        h8_fire_m2_lo=int((np.isfinite(zh8) & (zh8 < 0.0) & ~(zh8 > 2.0)).sum()),
        ctrl_means=ctrl_means,
        long_cells=int(is_long.sum()),
    )
    for name, mat in variants.items():
        info[f"gated_cells_{name}"] = int(((mat != 1.0) & is_long).sum())
    return out, info


def worker(shift):
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podlp_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histlp_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_lp_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwlp_{shift}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
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
    gated, ginfo = gate_frames(sb)
    # O2 gating: only include O2book/CTRL_O2 if dip screen passed
    dip_path = HERE / "dip_results.json"
    o2_ok = False
    if dip_path.exists():
        try:
            o2_ok = bool(json.loads(dip_path.read_text())["screen"]["o2_engine_allowed"])
        except Exception:
            o2_ok = False
    names = ["G2", "O1", "CTRL_O1", "M1", "CTRL_M1", "M2", "CTRL_M2"]
    if o2_ok:
        names += ["O2book", "CTRL_O2book"]
    fwd = {"G2": sb.reindex(idx, method="ffill").fillna(0.0)}
    for name in names:
        if name == "G2":
            continue
        key = name.replace("CTRL_O2book", "CTRL_O2book").replace("CTRL_", "")
        src = gated[name] if name in gated else gated[key]
        fwd[name] = src.reindex(idx, method="ffill").fillna(0.0)
    print(shift, "gated cells", {k: ginfo.get(f"gated_cells_{k}") for k in ("O1", "O2book", "M1", "M2")},
          "o2_ok", o2_ok, flush=True)
    hist.R2_TABLE = RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet"
    cfgs = {"G2": dict(BASE_CFG), "O1": dict(BASE_CFG), "M1": dict(BASE_CFG),
            "M2": dict(BASE_CFG), "CTRL_O1": dict(BASE_CFG), "CTRL_M1": dict(BASE_CFG),
            "CTRL_M2": dict(BASE_CFG)}
    if o2_ok:
        cfgs["O2book"] = dict(BASE_CFG)
        cfgs["CTRL_O2book"] = dict(BASE_CFG)
    out = {}
    for name in names:
        cfg = cfgs[name]
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]
        kd = cfg.get("kd", 1.0)

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd):
            m = f - 1
            n = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                    continue
                n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
            return mult * kd * base_size(i, a, r, f)
        kw["sleeve_fill_size"] = corr_size
        k = cfg["k"]
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
        if "G" in cfg:
            kw["sleeve_gross_cap"] = cfg["G"]
        eu.simulate(fwd[name], opens, prep, trade=trade, win_start=5, events=[], **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                         eq=(cap["eq"][lv] / base).tolist(),
                         eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    return shift, out


def stats(runs, row, ys):
    yy = [rm.year_reset(runs, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy),
                DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


def main():
    runs_cached = pickle.loads((RD / "v421" / "v421_runs.pkl").read_bytes())
    exp = json.loads((RD / "v421" / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    got = stats(runs_cached, "R2B1D17BFG2", list(range(5)))
    e, mn = v388.mix(runs_cached, "R2B1D17BFG2", Y1 + pd.Timedelta(hours=12))
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    print("cached G2:", got, "full", full, flush=True)
    assert got["R"] == EXP_R and got["W"] == EXP_W and got["DD"] == EXP_DD and full == EXP_FULL, (got, full, exp)
    print("G2 reproduction OK (5.41 / 2.588 / 16.91 / 16.82)", flush=True)

    cache = HERE / "engine_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
    else:
        with Pool(2) as pool:
            runs = dict(pool.map(worker, range(4)))
        cache.write_bytes(pickle.dumps(runs))
    names = list(next(iter(runs.values())).keys())
    out = {"version": "oc_lit_position_engine",
           "rows": {r: stats(runs, r, list(range(5))) for r in names},
           "dev4": {r: stats(runs, r, list(range(4))) for r in names}}
    g1 = Y1 + pd.Timedelta(hours=12)
    for r in names:
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        out["rows"][r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, out["rows"][r], "full", out["rows"][r]["full_path_dd"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "engine_results.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
