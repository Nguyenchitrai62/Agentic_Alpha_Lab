"""oc_i2_oiguard: OI-unwind dip-bid guard (IDEAS2_20261007 section 2).

Assignment: docs/opencode/OPENCODE_W_oc_i2_oiguard.md. Pre-registration is in
REPORT.md section 0 (frozen BEFORE this script ever ran; exactly 2 variants
O1/O2, no others). Steps, in order:

  0. Reproduce the G2 + carry baseline (5.634 / DD 16.75 / full 16.66,
     oc_carrycompound) or G2 (5.41) exactly from the frozen artefacts.
     Else stop and report (no further output beyond the failure).
  1. Dip replica: exact oc_placebo_dip D0+B1 4-phase replica (same constants,
     same grids), extended with the frozen OI-unwind guard flags.
  2. Screen base vs O1 vs O2 with the oc_placebo_dip scoring
     (4-phase means per year, daily w*y sums by exit date) + placebo gate
     (+0.273, applied strictly on dev4 per pre-reg). Selection on dev4
     (2021-2024) ONLY; 2025 scored once for the chosen variant only.
  3. 4-phase engine only if the screen passes (it gates on the rule above).

Heavy: 1m data like oc_placebo_dip (one coin H/L at a time, float32 O/C);
run ONLY via scripts/heavy_slot.py, never --leader. Scratch only under
research/tournament/oc_i2_oiguard/tmp/ (never the system temp folder).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_i2_oiguard \
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \
    research/tournament/oc_i2_oiguard/run_oiguard.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# frozen config (pre-registered; see REPORT.md section 0)
# --------------------------------------------------------------------------
MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
DD_TOL = 0.01  # dip-screen convention (oc_placebo_dip)
GATE_DSUM = 0.273  # pooled placebo p95, applied strictly on dev4 sums

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
DEV_YEARS = (0, 1, 2, 3)
POST_YEAR = 4

# OI guard (frozen)
OI_LAG = pd.Timedelta(minutes=5)  # manifest note: lag each row by 5 minutes
OI_LOOKBACK_H = 24
OI_TRAIL_BARS = 540  # 90d of 4h bars
OI_MIN_OBS = 60
OI_Z = 2.0
OI_COL = "sum_open_interest"
EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


# --------------------------------------------------------------------------
# step 0: baseline reproduction (read-only, no engine rerun)
# --------------------------------------------------------------------------
def check_baseline() -> dict:
    cc = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())
    g2c = cc["rows"]["G2_f0.25"]
    g2 = cc["rows"]["G2_f0.0"]
    assert g2c["R"] == 5.634, g2c
    assert g2c["DD"] == 16.75, g2c
    assert g2c["full_path_dd"]["full"] == 16.66, g2c
    assert g2["R"] == 5.41 and g2["W"] == 2.588 and g2["DD"] == 16.91, g2
    assert g2["full_path_dd"]["full"] == 16.82, g2
    v421 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())
    exp = v421["rows"]["R2B1D17BFG2"]
    assert [r for r, _ in exp["years"]] == [yy["R"] for yy in g2["years"]], exp
    return {"G2": {"R": g2["R"], "W": g2["W"], "DD": g2["DD"],
                   "losing": g2["losing"], "full_path_dd": g2["full_path_dd"],
                   "years": [(yy["anchor"], yy["R"], yy["DD"]) for yy in g2["years"]]},
            "G2_carry_f0.25": {"R": g2c["R"], "W": g2c["W"], "DD": g2c["DD"],
                               "losing": g2c["losing"], "full_path_dd": g2c["full_path_dd"],
                               "years": [(yy["anchor"], yy["R"], yy["DD"]) for yy in g2c["years"]]},
            "carry_add_pp_per_month": cc["carry_add_pp_per_month"]}


# --------------------------------------------------------------------------
# exact replica core (oc_placebo_dip / oc_velocity port; D0 from lv, B1 sizes)
# --------------------------------------------------------------------------
def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
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
    return 1.0 / (1 + int(n_fill))


def find_fill(low_win: np.ndarray, level: float):
    hit = np.asarray(low_win, dtype=float) < float(level)
    if hit.any():
        return int(np.argmax(hit))
    return None


def outcome_mu(Ha, La, Ca, Oa, f: int, lv: float, sg: float, mu: float,
               o2: float, settle: bool):
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


# --------------------------------------------------------------------------
# OI guard flags: pure function of causal inputs (causality-testable)
# --------------------------------------------------------------------------
def compute_guard_flags(bar_time: np.ndarray, opens: np.ndarray,
                        oi_time: np.ndarray, oi_val: np.ndarray) -> dict:
    """Fire flags for one (phase, coin) grid, strictly causal.

    bar_time: int64 ns of each grid bar open (ascending).
    opens: float bar opens (same length; NaN allowed).
    oi_time: int64 ns of OI rows (ascending); oi_val: float OI.
    Returns dict with fire (bool), dOI/dPx (float), zOI/zPx (float),
    eligible (bool: trailing stats available).
    OI as-of: last OI row with t <= bar-OI_LAG (and <= bar-24h-OI_LAG).
    Trailing stats: prior OI_TRAIL_BARS values of dOI/dPx, strictly before
    the bar; need >= OI_MIN_OBS finite and sd > 0, else no fire.
    """
    n = len(bar_time)
    fire = np.zeros(n, dtype=bool)
    dOI = np.full(n, np.nan)
    dPx = np.full(n, np.nan)
    zOI = np.full(n, np.nan)
    zPx = np.full(n, np.nan)
    eligible = np.zeros(n, dtype=bool)
    if n == 0:
        return {"fire": fire, "dOI": dOI, "dPx": dPx, "zOI": zOI,
                "zPx": zPx, "eligible": eligible}
    lag = OI_LAG.value
    h24 = pd.Timedelta(hours=OI_LOOKBACK_H).value
    q_now = bar_time - lag
    q_24 = bar_time - h24 - lag
    i_now = np.searchsorted(oi_time, q_now, side="right") - 1
    i_24 = np.searchsorted(oi_time, q_24, side="right") - 1
    ok = (i_now >= 0) & (i_24 >= 0)
    o_now = np.full(n, np.nan)
    o_24 = np.full(n, np.nan)
    o_now[ok] = oi_val[i_now[ok]]
    o_24[ok] = oi_val[i_24[ok]]
    good = ok & np.isfinite(o_now) & np.isfinite(o_24) & (o_now > 0) & (o_24 > 0)
    dOI[good] = np.log(o_now[good] / o_24[good])
    with np.errstate(divide="ignore", invalid="ignore"):
        px = np.full(n, np.nan)
        prev = np.full(n, np.nan)
        prev[6:] = opens[:-6]
        m = np.isfinite(opens) & np.isfinite(prev) & (opens > 0) & (prev > 0)
        dPx[m] = np.log(opens[m] / prev[m])
    sOI = pd.Series(dOI)
    sPx = pd.Series(dPx)
    muOI = sOI.shift(1).rolling(OI_TRAIL_BARS, min_periods=OI_MIN_OBS).mean().to_numpy()
    sdOI = sOI.shift(1).rolling(OI_TRAIL_BARS, min_periods=OI_MIN_OBS).std(ddof=1).to_numpy()
    muPx = sPx.shift(1).rolling(OI_TRAIL_BARS, min_periods=OI_MIN_OBS).mean().to_numpy()
    sdPx = sPx.shift(1).rolling(OI_TRAIL_BARS, min_periods=OI_MIN_OBS).std(ddof=1).to_numpy()
    okstat = (np.isfinite(muOI) & np.isfinite(sdOI) & (sdOI > 0)
              & np.isfinite(muPx) & np.isfinite(sdPx) & (sdPx > 0)
              & np.isfinite(dOI) & np.isfinite(dPx))
    eligible[okstat] = True
    zOI[okstat] = (dOI[okstat] - muOI[okstat]) / sdOI[okstat]
    zPx[okstat] = (dPx[okstat] - muPx[okstat]) / sdPx[okstat]
    fire[okstat] = (zOI[okstat] < -OI_Z) & (zPx[okstat] < -OI_Z)
    return {"fire": fire, "dOI": dOI, "dPx": dPx, "zOI": zOI,
            "zPx": zPx, "eligible": eligible}


# --------------------------------------------------------------------------
# scoring (oc_placebo_dip-exact)
# --------------------------------------------------------------------------
def year_of(t0) -> int | None:
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def exit_day_ordinal(bt, x: int) -> int:
    if int(x) < 240:
        d = (bt + pd.Timedelta(minutes=int(x))).date()
    else:
        d = (bt + pd.Timedelta(hours=4)).date()
    return (pd.Timestamp(d, tz="UTC") - EPOCH).days


def cell_stats(dates: np.ndarray, wy: np.ndarray):
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
                         "per_phase_sums": [float(s) for s in ss]})
    s_full, _, dd_full = cell_stats(dv, wv * yv)
    return {"per_year": per_year,
            "sum5y": float(sum(r["S"] for r in per_year)),
            "ddmean": float(np.mean([r["DD"] for r in per_year])),
            "full_sum": float(s_full), "full_dd": float(dd_full)}


def legs_vs_base(rule_sc: dict, base_sc: dict, years) -> dict:
    s = sum(1 for y in years
            if rule_sc["per_year"][y]["S"] >= base_sc["per_year"][y]["S"])
    d = sum(1 for y in years
            if rule_sc["per_year"][y]["DD"] <= base_sc["per_year"][y]["DD"] + DD_TOL)
    return {"years_sum_ge": int(s), "years_dd_ok": int(d)}


def dev4_dsum(rule_sc: dict, base_sc: dict) -> float:
    return float(sum(rule_sc["per_year"][y]["S"] - base_sc["per_year"][y]["S"]
                     for y in DEV_YEARS))


def select_on_dev4(dev: dict) -> dict:
    """dev: variant -> {sum_ge (of 4), dd_ok (of 4), dsum}. Pre-reg rule."""
    verdict = {}
    for v, st in dev.items():
        verdict[v] = bool(st["sum_ge"] >= 3 and st["dd_ok"] >= 3
                          and st["dsum"] >= GATE_DSUM)
    passers = [v for v, ok in verdict.items() if ok]
    if len(passers) == 1:
        chosen = passers[0]
    elif len(passers) > 1:
        chosen = sorted(passers, key=lambda v: (-dev[v]["dsum"], v))[0]
        d = [dev[v]["dsum"] for v in passers]
        if len(set(np.round(d, 12))) == 1:
            chosen = sorted(passers)[0]
    else:
        chosen = None
    return {"pass": verdict, "chosen": chosen}


# --------------------------------------------------------------------------
# data loading (1m, float32; same paths as oc_placebo_dip / oc_velocity)
# --------------------------------------------------------------------------
def load_oc(sym: str):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
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
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
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


def load_oi(sym: str):
    m = pd.read_parquet(ROOT / f"data/raw/um_metrics_20260926/{sym}_metrics.parquet",
                        columns=["create_time", OI_COL])
    m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
    m = m.drop_duplicates("create_time").sort_values("create_time")
    t = m["create_time"].values.astype("datetime64[ns]").astype(np.int64)
    v = m[OI_COL].to_numpy(dtype=float)
    return t, v


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def build_ledger() -> dict:
    O, C, base_idx = {}, {}, None
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)

    grids = {}
    for p in PHASES:
        off = p * 60
        nb = (n_all - off) // 240
        t0 = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in MAJORS:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb)
              if TRADE_START <= t0[j] < YEAR_END and (off + j * 240 + 240) < n_all]
        grids[p] = dict(off=off, nb=nb, t0=t0, opens=opens_bar, sig=sig_bar, js=js)
        print(f"shift {p}: nb={nb} traded={len(js)}", flush=True)

    F = {k: [] for k in ("phase", "coin", "year", "bar_time", "rung",
                         "w", "y10", "d10")}
    coin_ix = {s: i for i, s in enumerate(MAJORS)}
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        La, Ha = L, H
        others = [b for b in MAJORS if b != sym]
        Oa, Ca = O[sym], C[sym]
        for p in PHASES:
            g = grids[p]
            off, t0 = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            n_fill = 0
            for j in g["js"]:
                bt = t0[j]
                o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                base = off + j * 240
                o2m = Oa[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                if yi is None:
                    continue
                low_win = La[base + LIVE_A:base + LIVE_B + 1].astype(float)
                cmat = np.stack([C[b][base + LIVE_A - 1:base + LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                nvec = n_vector(cmat, oo, ss)
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
                    r10, x10, _ = outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                    if not np.isfinite(r10):
                        continue
                    n_fill += 1
                    F["phase"].append(p)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(yi)
                    F["bar_time"].append(off + j * 240)
                    F["rung"].append(ri)
                    F["w"].append(size_mult(nf))
                    F["y10"].append(r10)
                    F["d10"].append(exit_day_ordinal(bt, x10))
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha
    led = {k: np.array(v) for k, v in F.items()}
    for k in ("phase", "coin", "year", "bar_time", "rung", "d10"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    return led, grids


def build_guard_lookup(grids: dict) -> dict:
    """fire[(phase, coin_ix, bar_ordinal)] for traded bars; plus coverage."""
    lookup: dict[tuple, bool] = {}
    cov = {}
    for p in PHASES:
        g = grids[p]
        t0 = g["t0"]
        bt_ns = t0.values.astype("datetime64[ns]").astype(np.int64)
        for ci, sym in enumerate(MAJORS):
            opens = g["opens"][sym]
            oi_t, oi_v = load_oi(sym)
            fl = compute_guard_flags(bt_ns, opens, oi_t, oi_v)
            n_fire = int(fl["fire"].sum())
            n_elig = int(fl["eligible"].sum())
            cov[f"{p}/{sym}"] = {"grid_bars": int(len(bt_ns)), "eligible": n_elig,
                                 "fires": n_fire}
            # map traded bars only (js), with O2 delay = previous traded bar
            j_to_i = {j: i for i, j in enumerate(g["js"])}
            fire_traded = np.zeros(len(g["js"]), dtype=bool)
            for i, j in enumerate(g["js"]):
                fire_traded[i] = bool(fl["fire"][j])
            o1 = np.zeros(len(g["js"]), dtype=bool)
            o1[:] = fire_traded
            o2 = o1.copy()
            o2[1:] = o1[1:] | o1[:-1]
            for i, j in enumerate(g["js"]):
                key = (p, ci, int(g["off"] + j * 240))
                lookup[key] = (bool(o1[i]), bool(o2[i]))
            print(f"guard {p}/{sym}: eligible={n_elig} fires={n_fire}", flush=True)
    return lookup, cov


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="test-only: no 1m data; guard/scoring on synthetics")
    args = ap.parse_args()

    # ---- step 0: baseline (also in smoke) ----
    try:
        base = check_baseline()
    except AssertionError as e:
        print(f"BASELINE REPRODUCTION FAILED: {e}", flush=True)
        (HERE / "results.json").write_text(json.dumps(
            {"status": "STOPPED", "reason": "baseline reproduction failed",
             "detail": str(e)}, indent=1))
        sys.exit(2)
    print("baseline repro OK: G2 5.41 / G2+carry 5.634 DD 16.75 full 16.66",
          flush=True)

    if args.smoke:
        print("smoke: baseline only (guard/scoring covered by pytest)", flush=True)
        return

    # ---- step 1: replica ledger ----
    led, grids = build_ledger()
    n = len(led["w"])
    print(f"ledger fills={n}", flush=True)
    chk = hashlib.sha256(
        np.round(np.stack([led["w"], led["y10"]]), 9).tobytes()).hexdigest()[:16]

    base_sc = score_assignment(led["phase"], led["year"], led["w"],
                               led["y10"], led["d10"])
    print("base 4-phase-mean sums:",
          [round(r["S"], 4) for r in base_sc["per_year"]], flush=True)

    # fidelity vs oc_velocity phase-0 raw sums (same y1.0 definition)
    ref_p0 = [2.388, 0.183, 3.810, 2.579, 0.712]
    got_p0 = []
    for y in range(5):
        m = (led["phase"] == 0) & (led["year"] == y)
        got_p0.append(float((led["w"][m] * led["y10"][m]).sum()))
    # fidelity vs oc_placebo_dip 4-phase-mean base
    ref_m4 = [0.911, 0.833, 2.100, 3.197, 0.677]
    got_m4 = [base_sc["per_year"][y]["S"] for y in range(5)]

    # ---- step 2: guard flags + variants ----
    lookup, cov = build_guard_lookup(grids)
    keys = np.array([(p, c, b) for p, c, b in
                     zip(led["phase"], led["coin"], led["bar_time"])])
    o1_skip = np.array([lookup[(int(p), int(c), int(b))][0]
                        for p, c, b in keys])
    o2_skip = np.array([lookup[(int(p), int(c), int(b))][1]
                        for p, c, b in keys])
    keep_o1 = ~o1_skip
    keep_o2 = ~o2_skip
    o1_sc = score_assignment(led["phase"][keep_o1], led["year"][keep_o1],
                             led["w"][keep_o1], led["y10"][keep_o1],
                             led["d10"][keep_o1])
    o2_sc = score_assignment(led["phase"][keep_o2], led["year"][keep_o2],
                             led["w"][keep_o2], led["y10"][keep_o2],
                             led["d10"][keep_o2])

    # ---- step 3: dev4 selection (2025 masked until choice frozen) ----
    dev = {}
    for v, sc in (("O1", o1_sc), ("O2", o2_sc)):
        lg = legs_vs_base(sc, base_sc, DEV_YEARS)
        dev[v] = {"sum_ge": lg["years_sum_ge"], "dd_ok": lg["years_dd_ok"],
                  "dsum": dev4_dsum(sc, base_sc)}
    sel = select_on_dev4(dev)
    chosen = sel["chosen"]
    print(json.dumps({"dev": dev, "sel": sel}, indent=1), flush=True)

    per_year_out = {}
    for v, sc in (("base", base_sc), ("O1", o1_sc), ("O2", o2_sc)):
        rows = []
        for y in range(5):
            if v in ("O1", "O2") and y == POST_YEAR and v != chosen:
                rows.append({"year": ANCHORS[y].date().isoformat(),
                             "masked": True,
                             "note": "2025 scored once for the chosen variant only"})
                continue
            r = sc["per_year"][y]
            post = (y == POST_YEAR and v == chosen)
            rows.append({"year": ANCHORS[y].date().isoformat(),
                         "S": round(r["S"], 6), "DD": round(r["DD"], 6),
                         "n": round(r["n"], 2), "win": round(r["win"], 6),
                         "per_phase_sums": [round(s, 6) for s in r["per_phase_sums"]],
                         **({"POST_HOC": True} if post else {})})
        per_year_out[v] = rows

    res = {
        "meta": {
            "idea": "IDEAS2_20261007 section 2: OI-unwind dip-bid guard",
            "prereg": "REPORT.md section 0 (O1/O2 only; dev4 selection; +0.273 gate; 2025 once for chosen)",
            "baseline_src": "research/tournament/oc_carrycompound/results.json + v421_result.json (read-only, no engine rerun)",
            "replica": "oc_placebo_dip-exact D0+B1 4-phase (y1.0 leg); guard = subset sums, no renormalisation",
            "oi": f"{OI_COL} from data/raw/um_metrics_20260926 (as-of <=T-5min; metrics_ext_20260924 is a redundant BTC subset, unused)",
            "costs": "maker 0.0002 / taker 0.00055 / settle funding 0.0001 (gate: maker 0.02%%, taker 0.055%%, longs 0.01%%/8h)",
            "resources": "one process via scripts/heavy_slot.py; scratch under research/tournament/oc_i2_oiguard/tmp/",
        },
        "status": "SCREENED",
        "baseline": base,
        "fidelity": {
            "ledger_checksum": chk,
            "n_fills": int(n),
            "phase0_raw_sums_got": [round(s, 6) for s in got_p0],
            "phase0_raw_sums_oc_velocity_B1": ref_p0,
            "mean4_sums_got": [round(s, 6) for s in got_m4],
            "mean4_sums_oc_placebo_dip_base": ref_m4,
        },
        "guard_coverage": cov,
        "removed_fills": {"O1": int(o1_skip.sum()), "O2": int(o2_skip.sum()),
                          "base_fills": int(n)},
        "dev4_selection": {"dev": dev, "pass": sel["pass"], "chosen": chosen,
                           "gate_dsum": GATE_DSUM},
        "per_year": per_year_out,
        "engine_4phase": "NOT RUN (screen-gated; see verdict)" if chosen is None
                         else "GATED: run only on screen pass (see verdict)",
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(f"screen done: chosen={chosen} O1rem={int(o1_skip.sum())} "
          f"O2rem={int(o2_skip.sum())}", flush=True)


if __name__ == "__main__":
    main()
