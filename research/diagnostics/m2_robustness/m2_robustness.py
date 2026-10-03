"""M2 MANUAL robustness report (diagnostic only - nothing is selected on it).

Candidate: the MANUAL (book-only, human-followable) pipeline M2 (v317 / v318 reference):
books = (2A + 2PT + D)/5 with A = (member_A_O1_orders + member_Aq_O1_orders)/2,
PT = (member_PT_pooledtv + member_PTq_pooledtv)/2,
D = (members_v154 level D + members_quarterly_D)/2 (files in
artifacts/research/engine_real/, reindexed to the v154 books index, ffill, NaN -> 0);
engine_user trade mode, sleeve OFF, v216.GRID with the v216 grid policy
(b_abs 0.03, b_rel 0.40, cool 6) BUT the flat-state policy returns {"open": 0.75}
(pullback entry limit 0.75 sigma_4h), n_valid 3, theta 0.05, k_off 0.25
(in-position orders), tighten 1.5, be_k 2, be_off 0.001; v221.KW with m_sl 4,
m_tp 8, sleeve False; target 0.25, cap 2, win_start 5.
Reference leg: G2 manual (books (2A + 2B + D)/5 with
B = (member_B_tv + member_Bq_tv)/2, plain open policy k_off 0.25, n_valid 2).
Rows for both legs: base; cost_stress (maker 0.0004, taker 0.0007 + 0.0005);
HUMAN latency win_start 15 / 30 / 60 / 120; missed decisions every 6th decision
bar skipped for new orders (policy returns wait when flat and hold in a
position at those bars); band_lo / band_hi; cool 3 / 12; the stationary block
bootstrap (first four years daily returns, 30-day blocks, 2000 draws, seed 0)
and the small-account check at 500 / 1000 / 2000 USDT (Bybit lots).
Report per row dev4 / 5y / most recent year / gate DD / losing years / book win rate.

  python research/diagnostics/m2_robustness/m2_robustness.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = Path(__file__).parent / "m2_robustness.json"

MIN_QTY = {"BTCUSDT": 0.001, "ETHUSDT": 0.01, "SOLUSDT": 0.1, "BNBUSDT": 0.01, "XRPUSDT": 0.1}
MIN_NOTIONAL = 5.0
SMALL_EQUITIES = (500.0, 1000.0, 2000.0)
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
eu, v216, v204 = v221.eu, v221.v216, v221.v204
v213 = v221.v216.v213


def _placeable(events, equity):
    """Share of base book orders placeable at equity under the Bybit lot rules, most recent year only."""
    book_n = book_ok = rung_n = rung_ok = 0
    per = {}
    for e in events:
        if e["t"] < HIDDEN:
            continue
        sym = e["symbol"]
        if e["kind"] == "order_issue" and abs(float(e.get("weight", 0.0))) > 0:
            w, px = abs(float(e["weight"])), float(e["price"])
            if not (np.isfinite(w) and np.isfinite(px) and px > 0):
                continue
            notion = w * equity
            qty = notion / px
            ok = qty + 1e-12 >= MIN_QTY[sym] and notion + 1e-12 >= MIN_NOTIONAL
            book_n += 1
            book_ok += int(ok)
            d = per.setdefault(sym, {"book_n": 0, "book_ok": 0, "rung_n": 0, "rung_ok": 0})
            d["book_n"] += 1
            d["book_ok"] += int(ok)
        elif e["kind"] == "rung_fill":
            w, px = abs(float(e["weight"])), float(e["price"])
            if not (np.isfinite(w) and np.isfinite(px) and px > 0):
                continue
            notion = w * equity
            qty = notion / px
            ok = qty + 1e-12 >= MIN_QTY[sym] and notion + 1e-12 >= MIN_NOTIONAL
            rung_n += 1
            rung_ok += int(ok)
            d = per.setdefault(sym, {"book_n": 0, "book_ok": 0, "rung_n": 0, "rung_ok": 0})
            d["rung_n"] += 1
            d["rung_ok"] += int(ok)
    return {"equity_usdt": equity, "min_notional_usdt": MIN_NOTIONAL, "min_qty": MIN_QTY,
            "book_orders": book_n, "book_placeable": book_ok,
            "book_share": round(book_ok / book_n, 4) if book_n else None,
            "rung_orders": rung_n, "rung_placeable": rung_ok,
            "rung_share": round(rung_ok / rung_n, 4) if rung_n else None,
            "per_symbol": per}


def _bootstrap(cap):
    idx, eq = cap["idx"], cap["eq"]
    s = pd.Series(eq, index=idx)
    dev = s[(s.index >= pd.Timestamp("2021-09-24", tz="UTC")) & (s.index < pd.Timestamp("2025-09-24", tz="UTC"))]
    daily = dev.resample("1D").last().pct_change().dropna().to_numpy()
    rng = np.random.default_rng(0)
    months, dds = [], []
    for _ in range(2000):
        path = []
        while len(path) < 365:
            st = rng.integers(0, len(daily) - 30)
            path.extend(daily[st:st + 30])
        e = np.cumprod(1 + np.array(path[:365]))
        months.append(100 * (e[-1] ** (1 / 12) - 1))
        dds.append(100 * float(np.max(1 - e / np.maximum.accumulate(e))))
    return dict(monthly_p5=round(float(np.percentile(months, 5)), 2), monthly_p50=round(float(np.percentile(months, 50)), 2),
                monthly_p95=round(float(np.percentile(months, 95)), 2), p_monthly_ge5=round(float(np.mean(np.array(months) >= 5)), 3),
                p_loss_year=round(float(np.mean(np.array(months) < 0)), 3), dd_p50=round(float(np.percentile(dds, 50)), 2),
                dd_p95=round(float(np.percentile(dds, 95)), 2), p_dd_gt20=round(float(np.mean(np.array(dds) > 20)), 3))


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE

    def rdf(f):
        return pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols]

    A = (rdf("member_A_O1_orders.parquet") + rdf("member_Aq_O1_orders.parquet")) / 2
    B = (rdf("member_B_tv.parquet") + rdf("member_Bq_tv.parquet")) / 2
    PT = (rdf("member_PT_pooledtv.parquet") + rdf("member_PTq_pooledtv.parquet")) / 2
    D = (pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).ffill().fillna(0.0)[cols]
         + rdf("members_quarterly_D.parquet")) / 2
    books_m2 = (2 * A + 2 * PT + D) / 5
    books_g2 = (2 * A + 2 * B + D) / 5
    books_map = {"M2": books_m2, "G2": books_g2}
    prep = eu.prepare(books154, opens)
    maker0, taker0 = eu.MAKER, eu.TAKER
    m2_events, g2_events = [], []

    def make_policy(is_m2, band, missed):
        gp = v216.grid_policy(*band)

        def pol(i, a, st):
            if missed and (i % 6 == 0):
                return "wait" if st["pos"] == 0 else "hold"
            if st["pos"] == 0:
                return {"open": 0.75} if is_m2 else "open"
            return gp(i, a, st)

        return pol

    def run(leg, band=(0.03, 0.40), cool=6, win_start=5, maker=maker0, taker=taker0,
            missed=False, n_valid=None, capture=None, events=None):
        is_m2 = leg == "M2"
        eu.MAKER, eu.TAKER = maker, taker
        old = v216.COOL
        v216.COOL = cool
        try:
            pol = make_policy(is_m2, band, missed)
            trade = dict(v216.GRID, policy=pol, n_valid=(3 if is_m2 else 2) if n_valid is None else n_valid,
                         theta=0.05, k_off=0.25, tighten=1.5, be_k=2.0, be_off=0.001)
            kw = dict(v221.KW, m_sl=4.0, m_tp=8.0, sleeve=False)
            summ = eu.summarize
            if capture is not None:
                def grab(idx_, net, eq, eq_min, g, stats, eq_max=None):
                    capture.update(idx=idx_, eq=eq.copy())
                    return summ(idx_, net, eq, eq_min, g, stats, eq_max)
                eu.summarize = grab
            ev = [] if events is None else events
            r = eu.simulate(books_map[leg], opens, prep, trade=trade, win_start=win_start,
                            events=ev, target=0.25, cap=2.0, **kw)
            eu.summarize = summ
        finally:
            eu.MAKER, eu.TAKER, v216.COOL = maker0, taker0, old
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        ts = v213.trade_stats(ev)
        dev, hid = ts.get("dev", {}), ts.get("_hidden", {})
        return {k: r[k] for k in ("monthly_dev4", "worst_dev_month_pct", "monthly_5y", "monthly_last_year",
                                  "gate_dd", "losing_years")} | {
            "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"]],
            "win_rate_dev": dev.get("win_rate"), "trades_dev": dev.get("trades"),
            "win_rate_hidden": hid.get("win_rate"), "trades_hidden": hid.get("trades")}

    def run_m2(**kw):
        return run("M2", **kw)

    def run_g2(**kw):
        return run("G2", **kw)

    cap_m2, cap_g2 = {}, {}
    rows = {
        "M2_base": run_m2(capture=cap_m2, events=m2_events),
        "G2_base": run_g2(capture=cap_g2, events=g2_events),
    }
    m = rows["M2_base"]
    assert abs(m["monthly_dev4"] - 3.011) < 0.01, m
    assert abs(m["monthly_5y"] - 3.16) < 0.01, m
    assert abs(m["monthly_last_year"] - 3.759) < 0.01, m
    assert abs(m["gate_dd"] - 20.57) < 0.05, m
    g = rows["G2_base"]
    assert abs(g["monthly_dev4"] - 2.502) < 0.003, g
    assert abs(g["monthly_5y"] - 2.772) < 0.005, g
    assert abs(g["monthly_last_year"] - 3.859) < 0.005, g
    assert abs(g["gate_dd"] - 19.61) < 0.05, g

    specs = [
        ("cost_stress", dict(maker=0.0004, taker=0.0007 + 0.0005)),
        ("latency_15", dict(win_start=15)),
        ("latency_30", dict(win_start=30)),
        ("latency_60", dict(win_start=60)),
        ("latency_120", dict(win_start=120)),
        ("missed_k6", dict(missed=True)),
        ("band_lo", dict(band=(0.02, 0.30))),
        ("band_hi", dict(band=(0.04, 0.50))),
        ("cool_3", dict(cool=3)),
        ("cool_12", dict(cool=12)),
    ]
    for name, kw in specs:
        rows[f"M2_{name}"] = run_m2(**kw)
        rows[f"G2_{name}"] = run_g2(**kw)
    for k, r in rows.items():
        print(f"{k:16s} dev4 {r['monthly_dev4']:6.3f} worst {r['worst_dev_month_pct']:6.3f} 5y {r['monthly_5y']:6.3f} "
              f"last {r['monthly_last_year']:6.3f} DD {r['gate_dd']:6.2f} losing {r['losing_years']} "
              f"win {r['win_rate_dev']} n {r['trades_dev']}", flush=True)
    boot_m2 = _bootstrap(cap_m2)
    boot_g2 = _bootstrap(cap_g2)
    print("bootstrap_M2 (1-year paths from first-four-year daily returns, 30-day blocks):", boot_m2, flush=True)
    print("bootstrap_G2 (1-year paths from first-four-year daily returns, 30-day blocks):", boot_g2, flush=True)
    small = {}
    for eq in SMALL_EQUITIES:
        sm_m2 = _placeable(m2_events, eq)
        sm_g2 = _placeable(g2_events, eq)
        small[str(int(eq))] = {"M2": sm_m2, "G2": sm_g2}
        print(f"small_account_{int(eq)}_M2:", {k: v for k, v in sm_m2.items() if k != "per_symbol"}, flush=True)
        print(f"small_account_{int(eq)}_G2:", {k: v for k, v in sm_g2.items() if k != "per_symbol"}, flush=True)
    OUT.write_text(json.dumps({"rows": rows, "bootstrap_M2": boot_m2, "bootstrap_G2": boot_g2,
                               "bootstrap": boot_m2, "small_account": small,
                               "small_account_500_M2": small["500"]["M2"], "small_account_500_G2": small["500"]["G2"],
                               "small_account_1000_M2": small["1000"]["M2"], "small_account_1000_G2": small["1000"]["G2"],
                               "small_account_2000_M2": small["2000"]["M2"], "small_account_2000_G2": small["2000"]["G2"],
                               "small_account_2000": small["2000"]["M2"],
                               "meta": {"M2": "books (2A + 2PT + D)/5, pullback entry 0.75 sigma_4h, n_valid 3, grid (0.03, 0.40) cool 6, SL 4 / TP 8, sleeve OFF, target 0.25 cap 2 win_start 5",
                                        "G2": "books (2A + 2B + D)/5, plain open k_off 0.25, n_valid 2, same management, sleeve OFF",
                                        "missed_k6": "every 6th decision bar (i % 6 == 0) returns wait when flat and hold in a position",
                                        "cost_stress": "maker 0.0004 taker 0.0012", "latency": "win_start 15/30/60/120"}},
                              indent=1))


if __name__ == "__main__":
    main()
