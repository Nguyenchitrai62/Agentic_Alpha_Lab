"""oc_relflush: inside a multi-coin flush, size the coin that overshoots more.

Replica: oc_placebo_dip-exact D0 outcomes (TP 1sg, close5 stop 4sg, 8sg
backstop, timeout at next-bar open; maker 0.0002 / taker 0.00055; v293 settle
funding) with B1 sizes w = 1/(1+n_fill), majors x R2 depths, live offsets
16..238 strict trade-through, on all four clock phases (4h grid from
2020-08-01 00:00 UTC + 0/1/2/3h), bars with open in [2021-09-24, 2026-09-24).
Phase 0 == oc_dipexit grid exactly. Rule: per-fill relative-flush tilts
R1 / R2 (sign control) / R3 (smooth), bot_only, minute f-1 only. See PLAN.md.

Usage:
  .venv/Scripts/python.exe research/tournament/oc_relflush/compute_relflush.py [--smoke]

Full run is HEAVY (4-phase 1m replica): wrap with scripts/heavy_slot.py.
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
sys.path.insert(0, str(HERE))
import core as K

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
DD_TOL = 0.01
GATE_DSUM = 0.273
EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


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
    return float(daily.sum()), float(daily.min()), float(-np.min(cum - peak))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="test-only: 1 coin, phase 0, 300 bars; no files")
    args = ap.parse_args()
    coins = ("BTCUSDT",) if args.smoke else MAJORS
    phases = (0,) if args.smoke else PHASES

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
        if args.smoke:
            js = js[:300]
        grids[p] = dict(off=off, nb=nb, t0=t0, opens=opens_bar, sig=sig_bar, js=js)
        print(f"shift {p}: nb={nb} traded={len(js)}", flush=True)
    del opens_bar, sig_bar

    F = {k: [] for k in ("phase", "coin", "year", "Tns", "bar_ord", "rung",
                         "f", "nfill", "nF", "d_own", "dFmean", "rel",
                         "t1", "t2", "t3", "w",
                         "y", "d", "x")}
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
                low_win = La[base + K.LIVE_A:base + K.LIVE_B + 1].astype(float)
                if others:
                    cmat = np.stack([C[b][base + K.LIVE_A - 1:base + K.LIVE_B].astype(float)
                                     for b in others])
                    oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                    ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                    nvec = K.n_vector(cmat, oo, ss)
                else:
                    nvec = np.zeros(K.LIVE_B - K.LIVE_A + 1, dtype=np.int64)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                # per-bar 1m-close row for the rel feature (all coins, f-1 only)
                # Cfull[x] = full 1m close array of coin x (float32); index base+f-1.
                for ri, k in enumerate(K.RUNGS):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = K.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = K.LIVE_A + ib
                    nf = int(nvec[ib])
                    ret, x, _ = K.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                    if not np.isfinite(ret):
                        continue
                    # --- relative-flush feature (bot_only, minute f-1) ---
                    d_all = {}
                    for cx in coins:
                        try:
                            px = float(C[cx][base + f - 1])
                        except Exception:
                            px = float("nan")
                        ox = float(opens_bar[cx][j])
                        sx = float(sig_bar[cx][j])
                        d_all[cx] = K.depth_sigma(px, ox, sx)
                    d_own = d_all[sym]
                    dF = np.array([d_all[b] for b in others
                                   if np.isfinite(d_all[b]) and d_all[b] >= K.DETECT_K],
                                  dtype=float)
                    nF = int(dF.size)
                    dFm = float(dF.mean()) if nF else float("nan")
                    rel = K.rel_overshoot(d_own, dF)
                    t1 = K.tilt_r1(rel, nf)
                    t2 = K.tilt_r2(rel, nf)
                    t3 = K.tilt_r3(rel, nf)
                    n_fill += 1
                    F["phase"].append(p)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(yi)
                    F["Tns"].append(int(bt.value))
                    F["bar_ord"].append(off + j * 240)
                    F["rung"].append(ri)
                    F["f"].append(f)
                    F["nfill"].append(nf)
                    F["nF"].append(nF)
                    F["d_own"].append(float(d_own) if np.isfinite(d_own) else float("nan"))
                    F["dFmean"].append(float(dFm) if np.isfinite(dFm) else float("nan"))
                    F["rel"].append(float(rel) if np.isfinite(rel) else float("nan"))
                    F["t1"].append(float(t1))
                    F["t2"].append(float(t2))
                    F["t3"].append(float(t3))
                    F["w"].append(K.size_mult(nf))
                    F["y"].append(float(ret))
                    F["d"].append(exit_day_ordinal(bt, x))
                    F["x"].append(int(x))
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha
    del O, C

    led = {k: np.array(v) for k, v in F.items()}
    for k in ("phase", "coin", "year", "bar_ord", "rung", "f", "nfill", "nF", "d", "x"):
        led[k] = led[k].astype(np.int64)
    for k in ("d_own", "dFmean", "rel", "t1", "t2", "t3", "w", "y"):
        led[k] = led[k].astype(np.float64)
    w_r1 = led["w"] * led["t1"]
    w_r2 = led["w"] * led["t2"]
    w_r3 = led["w"] * led["t3"]

    arms = {"base": led["w"], "R1": w_r1, "R2": w_r2, "R3": w_r3}
    per_year: dict = {a: [] for a in arms}
    for a, wv in arms.items():
        for y in range(5):
            ss, ds, ws, ns, wins = [], [], [], [], []
            for p in phases:
                m = (led["phase"] == p) & (led["year"] == y)
                n = int(m.sum())
                ns.append(n)
                if n:
                    s, wday, dd = cell_stats(led["d"][m], (wv * led["y"])[m])
                    wins.append(float((led["y"][m] > 0).mean()))
                else:
                    s, wday, dd = 0.0, 0.0, 0.0
                    wins.append(0.0)
                ss.append(s)
                ds.append(dd)
                ws.append(wday)
            per_year[a].append({"S": float(np.mean(ss)), "DD": float(np.mean(ds)),
                                "W": float(np.mean(ws)), "n": float(np.mean(ns)),
                                "win": float(np.mean(wins)),
                                "per_phase_sums": [float(s) for s in ss],
                                "per_phase_dd": [float(d) for d in ds]})
    full = {}
    for a, wv in arms.items():
        s_full, _, dd_full = cell_stats(led["d"], wv * led["y"])
        full[a] = {"full_sum": float(s_full), "full_dd": float(dd_full)}

    if args.smoke:
        print(json.dumps({"n": int(len(led["w"])),
                          "base_sum5y": round(float(sum(r["S"] for r in per_year["base"])), 6),
                          "R1_sum5y": round(float(sum(r["S"] for r in per_year["R1"])), 6),
                          "R3_sum5y": round(float(sum(r["S"] for r in per_year["R3"])), 6)}, indent=1))
        return

    # --- decisions ---
    def legs(rule: str):
        sp = sum(1 for y in range(5)
                 if per_year[rule][y]["S"] >= per_year["base"][y]["S"])
        dp = sum(1 for y in range(5)
                 if per_year[rule][y]["DD"] <= per_year["base"][y]["DD"] + DD_TOL)
        dsum = float(sum(r["S"] for r in per_year[rule])
                     - sum(r["S"] for r in per_year["base"]))
        return sp, dp, dsum

    dec = {}
    for rule in ("R1", "R2", "R3"):
        sp, dp, dsum = legs(rule)
        dec[rule] = {"years_sum_ge": sp, "years_dd_ok": dp, "dSum5y": dsum,
                     "promising": bool(sp >= 4 and dp >= 4 and dsum >= GATE_DSUM)}
    # protocol view on dev4 (Y0..Y3)
    dev = {}
    for rule in ("R1", "R2", "R3"):
        sp4 = sum(1 for y in range(4)
                  if per_year[rule][y]["S"] >= per_year["base"][y]["S"])
        dp4 = sum(1 for y in range(4)
                  if per_year[rule][y]["DD"] <= per_year["base"][y]["DD"] + DD_TOL)
        dsum4 = float(sum(per_year[rule][y]["S"] for y in range(4))
                      - sum(per_year["base"][y]["S"] for y in range(4)))
        dev[rule] = {"dev4_sum_ge": sp4, "dev4_dd_ok": dp4, "dev4_dSum": dsum4}

    # --- descriptives ---
    rel_all = led["rel"]
    nfill_all = led["nfill"]
    share_n1 = float((nfill_all >= 1).mean()) if len(nfill_all) else 0.0
    m_n1 = (nfill_all >= 1)
    rel_n1 = rel_all[m_n1]
    rel_fin = rel_n1[np.isfinite(rel_n1)]
    def q(v, p):
        return float(np.quantile(v, p)) if v.size else float("nan")
    rel_dist = {
        "n_nfill_ge1": int(m_n1.sum()),
        "share_nfill_ge1": round(share_n1, 6),
        "n_rel_finite": int(rel_fin.size),
        "share_rel_hi": round(float((rel_fin > 0.5).mean()) if rel_fin.size else 0.0, 6),
        "share_rel_mid": round(float((np.abs(rel_fin) <= 0.5).mean()) if rel_fin.size else 0.0, 6),
        "share_rel_lo": round(float((rel_fin < -0.5).mean()) if rel_fin.size else 0.0, 6),
        "q": {"p5": round(q(rel_fin, 0.05), 4), "p25": round(q(rel_fin, 0.25), 4),
              "p50": round(q(rel_fin, 0.50), 4), "p75": round(q(rel_fin, 0.75), 4),
              "p95": round(q(rel_fin, 0.95), 4)},
        "mismatch_nfill_vs_nF": int((led["nfill"] != led["nF"]).sum()),
        "mismatch_rate": round(float((led["nfill"] != led["nF"]).mean()), 6),
    }
    # terciles cut on pooled rel (n_fill>=1, finite), applied per year
    terc = {}
    if rel_fin.size >= 3:
        t1c, t2c = float(np.quantile(rel_fin, 1 / 3)), float(np.quantile(rel_fin, 2 / 3))
    else:
        t1c, t2c = float("nan"), float("nan")
    terc_cuts = [t1c, t2c]
    terc_rows = []
    for y in range(5):
        my = (led["year"] == y) & m_n1 & np.isfinite(rel_all)
        r = rel_all[my]
        yy = led["y"][my]
        row = {"year": ANCHORS[y].date().isoformat(), "n": int(my.sum()),
               "t1": round(t1c, 4) if np.isfinite(t1c) else None,
               "t2": round(t2c, 4) if np.isfinite(t2c) else None}
        for ti, nm in enumerate(("lo", "mid", "hi")):
            if not np.isfinite(t1c):
                row[nm] = {"n": 0, "mean_y": None}
                continue
            if ti == 0:
                mm = r <= t1c
            elif ti == 1:
                mm = (r > t1c) & (r <= t2c)
            else:
                mm = r > t2c
            row[nm] = {"n": int(mm.sum()),
                       "mean_y": round(float(yy[mm].mean()), 6) if mm.any() else None}
        terc_rows.append(row)
    terc["cuts"] = [round(c, 4) if np.isfinite(c) else None for c in terc_cuts]
    terc["per_year"] = terc_rows
    # per-year share n>=1 + rel bucket shares
    desc_year = []
    for y in range(5):
        my = (led["year"] == y)
        r1 = rel_all[my & m_n1]
        r1f = r1[np.isfinite(r1)]
        desc_year.append({
            "year": ANCHORS[y].date().isoformat(),
            "n": int(my.sum()),
            "share_nfill_ge1": round(float(((led["nfill"][my] >= 1).mean())) if my.any() else 0.0, 4),
            "share_rel_hi": round(float((r1f > 0.5).mean()) if r1f.size else 0.0, 4),
            "share_rel_mid": round(float((np.abs(r1f) <= 0.5).mean()) if r1f.size else 0.0, 4),
            "share_rel_lo": round(float((r1f < -0.5).mean()) if r1f.size else 0.0, 4),
        })

    # phase-0 fidelity vs oc_dipexit/oc_stoptf/oc_placebo_dip
    ref_p0 = [2.388, 0.183, 3.810, 2.579, 0.712]
    got_p0 = []
    for y in range(5):
        m = (led["phase"] == 0) & (led["year"] == y)
        got_p0.append(float((led["w"][m] * led["y"][m]).sum()))
    fills_coin_p0 = []
    for s in MAJORS:
        fills_coin_p0.append(int(((led["phase"] == 0) & (led["coin"] == coin_ix[s])).sum()))

    chk = hashlib.sha256(
        np.round(np.stack([led["w"], led["y"], led["rel"],
                           led["t1"], led["t3"]]), 9).tobytes()).hexdigest()[:16]

    years = []
    for y in range(5):
        b = per_year["base"][y]
        row = {"year": ANCHORS[y].date().isoformat(),
               "base": {k: round(b[k], 6) for k in ("S", "DD", "W", "n", "win")}}
        for rule in ("R1", "R2", "R3"):
            r = per_year[rule][y]
            row[rule] = {k: round(r[k], 6) for k in ("S", "DD", "W", "n", "win")}
            row[f"{rule}_sum_ge"] = bool(r["S"] >= b["S"])
            row[f"{rule}_dd_ok"] = bool(r["DD"] <= b["DD"] + DD_TOL)
            row[f"{rule}_dS"] = round(r["S"] - b["S"], 6)
        row["per_phase_sums_base"] = [round(s, 6) for s in b["per_phase_sums"]]
        for rule in ("R1", "R2", "R3"):
            row[f"per_phase_sums_{rule}"] = [round(s, 6) for s in per_year[rule][y]["per_phase_sums"]]
        years.append(row)

    res = {
        "config": {
            "coins": list(MAJORS), "rungs": list(K.RUNGS),
            "bars": "open in [2021-09-24, 2026-09-24)",
            "grid": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h; phase 0 == oc_dipexit grid",
            "live": [K.LIVE_A, K.LIVE_B], "maker": K.MAKER, "taker": K.TAKER,
            "fund_long": K.FUND, "settle_hours": list(SETTLE_HOURS),
            "size": "B1 w=1/(1+n_fill), v399-exact n (oc_b1deeper); fills n_fill=0 keep w=1",
            "exits": "D0 replica from fill lv (TP=lv*(1+sg), sl 4sg, bl 8sg, timeout next open)",
            "feature": "d_x=-log(P_x(f-1)/O_x)/sigma_x (P=1m close f-1, O=bar open, sigma=ladder sigma); "
                       "F={other majors d_x>=2.5}; rel=d_i-mean(F); NaN->tilt 1.0; bot_only",
            "R1": "w=1/(1+n)*(1.5 if rel>+0.5; 0.75 if rel<-0.5; else 1)",
            "R2": "sign control: w=1/(1+n)*(0.75 if rel>+0.5; 1.5 if rel<-0.5; else 1)",
            "R3": "w=1/(1+n)*clip(1+0.25*rel, 0.6, 1.4)",
            "budget": "exactly as replica (no re-normalisation)",
            "daily": "exit-date UTC sums; maxDD of cumulative daily-sum path from 0",
            "pairing": "kept iff filled AND D0 y1.0 finite (same fills all arms)",
            "criterion_5y": "(a) Sbar_rule>=Sbar_base >=4/5 AND DDbar_rule<=DDbar_base+0.01 >=4/5; "
                            f"(b) 5y 4-phase-mean dSum>={GATE_DSUM} (pooled placebo p95); "
                            "calibrated on all 5y incl. most-recent year (labelled)",
            "protocol_dev4": "same legs on Y0..Y3 (>=3/4); choose among R1/R3 on dev4; "
                             "R2 must mirror R1",
            "resources": "one process, majors 1m O/C float32 + one-coin H/L",
        },
        "n_fills": int(len(led["w"])),
        "ledger_checksum": chk,
        "phase0_fidelity": {
            "fills_per_coin": fills_coin_p0,
            "oc_dipexit_ref_fills_per_coin": [1067, 1126, 952, 1179, 1174],
            "got_raw_sums": [round(s, 6) for s in got_p0],
            "oc_stoptf_D0_raw_sums": ref_p0,
            "oc_placebo_dip_4phase_means": [0.911, 0.833, 2.100, 3.197, 0.677],
            "got_4phase_means": [round(per_year["base"][y]["S"], 6) for y in range(5)],
            "got_4phase_DD": [round(per_year["base"][y]["DD"], 6) for y in range(5)],
            "base_sum5y": round(float(sum(r["S"] for r in per_year["base"])), 6),
            "note": "same replica+B1 sizes; pairing here y1.0-only (placebo required y0.9/y1.0/y1.1)",
        },
        "years": years,
        "sum5y": {a: round(float(sum(r["S"] for r in per_year[a])), 6) for a in arms} | {
            "dSum_R1": round(dec["R1"]["dSum5y"], 6),
            "dSum_R2": round(dec["R2"]["dSum5y"], 6),
            "dSum_R3": round(dec["R3"]["dSum5y"], 6),
            "gate_dSum": GATE_DSUM},
        "full_pooled": {a: {"sum": round(full[a]["full_sum"], 6),
                            "dd": round(full[a]["full_dd"], 6)} for a in arms},
        "decision_5y": {rule: {"years_sum_ge_base": f"{dec[rule]['years_sum_ge']}/5",
                               "years_dd_ok": f"{dec[rule]['years_dd_ok']}/5",
                               "dSum5y": round(dec[rule]["dSum5y"], 6),
                               "promising": dec[rule]["promising"]} for rule in ("R1", "R2", "R3")},
        "protocol_dev4": {rule: {"dev4_sum_ge": f"{dev[rule]['dev4_sum_ge']}/4",
                                 "dev4_dd_ok": f"{dev[rule]['dev4_dd_ok']}/4",
                                 "dev4_dSum": round(dev[rule]["dev4_dSum"], 6)}
                          for rule in ("R1", "R2", "R3")},
        "descriptives": {"rel": rel_dist, "per_year": desc_year, "tercile": terc},
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    Tiso = pd.to_datetime(led["Tns"], utc=True)
    panel = pd.DataFrame({
        "phase": led["phase"], "sym": [coins[i] for i in led["coin"]],
        "year": [ANCHORS[y].date().isoformat() for y in led["year"]],
        "T": Tiso.astype(str), "bar_ord": led["bar_ord"],
        "rung_k": [K.RUNGS[i] for i in led["rung"]], "f": led["f"],
        "n_fill": led["nfill"], "nF": led["nF"],
        "d_own": np.round(led["d_own"], 6), "dFmean": np.round(led["dFmean"], 6),
        "rel": np.round(led["rel"], 6),
        "t1": led["t1"], "t2": led["t2"], "t3": led["t3"],
        "w_base": led["w"], "w_R1": w_r1, "w_R2": w_r2, "w_R3": w_r3,
        "y": led["y"], "x": led["x"],
        "exit_iso": [(EPOCH + pd.Timedelta(days=int(d))).date().isoformat() for d in led["d"]],
    })
    panel.to_parquet(HERE / "panel.parquet", index=False)
    print("n_fills", len(led["w"]), "checksum", chk, flush=True)
    print(json.dumps({"base_sum5y": res["phase0_fidelity"]["base_sum5y"],
                      "decision_5y": res["decision_5y"],
                      "protocol_dev4": res["protocol_dev4"]}, indent=1))
    for y in years:
        print(y["year"], "base", y["base"], "R1", y["R1"], "R2", y["R2"], "R3", y["R3"], flush=True)


if __name__ == "__main__":
    main()
