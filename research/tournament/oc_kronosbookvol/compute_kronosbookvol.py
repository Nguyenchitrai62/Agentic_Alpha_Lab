"""oc_kronosbookvol: book exposure scaled by Kronos forecast volatility (4-phase engine on G2).

Pre-registered rows (PLAN.md, frozen before any outcome):
  G2    v421 R2B1D17BFG2 cached (rule inv, k 1.0, kd 1.7, bear True, G 2.0) — must reproduce
        5.41 / 16.91 / 16.82, else STOP.
  KV1   book weight x m, m = clip(median_train(vol1) / vol1, 0.6, 1.4), both long+short.
  KV2   same with rng1 instead of vol1.
  CTRL  same with trailing ratio sigma42/sigma instead of Kronos.

Per-shift application: shift-s Kronos rows feed phase s only, looked up as the latest
row with T <= bar open t (merge_asof backward). Medians per (anchor, shift, sym) over
rows with T < A - 7d. v426 scaled STANDARD rows before the shifted-clock ffill; the
per-shift analogue here scales the PHASE-GRID books (books_bear ffill to idx_s)
elementwise — each phase sees only its own shift's features (proven by tests).

Two-stage execution (most-recent-year-ONCE):
  --stage dev   4-phase runs for KV1,KV2 with live1 = 2025-09-24+sh (last year never run).
  --stage full  full-period 4-phase runs for the chosen row + CTRL (v388 precedent so
                positions carry across the dev boundary); only year 4 is scored from it.
  G2 numbers come from the v421 cache (reproduced in --validate).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag ockronosbookvol --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_kronosbookvol/compute_kronosbookvol.py --stage dev
"""

from __future__ import annotations

import argparse
import gc
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
TMP = HERE / "tmp"
KRONOS_PATH = ROOT / "research/tournament/oc_kronoshidden/kronos_features_4shift.parquet"
BARS4_PATH = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
V421_RUNS = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"

