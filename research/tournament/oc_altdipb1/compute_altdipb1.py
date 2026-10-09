"""oc_altdipb1: G2 dip ladder WITH corr-aware sizing on three large alts.

Replica of research/tournament/oc_placebo_dip/compute_placebo_dip.py
verbatim core (outcome_mu / n_vector / size_mult / find_fill / cell_stats),
extended to DOGE/ADA/TRX. See PLAN.md (pre-registered before any outcome).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_altdipb1 \\
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \\
    research/tournament/oc_altdipb1/compute_altdipb1.py
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
DD_TOL = 0.01
PLACEBO_P95 = 0.273  # oc_placebo_dip pooled dSum5y p95 ~0.2728, labelled gate

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ALTS = ("DOGEUSDT", "ADAUSDT", "TRXUSDT")
ALL8 = MAJORS + ALTS
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
ALT_DIR = Path("data/raw/alts_intraday_20260926")


# --------------------------------------------------------------------------
# verbatim placebo core
# --------------------------------------------------------------------------
def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """v399-exact correlation count per live minute (0..N-1). NaN -> no detect."""
    W = close_others.shape[1]
    n = np.zeros(W, dtype=np.int64)
    for i in range(close_others.shape[0]):
        o, sg = float(open_others[i]), float(sigma_others[i])
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - DETECT_K * sg)
        if not np.isfinite(thr):
            continue
        c = close_others[i]
        n += (np.isfinite(c) & (c <= thr)).astype(np.int64)
    return n


def size_mult(n_fill: int) -> float:
    """B1 size multiplier: 1/(1+n)."""
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level: float):
    """First live-window index with low < level (STRICT). None if never."""
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_mu(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
               o2: float, settle: bool):
    """oc_dipexit-exact long rung outcome for TP multiple mu.

    Returns (ret, x, how); x = exit offset (240 = next-bar open).
    """
    sl = lv * (1 - M_SL * sg)
    bl = lv * (1 - BACKSTOP * sg)
    tp = lv * (1 + mu * sg)
    post = np.arange(f + 1, 240)
    trig = (np.asarray(Ca[f + 1:240], dtype=float) <= sl) & ((post + 1) % 5 == 0)
    ks = _first_idx(trig)
    hb = np.asarray(La[f + 1:240], dtype=float) <= bl
    kb = _first_idx(hb)
    ht = np.asarray(Ha[f + 1:240], dtype=float) > tp
    kt = _first_idx(ht)
    if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
        x = f + 1 + kb
        ox = Oa[x]
        if not np.isfinite(ox):
            return (np.nan, x, "backstop")
        px = bl if ox > bl else ox
        return (px / lv - 1 - MAKER - TAKER, x, "backstop")
    if kt is not None and (ks is None or kt < ks):
        x = f + 1 + kt
        return (tp / lv - 1 - 2 * MAKER, x, "tp")
    if ks is not None:
        km = f + 1 + ks
        if km + 1 < 240:
            px, x = Oa[km + 1], km + 1
        else:
            px, x = o2, 240
        if not np.isfinite(px):
            return (np.nan, x, "stop")
        ret = px / lv - 1 - MAKER - TAKER
        if x == 240 and settle:
            ret -= FUND
        return (ret, x, "stop")
    x = 240
    if not np.isfinite(o2):
        return (np.nan, x, "time")
    return (o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0), x, "time")


def year_of(t0) -> int | None:
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def exit_day_ordinal(bt, x: int, base_min: int) -> int:
    """Days since epoch (UTC) of the exit calendar date."""
    if int(x) < 240:
        d = (bt + pd.Timedelta(minutes=int(x))).date()
    else:
        d = (bt + pd.Timedelta(hours=4)).date()
    return (pd.Timestamp(d, tz="UTC") - EPOCH).days


def cell_stats(dates: np.ndarray, wy: np.ndarray):
    """(S, worst_day, maxDD) of daily sums. DD >= 0 in w*y units."""
    if wy.size == 0:
        return 0.0, 0.0, 0.0
    order = np.argsort(dates, kind="stable")
    d = dates[order]
    v = wy[order]
    uniq, idx = np.unique(d, return_index=True)
    bounds = np.append(idx[1:], v.size)
    daily = np.array([v[s:e].sum() for s, e in zip(idx, bounds)])
    cum = np.cumsum(daily)
    peak = np.maximum.accumulate(cum)
    dd = float(np.min(cum - peak))
    return float(daily.sum()), float(daily.min()), float(-dd)


def score_assignment(ph: np.ndarray, yr: np.ndarray,
                     wv: np.ndarray, yv: np.ndarray,
                     dv: np.ndarray) -> dict:
    """Per-year 4-phase means (S, DD, n, win) + full pooled path + 5y sums."""
    per_year = []
    for y in range(5):
        ss, ds, ns = [], [], []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            n = int(m.sum())
            ns.append(n)
            if n:
                s, _, dd = cell_stats(dv[m], (wv * yv)[m])
            else:
                s, dd = 0.0, 0.0
            ss.append(s)
            ds.append(dd)
        my = (yr == y)
        per_year.append({"S": float(np.mean(ss)), "DD": float(np.mean(ds)),
                         "n": float(np.mean(ns)),
                         "win": float((yv[my] > 0).mean()) if my.any() else 0.0,
                         "per_phase_sums": [float(s) for s in ss],
                         "per_phase_dd": [float(s) for s in ds],
                         "per_phase_n": [int(s) for s in ns]})
    s_full, _, dd_full = cell_stats(dv, wv * yv)
    return {"per_year": per_year,
            "sum5y": float(sum(r["S"] for r in per_year)),
            "ddmean": float(np.mean([r["DD"] for r in per_year])),
            "full_sum": float(s_full), "full_dd": float(dd_full)}


# --------------------------------------------------------------------------
# data loading (1m, float32, one coin H/L at a time)
# --------------------------------------------------------------------------
def load_oc(sym: str):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    elif sym in MAJORS:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    else:
        files = sorted(ALT_DIR.glob(f"{sym}_1m_20*.parquet"))
    assert files, sym
    parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    idx = pd.date_range(START, END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m, parts
    return idx, O, C


def load_hl(sym: str, idx):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    elif sym in MAJORS:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    else:
        files = sorted(ALT_DIR.glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "high", "low"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    m = m.set_index("open_time").reindex(idx)
    H = m["high"].to_numpy(dtype=np.float32)
    L = m["low"].to_numpy(dtype=np.float32)
    del m, parts
    return H, L


# --------------------------------------------------------------------------
# ledger builder (coins tuple defines the n universe)
# --------------------------------------------------------------------------
HOW_CODE = {"tp": 0, "stop": 1, "backstop": 2, "time": 3}


def build_ledger(coins: tuple, phases: tuple = PHASES,
                 max_bars_per_coin_phase: int | None = None) -> dict:
    """Exact D0+B1 replica on the given coin universe (n counts within coins).

    Kept fills: filled on lv AND y1.0 finite. Records exit reason how10.
    """
    O, C, base_idx = {}, {}, None
    for sym in coins:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)

    grids = {}
    for p in phases:
        off = p * 60
        nb = (n_all - off) // 240
        t0 = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in coins:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb)
              if TRADE_START <= t0[j] < YEAR_END and (off + j * 240 + 240) < n_all]
        if max_bars_per_coin_phase is not None:
            js = js[:max_bars_per_coin_phase]
        grids[p] = dict(off=off, nb=nb, t0=t0, opens=opens_bar, sig=sig_bar, js=js)
        print(f"shift {p}: nb={nb} traded={len(js)}", flush=True)
    del opens_bar, sig_bar

    F = {k: [] for k in ("phase", "coin", "year", "bar_time", "rung",
                         "w", "y", "d", "how")}
    coin_ix = {s: i for i, s in enumerate(coins)}
    bars_traded = {s: [0] * 5 for s in coins}
    for sym in coins:
        H, L = load_hl(sym, base_idx)
        La, Ha = L, H
        others = [b for b in coins if b != sym]
        Oa, Ca = O[sym], C[sym]
        for p in phases:
            g = grids[p]
            off, t0 = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            n_fill = 0
            for j in g["js"]:
                bt = t0[j]
                o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                yi = year_of(bt)
                if yi is None:
                    continue
                bars_traded[sym][yi] += 1
                base = off + j * 240
                o2m = Oa[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                low_win = La[base + LIVE_A:base + LIVE_B + 1].astype(float)
                if others:
                    cmat = np.stack([C[b][base + LIVE_A - 1:base + LIVE_B].astype(float)
                                     for b in others])
                    oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                    ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                    nvec = n_vector(cmat, oo, ss)
                else:  # smoke mode (single coin): no flushers by construction
                    nvec = np.zeros(LIVE_B - LIVE_A + 1, dtype=np.int64)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for ri, k in enumerate(RUNGS):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = LIVE_A + ib
                    nf = int(nvec[ib])
                    r10, x10, h10 = outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                    if not np.isfinite(r10):
                        continue
                    n_fill += 1
                    F["phase"].append(p)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(yi)
                    F["bar_time"].append(off + j * 240)
                    F["rung"].append(ri)
                    F["w"].append(size_mult(nf))
                    F["y"].append(r10)
                    F["d"].append(exit_day_ordinal(bt, x10, base))
                    F["how"].append(HOW_CODE[h10])
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha
    led = {k: np.array(v) for k, v in F.items()}
    for k in ("phase", "coin", "year", "bar_time", "rung", "d", "how"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y"):
        led[k] = led[k].astype(np.float64)
    led["coins"] = np.array(coins)
    led["bars_traded"] = bars_traded
    return led


def daily_series(dv: np.ndarray, wy: np.ndarray):
    order = np.argsort(dv, kind="stable")
    d = dv[order]
    v = wy[order]
    uniq, idx = np.unique(d, return_index=True)
    bounds = np.append(idx[1:], v.size)
    daily = np.array([v[s:e].sum() for s, e in zip(idx, bounds)])
    return uniq.astype(np.int64), daily.astype(float)


def pearson_corr(a_days, a_vals, b_days, b_vals) -> float:
    days = np.union1d(a_days, b_days)
    am = dict(zip(a_days.tolist(), a_vals.tolist()))
    bm = dict(zip(b_days.tolist(), b_vals.tolist()))
    x = np.array([am.get(int(d), 0.0) for d in days], dtype=float)
    y = np.array([bm.get(int(d), 0.0) for d in days], dtype=float)
    if x.std() == 0 or y.std() == 0 or len(x) < 3:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="test-only: 1 alt coin, phase 0, 300 bars; no files")
    args = ap.parse_args()

    # ---- G2 read-only baseline check (hourly only, no 1m) ----
    spec = importlib.util.spec_from_file_location(
        "v388_altdipb1", RD / "v388/v388_bot_stop_distance.py")
    v388 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v388)
    runs = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    strat = "R2B1D17BFG2"
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    E4, M4 = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][strat], grid0, g1)
        E4.append(e1)
        M4.append(m1)
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"][strat]
    got_years = []
    for y in range(5):
        a0 = pd.Timestamp(v388.ANCH[y], tz="UTC")
        E, MN = [], []
        for s in range(4):
            e1, m1 = E4[s], M4[s]
            b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
            seg = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
            E.append(e1[seg] / b)
            MN.append(m1[seg] / b)
        es = sum(E) / 4
        ms = sum(MN) / 4
        pk = np.maximum.accumulate(es.to_numpy())
        R = round(100 * float(es.iloc[-1] ** (1 / 12) - 1), 3)
        DD = round(100 * float(np.max(1 - ms.to_numpy() / pk)), 2)
        got_years.append([R, DD])
    assert [r for r, _ in got_years] == [r for r, _ in exp["years"]], (got_years, exp)
    assert [d for _, d in got_years] == [d for _, d in exp["years"]], (got_years, exp)
    assert round(float(np.prod([1 + r / 100 for r, _ in got_years]) ** (1 / 5) - 1) * 100, 3) == exp["R"]
    print(f"G2 f=0 check OK: reproduces {strat} "
          f"R={exp['R']} W={exp['W']} DD={exp['DD']} full={exp['full_path_dd']}", flush=True)

    if args.smoke:
        led = build_ledger(("DOGEUSDT",), phases=(0,), max_bars_per_coin_phase=300)
        print(f"smoke n={len(led['w'])} coins={led['coins'].tolist()}", flush=True)
        return

    # ---- coverage manifest (pre-registered check) ----
    man = json.loads((ALT_DIR / "manifest.json").read_text())
    cov = {k: {"first": v["first"], "last": v["last"], "missing": v.get("missing", 0)}
           for k, v in man["symbols"].items() if k in ALTS}
    print("alt coverage manifest: " + json.dumps(cov), flush=True)

    # ---- MAJORS reference (must reproduce 7.718 first) ----
    maj = build_ledger(MAJORS)
    nm = len(maj["w"])
    print(f"MAJORS ledger fills={nm}", flush=True)
    base_sc = score_assignment(maj["phase"], maj["year"], maj["w"], maj["y"], maj["d"])
    print("MAJORS 4-phase-mean sums:",
          [round(r["S"], 4) for r in base_sc["per_year"]], flush=True)
    print("MAJORS 4-phase-mean DDs:",
          [round(r["DD"], 4) for r in base_sc["per_year"]], flush=True)
    print(f"MAJORS base_sum5y={base_sc['sum5y']:.6f} (placebo 7.718304)", flush=True)
    if abs(base_sc["sum5y"] - 7.718304) > 0.02:
        print("FATAL: MAJORS replica does not reproduce 7.718; stopping.", flush=True)
        (HERE / "tmp_replica_fail.json").write_text(json.dumps(
            {"base_sum5y": base_sc["sum5y"],
             "per_year": base_sc["per_year"]}, indent=1))
        sys.exit(2)

    # ---- ALT8 (8-coin universe, n among all 8) ----
    alt8 = build_ledger(ALL8)
    print(f"ALT8 ledger fills={len(alt8['w'])}", flush=True)
    alt8_sc = score_assignment(alt8["phase"], alt8["year"], alt8["w"], alt8["y"], alt8["d"])

    # ALT3 = alts subset of ALT8 (same w, n counted on 8)
    alt_ix = np.array([ALL8.index(s) for s in ALTS])
    m_alt = np.isin(alt8["coin"], alt_ix)
    a3 = {k: alt8[k][m_alt] for k in ("phase", "year", "w", "y", "d", "how", "coin", "rung")}
    alt3_sc = score_assignment(a3["phase"], a3["year"], a3["w"], a3["y"], a3["d"])

    # majors-leg of ALT8 (same fills as MAJORS reference set, but 8-coin sizes)
    maj_ix8 = np.array([ALL8.index(s) for s in MAJORS])
    m_maj8 = np.isin(alt8["coin"], maj_ix8)
    m8 = {k: alt8[k][m_maj8] for k in ("phase", "year", "w", "y", "d")}
    maj8_sc = score_assignment(m8["phase"], m8["year"], m8["w"], m8["y"], m8["d"])

    # ---- dip-gate legs ALT8 vs MAJORS ----
    pass_sum, pass_dd = [], []
    for y in range(5):
        pass_sum.append(bool(alt8_sc["per_year"][y]["S"] >= base_sc["per_year"][y]["S"]))
        pass_dd.append(bool(alt8_sc["per_year"][y]["DD"] <= base_sc["per_year"][y]["DD"] + DD_TOL))
    dsum5y = float(alt8_sc["sum5y"] - base_sc["sum5y"])

    # ---- ALT3 standalone per-year detail (stop rate pooled) ----
    alt3_rows = []
    for y in range(5):
        my = (a3["year"] == y)
        n_y = int(my.sum())
        if n_y:
            win_y = float((a3["y"][my] > 0).mean())
            stop_y = float(np.isin(a3["how"][my], [HOW_CODE["stop"], HOW_CODE["backstop"]]).mean())
        else:
            win_y, stop_y = 0.0, 0.0
        alt3_rows.append({"S": round(alt3_sc["per_year"][y]["S"], 6),
                           "DD": round(alt3_sc["per_year"][y]["DD"], 6),
                           "n": round(alt3_sc["per_year"][y]["n"], 2),
                           "win": round(win_y, 6),
                           "stop_rate": round(stop_y, 6)})

    # ---- correlation ALT3 vs majors-leg daily P&L ----
    ad, av = daily_series(a3["d"], a3["w"] * a3["y"])
    bd, bv = daily_series(m8["d"], m8["w"] * m8["y"])
    corr_all = pearson_corr(ad, av, bd, bv)
    corr_by_year = []
    for y in range(5):
        ma = (a3["year"] == y)
        mb = (m8["year"] == y)
        if ma.any() and mb.any():
            da, va = daily_series(a3["d"][ma], (a3["w"] * a3["y"])[ma])
            db, vb = daily_series(m8["d"][mb], (m8["w"] * m8["y"])[mb])
            corr_by_year.append(round(float(pearson_corr(da, va, db, vb)), 4))
        else:
            corr_by_year.append(None)

    res = {
        "config": {
            "replica": "oc_placebo_dip verbatim (TP1sg, sl4sg close5, bl8sg, timeout next-bar open; "
                       "maker 0.0002/taker 0.00055; v293 settle funding) + B1 w=1/(1+n); "
                       "4 clock phases; R2 rungs 2.5..5.0; live 16..238 strict; "
                       "bars open [2021-09-24,2026-09-24); kept iff y1.0 finite",
            "alts_src": "data/raw/alts_intraday_20260926 (Binance USD-M 1m) + manifest",
            "alt_coverage_manifest": cov,
            "alt_bars_traded_per_year": {s: alt8["bars_traded"][s] for s in ALL8},
            "ALT8": "8 coins traded; n among ALL 8 (0..7); budget per coin as majors",
            "ALT3": "3 alts only; n counted on all 8; sizes exactly as in ALT8",
            "g2_check": f"v421 {strat} reproduced to the digit read-only "
                        f"(R={exp['R']} W={exp['W']} DD={exp['DD']} full={exp['full_path_dd']})",
            "gates": {"PASS_sum(Y)": "Sbar_ALT8(Y) >= Sbar_MAJORS(Y)",
                      "PASS_dd(Y)": "DDbar_ALT8(Y) <= DDbar_MAJORS(Y) + 0.01",
                      "stricter_dSum5y_vs_placebo_p95": PLACEBO_P95,
                      "show_to_owner": "PASS_sum >= 4/5 AND PASS_dd >= 4/5"},
        },
        "n_fills": {"MAJORS": int(nm), "ALT8": int(len(alt8["w"])),
                    "ALT3": int(m_alt.sum())},
        "ledger_checksum": {
            "MAJORS": hashlib.sha256(
                np.round(np.stack([maj["w"], maj["y"]]), 9).tobytes()).hexdigest()[:16],
            "ALT8": hashlib.sha256(
                np.round(np.stack([alt8["w"], alt8["y"]]), 9).tobytes()).hexdigest()[:16],
        },
        "MAJORS_mean4": [
            {"year": ANCHORS[y].date().isoformat(),
             "S": round(base_sc["per_year"][y]["S"], 6),
             "DD": round(base_sc["per_year"][y]["DD"], 6),
             "n": round(base_sc["per_year"][y]["n"], 2),
             "win": round(base_sc["per_year"][y]["win"], 6)}
            for y in range(5)],
        "MAJORS_sum5y": round(base_sc["sum5y"], 6),
        "ALT8_mean4": [
            {"year": ANCHORS[y].date().isoformat(),
             "S": round(alt8_sc["per_year"][y]["S"], 6),
             "DD": round(alt8_sc["per_year"][y]["DD"], 6),
             "n": round(alt8_sc["per_year"][y]["n"], 2),
             "win": round(alt8_sc["per_year"][y]["win"], 6)}
            for y in range(5)],
        "ALT8_sum5y": round(alt8_sc["sum5y"], 6),
        "ALT3_mean4": [
            dict({"year": ANCHORS[y].date().isoformat()}, **alt3_rows[y])
            for y in range(5)],
        "ALT3_sum5y": round(alt3_sc["sum5y"], 6),
        "majors_leg_of_ALT8_sum5y": round(maj8_sc["sum5y"], 6),
        "gate": {
            "pass_sum_per_year": [bool(v) for v in pass_sum],
            "pass_dd_per_year": [bool(v) for v in pass_dd],
            "years_sum_ge": int(sum(pass_sum)),
            "years_dd_ok": int(sum(pass_dd)),
            "dSum5y_ALT8_minus_MAJORS": round(dsum5y, 6),
            "dSum5y_vs_placebo_p95": round(dsum5y - PLACEBO_P95, 6),
            "show_to_owner": bool(sum(pass_sum) >= 4 and sum(pass_dd) >= 4),
        },
        "correlation_ALT3_vs_majors_leg_daily": {
            "pooled": round(float(corr_all), 4) if np.isfinite(corr_all) else None,
            "per_year": corr_by_year,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({"MAJORS_sum5y": res["MAJORS_sum5y"],
                      "ALT8_sum5y": res["ALT8_sum5y"],
                      "ALT3_sum5y": res["ALT3_sum5y"],
                      "gate": res["gate"],
                      "corr": res["correlation_ALT3_vs_majors_leg_daily"]}, indent=1))


if __name__ == "__main__":
    main()
