"""oc_lit_calendar engine (4-phase, HEAVY via heavy_slot, Pool(2)).

PLAN-fixed. Mechanism copied from v426/v426_book_brake.py: per-(T,sym)
book multipliers on STANDARD rows AFTER the v410 bear-book filter and BEFORE
the shifted-clock forward fill. G2 = R2B1D17BFG2 (rule inv, k 1.0, kd 1.7,
bear True, G 2.0), loaded from the v421 cache and reproduced to the digit
first, else stop. Rows before 2021-09-24 never gated (v426 convention).
Gate costs/fills/funding = gate model in PLAN (engine handles it).

Rows (19): G2 (cached) + 9 variants (V1 V2 V3 S1 S2 S3 G1H G2H G3H) + 9
exposure-matched controls (C_V1 C_V2 C_V3 C_S1 C_S2 C_S3 C_G1 C_G2 C_G3).
Variant/controls definitions: PLAN.md. G2H dip leg: dip fill-size x0.20/0.26
in-window (time-varying sleeve_fill_size scale); C_G2 dip: constant per-year
mean scale. All other rows dip scale 1.0.

This script scores dev4 (years 0-3) for selection and checks the G2 5y repro.
The most-recent year (index 4) is appended ONLY for G2/candidate/control by
make_results.py (light). Variant 2025 equities in this cache are never read
for non-candidates.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_lit_calendar --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_lit_calendar/run_engine.py
"""
from __future__ import annotations

import datetime as _dt
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
TABLES = RD / "v376" / "tables_hidden"

RUNS = {"R2B1D17BFG2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0),
        "V1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="V1"),
        "V2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="V2"),
        "V3": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="V3"),
        "S1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="S1"),
        "S2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="S2"),
        "S3": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="S3"),
        "G1H": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="G1H"),
        "G2H": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="G2H"),
        "G3H": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="G3H"),
        "C_V1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_V1"),
        "C_V2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_V2"),
        "C_V3": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_V3"),
        "C_S1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_S1"),
        "C_S2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_S2"),
        "C_S3": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_S3"),
        "C_G1": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_G1"),
        "C_G2": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_G2"),
        "C_G3": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_G3"),
        # Disclosed extras (2026-10-07): corrected exposure controls for the
        # side-specific families (first-run C_V3/C_S1/C_S2/C_S3 were no-ops).
        "C_V3_FIX": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_V3_FIX"),
        "C_S1_FIX": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_S1_FIX"),
        "C_S2_FIX": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_S2_FIX"),
        "C_S3_FIX": dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, gate="C_S3_FIX")}
CACHED = {"R2B1D17BFG2": ("research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl", "R2B1D17BFG2")}
VARIANTS = ["V1", "V2", "V3", "S1", "S2", "S3", "G1H", "G2H", "G3H"]
CONTROLS = ["C_V1", "C_V2", "C_V3", "C_S1", "C_S2", "C_S3", "C_G1", "C_G2", "C_G3"]
CTRL_OF = dict(zip(VARIANTS, CONTROLS))
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
END = pd.Timestamp("2026-09-24", tz="UTC")
BOUNDS = ANCH + [END]
CUTOFF21 = pd.Timestamp("2021-09-24", tz="UTC")
DIP_SCALE = 0.20 / 0.26
HALVINGS = [_dt.date(2012, 11, 28), _dt.date(2016, 7, 9),
            _dt.date(2020, 5, 11), _dt.date(2024, 4, 19)]
EXP_R, EXP_W, EXP_DD, EXP_FULL = 5.41, 2.588, 16.91, 16.82
EXP_YEARS = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27), (4.648, 12.9)]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_litcal", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("reset_for_litcal", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
Y1 = v388.Y1

_PANEL = None


def panel_flags():
    """Per-T calendar flags from panel.parquet (deduped across syms)."""
    global _PANEL
    if _PANEL is None:
        p = pd.read_parquet(HERE / "panel.parquet",
                            columns=["T", "tom_in", "on_in", "onwide_in", "halv_in", "halv525_in"])
        p["T"] = pd.to_datetime(p["T"], utc=True)
        _PANEL = p.drop_duplicates(subset=["T"]).set_index("T").sort_index()
    return _PANEL