# ---- pre-registered constants (mirrored in tests) ----
MAJORS = ("BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
LO, HI = 0.6, 1.4
EPS = 1e-12
EMBARGO_DAYS = 7
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
G2_STRAT = "R2B1D17BFG2"
ENGINE_ROWS = ("KV1", "KV2", "CTRL")
ROW_FEATURE = {"KV1": "vol1", "KV2": "rng1", "CTRL": "ratio42"}
RUNG_KINDS = ("rung_tp", "rung_sl", "rung_timeout")


# --------------------------------------------------------------------------
# Pure helpers (unit-tested; no data access)
# --------------------------------------------------------------------------
def clip_mult(median: float, f: float) -> float:
    """m = clip(median / f, LO, HI); missing/non-positive -> 1.0."""
    try:
        med, v = float(median), float(f)
    except (TypeError, ValueError):
        return 1.0
    if not (np.isfinite(med) and np.isfinite(v)) or med <= EPS or v <= EPS:
        return 1.0
    return float(min(HI, max(LO, med / v)))


def anchor_of(t: pd.Timestamp, shift: int) -> int:
    """Year index 0..4 for a phase-shift decision time t (bar open on idx grid).

    Year y covers [A_y+sh, A_y+365d+sh); bars before A_0+sh use 0, bars at/after
    live1 use 4. Matches the reset-metric year partition per phase.
    """
    sh = pd.Timedelta(hours=shift)
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    if tt < pd.Timestamp(ANCH5[0], tz="UTC") + sh:
        return 0
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC") + sh
        if y < 4 and tt < a0 + pd.Timedelta(days=365):
            return y
        if y == 4:
            return 4
    return 4


def geo_mean_monthly(Rs) -> float:
    g = 1.0
    for r in Rs:
        g *= 1.0 + float(r) / 100.0
    return 100.0 * (g ** (1.0 / len(Rs)) - 1.0)


# --------------------------------------------------------------------------
# Feature loading (fits use only T < A - 7d; lookup uses T <= t)
# --------------------------------------------------------------------------
def load_kronos() -> dict:
    """Per (shift, sym): frame sorted by T with vol1/rng1. Asserts 20 groups."""
    df = pd.read_parquet(KRONOS_PATH, columns=["sym", "shift", "T", "vol1", "rng1"])
    groups = df.groupby(["shift", "sym"]).size()
    assert len(groups) == 20, "kronos groups %d != 20" % len(groups)
    assert set(df["sym"].unique()) == set(MAJORS), df["sym"].unique()
    out = {}
    for (shift, sym), g in df.groupby(["shift", "sym"]):
        g = g.sort_values("T").reset_index(drop=True)
        out[(int(shift), str(sym))] = g[["T", "vol1", "rng1"]].copy()
    return out


def load_ctrl() -> dict:
    """Per (shift, sym): trailing ratio42 = sigma42/sigma from 4h bars.

    sigma = rolling(360).std of diff(log open) (same math as run_inference_4shift.py),
    sigma42 = rolling(42).std; ratio defined where both finite, sigma > 0 and nmin == 240.
    """
    b = pd.read_parquet(BARS4_PATH, columns=["sym", "shift", "T", "open", "nmin"])
    out = {}
    for (shift, sym), g in b.groupby(["shift", "sym"]):
        g = g.sort_values("T").reset_index(drop=True)
        lo = np.log(g["open"].to_numpy(dtype=float))
        d = np.r_[np.nan, np.diff(lo)]
        sig = pd.Series(d).rolling(360).std().to_numpy()
        sig42 = pd.Series(d).rolling(42).std().to_numpy()
        ok = np.isfinite(sig) & np.isfinite(sig42) & (sig > 0) & (g["nmin"].to_numpy() == 240)
        ratio = np.where(ok, sig42 / np.where(sig > 0, sig, np.nan), np.nan)
        out[(int(shift), str(sym))] = pd.DataFrame({"T": pd.to_datetime(g["T"], utc=True), "ratio42": ratio})
    return out


def training_medians(kronos: dict, ctrl: dict) -> dict:
    """median_train[(row, anchor, shift, sym)] over rows with T < A - 7d (finite, > EPS)."""
    med = {}
    for y, a in enumerate(ANCH5):
        cutoff = pd.Timestamp(a, tz="UTC") - pd.Timedelta(days=EMBARGO_DAYS)
        for s in range(4):
            for sym in MAJORS:
                kf = kronos[(s, sym)]
                for row, col in (("KV1", "vol1"), ("KV2", "rng1")):
                    v = kf.loc[pd.to_datetime(kf["T"], utc=True) < cutoff, col].to_numpy(dtype=float)
                    v = v[np.isfinite(v) & (v > EPS)]
                    med[(row, a, s, sym)] = float(np.median(v)) if len(v) else float("nan")
                cf = ctrl[(s, sym)]
                v = cf.loc[cf["T"] < cutoff, "ratio42"].to_numpy(dtype=float)
                v = v[np.isfinite(v) & (v > EPS)]
                med[("CTRL", a, s, sym)] = float(np.median(v)) if len(v) else float("nan")
    return med


def feature_at(frames: dict, key: tuple, t: pd.Timestamp) -> float:
    """Latest feature value with T <= t (merge_asof backward); NaN if none.

    frames maps (shift, sym) -> frame with T + one feature column (besides T the
    frame has exactly one value column). Pure-python backward search (testable).
    """
    fr = frames[key]
    ts = pd.to_datetime(fr["T"], utc=True).to_numpy()
    tt = pd.Timestamp(t)
    if tt.tzinfo is None:
        tt = tt.tz_localize("UTC")
    q = tt.value
    tsns = pd.DatetimeIndex(ts).asi8
    j = int(np.searchsorted(tsns, q, side="right")) - 1
    if j < 0:
        return float("nan")
    valcol = [c for c in fr.columns if c != "T"][0]
    return float(fr[valcol].iloc[j])


def mult_for(sym: str, t: pd.Timestamp, shift: int, row: str,
             kronos: dict, ctrl: dict, medians: dict) -> float:
    """Final book multiplier for one (sym, bar open t, shift) and row."""
    a = ANCH5[anchor_of(t, shift)]
    if row in ("KV1", "KV2"):
        col = ROW_FEATURE[row]
        fr = kronos[(shift, sym)][["T", col]]
        f = feature_at({"k": fr}, "k", t)
    elif row == "CTRL":
        fr = ctrl[(shift, sym)]
        f = feature_at({"k": fr}, "k", t)
    else:
        raise ValueError(row)  # pragma: no cover
    return clip_mult(medians.get((row, a, shift, sym), float("nan")), f)


def build_mult_frame(idx: pd.DatetimeIndex, cols: list, shift: int, row: str,
                     kronos: dict, ctrl: dict, medians: dict) -> pd.DataFrame:
    """Per-phase multiplier frame indexed like idx (vectorized; same math as mult_for).

    One row per decision bar; each phase sees only its own shift's feature rows with
    T <= bar open (searchsorted backward). Year y uses median_train(y, shift, sym).
    """
    idx = pd.DatetimeIndex(idx, tz="UTC")
    q = idx.asi8
    feat_col = ROW_FEATURE[row] if row in ("KV1", "KV2") else "ratio42"
    src = kronos if row in ("KV1", "KV2") else ctrl
    sh = pd.Timedelta(hours=shift)
    bounds = [pd.Timestamp(a, tz="UTC") + sh for a in ANCH5]
    m = pd.DataFrame(1.0, index=idx, columns=list(cols))
    for sym in cols:
        fr = src[(shift, sym)]
        tsns = pd.DatetimeIndex(pd.to_datetime(fr["T"], utc=True)).asi8
        vals = fr[feat_col].to_numpy(dtype=float)
        order = np.argsort(tsns)
        tsns, vals = tsns[order], vals[order]
        j = np.searchsorted(tsns, q, side="right") - 1
        f = np.where(j >= 0, vals[np.maximum(j, 0)], np.nan)
        col = np.ones(len(idx))
        for y, a in enumerate(ANCH5):
            b1 = bounds[y] + pd.Timedelta(days=365) if y < 4 else idx[-1] + pd.Timedelta(seconds=1)
            mask = np.asarray((idx < b1) if y == 0 else ((idx >= bounds[y]) & (idx < b1)))
            if not mask.any():
                continue
            med = medians.get((row, a, shift, sym), float("nan"))
            if not np.isfinite(med) or med <= EPS:
                continue
            fv = f[mask]
            with np.errstate(divide="ignore", invalid="ignore"):
                r = med / fv
            ok = np.isfinite(r) & (fv > EPS)
            col_m = np.ones(int(mask.sum()))
            col_m[ok] = np.clip(r[ok], LO, HI)
            col[mask] = col_m
        m[sym] = col
    return m


# --------------------------------------------------------------------------
# Stage 0: validate G2 reproduction + feature completeness (read-only, light)
# --------------------------------------------------------------------------
def validate() -> dict:
    exp = json.loads(V421_RES.read_text())["rows"][G2_STRAT]
    assert (exp["R"], exp["DD"], exp["full_path_dd"]) == (5.41, 16.91, 16.82), exp
    runs = pickle.loads(V421_RUNS.read_bytes())
    assert set(runs) == {0, 1, 2, 3} and all(G2_STRAT in runs[s] for s in runs)
    import importlib.util as iu
    spec = iu.spec_from_file_location("rm_val", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    rm = iu.module_from_spec(spec)
    spec.loader.exec_module(rm)
    got5 = [rm.year_reset(runs, G2_STRAT, y) for y in range(5)]
    assert [y["R"] for y in got5] == [r for r, _ in exp["years"]], got5
    assert [y["DD"] for y in got5] == [d for _, d in exp["years"]], got5
    print("G2 baseline OK: R 5.41 / DD 16.91 / full 16.82; years %s" % got5, flush=True)
    kronos = load_kronos()
    ctrl = load_ctrl()
    med = training_medians(kronos, ctrl)
    nmed = sum(1 for v in med.values() if np.isfinite(v))
    print("features OK: kronos 20 groups; ctrl %d groups; medians finite %d/%d"
          % (len(ctrl), nmed, len(med)), flush=True)
    for (row, a, s, sym), v in sorted(med.items()):
        assert np.isfinite(v) and v > 0, (row, a, s, sym, v)
    print("all %d training medians finite+positive" % len(med), flush=True)
    return {"g2_years": got5}


# --------------------------------------------------------------------------
# Stage 1/2: 4-phase runs (heavy; one phase = one engine session)
# --------------------------------------------------------------------------
def _load(name: str, path: Path):
    import importlib.util as iu
    spec = iu.spec_from_file_location(name, path)
    mod = iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_phase(shift: int, rows: list, live1: pd.Timestamp, kronos: dict,
              ctrl: dict, medians: dict) -> dict:
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    pod = pof._load("pod_kbv_%d" % shift,
                    ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_kbv_%d" % shift, ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_kbv_%d" % shift, pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_kbv_%d" % shift, ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap: dict = {}
    stats_hold: dict = {}

    def _summ(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                   eq_max=(eq if eq_max is None else eq_max).copy())
        stats_hold.update(stats)
        return {}

    eu.summarize = _summ
    sh = pd.Timedelta(hours=shift)
    live0 = DEV0 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    assert set(cols) == set(MAJORS), cols
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, cols)
    del M
    gc.collect()
    idx = prep["idx"]
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / ("r2_table_s%d.parquet" % shift)
    O, C, sg = prep["O"], prep["C"], prep["sig4"]
    out: dict = {}
    for row in rows:
        mult = build_mult_frame(idx, cols, shift, row, kronos, ctrl, medians)
        share = float((mult.to_numpy() != 1.0).mean())
        mdev = float(np.abs(mult.to_numpy() - 1.0).mean())
        books = books_bear * mult
        kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
        base_size, rule, kd = kw["sleeve_fill_size"], "inv", 1.7
        ev, stops, ptr = [], {}, [0]
        COOL = pd.Timedelta(hours=24)

        def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd):
            m_ = f - 1
            n_ = 0
            for b_ in range(len(cols)):
                if b_ == a or not (np.isfinite(O[i, 0, b_]) and np.isfinite(C[i, m_, b_]) and np.isfinite(sg[i][b_])):
                    continue
                n_ += float(C[i, m_, b_]) <= float(O[i, 0, b_]) * (1 - 2.5 * float(sg[i][b_]))
            mult_ = 1.0 / (1 + n_) if rule == "inv" else (0.5 if n_ >= 2 else 1.0)
            return mult_ * kd * base_size(i, a, r, f)

        kw["sleeve_fill_size"] = corr_size
        kw["risk_mult"] = lambda i, e, k=1.0: k
        kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
        kw["sleeve_gross_cap"] = 2.0
        events: list = []
        stats_hold.clear()
        eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw)
        lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
        first = int(np.argmax(lv))
        base = cap["eq"][first - 1] if first > 0 else 1.0
        run = dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                   eq=(cap["eq"][lv] / base).tolist(),
                   eq_min=(cap["eq_min"][lv] / base).tolist())
        years, cross = [], []
        for y, a in enumerate(ANCH5):
            a0 = pd.Timestamp(a, tz="UTC") + sh
            a1 = min(a0 + pd.Timedelta(days=365), live1)
            if a0 >= live1:
                years.append(dict(nb=0, wb=0, nr=0, wr=0))
                cross.append(dict(net=0.0, dd=0.0))
                continue
            evy = [e for e in events if a0 <= pd.Timestamp(e["t"]) < a1 + pd.Timedelta(hours=8)]
            ts = v216.v213.trade_stats(evy)
            nb = sum((ts.get(k) or {}).get("trades", 0) for k in ("dev", "_hidden"))
            wb = sum(round((ts.get(k) or {}).get("win_rate", 0) * (ts.get(k) or {}).get("trades", 0))
                      for k in ("dev", "_hidden"))
            rr = [float(e["ret"]) for e in evy if e["kind"] in RUNG_KINDS and "ret" in e]
            years.append(dict(nb=int(nb), wb=int(wb), nr=len(rr), wr=int(sum(r > 0 for r in rr))))
            cross.append(dict(net=0.0, dd=0.0))
        out[row] = dict(run=run, wins=years, cross=cross,
                        mult_share=share, mult_mad=mdev)
        print("phase %d row %s done (scaled share %.3f, mad %.4f)" % (shift, row, share, mdev), flush=True)
        del events, books, mult
        gc.collect()
    del opens, prep
    gc.collect()
    return shift, out


