"""oc_placebo_dip: false-positive rate of the dip-screen PROMISING criterion.

Replica: exact oc_dipexit D0 rung outcomes (TP 1 sigma, close5 stop 4 sigma,
8-sigma backstop, timeout at next 4h open; maker 0.0002 / taker 0.00055;
v293 settle funding on timeouts) with oc_b1deeper B1 sizes w = 1/(1+n_fill),
on all four clock phases (4h grid from 2020-08-01 00:00 UTC + 0/1/2/3h),
majors x R2 depths {2.5,3,3.5,4,5}, bars with open in [2021-09-24,2026-09-24).
Phase 0 == oc_dipexit grid exactly. See module docstring of run for the
pre-registered placebo design.

300 seeded placebo rules, 100 per shape (seed 20261006):
  (A) size tilt: per rule a fraction q ~ Uniform(0.10,0.20) of BARS is picked
      by a seeded hash of the bar time (never by returns); on picked bars the
      rung weight is multiplied by m in {0.8, 1.2} (one m per rule, seeded).
  (B) skip: each rung fill is skipped iff seeded-hash(fill key) < 0.10.
  (C) TP jitter: per rule t in {0.9, 1.1} (seeded); each fill uses TP t*sigma
      iff seeded-hash(fill key) < 0.20, else TP 1.0 sigma (exact outcome legs
      y0.9 / y1.0 / y1.1 precomputed per fill, exits race identically to D0).

Criterion (typical dip-screen rule): per year on 4-phase means,
PASS_sum(Y) iff S_bar_rule(Y) >= S_bar_base(Y);
PASS_dd(Y) iff DD_bar_rule(Y) <= DD_bar_base(Y) + 0.01 (1 pp).
PROMISING iff PASS_sum in >= 4/5 years AND PASS_dd in >= 4/5 years.
The sum-half (>= 4/5 alone) is scored too.

Outputs: results.json (this folder). One process, one coin H/L at a time,
all-five-coins 1m O/C float32, RAM < 3 GB.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_placebo_dip \\
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \\
    research/tournament/oc_placebo_dip/compute_placebo_dip.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent

# --------------------------------------------------------------------------
# frozen config (pre-registered)
# --------------------------------------------------------------------------
SEED = 20261006
N_A, N_B, N_C = 100, 100, 100  # 300 placebo rules total
FRAC_B = 0.10  # shape B skip rate
FRAC_C = 0.20  # shape C jittered-fill rate
DD_TOL = 0.01  # 1 pp maxDD tolerance (dip-screen convention)

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
TP_LEGS = (0.9, 1.0, 1.1)

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


# --------------------------------------------------------------------------
# exact replica core (oc_dipexit outcome_mu + oc_b1deeper/oc_stoptf n/size/fill)
# --------------------------------------------------------------------------
def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    """v399-exact correlation count per live minute (0..4). NaN -> no detect."""
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


# --------------------------------------------------------------------------
# seeded hash selection (keys only: phase / bar time / coin / rung + seed;
# never returns, prices, or outcomes)
# --------------------------------------------------------------------------
_SPLIT_A = np.uint64(0x9E3779B97F4A7C15)
_SPLIT_B = np.uint64(0xBF58476D1CE4E5B9)
_SPLIT_C = np.uint64(0x94D049BB133111EB)
_MAXT = np.uint64(4194304)  # 2^22 > max bar-time ordinal (~3.2M minutes)


def hash_uniform(key: np.ndarray) -> np.ndarray:
    """splitmix64 key -> uniform [0,1). Vectorised over uint64 array."""
    z = np.asarray(key, dtype=np.uint64) + _SPLIT_A
    z = (z ^ (z >> np.uint64(30))) * _SPLIT_B
    z = (z ^ (z >> np.uint64(27))) * _SPLIT_C
    z = z ^ (z >> np.uint64(31))
    return ((z >> np.uint64(11)).astype(np.float64)) / float(1 << 53)


def bar_key(tag: int, rule: int, phase: np.ndarray,
            bar_time: np.ndarray) -> np.ndarray:
    """64-bit key per (tag, rule, phase, bar_time ordinal)."""
    k = (np.uint64(tag * 256 + rule) * np.uint64(4)
         + phase.astype(np.uint64))
    k = k * _MAXT + bar_time.astype(np.uint64)
    return k + np.uint64(SEED)


def fill_key(tag: int, rule: int, phase: np.ndarray, bar_time: np.ndarray,
             coin: np.ndarray, rung: np.ndarray) -> np.ndarray:
    """64-bit key per (tag, rule, phase, bar_time, coin, rung)."""
    k = bar_key(tag, rule, phase, bar_time) * np.uint64(32)
    return k + (coin.astype(np.uint64) * np.uint64(8)
                + rung.astype(np.uint64))


# --------------------------------------------------------------------------
# scoring helpers
# --------------------------------------------------------------------------
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


def qstats(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    return {
        "mean": round(float(np.mean(x)), 6),
        "sd": round(float(np.std(x, ddof=1)) if len(x) > 1 else 0.0, 6),
        "min": round(float(np.min(x)), 6),
        "p5": round(float(np.quantile(x, 0.05)), 6),
        "p25": round(float(np.quantile(x, 0.25)), 6),
        "p50": round(float(np.quantile(x, 0.50)), 6),
        "p75": round(float(np.quantile(x, 0.75)), 6),
        "p95": round(float(np.quantile(x, 0.95)), 6),
        "max": round(float(np.max(x)), 6),
    }


# --------------------------------------------------------------------------
# data loading (1m, float32, one coin H/L at a time)
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


# --------------------------------------------------------------------------
# base replica -> per-fill ledger arrays
# --------------------------------------------------------------------------
def build_base(max_bars_per_coin_phase: int | None = None,
               coins: tuple = MAJORS, phases: tuple = PHASES) -> dict:
    """Run the exact D0+B1 4-phase replica; return ledger dict of np arrays.

    Kept fills: filled on lv AND y0.9/y1.0/y1.1 all finite (paired TP legs).
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
                         "w", "y09", "y10", "y11", "d09", "d10", "d11")}
    coin_ix = {s: i for i, s in enumerate(coins)}
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
                base = off + j * 240
                o2m = Oa[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                if yi is None:
                    continue
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
                    r09, x09, _ = outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 0.9, o2, settle)
                    r10, x10, _ = outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                    r11, x11, _ = outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.1, o2, settle)
                    if not (np.isfinite(r09) and np.isfinite(r10) and np.isfinite(r11)):
                        continue
                    n_fill += 1
                    F["phase"].append(p)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(yi)
                    F["bar_time"].append(off + j * 240)  # minute ordinal since START
                    F["rung"].append(ri)
                    F["w"].append(size_mult(nf))
                    F["y09"].append(r09)
                    F["y10"].append(r10)
                    F["y11"].append(r11)
                    F["d09"].append(exit_day_ordinal(bt, x09, base))
                    F["d10"].append(exit_day_ordinal(bt, x10, base))
                    F["d11"].append(exit_day_ordinal(bt, x11, base))
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha
    led = {k: np.array(v) for k, v in F.items()}
    for k in ("phase", "coin", "year", "bar_time", "rung", "d09", "d10", "d11"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y09", "y10", "y11"):
        led[k] = led[k].astype(np.float64)
    return led


# --------------------------------------------------------------------------
# aggregation of one weight/outcome assignment -> 4-phase means + full path
# --------------------------------------------------------------------------
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
                         "per_phase_sums": [float(s) for s in ss]})
    s_full, _, dd_full = cell_stats(dv, wv * yv)
    return {"per_year": per_year,
            "sum5y": float(sum(r["S"] for r in per_year)),
            "ddmean": float(np.mean([r["DD"] for r in per_year])),
            "full_sum": float(s_full), "full_dd": float(dd_full)}


