"""oc_tapepeg run: 4-phase D0+B1 replica + tape-anchored V1/V2 (heavy 1m job).

Frozen definitions in PLAN.md (IDEAS6 #4). One process, one coin H/L at a time,
float32 1m arrays, RAM < 3 GB. Run ONLY via the shared semaphore:
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_tapepeg --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_tapepeg/run.py
Long job: heartbeat every 600 s. Log to tmp/run.log when launched with nohup.

Outputs: tmp/ledger.npz + results.json (this folder).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from tapepeg import (LIVE_A, LIVE_B, LOOKBACK, find_fill, n_vector, outcome_mu,
                     rung_px, size_mult, trailing_low)

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
PHASES = (0, 1, 2, 3)
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
DD_TOL = 0.01
DSUM_GATE = 0.273
# Fidelity refs (disclosed, not binding gates).
REF_P0 = [2.388, 0.183, 3.810, 2.579, 0.712]  # oc_dipexit phase-0 raw sums
REF_M4 = [0.911, 0.833, 2.100, 3.197, 0.677]  # oc_placebo_dip 4-phase means


def year_of(t0) -> int | None:
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def exit_day_ordinal(bt: pd.Timestamp, x: int) -> int:
    d = (bt + pd.Timedelta(minutes=int(x))).date()
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="test-only: BTC phase 0, first 300 traded bars; writes tmp/smoke.json")
    args = ap.parse_args()
    smoke = bool(args.smoke)
    coins = ("BTCUSDT",) if smoke else MAJORS
    phases = (0,) if smoke else PHASES
    t_start = time.time()
    last_beat = t_start

    def beat(msg: str):
        print(f"[{time.time() - t_start:8.0f}s] {msg}", flush=True)

    O, C, base_idx = {}, {}, None
    for sym in coins:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        beat(f"loaded OC {sym}")
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
        if smoke:
            js = js[:300]
        grids[p] = dict(off=off, nb=nb, t0=t0, opens=opens_bar, sig=sig_bar, js=js)
        beat(f"shift {p}: nb={nb} traded={len(js)}")
    del opens_bar, sig_bar

    F = {k: [] for k in ("phase", "coin", "year", "arm",
                         "w", "y", "d", "x", "h")}
    coin_ix = {s: i for i, s in enumerate(MAJORS)}
    arm_ix = {"base": 0, "V1": 1, "V2": 2}
    n_rungs = 0
    n_peg_bind_v1 = 0
    n_peg_bind_v2 = 0
    n_bars = 0
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
                if not np.isfinite(o2):
                    continue
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                if yi is None:
                    continue
                n_bars += 1
                low_win = La[base + LIVE_A:base + LIVE_B + 1].astype(float)
                if base - LOOKBACK >= 0:
                    low60 = trailing_low(La[base - LOOKBACK:base].astype(float))
                else:
                    low60 = np.nan
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
                for k in RUNGS:
                    lv_b, lv_1, lv_2 = rung_px(o1, sg, k, low60)
                    if not (np.isfinite(lv_b) and lv_b > 0):
                        continue
                    n_rungs += 1
                    if lv_1 < lv_b - 1e-12:
                        n_peg_bind_v1 += 1
                    if lv_2 < lv_b - 1e-12:
                        n_peg_bind_v2 += 1
                    for tag, lv in (("base", lv_b), ("V1", lv_1), ("V2", lv_2)):
                        if not (np.isfinite(lv) and lv > 0):
                            continue
                        ib = find_fill(low_win, lv)
                        if ib is None:
                            continue
                        f = LIVE_A + ib
                        nf = int(nvec[ib])
                        ret, x, how = outcome_mu(
                            Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                        if not np.isfinite(ret):
                            continue
                        n_fill += 1
                        F["phase"].append(p)
                        F["coin"].append(coin_ix[sym])
                        F["year"].append(yi)
                        F["arm"].append(arm_ix[tag])
                        F["w"].append(size_mult(nf))
                        F["y"].append(float(ret))
                        F["d"].append(exit_day_ordinal(bt, int(x)))
                        F["x"].append(int(x))
                        F["h"].append(how)
                if time.time() - last_beat > 600:
                    beat(f"{sym} p{p}: bars={n_bars} fills={len(F['w'])}")
            beat(f"{sym} p{p}: fills={n_fill}")
        del H, L, La, Ha
    n = len(F["w"])
    beat(f"ledger fills={n} rungs={n_rungs} pegbind V1={n_peg_bind_v1} V2={n_peg_bind_v2}")

    led = {}
    for k in ("phase", "coin", "year", "arm", "d", "x"):
        led[k] = np.array(F[k], dtype=np.int64)
    for k in ("w", "y"):
        led[k] = np.array(F[k], dtype=np.float64)
    led_h = np.array(F["h"], dtype=object)
    if not smoke:
        np.savez(HERE / "tmp/ledger.npz",
                 **{k: led[k] for k in ("phase", "coin", "year", "arm", "w", "y", "d", "x")})
        beat("saved tmp/ledger.npz")

    def score_arm(tag: str):
        a = arm_ix[tag]
        m = led["arm"] == a
        ph, yr, wv, yv, dv = led["phase"][m], led["year"][m], led["w"][m], led["y"][m], led["d"][m]
        per_year = []
        for y in range(5):
            ss, ds = [], []
            for p in PHASES:
                mm = (ph == p) & (yr == y)
                if mm.any():
                    s, _, dd = cell_stats(dv[mm], (wv[mm] * yv[mm]))
                else:
                    s, dd = 0.0, 0.0
                ss.append(s)
                ds.append(dd)
            per_year.append({"S": float(np.mean(ss)), "DD": float(np.mean(ds)),
                             "sums": [float(s) for s in ss]})
        s_full, _, dd_full = cell_stats(dv, wv * yv)
        n_arm = int(m.sum())
        win = float((yv > 0).mean()) if n_arm else 0.0
        mean_bps = float(yv.mean() * 1e4) if n_arm else 0.0
        return {"per_year": per_year, "sum5y": float(sum(r["S"] for r in per_year)),
                "ddmean": float(np.mean([r["DD"] for r in per_year])),
                "full_sum": float(s_full), "full_dd": float(dd_full),
                "n": n_arm, "win": win, "mean_bps": mean_bps}

    base_sc = score_arm("base")
    v1_sc = score_arm("V1")
    v2_sc = score_arm("V2")
    beat(f"base 4-phase-mean sums={[round(r['S'], 4) for r in base_sc['per_year']]}")

    got_p0 = []
    for y in range(5):
        m = (led["phase"] == 0) & (led["year"] == y) & (led["arm"] == arm_ix["base"])
        got_p0.append(float((led["w"][m] * led["y"][m]).sum()))

    def decide(rsc, bsc):
        ps = sum(1 for y in range(5) if rsc["per_year"][y]["S"] >= bsc["per_year"][y]["S"] - 1e-12)
        pd_ = sum(1 for y in range(5) if rsc["per_year"][y]["DD"] <= bsc["per_year"][y]["DD"] + DD_TOL)
        return {"years_sum_ge": int(ps), "years_dd_ok": int(pd_),
                "pass_sum_half": bool(ps >= 4), "pass_dd_half": bool(pd_ >= 4),
                "promising_legs": bool(ps >= 4 and pd_ >= 4),
                "dSum5y": float(rsc["sum5y"] - bsc["sum5y"]),
                "dDDmean": float(rsc["ddmean"] - bsc["ddmean"]),
                "dDDfull": float(rsc["full_dd"] - bsc["full_dd"])}

    out = {"config": {
        "replica": "oc_dipexit/oc_placebo_dip-exact D0 (TP1sg, sl4sg close5, bl8sg, timeout next-bar "
                   "open; maker 0.0002/taker 0.00055; settle funding) + B1 sizes w=1/(1+n); 4 clock "
                   "phases (4h grid 2020-08-01 +0/1/2/3h); majors x R2 rungs 2.5..5.0; live 16..238 "
                   "strict trade-through; bars open [2021-09-24,2026-09-24)",
        "V1": "rung=min(sigma O*(1-k*sg), LOW60*(1-0.0001)) with LOW60=min 1m low over [T-60m,T-1m]; "
              "frozen at T; exits from the variant px; sizes w=1/(1+n_fill) at variant fill minute",
        "V2": "rung=min(sigma O*(1-k*sg), floor_to_5tick(LOW60*(1-0.0001))) with 5-tick grid "
              "5*LOW60*0.0001 (=0.9995*LOW60); frozen at T; same exits/sizes convention as V1",
        "tick_note": "1tick proxied as 1bp of LOW60 (conservative: real ticks ~0.17-0.33bps, so the "
                     "proxy peg is deeper and variant fill rates are lower bounds; disclosed in PLAN)",
        "criterion": "full PROMISING legs (sum>=base 4/5 AND DD<=base+0.01 4/5) PLUS dSum5y>=+0.273",
        "pairing": "arms scored independently (different fill sets by construction); no cross-arm "
                   "pairing; comparability from the identical bar universe + yearly-sum gate",
        "resources": "one process, one-coin H/L at a time, float32 1m, via heavy_slot"},
        "n_fills": int(n),
        "n_rungs": int(n_rungs),
        "peg_bind": {"V1_share": round(float(n_peg_bind_v1 / n_rungs), 4) if n_rungs else 0.0,
                     "V2_share": round(float(n_peg_bind_v2 / n_rungs), 4) if n_rungs else 0.0},
        "ledger_checksum": hashlib.sha256(
            np.round(np.stack([led["w"], led["y"]]), 9).tobytes()).hexdigest()[:16],
        "base_mean4": [{"year": ANCHORS[y].date().isoformat(),
                        "S": round(base_sc["per_year"][y]["S"], 6),
                        "DD": round(base_sc["per_year"][y]["DD"], 6)} for y in range(5)],
        "base_sum5y": round(base_sc["sum5y"], 6),
        "base_full": {"sum": round(base_sc["full_sum"], 6), "dd": round(base_sc["full_dd"], 6)},
        "phase0_fidelity": {"got_raw_sums": [round(s, 6) for s in got_p0],
                            "oc_dipexit_ref": REF_P0,
                            "base4_vs_placebo_ref": REF_M4,
                            "got_base4": [round(base_sc["per_year"][y]["S"], 6) for y in range(5)]}}
    for tag, sc in (("V1", v1_sc), ("V2", v2_sc)):
        dec = decide(sc, base_sc)
        gate = bool(dec["promising_legs"] and dec["dSum5y"] >= DSUM_GATE)
        rows = []
        for y in range(5):
            rows.append({"year": ANCHORS[y].date().isoformat(),
                         "base": round(base_sc["per_year"][y]["S"], 6),
                         tag.lower(): round(sc["per_year"][y]["S"], 6),
                         "base_dd": round(base_sc["per_year"][y]["DD"], 6),
                         f"{tag.lower()}_dd": round(sc["per_year"][y]["DD"], 6)})
        out[tag] = {"per_year": rows, "dec": {k: (round(v, 6) if isinstance(v, float) else v)
                                                for k, v in dec.items()},
                    "sum5y": round(sc["sum5y"], 6),
                    "full": {"sum": round(sc["full_sum"], 6), "dd": round(sc["full_dd"], 6)},
                    "n": sc["n"], "win": round(sc["win"], 4),
                    "mean_bps": round(sc["mean_bps"], 2),
                    "gate_pass": gate}
        beat(f"{tag}: dSum5y={dec['dSum5y']:.6f} sum={dec['years_sum_ge']}/5 "
             f"dd={dec['years_dd_ok']}/5 gate={gate}")
    out["base_diag"] = {"n": base_sc["n"], "win": round(base_sc["win"], 4),
                        "mean_bps": round(base_sc["mean_bps"], 2)}
    if smoke:
        (HERE / "tmp/smoke.json").write_text(json.dumps(
            {"n": n, "base_sum5y": out["base_sum5y"],
             "V1": out["V1"]["dec"], "V2": out["V2"]["dec"],
             "peg_bind": out["peg_bind"],
             "phase0": out["phase0_fidelity"]}, indent=1))
        beat("smoke done -> tmp/smoke.json (no results.json / ledger written)")
        print(json.dumps({"smoke_n": n, "base_sum5y": out["base_sum5y"]}, indent=1))
        return
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    beat("wrote results.json")
    print(json.dumps({"n": n, "base_sum5y": out["base_sum5y"],
                      "V1": out["V1"]["dec"], "V2": out["V2"]["dec"]}, indent=1))


if __name__ == "__main__":
    main()