def halv_in_for(dates) -> np.ndarray:
    """D(date) in [400,900]? (same constants as make_panel; tested equal)."""
    out = np.zeros(len(dates), dtype=bool)
    for i, d in enumerate(dates):
        dd = d.date() if hasattr(d, "date") else d
        past = [h for h in HALVINGS if h <= dd]
        D = (dd - max(past)).days
        out[i] = 400 <= D <= 900
    return out


def gate_books(sb: pd.DataFrame):
    """Variant + control book DataFrames on the STANDARD index + dip info.

    Returns (books: dict gate->DataFrame, dip_year_const: dict year->d_y for
    C_G2, info: dict with realised means/controls/shares per variant-year).
    """
    pf = panel_flags()
    T = sb.index
    Tts = pd.to_datetime(T, utc=True)
    ok = (Tts >= CUTOFF21).to_numpy() if hasattr(Tts >= CUTOFF21, "to_numpy") else np.asarray(Tts >= CUTOFF21)
    pre = ~ok
    get = lambda c: pf[c].reindex(Tts, fill_value=False).to_numpy(bool) & ok
    tom = get("tom_in")
    on = get("on_in")
    onw = get("onwide_in")
    halv = get("halv_in")
    halv525 = get("halv525_in")
    sbv = sb.to_numpy(float)
    n, m = sbv.shape

    def uni(mask, in_v, out_v):
        col = np.where(mask, in_v, np.where(ok, out_v, 1.0))
        return sbv * col[:, None]

    books = {}
    mults = {}  # realised per-cell multiplier per variant (for controls)
    mv = {}
    mv["V1"] = np.where(tom, 1.0, 0.85)
    books["V1"] = sb.copy(); books["V1"][:] = uni(tom, 1.0, 0.85)
    mults["V1"] = np.broadcast_to(mv["V1"][:, None], (n, m)).copy()
    mv["V2"] = np.where(tom, 1.0, 0.70)
    books["V2"] = sb.copy(); books["V2"][:] = uni(tom, 1.0, 0.70)
    mults["V2"] = np.broadcast_to(mv["V2"][:, None], (n, m)).copy()
    # V3: longs 1.0/0.85, shorts 1.0/0.50
    long3 = np.where(tom, 1.0, 0.85)[:, None]
    short3 = np.where(tom, 1.0, 0.50)[:, None]
    m3 = np.where(sbv > 0, long3, np.where(sbv < 0, short3, 1.0))
    m3[pre, :] = 1.0
    books["V3"] = sb.copy(); books["V3"][:] = sbv * m3
    mults["V3"] = m3
    # S1/S2/S3: longs gated, shorts 1.0
    for key, mask, out_v in (("S1", on, 0.75), ("S2", on, 0.0), ("S3", onw, 0.75)):
        lm = np.where(mask, 1.0, np.where(ok, out_v, 1.0))[:, None]
        mm = np.where(sbv > 0, lm, 1.0)
        mm[pre, :] = 1.0
        books[key] = sb.copy(); books[key][:] = sbv * mm
        mults[key] = mm
    # G1H/G2H book: 0.75 in [400,900]; G3H: 0.75 in [525,900]
    books["G1H"] = sb.copy(); books["G1H"][:] = uni(halv, 0.75, 1.0)
    mults["G1H"] = mults["G2H_book"] = np.broadcast_to(np.where(halv, 0.75, 1.0)[:, None], (n, m)).copy()
    books["G2H"] = sb.copy(); books["G2H"][:] = uni(halv, 0.75, 1.0)
    books["G3H"] = sb.copy(); books["G3H"][:] = uni(halv525, 0.75, 1.0)
    mults["G3H"] = np.broadcast_to(np.where(halv525, 0.75, 1.0)[:, None], (n, m)).copy()

    info: dict = {"per_year": {}, "controls": {}, "dip": {"scale": DIP_SCALE, "d_y": {}}}
    for key in VARIANTS:
        mm = mults["G2H_book"] if key == "G2H" else mults[key]
        per_y = []
        for k in range(5):
            sel = np.asarray((Tts >= BOUNDS[k]) & (Tts < BOUNDS[k + 1]))
            entry: dict = {"year": str(ANCH[k].date())}
            if sel.sum() == 0:
                entry.update(share_in=0.0, mean_mult=1.0, mean_long=1.0, mean_short=1.0,
                             c=1.0, cL=1.0, cS=1.0)
                per_y.append(entry)
                continue
            L = sbv[sel] > 0
            S = sbv[sel] < 0
            entry["share_in"] = None  # filled below per family
            entry["mean_mult"] = round(float(mm[sel].mean()), 6)
            entry["mean_long"] = round(float(mm[sel][L].mean()), 6) if L.sum() else 1.0
            entry["mean_short"] = round(float(mm[sel][S].mean()), 6) if S.sum() else 1.0
            if key in ("V1", "V2", "G1H", "G2H", "G3H"):
                entry["c"] = entry["mean_mult"]
                entry["cL"] = entry["cS"] = entry["mean_mult"]
            elif key == "V3":
                entry["cL"] = entry["mean_long"]; entry["cS"] = entry["mean_short"]
                entry["c"] = entry["mean_mult"]
            else:  # S1/S2/S3 longs-only
                entry["cL"] = entry["mean_long"]; entry["cS"] = 1.0
                entry["c"] = entry["mean_long"]
            per_y.append(entry)
        # IN-share per family (bar grain)
        for k in range(5):
            sel = np.asarray((Tts >= BOUNDS[k]) & (Tts < BOUNDS[k + 1]))
            if key in ("V1", "V2", "V3"):
                per_y[k]["share_in"] = round(float(tom[sel].mean()), 6) if sel.sum() else 0.0
            elif key in ("S1", "S2"):
                per_y[k]["share_in"] = round(float(on[sel].mean()), 6) if sel.sum() else 0.0
            elif key == "S3":
                per_y[k]["share_in"] = round(float(onw[sel].mean()), 6) if sel.sum() else 0.0
            elif key in ("G1H", "G2H"):
                per_y[k]["share_in"] = round(float(halv[sel].mean()), 6) if sel.sum() else 0.0
            else:
                per_y[k]["share_in"] = round(float(halv525[sel].mean()), 6) if sel.sum() else 0.0
        info["per_year"][key] = per_y

    # Controls: constant per-year multipliers (no cross-year peek).
    # Uniform families were correct in the first run (cv[sel] *= c is in-place)
    # and are reproduced bit-exactly here. Side-specific families (V3/S1/S2/S3)
    # are handled below (bug replica + _FIX), so they are skipped in this loop.
    # NOTE (2026-10-07, disclosed): the first run used cv[sel][Lk] *= c here,
    # which fancy-indexes a temp copy, so C_V3/C_S1/C_S2/C_S3 were no-ops
    # (= G2 bit-exact). Original buggy rows are KEPT under their names;
    # corrected controls run as C_*_FIX extra rows and are the ones judged.
    for key in ("V1", "V2", "G1H", "G2H", "G3H"):
        cbook = sb.copy()
        cv = sbv.copy()
        for k in range(5):
            sel = np.asarray((Tts >= BOUNDS[k]) & (Tts < BOUNDS[k + 1]))
            if sel.sum() == 0:
                continue
            e = info["per_year"][key][k]
            cv[sel] *= e["c"]
        cbook[:] = cv
        books[CTRL_OF[key]] = cbook
        info["controls"][CTRL_OF[key]] = [
            {"year": info["per_year"][key][k]["year"],
             "c": info["per_year"][key][k]["c"],
             "cL": info["per_year"][key][k]["cL"],
             "cS": info["per_year"][key][k]["cS"]}
            for k in range(5)]

    # C_G2 dip constant per year (mean dip scale on standard index)
    dip_std = np.where(halv, DIP_SCALE, 1.0)
    for k in range(5):
        sel = np.asarray((Tts >= BOUNDS[k]) & (Tts < BOUNDS[k + 1]))
        info["dip"]["d_y"][str(ANCH[k].date())] = round(float(dip_std[sel].mean()), 6) if sel.sum() else 1.0
    # Bug replicas (first-run behaviour, kept for the record): the no-op
    # C_V3/C_S1/C_S2/C_S3 books were bit-identical to sb (bear-filtered base).
    for key in ("V3", "S1", "S2", "S3"):
        books[CTRL_OF[key]] = sb.copy()
    # Fixed side-specific controls under _FIX names (same per-year constants).
    for key in ("V3", "S1", "S2", "S3"):
        cbook = sb.copy()
        cv = sbv.copy()
        for k in range(5):
            sel = np.asarray((Tts >= BOUNDS[k]) & (Tts < BOUNDS[k + 1]))
            if sel.sum() == 0:
                continue
            e = info["per_year"][key][k]
            if key == "V3":
                mL = (sbv > 0) & sel[:, None]
                mS = (sbv < 0) & sel[:, None]
                cv[mL] *= e["cL"]
                cv[mS] *= e["cS"]
            else:
                mL = (sbv > 0) & sel[:, None]
                cv[mL] *= e["cL"]
        cbook[:] = cv
        books[CTRL_OF[key] + "_FIX"] = cbook
        info["controls"][CTRL_OF[key]] = [
            {"year": info["per_year"][key][k]["year"],
             "c": info["per_year"][key][k]["c"],
             "cL": info["per_year"][key][k]["cL"],
             "cS": info["per_year"][key][k]["cS"]}
            for k in range(5)]
        info["controls"][CTRL_OF[key] + "_FIX"] = info["controls"][CTRL_OF[key]]
    return books, info