def decide(rule_sc: dict, base_sc: dict) -> dict:
    ps = sum(1 for y in range(5)
             if rule_sc["per_year"][y]["S"] >= base_sc["per_year"][y]["S"])
    pd_ = sum(1 for y in range(5)
              if rule_sc["per_year"][y]["DD"] <= base_sc["per_year"][y]["DD"] + DD_TOL)
    return {"years_sum_ge": int(ps), "years_dd_ok": int(pd_),
            "pass_sum_half": bool(ps >= 4), "pass_dd_half": bool(pd_ >= 4),
            "promising": bool(ps >= 4 and pd_ >= 4),
            "dSum5y": float(rule_sc["sum5y"] - base_sc["sum5y"]),
            "dDDmean": float(rule_sc["ddmean"] - base_sc["ddmean"]),
            "dDDfull": float(rule_sc["full_dd"] - base_sc["full_dd"])}


# --------------------------------------------------------------------------
# placebo loop
# --------------------------------------------------------------------------
def run_placebos(led: dict) -> dict:
    rng = np.random.default_rng(SEED)
    ph = led["phase"].astype(np.uint64)
    bt = led["bar_time"].astype(np.uint64)
    co = led["coin"].astype(np.uint64)
    ru = led["rung"].astype(np.uint64)
    w0 = led["w"]
    n = len(w0)
    out = {}
    ph0, yr0 = led["phase"], led["year"]

    # ---- shape A: size tilt on a random 10-20% of bars ----
    rules_a = []
    for i in range(N_A):
        q = float(rng.uniform(0.10, 0.20))
        m = float(rng.choice((0.8, 1.2)))
        sel = hash_uniform(bar_key(1, i, ph, bt)) < q
        wv = w0 * np.where(sel, m, 1.0)
        sc = score_assignment(ph0, yr0, wv, led["y10"], led["d10"])
        dec = decide(sc, out.get("base", sc))  # placeholder, fixed below
        rules_a.append({"q": round(q, 6), "mult": m, "dec": dec, "sc": sc})
    out["A"] = rules_a

    # ---- shape B: skip 10% of fills ----
    rules_b = []
    for i in range(N_B):
        keep = hash_uniform(fill_key(2, i, ph, bt, co, ru)) >= FRAC_B
        sc = score_assignment(ph0[keep], yr0[keep], w0[keep], led["y10"][keep], led["d10"][keep])
        rules_b.append({"dec": decide(sc, out.get("base", sc)), "sc": sc})
    out["B"] = rules_b

    # ---- shape C: TP x0.9/x1.1 on a random 20% of fills ----
    rules_c = []
    for i in range(N_C):
        t = float(rng.choice((0.9, 1.1)))
        sel = hash_uniform(fill_key(3, i, ph, bt, co, ru)) < FRAC_C
        if t == 0.9:
            yv = np.where(sel, led["y09"], led["y10"])
            dv = np.where(sel, led["d09"], led["d10"])
        else:
            yv = np.where(sel, led["y11"], led["y10"])
            dv = np.where(sel, led["d11"], led["d10"])
        sc = score_assignment(ph0, yr0, w0, yv, dv)
        rules_c.append({"tp": t, "dec": decide(sc, out.get("base", sc)), "sc": sc})
    out["C"] = rules_c
    return out


