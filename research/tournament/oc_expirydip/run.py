"""oc_expirydip run: base (D0+B1, 4 phases) vs rule (base + expiry-day extra 5sg rung).

One process, one coin's H/L in RAM at a time; all-five-coins 1m O/C held as
float32 arrays; RAM < 3 GB. See PLAN.md (pre-registered, written before any
outcome computation).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_expirydip \\
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \\
    research/tournament/oc_expirydip/run.py
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
import expirydip as X

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
EXPIRIES = X.expiry_dates(2021, 2026, 9)


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


def score_assignment(ph, yr, wv, yv, dv):
    per_year = []
    for y in range(5):
        ss, ds, ws, ns = [], [], [], []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            n = int(m.sum())
            ns.append(n)
            if n:
                s, w, dd = cell_stats(dv[m], (wv * yv)[m])
            else:
                s, w, dd = 0.0, 0.0, 0.0
            ss.append(s)
            ds.append(dd)
            ws.append(w)
        my = (yr == y)
        per_year.append({"S": float(np.mean(ss)), "DD": float(np.mean(ds)),
                         "W": float(np.mean(ws)), "n": float(np.mean(ns)),
                         "win": float((yv[my] > 0).mean()) if my.any() else 0.0,
                         "per_phase_sums": [float(s) for s in ss],
                         "per_phase_dd": [float(s) for s in ds],
                         "per_phase_worst": [float(s) for s in ws]})
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


def build(max_bars_per_coin_phase=None, coins=MAJORS, phases=PHASES):
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

    B = {k: [] for k in ("phase", "coin", "year", "w", "y", "d")}
    E = {k: [] for k in ("phase", "coin", "year", "w", "y", "d")}
    coin_ix = {s: i for i, s in enumerate(coins)}
    for sym in coins:
        H, L = load_hl(sym, base_idx)
        Oa, Ca = O[sym], C[sym]
        others = [b for b in coins if b != sym]
        for p in phases:
            g = grids[p]
            off, t0 = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            n_b = n_e = 0
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
                low_win = L[base + X.LIVE_A:base + X.LIVE_B + 1].astype(float)
                if others:
                    cmat = np.stack([C[b][base + X.LIVE_A - 1:base + X.LIVE_B].astype(float)
                                     for b in others])
                    oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                    ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                    nvec = X.n_vector(cmat, oo, ss)
                else:  # smoke mode (single coin): no flushers by construction
                    nvec = np.zeros(X.LIVE_B - X.LIVE_A + 1, dtype=np.int64)
                Ha_b = H[base:base + 240].astype(float)
                La_b = L[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                exp = X.in_exp_window(bt, EXPIRIES)
                for ri, k in enumerate(X.RUNGS):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = X.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = X.LIVE_A + ib
                    nf = int(nvec[ib])
                    r10, x10, _ = X.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle)
                    if not np.isfinite(r10):
                        continue
                    w = X.size_mult(nf)
                    dd = exit_day_ordinal(bt, x10)
                    B["phase"].append(p)
                    B["coin"].append(coin_ix[sym])
                    B["year"].append(yi)
                    B["w"].append(w)
                    B["y"].append(r10)
                    B["d"].append(dd)
                    n_b += 1
                    # extra rung: expiry bars only, k == 5.0 -> duplicate exposure
                    if exp and k == X.EXTRA_K:
                        # level identical to base 5.0 by construction; fill,
                        # size and outcome are exactly the base 5.0 values.
                        E["phase"].append(p)
                        E["coin"].append(coin_ix[sym])
                        E["year"].append(yi)
                        E["w"].append(w)
                        E["y"].append(r10)
                        E["d"].append(dd)
                        n_e += 1
            print(f"{sym} p{p}: base={n_b} extra={n_e}", flush=True)
        del H, L
    base = {k: np.array(v) for k, v in B.items()}
    extra = {k: np.array(v) for k, v in E.items()}
    for k in ("phase", "coin", "year", "d"):
        if len(base[k]):
            base[k] = base[k].astype(np.int64)
        else:
            base[k] = np.zeros(0, dtype=np.int64)
        if len(extra[k]):
            extra[k] = extra[k].astype(np.int64)
        else:
            extra[k] = np.zeros(0, dtype=np.int64)
    for k in ("w", "y"):
        base[k] = np.asarray(base[k], dtype=np.float64)
        extra[k] = np.asarray(extra[k], dtype=np.float64)
    return base, extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    if args.smoke:
        base, extra = build(max_bars_per_coin_phase=300, coins=("BTCUSDT",), phases=(0,))
        print(f"smoke base={len(base['w'])} extra={len(extra['w'])}", flush=True)
        return
    base, extra = build()
    ph, yr, w0, y0, d0 = base["phase"], base["year"], base["w"], base["y"], base["d"]
    print(f"ledger base={len(w0)} extra={len(extra['w'])}", flush=True)

    base_sc = score_assignment(ph, yr, w0, y0, d0)
    print("base 4-phase-mean sums:", [round(r["S"], 4) for r in base_sc["per_year"]], flush=True)

    if len(extra["w"]):
        phr = np.concatenate([ph, extra["phase"]])
        yrr = np.concatenate([yr, extra["year"]])
        wr = np.concatenate([w0, extra["w"]])
        yr_ = np.concatenate([y0, extra["y"]])
        dr = np.concatenate([d0, extra["d"]])
    else:
        phr, yrr, wr, yr_, dr = ph, yr, w0, y0, d0
    rule_sc = score_assignment(phr, yrr, wr, yr_, dr)

    ref_p0 = [2.388, 0.183, 3.810, 2.579, 0.712]
    got_p0 = []
    for y in range(5):
        m = (ph == 0) & (yr == y)
        got_p0.append(float((w0[m] * y0[m]).sum()) if m.any() else 0.0)
    print("phase0 base sums:", [round(s, 4) for s in got_p0], flush=True)
    print("phase0 ref       :", ref_p0, flush=True)

    # extra-rung descriptives per year (4-phase-mean n/sum, pooled win)
    ex_ph, ex_yr, ex_w, ex_y = extra["phase"], extra["year"], extra["w"], extra["y"]
    extra_years = []
    for y in range(5):
        ns = [int(((ex_ph == p) & (ex_yr == y)).sum()) for p in PHASES]
        m = ex_yr == y
        if m.any():
            s_mean = float(np.mean([float((ex_w[(ex_ph == p) & (ex_yr == y)] *
                                            ex_y[(ex_ph == p) & (ex_yr == y)]).sum())
                                    for p in PHASES]))
            win = float((ex_y[m] > 0).mean())
            net = float((ex_w[m] * ex_y[m]).sum())
        else:
            s_mean, win, net = 0.0, 0.0, 0.0
        extra_years.append({"n_mean": round(float(np.mean(ns)), 2),
                            "n_per_phase": ns,
                            "sum_mean": round(s_mean, 6),
                            "win_pooled": round(win, 6),
                            "net_pooled": round(net, 6)})

    ps = sum(1 for y in range(5)
             if rule_sc["per_year"][y]["S"] >= base_sc["per_year"][y]["S"])
    pd_ = sum(1 for y in range(5)
              if rule_sc["per_year"][y]["DD"] <= base_sc["per_year"][y]["DD"] + DD_TOL)
    dsum = float(rule_sc["sum5y"] - base_sc["sum5y"])
    decision = {"years_sum_ge": int(ps), "years_dd_ok": int(pd_),
                "dSum5y": round(dsum, 6), "gate_dSum5y": GATE_DSUM,
                "promising": bool(ps >= 4 and pd_ >= 4 and dsum >= GATE_DSUM)}

    chk = hashlib.sha256(np.round(np.stack([w0, y0]), 9).tobytes()).hexdigest()[:16]
    out = {
        "config": {
            "idea": "#76 expiry-day pin-flush buyer (IDEAS2 idea 9)",
            "replica": "oc_dipexit D0 exact (TP1sg, sl4sg close5, bl8sg, timeout next-bar open; "
                       "maker 0.0002/taker 0.00055; v293 settle funding) + oc_b1deeper B1 sizes "
                       "w=1/(1+n); 4 clock phases (4h grid 2020-08-01 + 0/1/2/3h); majors x R2 "
                       "rungs 2.5..5.0; live offsets 16..238 strict trade-through; bars open "
                       "[2021-09-24,2026-09-24)",
            "pairing": "kept only if y1.0 finite (single leg; placebo required 3 TP legs)",
            "expiry": "E(y,m)=last Friday of month; in_exp(T) iff T.date() is expiry AND "
                      "T.time() in [00:00,12:00) UTC (phase0: 00/04/08 bars; phases 1-3: 3 bars "
                      "in the same window)",
            "extra": "on in_exp bars, per coin ONE extra 5.0-sigma rung at base B1 size "
                     "(level/size/fill identical to base 5.0 rung -> duplicate 5.0 exposure); "
                     "TP 1.0sg, sl 4sg close5, bl 8sg, timeout next-bar open; else unchanged",
            "criterion": "per year on 4-phase means: PASS_sum iff S_rule>=S_base; PASS_dd iff "
                         "DD_rule<=DD_base+0.01; PROMISING iff both in >=4/5 years AND "
                         "dSum5y >= +0.273 (oc_placebo_dip pooled p95)",
            "deltas": "dSum5y = sum_Y(Sbar_rule-Sbar_base); DD in w*y units",
            "resources": "one process, majors 1m O/C float32 + one-coin H/L",
            "note": "all 5 years are research data; PROMISING needs prospective validation",
        },
        "n_base": int(len(w0)), "n_extra": int(len(extra["w"])),
        "ledger_checksum": chk,
        "phase0_fidelity": {"got_raw_sums": [round(s, 6) for s in got_p0],
                            "oc_placebo_ref": ref_p0},
        "base_mean4": [
            {"year": ANCHORS[y].date().isoformat(),
             "S": round(base_sc["per_year"][y]["S"], 6),
             "DD": round(base_sc["per_year"][y]["DD"], 6),
             "W": round(base_sc["per_year"][y]["W"], 6),
             "n": round(base_sc["per_year"][y]["n"], 2),
             "win": round(base_sc["per_year"][y]["win"], 6),
             "per_phase_sums": [round(s, 6) for s in base_sc["per_year"][y]["per_phase_sums"]],
             "per_phase_dd": [round(s, 6) for s in base_sc["per_year"][y]["per_phase_dd"]]}
            for y in range(5)],
        "rule_mean4": [
            {"year": ANCHORS[y].date().isoformat(),
             "S": round(rule_sc["per_year"][y]["S"], 6),
             "DD": round(rule_sc["per_year"][y]["DD"], 6),
             "W": round(rule_sc["per_year"][y]["W"], 6),
             "n": round(rule_sc["per_year"][y]["n"], 2),
             "win": round(rule_sc["per_year"][y]["win"], 6),
             "per_phase_sums": [round(s, 6) for s in rule_sc["per_year"][y]["per_phase_sums"]],
             "per_phase_dd": [round(s, 6) for s in rule_sc["per_year"][y]["per_phase_dd"]]}
            for y in range(5)],
        "extra_years": [
            {"year": ANCHORS[y].date().isoformat(), **extra_years[y]} for y in range(5)],
        "base_sum5y": round(base_sc["sum5y"], 6),
        "rule_sum5y": round(rule_sc["sum5y"], 6),
        "base_full": {"sum": round(base_sc["full_sum"], 6), "dd": round(base_sc["full_dd"], 6)},
        "rule_full": {"sum": round(rule_sc["full_sum"], 6), "dd": round(rule_sc["full_dd"], 6)},
        "decision": decision,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(decision, indent=1))
    print(f"n_base={len(w0)} n_extra={len(extra['w'])} checksum={chk}", flush=True)


if __name__ == "__main__":
    main()
