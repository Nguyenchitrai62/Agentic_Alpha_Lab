"""oc_lit_position Leg0: H6-O2 dip-bid skip screen (gates the O2 engine row).

PLAN-fixed (see PLAN.md). Replica = oc_placebo_dip-exact D0+B1 4-phase
(TP1sg/sl4sg-close5/bl8sg/timeout next-bar open; maker 0.0002/taker 0.00055;
v293 settle funding; B1 sizes w=1/(1+n); majors x R2 2.5..5.0; live 16..238
strict trade-through; bars open [2021-09-24,2026-09-24); 4 clock phases from
2020-08-01 +0/1/2/3h). O2dip: skip NEW bids on (phase,coin,bar) bars where the
H6-O2 condition fires (per-coin 7d OI-change z > 1.5, same 5-min-lag OI as-of
as signals.py; NaN -> no skip). Holds/exits unchanged; subset sums, no
renormalisation. PROMISING iff sum>=base in >=4/5y AND DD<=base+0.01 in >=4/5y
AND dSum5y >= +0.273 (pooled placebo p95). O2 engine runs ONLY if PROMISING.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_lit_position_dip \
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \
    research/tournament/oc_lit_position/compute_dip_o2.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from signals import h6_d7_z, load_oi

import numpy as np
import pandas as pd

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
LIVE_A, LIVE_B = 16, 238
M_SL, BACKSTOP = 4.0, 8.0
DETECT_K = 2.5
DD_TOL = 0.01
GATE_DSUM = 0.273
O2_THRESH = 1.5

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


def _first_idx(mask: np.ndarray):
    if mask.any():
        return int(np.argmax(mask))
    return None


def n_vector(close_others, open_others, sigma_others):
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


def find_fill(low_win, level: float):
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


def year_of(t0):
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


def cell_stats(dates, wy):
    if wy.size == 0:
        return 0.0, 0.0, 0.0
    order = np.argsort(dates, kind="stable")
    d = dates[order]
    v = wy[order]
    _, idx = np.unique(d, return_index=True)
    bounds = np.append(idx[1:], v.size)
    daily = np.array([v[s:e].sum() for s, e in zip(idx, bounds)])
    cum = np.cumsum(daily)
    peak = np.maximum.accumulate(cum)
    dd = float(np.min(cum - peak))
    return float(daily.sum()), float(daily.min()), float(-dd)


def score_assignment(ph, yr, wv, yv, dv):
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


def build_ledger():
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


def build_o2_lookup(grids):
    lookup = {}
    cov = {}
    for p in PHASES:
        g = grids[p]
        t0 = g["t0"]
        bt_ns = t0.values.astype("datetime64[ns]").astype(np.int64)
        for ci, sym in enumerate(MAJORS):
            opens = g["opens"][sym]
            oi_t, oi_v = load_oi(sym)
            _, z = h6_d7_z(bt_ns, oi_t, oi_v)
            fire = np.isfinite(z) & (z > O2_THRESH)
            cov[f"{p}/{sym}"] = {"grid_bars": int(len(bt_ns)),
                                 "eligible": int(np.isfinite(z).sum()),
                                 "fires": int(fire.sum())}
            for i, j in enumerate(g["js"]):
                lookup[(p, ci, int(g["off"] + j * 240))] = bool(fire[j])
            print(f"O2 {p}/{sym}: eligible={cov[f'{p}/{sym}']['eligible']} "
                  f"fires={cov[f'{p}/{sym}']['fires']}", flush=True)
    return lookup, cov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    # placebo base reproduction (read-only)
    pb = json.loads((ROOT / "research/tournament/oc_placebo_dip/results.json").read_text())
    assert abs(pb["base_sum5y"] - 7.718304) < 1e-6, pb["base_sum5y"]
    assert abs(pb["stricter"]["gate_pooled_p95_dSum5y"] - 0.272796) < 1e-6
    print("placebo gate repro OK: base 7.718304 / p95 0.272796", flush=True)

    if args.smoke:
        print("smoke: baseline only", flush=True)
        return

    led, grids = build_ledger()
    n = len(led["w"])
    print(f"ledger fills={n}", flush=True)
    chk = hashlib.sha256(
        np.round(np.stack([led["w"], led["y10"]]), 9).tobytes()).hexdigest()[:16]
    base_sc = score_assignment(led["phase"], led["year"], led["w"],
                               led["y10"], led["d10"])
    print("base 4-phase-mean sums:",
          [round(r["S"], 4) for r in base_sc["per_year"]], flush=True)
    ref_p0 = [2.388, 0.183, 3.810, 2.579, 0.712]
    got_p0 = []
    for y in range(5):
        m = (led["phase"] == 0) & (led["year"] == y)
        got_p0.append(float((led["w"][m] * led["y10"][m]).sum()))

    lookup, cov = build_o2_lookup(grids)
    keys = list(zip(led["phase"], led["coin"], led["bar_time"]))
    skip = np.array([lookup[(int(p), int(c), int(b))] for p, c, b in keys])
    keep = ~skip
    o2_sc = score_assignment(led["phase"][keep], led["year"][keep],
                             led["w"][keep], led["y10"][keep],
                             led["d10"][keep])
    s_ge = sum(1 for y in range(5)
               if o2_sc["per_year"][y]["S"] >= base_sc["per_year"][y]["S"])
    d_ok = sum(1 for y in range(5)
               if o2_sc["per_year"][y]["DD"] <= base_sc["per_year"][y]["DD"] + DD_TOL)
    dsum5 = float(o2_sc["sum5y"] - base_sc["sum5y"])
    dev_dsum = float(sum(o2_sc["per_year"][y]["S"] - base_sc["per_year"][y]["S"]
                         for y in range(4)))
    promising = bool(s_ge >= 4 and d_ok >= 4 and dsum5 >= GATE_DSUM)
    print(json.dumps({"sum_ge": s_ge, "dd_ok": d_ok, "dSum5y": round(dsum5, 6),
                      "dev4_dsum": round(dev_dsum, 6), "promising": promising,
                      "removed": int(skip.sum())}, indent=1), flush=True)
    res = {
        "meta": {
            "idea": "H6-O2 dip leg: skip new dip bids when per-coin 7d OI-change z > 1.5",
            "prereg": "PLAN.md Leg0 (O2dip only; PROMISING needs 4/5 sums + 4/5 DD + dSum>=0.273)",
            "replica": "oc_placebo_dip-exact D0+B1 4-phase (y1.0 leg); subset sums, no renormalisation",
            "oi": "sum_open_interest from data/raw/um_metrics_20260926 (as-of <=T-5min; 7d log change; trailing 2190/min540; NaN->no skip)",
            "costs": "maker 0.0002 / taker 0.00055 / settle funding 0.0001",
        },
        "status": "SCREENED",
        "fidelity": {
            "ledger_checksum": chk, "n_fills": int(n),
            "phase0_raw_sums_got": [round(s, 6) for s in got_p0],
            "phase0_raw_sums_ref": ref_p0,
            "mean4_sums_got": [round(r["S"], 6) for r in base_sc["per_year"]],
        },
        "guard_coverage": cov,
        "removed_fills": int(skip.sum()),
        "screen": {
            "sum_ge_5y": int(s_ge), "dd_ok_5y": int(d_ok),
            "dSum5y": round(dsum5, 6), "dev4_dsum": round(dev_dsum, 6),
            "promising": promising,
            "o2_engine_allowed": promising,
        },
        "per_year": {
            "base": [{"year": ANCHORS[y].date().isoformat(),
                      "S": round(base_sc["per_year"][y]["S"], 6),
                      "DD": round(base_sc["per_year"][y]["DD"], 6)}
                     for y in range(5)],
            "O2dip": [{"year": ANCHORS[y].date().isoformat(),
                       "S": round(o2_sc["per_year"][y]["S"], 6),
                       "DD": round(o2_sc["per_year"][y]["DD"], 6)}
                      for y in range(5)],
        },
    }
    (HERE / "dip_results.json").write_text(json.dumps(res, indent=1))
    print(f"dip screen done: promising={promising} removed={int(skip.sum())}", flush=True)


if __name__ == "__main__":
    main()