def summarise(shape_rules: list) -> dict:
    dec = [r["dec"] for r in shape_rules]
    dsum = np.array([d["dSum5y"] for d in dec])
    ddd = np.array([d["dDDmean"] for d in dec])
    ddf = np.array([d["dDDfull"] for d in dec])
    return {
        "n": len(dec),
        "fpr_full": round(float(np.mean([d["promising"] for d in dec])), 4),
        "rate_sum_half": round(float(np.mean([d["pass_sum_half"] for d in dec])), 4),
        "rate_dd_half": round(float(np.mean([d["pass_dd_half"] for d in dec])), 4),
        "n_full": int(sum(d["promising"] for d in dec)),
        "n_sum_half": int(sum(d["pass_sum_half"] for d in dec)),
        "n_dd_half": int(sum(d["pass_dd_half"] for d in dec)),
        "dSum5y": qstats(dsum),
        "dDDmean": qstats(ddd),
        "dDDfull": qstats(ddf),
        "dSum5y_list": [round(float(v), 6) for v in dsum],
        "dDDmean_list": [round(float(v), 6) for v in ddd],
        "dDDfull_list": [round(float(v), 6) for v in ddf],
        "pass_full_list": [bool(d["promising"]) for d in dec],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="test-only: 1 coin, phase 0, 300 bars, 9 rules; no files")
    args = ap.parse_args()

    if args.smoke:
        led = build_base(max_bars_per_coin_phase=300, coins=("BTCUSDT",),
                         phases=(0,))
        print(f"smoke ledger n={len(led['w'])}", flush=True)
        global N_A, N_B, N_C
        N_A, N_B, N_C = 3, 3, 3
    else:
        led = build_base()
    n = len(led["w"])
    print(f"ledger fills={n}", flush=True)

    base_sc = score_assignment(led["phase"], led["year"], led["w"], led["y10"], led["d10"])
    print("base 4-phase-mean sums:",
          [round(r["S"], 4) for r in base_sc["per_year"]], flush=True)
    print("base 4-phase-mean DDs:",
          [round(r["DD"], 4) for r in base_sc["per_year"]], flush=True)

    # phase-0 fidelity vs oc_stoptf D0 raw sums (B1 sizes, same replica;
    # pairing differs slightly: here all 3 TP legs finite).
    ref_p0 = [2.388, 0.183, 3.810, 2.579, 0.712]
    got_p0 = []
    for y in range(5):
        m = (led["phase"] == 0) & (led["year"] == y)
        got_p0.append(float((led["w"][m] * led["y10"][m]).sum()))
    print("phase0 sums:", [round(s, 4) for s in got_p0], flush=True)
    print("phase0 ref :", ref_p0, flush=True)

    raw = run_placebos(led)
    # fix the base reference used in decide() (was placeholder)
    for shape in ("A", "B", "C"):
        for r in raw[shape]:
            r["dec"] = decide(r["sc"], base_sc)
            del r["sc"]

    res = {
        "config": {
            "seed": SEED,
            "n_rules": {"A_size_tilt": N_A, "B_skip": N_B, "C_tp_jitter": N_C},
            "shape_A": "per rule q~U(0.10,0.20) of bars via splitmix64 hash of "
                       "(seed,rule,phase,bar_time); weight x m in {0.8,1.2} "
                       "(one m per rule); y = D0 y1.0",
            "shape_B": "per fill skip iff splitmix64(seed,rule,phase,bar_time,"
                       "coin,rung) < 0.10; y = D0 y1.0",
            "shape_C": "per rule t in {0.9,1.1}; per fill use TP t*sigma iff "
                       "splitmix64(seed,rule,phase,bar_time,coin,rung) < 0.20 "
                       "(exact y0.9/y1.1 legs, same race/fees); else TP 1.0",
            "selection_uses_only": "phase/bar_time/coin/rung ids + seed; "
                                   "never returns, prices, or outcomes",
            "replica": "oc_dipexit D0 exact (TP1sg, sl4sg close5, bl8sg, "
                       "timeout next-bar open; maker 0.0002/taker 0.00055; "
                       "v293 settle funding) + oc_b1deeper B1 sizes w=1/(1+n); "
                       "4 clock phases (4h grid 2020-08-01 + 0/1/2/3h); "
                       "majors x R2 rungs 2.5..5.0; live offsets 16..238 "
                       "strict trade-through; bars open [2021-09-24,2026-09-24)",
            "pairing": "kept only if y0.9,y1.0,y1.1 all finite",
            "criterion": "per year on 4-phase means: PASS_sum iff S_rule>=S_base; "
                         "PASS_dd iff DD_rule<=DD_base+0.01; PROMISING iff "
                         "both in >=4/5 years",
            "deltas": "dSum5y = sum_Y(Sbar_rule-Sbar_base); dDDmean = "
                      "mean_Y(DDbar_rule-DDbar_base); dDDfull = pooled "
                      "all-phase full-path DD difference",
            "resources": "one process, majors 1m O/C float32 + one-coin H/L",
        },
        "n_fills": int(n),
        "ledger_checksum": hashlib.sha256(
            np.round(np.stack([led["w"], led["y09"], led["y10"],
                               led["y11"]]), 9).tobytes()).hexdigest()[:16],
        "base_mean4": [
            {"year": ANCHORS[y].date().isoformat(),
             "S": round(base_sc["per_year"][y]["S"], 6),
             "DD": round(base_sc["per_year"][y]["DD"], 6),
             "n": round(base_sc["per_year"][y]["n"], 2),
             "win": round(base_sc["per_year"][y]["win"], 6),
             "per_phase_sums": [round(s, 6) for s in
                                base_sc["per_year"][y]["per_phase_sums"]]}
            for y in range(5)
        ],
        "base_sum5y": round(base_sc["sum5y"], 6),
        "phase0_fidelity": {
            "got_raw_sums": [round(s, 6) for s in got_p0],
            "oc_stoptf_D0_raw_sums": ref_p0,
            "note": "same replica+B1 sizes; pairing differs (here 3 TP legs)",
        },
    }
    for shape in ("A", "B", "C"):
        res[f"placebo_{shape}"] = summarise(raw[shape])
        if shape == "A":
            res["placebo_A"]["rules_q_mult"] = [
                {"q": r["q"], "mult": r["mult"]} for r in raw[shape]]
        if shape == "C":
            res["placebo_C"]["rules_tp"] = [r["tp"] for r in raw[shape]]

    # ---- stricter gates (pre-registered method) ----
    all_dsum = np.array(res["placebo_A"]["dSum5y_list"]
                        + res["placebo_B"]["dSum5y_list"]
                        + res["placebo_C"]["dSum5y_list"])
    g_all = float(np.quantile(all_dsum, 0.95))
    g_shapes = {s: float(np.quantile(np.array(res[f"placebo_{s}"]["dSum5y_list"]), 0.95))
                for s in ("A", "B", "C")}
    g_effect = round(0.02 * abs(base_sc["sum5y"]), 6)  # 2% of base 5y total
    strict = {"gate_pooled_p95_dSum5y": round(g_all, 6),
              "gate_per_shape_p95_dSum5y": {s: round(g, 6) for s, g in g_shapes.items()},
              "gate_effect_2pct_base5y": g_effect}
    for name, gate in (("pooled_p95", g_all),
                       ("max_shape_p95", max(g_shapes.values())),
                       ("effect_2pct", g_effect)):
        for s in ("A", "B", "C"):
            d = np.array(res[f"placebo_{s}"]["dSum5y_list"])
            p = np.array(res[f"placebo_{s}"]["pass_full_list"])
            joint = p & (d >= gate)
            strict[f"S1_full_plus_dSum_ge_{name}_{s}"] = round(float(joint.mean()), 4)
        dall = all_dsum
        pall = np.array(res["placebo_A"]["pass_full_list"]
                        + res["placebo_B"]["pass_full_list"]
                        + res["placebo_C"]["pass_full_list"])
        strict[f"S1_full_plus_dSum_ge_{name}_pooled"] = round(float(((pall) & (dall >= gate)).mean()), 4)
        # sum-half + tail (sensitivity)
        for s in ("A", "B", "C"):
            r = raw[s]
            sh = np.array([rr["dec"]["pass_sum_half"] for rr in r])
            d = np.array(res[f"placebo_{s}"]["dSum5y_list"])
            strict[f"S2_sumhalf_plus_dSum_ge_{name}_{s}"] = round(float((sh & (d >= gate)).mean()), 4)
    strict["recommendation"] = ("require the full PROMISING legs PLUS 5y "
                                "4-phase-mean sum delta >= pooled placebo p95; "
                                "realised joint FPRs above, must be <= 0.05")
    res["stricter"] = strict

    if args.smoke:
        print(json.dumps({"n": n, "base_sum5y": res["base_sum5y"],
                          "fpr": {s: res[f"placebo_{s}"]["fpr_full"]
                                  for s in ("A", "B", "C")}}, indent=1))
        return
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({"n": n, "checksum": res["ledger_checksum"],
                      "fpr_full": {s: res[f"placebo_{s}"]["fpr_full"]
                                   for s in ("A", "B", "C")},
                      "rate_sum_half": {s: res[f"placebo_{s}"]["rate_sum_half"]
                                        for s in ("A", "B", "C")},
                      "gate_pooled_p95": strict["gate_pooled_p95_dSum5y"]}, indent=1))


if __name__ == "__main__":
    main()