def runs_for_reset(allres: dict, row: str) -> dict:
    return {s: {row: allres[s][row]["run"]} for s in allres}


def score_years(allres: dict, row: str, years: list) -> dict:
    v388 = _load("v388_kbv_score", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_kbv_score", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    runs = runs_for_reset(allres, row)
    yr = [rm.year_reset(runs, row, y) for y in years]
    Rs = [y["R"] for y in yr]
    DDs = [y["DD"] for y in yr]
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, row, g1)
    seg = e.index > DEV0
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    fullDD = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    nb = sum(allres[s][row]["wins"][y]["nb"] for s in allres for y in range(len(allres[s][row]["wins"])))
    wb = sum(allres[s][row]["wins"][y]["wb"] for s in allres for y in range(len(allres[s][row]["wins"])))
    nr = sum(allres[s][row]["wins"][y]["nr"] for s in allres for y in range(len(allres[s][row]["wins"])))
    wr = sum(allres[s][row]["wins"][y]["wr"] for s in allres for y in range(len(allres[s][row]["wins"])))
    return dict(years_R=Rs, years_DD=DDs,
                R=round(geo_mean_monthly(Rs), 3), W=round(min(Rs), 3),
                DD=round(max(DDs), 2), losing=sum(r < 0 for r in Rs),
                fullDD=fullDD, book_trades=int(nb),
                book_win=round(wb / nb, 4) if nb else None,
                rung_trades=int(nr), rung_win=round(wr / nr, 4) if nr else None,
                win_all=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None)