def worker(job):
    shift = job[0]
    want = job[1] if len(job) > 1 else None
    print(f"shift {shift} start", flush=True)
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load(f"podlitcal_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"histlitcal_{shift}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_litcal_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fwlitcal_{shift}", ROOT / "scripts/forward_v205.py")
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
    gated, ginfo = gate_books(sb)
    idx_ts = pd.to_datetime(idx, utc=True)
    # dip scales on the shifted clock
    dip_win = halv_in_for(idx_ts)  # G2H book-window on holding-bar start
    dip_scales = {"G2H": np.where(dip_win, DIP_SCALE, 1.0)}
    d_y = ginfo["dip"]["d_y"]
    ykey = np.array([str(_ykey(idx_ts[i])) for i in range(len(idx_ts))])
    dip_scales["C_G2"] = np.array([d_y.get(k, 1.0) for k in ykey], dtype=float)
    fwd = {k: gated[k].reindex(idx, method="ffill").fillna(0.0)
           for k in list(gated.keys())}
    n_gated = {k: int((fwd[k].to_numpy() != sb.reindex(idx, method="ffill").fillna(0.0).to_numpy()).sum())
               for k in VARIANTS}
    print(shift, "gated cells", json.dumps(n_gated), flush=True)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    out = {}
    for name, cfg in RUNS.items():
        if name in CACHED or (want is not None and name not in want):
            continue
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        O, C, sg = prep["O"], prep["C"], prep["sig4"]
        base_size, rule = kw["sleeve_fill_size"], cfg["rule"]
        kd = cfg.get("kd", 1.0)
        dscale = dip_scales.get(cfg["gate"])

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd, dscale=dscale):
            mm = f - 1
            nn = 0
            for b in range(len(cols)):
                if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, mm, b]) and np.isfinite(sg[i][b])):
                    continue
                nn += float(C[i, mm, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
            mult = 1.0 / (1 + nn) if rule == "inv" else (0.5 if nn >= 2 else 1.0)
            s = mult * kd * base_size(i, a, r, f)
            if dscale is not None:
                s *= float(dscale[i])
            return s
        kw["sleeve_fill_size"] = corr_size
        k = cfg["k"]
        kw["risk_mult"] = lambda i, e, k=k: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
        if "G" in cfg:
            kw["sleeve_gross_cap"] = cfg["G"]
        eu.simulate(fwd[cfg["gate"]], opens, prep, trade=trade, win_start=5, events=[], **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        out[name] = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)], eq=(cap["eq"][lv] / base).tolist(), eq_min=(cap["eq_min"][lv] / base).tolist())
        print(shift, name, round(out[name]["eq"][-1], 3), flush=True)
    print(f"shift {shift} done", flush=True)
    return shift, out, ginfo


