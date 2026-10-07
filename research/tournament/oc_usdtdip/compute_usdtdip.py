"""oc_usdtdip: USDT/USD premium DIP rung size tilt (idea #73, pre-registered).

Replica: oc_dipexit D0 exact outcomes (TP 1sg, close5 stop 4sg, 8sg backstop,
timeout at next-bar open; maker 0.0002 / taker 0.00055; v293 settle funding)
with oc_b1deeper B1 sizes w = 1/(1+n_fill), majors x R2 depths, live offsets
16..238 strict trade-through, on all four clock phases (4h grid from
2020-08-01 00:00 UTC + 0/1/2/3h), bars with open in [2021-09-24, 2026-09-24).
Phase 0 == oc_dipexit grid exactly. Rule: per-fill size x1.2 when USDT z > 1,
x0.8 when z < -1, else x1.0 (z = oc_usdtprem-exact, as-of strictly before the
bar open). Control: per (year, phase) constant avg mult. See PLAN.md.

Usage:
  .venv/Scripts/python.exe research/tournament/oc_usdtdip/compute_usdtdip.py [--smoke]

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

ROOT = HERE.parents[2]
USDT = ROOT / "data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet"
UMANIFEST = ROOT / "data/raw/coinbase_usdt_20261006/manifest.json"

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


def load_usdt():
    u = pd.read_parquet(USDT).copy()
    u["t"] = pd.to_datetime(u["open_time"], utc=True)
    u = u[u["t"] < END].sort_values("t").reset_index(drop=True)
    u["prem"] = pd.to_numeric(u["close"], errors="coerce") - 1.0
    u["mean24"] = u["prem"].rolling(24, min_periods=20).mean()
    r = u["mean24"].rolling(2160, min_periods=1728)
    u["z"] = (u["mean24"] - r.mean().shift(1)) / r.std(ddof=1).shift(1)
    u["end"] = u["t"] + pd.Timedelta(hours=1)
    return u


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

    usdt = load_usdt()
    ends_ns = usdt["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    zvals = usdt["z"].to_numpy(float)
    print(f"usdt: rows={len(usdt)} span={usdt['t'].iloc[0]}..{usdt['t'].iloc[-1]} "
          f"median_prem_bps={float(np.nanmedian(usdt['prem'].to_numpy())) * 1e4:.2f}",
          flush=True)

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
                         "f", "nfill", "w", "y", "d", "x")}
    B = {k: [] for k in ("phase", "year", "Tns")}  # valid bars (rungs live)
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
                B["phase"].append(p)
                B["year"].append(yi)
                B["Tns"].append(int(bt.value))
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
                    n_fill += 1
                    F["phase"].append(p)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(yi)
                    F["Tns"].append(int(bt.value))
                    F["bar_ord"].append(off + j * 240)
                    F["rung"].append(ri)
                    F["f"].append(f)
                    F["nfill"].append(nf)
                    F["w"].append(K.size_mult(nf))
                    F["y"].append(float(ret))
                    F["d"].append(exit_day_ordinal(bt, x))
                    F["x"].append(int(x))
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha
    # free 1m arrays before scoring
    del O, C

    led = {k: np.array(v) for k, v in F.items()}
    for k in ("phase", "coin", "year", "bar_ord", "rung", "f", "nfill", "d", "x"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y"):
        led[k] = led[k].astype(np.float64)
    Tns = led["Tns"].astype(np.int64)
    ii = K.asof_index(ends_ns, Tns)
    zfill = np.full(len(Tns), np.nan)
    ok = ii >= 0
    zfill[ok] = zvals[ii[ok]]
    mult = np.array([K.tilt_mult(z) for z in zfill])
    w_rule = led["w"] * mult
    # exposure-matched control: constant avg mult per (year, phase)
    avg = {}
    for y in range(5):
        for p in phases:
            m = (led["year"] == y) & (led["phase"] == p)
            avg[(y, p)] = float(mult[m].mean()) if m.any() else 1.0
    avgvec = np.array([avg[(int(y), int(p))] for y, p in zip(led["year"], led["phase"])])
    w_ctrl = led["w"] * avgvec

    bars = {k: np.array(v) for k, v in B.items()}
    bT = bars["Tns"].astype(np.int64) if len(bars["Tns"]) else np.array([], dtype=np.int64)
    bii = K.asof_index(ends_ns, bT) if bT.size else np.array([], dtype=np.int64)
    bz = np.full(bT.shape, np.nan)
    bok = bii >= 0
    bz[bok] = zvals[bii[bok]]

    arms = {"base": led["w"], "rule": w_rule, "ctrl": w_ctrl}
    per_year, per_phase = {}, {}
    for a, wv in arms.items():
        per_year[a] = []
        for y in range(5):
            ss, ds, ws, ns, wins, ups, dns = [], [], [], [], [], [], []
            for p in phases:
                m = (led["phase"] == p) & (led["year"] == y)
                n = int(m.sum())
                ns.append(n)
                if n:
                    s, wday, dd = cell_stats(led["d"][m], (wv * led["y"])[m])
                    wins.append(float((led["y"][m] > 0).mean()))
                    ups.append(float((mult[m] == K.MULT_UP).mean()))
                    dns.append(float((mult[m] == K.MULT_DOWN).mean()))
                else:
                    s, wday, dd = 0.0, 0.0, 0.0
                    wins.append(0.0)
                    ups.append(0.0)
                    dns.append(0.0)
                ss.append(s)
                ds.append(dd)
                ws.append(wday)
            # bar shares for this year (valid bars pooled over phases)
            mb = (bars["year"] == y) if len(bars["year"]) else np.array([], dtype=bool)
            if mb.size and mb.any():
                zb = bz[mb]
                fin = np.isfinite(zb)
                bup = float(((zb > K.Z_HI) & fin).mean()) if fin.size else 0.0
                bdn = float(((zb < K.Z_LO) & fin).mean()) if fin.size else 0.0
            else:
                bup = bdn = 0.0
            my = (led["year"] == y)
            per_year[a].append({"S": float(np.mean(ss)), "DD": float(np.mean(ds)),
                                "W": float(np.mean(ws)), "n": float(np.mean(ns)),
                                "win": float(np.mean(wins)),
                                "fill_up": float(np.mean(ups)), "fill_down": float(np.mean(dns)),
                                "bar_up": bup, "bar_down": bdn,
                                "per_phase_sums": [float(s) for s in ss],
                                "per_phase_dd": [float(d) for d in ds]})
        # pooled full path (all phases, exit-date order)
        s_full, _, dd_full = cell_stats(led["d"], arms[a] * led["y"])
        per_phase[a] = {"full_sum": float(s_full), "full_dd": float(dd_full)}

    if args.smoke:
        print(json.dumps({"n": int(len(led["w"])),
                          "base_sum5y": round(float(sum(r["S"] for r in per_year["base"])), 6),
                          "rule_sum5y": round(float(sum(r["S"] for r in per_year["rule"])), 6)}, indent=1))
        return

    sum_pass = sum(1 for y in range(5)
                   if per_year["rule"][y]["S"] >= per_year["base"][y]["S"])
    dd_pass = sum(1 for y in range(5)
                  if per_year["rule"][y]["DD"] <= per_year["base"][y]["DD"] + DD_TOL)
    gain_pass = sum(1 for y in range(5)
                    if per_year["rule"][y]["S"] - per_year["ctrl"][y]["S"] > 0)
    dsum5y = float(sum(r["S"] for r in per_year["rule"]) - sum(r["S"] for r in per_year["base"]))
    promising = bool(sum_pass >= 4 and dd_pass >= 4 and dsum5y >= GATE_DSUM and gain_pass >= 4)

    # phase-0 fidelity vs oc_dipexit/oc_stoptf raw sums (B1 sizes, y1.0-only pairing)
    ref_p0 = [2.388, 0.183, 3.810, 2.579, 0.712]
    got_p0, fills_p0 = [], []
    for y in range(5):
        m = (led["phase"] == 0) & (led["year"] == y)
        got_p0.append(float((led["w"][m] * led["y"][m]).sum()))
        fills_p0.append(int(m.sum()))
    fills_coin_p0 = []
    for s in MAJORS:
        fills_coin_p0.append(int(((led["phase"] == 0) & (led["coin"] == coin_ix[s])).sum()))

    chk = hashlib.sha256(np.round(np.stack([led["w"], led["y"], mult]), 9).tobytes()).hexdigest()[:16]
    try:
        manif = json.loads(UMANIFEST.read_text())
    except Exception:
        manif = None
    years = []
    for y in range(5):
        b, r, c = per_year["base"][y], per_year["rule"][y], per_year["ctrl"][y]
        years.append({
            "year": ANCHORS[y].date().isoformat(),
            "base": {k: round(b[k], 6) for k in ("S", "DD", "W", "n", "win")},
            "rule": {k: round(r[k], 6) for k in ("S", "DD", "W", "n", "win")},
            "ctrl": {k: round(c[k], 6) for k in ("S", "DD")},
            "fill_share_up": round(r["fill_up"], 6), "fill_share_down": round(r["fill_down"], 6),
            "bar_share_up": round(r["bar_up"], 6), "bar_share_down": round(r["bar_down"], 6),
            "avg_mult_pooled": round(float(mult[led["year"] == y].mean()), 6),
            "avg_mult_per_phase": [round(avg[(y, p)], 6) for p in PHASES],
            "sum_ge_base": bool(r["S"] >= b["S"]),
            "dd_ok": bool(r["DD"] <= b["DD"] + DD_TOL),
            "gain_over_ctrl": round(r["S"] - c["S"], 6),
            "gain_over_ctrl_pos": bool(r["S"] - c["S"] > 0),
            "per_phase_sums_base": [round(s, 6) for s in b["per_phase_sums"]],
            "per_phase_sums_rule": [round(s, 6) for s in r["per_phase_sums"]],
            "per_phase_sums_ctrl": [round(s, 6) for s in c["per_phase_sums"]],
            "per_phase_dd_base": [round(d, 6) for d in b["per_phase_dd"]],
            "per_phase_dd_rule": [round(d, 6) for d in r["per_phase_dd"]],
        })
    res = {
        "config": {
            "coins": list(MAJORS), "rungs": list(K.RUNGS),
            "bars": "open in [2021-09-24, 2026-09-24)",
            "grid": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h; phase 0 == oc_dipexit grid",
            "live": [K.LIVE_A, K.LIVE_B], "maker": K.MAKER, "taker": K.TAKER,
            "fund_long": K.FUND, "settle_hours": list(SETTLE_HOURS),
            "size": "B1 w=1/(1+n_fill), v399-exact n (oc_b1deeper)",
            "exits": "D0 replica from fill lv (TP=lv*(1+sg), sl 4sg, bl 8sg, timeout next open)",
            "rule": "w_rule = w_base * (1.2 if z>1 else 0.8 if z<-1 else 1.0), z at bar open",
            "z": "coinbase USDT-USD hourly prem=close-1; mean24 rolling(24,min20); "
                 "z90 rolling(2160,min1728) shift(1); as-of last row end<=T-1s",
            "control": "per (year,phase) constant avg mult (equal-weight mean over kept fills)",
            "daily": "exit-date UTC sums; maxDD of cumulative daily-sum path from 0",
            "pairing": "kept iff filled AND D0 y1.0 finite (same fills all arms)",
            "criterion": "(a) Sbar_rule>=Sbar_base >=4/5 AND DDbar_rule<=DDbar_base+0.01 >=4/5; "
                         f"(b) 5y 4-phase-mean dSum>={GATE_DSUM}; (c) gain over ctrl >0 >=4/5",
            "resources": "one process, majors 1m O/C float32 + one-coin H/L",
        },
        "usdt_source": {
            "file": "data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet",
            "manifest": manif,
            "rows": int(len(usdt)),
            "span": [str(usdt["t"].iloc[0]), str(usdt["t"].iloc[-1])],
            "median_prem_bps": round(float(np.nanmedian(usdt["prem"].to_numpy())) * 1e4, 4),
            "coverage_note": "warm-up rows NaN never tilted",
        },
        "n_fills": int(len(led["w"])),
        "ledger_checksum": chk,
        "phase0_fidelity": {
            "fills_per_coin": fills_coin_p0,
            "oc_dipexit_ref_fills_per_coin": [1067, 1126, 952, 1179, 1174],
            "got_raw_sums": [round(s, 6) for s in got_p0],
            "oc_stoptf_D0_raw_sums": ref_p0,
            "note": "same replica+B1 sizes; pairing here y1.0-only (placebo required y0.9/y1.0/y1.1)",
        },
        "years": years,
        "sum5y": {
            "base": round(float(sum(r["S"] for r in per_year["base"])), 6),
            "rule": round(float(sum(r["S"] for r in per_year["rule"])), 6),
            "ctrl": round(float(sum(r["S"] for r in per_year["ctrl"])), 6),
            "dSum_rule_base": round(dsum5y, 6),
            "gate_dSum": GATE_DSUM,
        },
        "full_pooled": {a: {"sum": round(per_phase[a]["full_sum"], 6),
                            "dd": round(per_phase[a]["full_dd"], 6)} for a in arms},
        "decision": {
            "years_sum_ge_base": f"{sum_pass}/5",
            "years_dd_ok": f"{dd_pass}/5",
            "years_gain_over_ctrl_pos": f"{gain_pass}/5",
            "dSum5y": round(dsum5y, 6),
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    Tiso = pd.to_datetime(led["Tns"], utc=True)
    panel = pd.DataFrame({
        "phase": led["phase"], "sym": [coins[i] for i in led["coin"]],
        "year": [ANCHORS[y].date().isoformat() for y in led["year"]],
        "T": Tiso.astype(str), "bar_ord": led["bar_ord"],
        "rung_k": [K.RUNGS[i] for i in led["rung"]], "f": led["f"],
        "n_fill": led["nfill"], "w_base": led["w"], "z": np.round(zfill, 6),
        "mult": mult, "w_rule": w_rule, "w_ctrl": w_ctrl,
        "y": led["y"], "x": led["x"],
        "exit_iso": [(EPOCH + pd.Timedelta(days=int(d))).date().isoformat() for d in led["d"]],
    })
    panel.to_parquet(HERE / "panel.parquet", index=False)
    print("n_fills", len(led["w"]), "checksum", chk, flush=True)
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y["year"], "base", y["base"], "rule", y["rule"], "ctrl", y["ctrl"],
              "gain", y["gain_over_ctrl"], "tilt_fill", (y["fill_share_up"], y["fill_share_down"]),
              flush=True)


if __name__ == "__main__":
    main()