def robust_pick(dev: dict) -> str:
    cands = {r: dev[r] for r in ("KV1", "KV2")
             if dev[r]["DD"] <= 20 and dev[r]["losing"] == 0}
    if not cands:
        return "none-eligible"
    hot = {k: v for k, v in cands.items() if v["R"] >= 5}
    pool = hot or cands
    return max(pool, key=lambda k: (pool[k]["W"], pool[k]["R"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--stage", choices=["dev", "full"], default=None)
    ap.add_argument("--rows", nargs="*", default=None)
    args = ap.parse_args()
    base = validate()
    kronos = load_kronos()
    ctrl = load_ctrl()
    medians = training_medians(kronos, ctrl)
    if args.validate and args.stage is None:
        print("validate-only done (no engine run).", flush=True)
        return
    assert args.stage in ("dev", "full"), "--stage dev|full required for engine runs"
    rows = args.rows or (["KV1", "KV2"] if args.stage == "dev" else ["KV1", "KV2", "CTRL"])
    for r in rows:
        assert r in ENGINE_ROWS, r
    # live1 is phase-shifted inside run_phase via DEV0+sh/live1+sh; pass anchor cap instead:
    cache = TMP / ("runs_%s_%s.pkl" % (args.stage, "+".join(rows)))
    if cache.exists():
        allres = pickle.loads(cache.read_bytes())
        missing = [s for s in range(4) if s not in allres]
        print("loaded cached %s runs (%d/4)" % (args.stage, len(allres)), flush=True)
    else:
        allres, missing = {}, list(range(4))
    for shift in missing:
        t0 = time.time()
        s, out = run_phase(shift, rows,
                           (DEV1 if args.stage == "dev" else Y1) + pd.Timedelta(hours=shift),
                           kronos, ctrl, medians)
        allres[s] = out
        cache.write_bytes(pickle.dumps(allres))
        print("phase %d cached (%s, %.0fs)" % (s, args.stage, time.time() - t0), flush=True)
    if args.stage == "dev":
        dev = {r: score_years(allres, r, [0, 1, 2, 3]) for r in rows}
        for r, v in dev.items():
            print("DEV %s R %s W %s DD %s losing %s fullDD %s book_win %s win_all %s"
                  % (r, v["R"], v["W"], v["DD"], v["losing"], v["fullDD"], v["book_win"], v["win_all"]),
                  flush=True)
        print("PICK (dev4 only): %s" % robust_pick(dev if set(("KV1", "KV2")) <= set(dev) else
              {**dev, **{k: {"DD": 99, "losing": 9, "R": -99, "W": -99} for k in ("KV1", "KV2") if k not in dev}}),
              flush=True)
    else:
        for r in rows:
            v = score_years(allres, r, [4])
            print("LAST %s R %s DD %s book_win %s win_all %s" % (r, v["R"], v["DD"], v["book_win"], v["win_all"]), flush=True)


if __name__ == "__main__":
    main()