def _ykey(t) -> str:
    for k in range(5):
        if BOUNDS[k] <= t < BOUNDS[k + 1]:
            return str(ANCH[k].date())
    return str(ANCH[-1].date())


def stats(runs, row, ys):
    yy = [rm.year_reset(runs, row, y) for y in ys]
    geo = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / len(yy)) - 1)
    return dict(R=round(float(geo), 3), W=min(y["R"] for y in yy), DD=max(y["DD"] for y in yy), losing=sum(y["R"] < 0 for y in yy),
                years=[(y["R"], y["DD"]) for y in yy])


JUDGED_CTRL = dict(CTRL_OF)
JUDGED_CTRL.update({"V3": "C_V3_FIX", "S1": "C_S1_FIX", "S2": "C_S2_FIX", "S3": "C_S3_FIX"})


def main():
    cache = HERE / "tmp" / "engine_runs.pkl"
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
        print("loaded cache", cache, flush=True)
        missing = [r for r in RUNS if r not in CACHED and r not in runs.get(0, {})]
        if missing:
            print("incremental rows:", missing, flush=True)
            with Pool(2) as pool:
                res = pool.map(worker, [(s, missing) for s in range(4)])
            for shift, out, ginfo in res:
                runs[shift].update(out)
                if shift == 0:
                    runs["_ginfo"] = ginfo
            cache.write_bytes(pickle.dumps(runs))
            print("cache updated with", missing, flush=True)
        else:
            print("no missing rows", flush=True)
    else:
        with Pool(2) as pool:
            res = pool.map(worker, [(s, None) for s in range(4)])
        runs = {}
        ginfo0 = None
        for shift, out, ginfo in res:
            runs[shift] = out
            if shift == 0:
                ginfo0 = ginfo
        for row, (pth, key) in CACHED.items():
            cr = pickle.loads((ROOT / pth).read_bytes())
            for s in range(4):
                runs[s][row] = cr[s][key]
        runs["_ginfo"] = ginfo0
        cache.write_bytes(pickle.dumps(runs))
    ginfo0 = runs.get("_ginfo")
    # G2 5y reproduction to the digit (uses all five years, like v421).
    exp = json.loads((RD / "v421" / "v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    got5 = stats(runs, "R2B1D17BFG2", list(range(5)))
    assert [a for a, _ in got5["years"]] == [r for r, _ in exp["years"]], (got5, exp)
    assert [d for _, d in got5["years"]] == [d for _, d in exp["years"]], (got5, exp)
    assert got5["R"] == EXP_R and got5["W"] == EXP_W and got5["DD"] == EXP_DD, (got5, exp)
    print("G2 5y reproduction OK:", got5, flush=True)
    g1 = Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, "R2B1D17BFG2", g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    assert full == EXP_FULL, (full, EXP_FULL)
    print("G2 full-path DD OK:", full, flush=True)
    # Dev4 selection table (years 0-3 only; 2025 never read for variants here).
    dev4 = {r: stats(runs, r, [0, 1, 2, 3]) for r in RUNS}
    for r, m in dev4.items():
        print(r, m, flush=True)
    g2dev = stats(runs, "R2B1D17BFG2", [0, 1, 2, 3])
    print("G2 dev4:", g2dev, flush=True)
    pick = None
    qual = []
    for v in VARIANTS:
        jc = JUDGED_CTRL[v]
        m, c = dev4[v], dev4[jc]
        ok = (m["R"] > g2dev["R"] and m["W"] > g2dev["W"]
              and m["DD"] <= g2dev["DD"] + 0.5 and m["R"] > c["R"])
        print(f"{v} vs {jc} (orig {CTRL_OF[v]}): R {m['R']} vs {c['R']}, W {m['W']}, "
              f"DD {m['DD']} -> {'CANDIDATE' if ok else 'no'}", flush=True)
        if ok:
            qual.append(v)
    if qual:
        # Robust tie-break (AGENTS.md leader rule): highest dev4 worst-year, ties -> higher mean.
        pick = max(qual, key=lambda v: (dev4[v]["W"], dev4[v]["R"]))
        print("qualifiers:", qual, "robust pick:", pick, flush=True)
    out = {"version": "oc_lit_calendar_engine_dev4",
           "g2_5y": got5, "g2_full": full, "g2_dev4": g2dev,
           "dev4": dev4, "pick": pick, "qualifiers": qual,
           "pick_control": JUDGED_CTRL[pick] if pick else None,
           "judged_ctrl": JUDGED_CTRL,
           "gate_info": ginfo0}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "tmp" / "engine_dev4.json").write_text(raw)
    print("pick:", pick, "sha256", hashlib.sha256(raw.encode()).hexdigest(), flush=True)


if __name__ == "__main__":
    main()
