"""R2 robustness report (candidate: BOT pipeline R2 (v321) vs the deployed G2 (v301), both in the deployed BAR-OPEN form) (diagnostic only - nothing is selected on it).

Copied from research/diagnostics/s1_robustness/s1_robustness.py (same rows, same bootstrap, same small-account check) and adapted to the two lookup legs:
  G2_*: books CB = (2A + 2B + D)/5 from the v306 member groups (= 0.8 C4 + 0.2 (D + Dq)/2), lookup hooks from
        artifacts/research/engine_real/v301_g2_table_m0.parquet (keys: holding bar T = decision bar + 4h, symbol, rung index), rungs (2.5, 3, 3.5, 4),
        sleeve_risk_budget 0.26, size_mult 1.75, align (1.5, 0.5), close5 stop 4 sigma + 8-sigma backstop, grid_policy(0.03, 0.40), win_start 5.
        Base must reproduce dev4 6.504 / gate DD 17.09 / 5y 6.272 / most recent year 5.349.
  R2_*: same books and rules, hooks from artifacts/research/engine_real/v321_r2_table_m0.parquet, rungs (2.5, 3, 3.5, 4, 5). Base must reproduce
        dev4 7.079 / gate DD 18.39 / 5y 6.793 / most recent year 5.655.
Rows for both legs: base, cost_stress (maker 0.0004, taker 0.0007 + 0.0005), latency_15 / 30 / 60 (book win_start), band_lo / band_hi, cool3 / cool12,
sleeve budget 0.22 / 0.30, offset 0.15 / 0.40, outage_backstop_only (stop touch at 8 sigma, no close stop), close_1m; sleeve_start 21 / 31
(the bot places the ladder 5 / 15 minutes late); the stationary block bootstrap (first four years, 30-day blocks, 2000 draws, seed 0) and the
small-account check at 1000 and 2000 USDT (Bybit lots).

  python research/diagnostics/r2_robustness/r2_robustness.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = Path(__file__).parent / "r2_robustness.json"

G2_RUNGS = (2.5, 3.0, 3.5, 4.0)
R2_RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
BASE_BUDGET = 0.26

MIN_QTY = {"BTCUSDT": 0.001, "ETHUSDT": 0.01, "SOLUSDT": 0.1, "BNBUSDT": 0.01, "XRPUSDT": 0.1}
MIN_NOTIONAL = 5.0
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
    """Share of base orders placeable at `equity` under the Bybit lot rules, most recent year only."""
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
                monthly_p95=round(float(np.percentile(months, 95)), 2),
                p_monthly_ge5=round(float(np.mean(np.array(months) >= 5)), 3),
                p_loss_year=round(float(np.mean(np.array(months) < 0)), 3), dd_p50=round(float(np.percentile(dds, 50)), 2),
                dd_p95=round(float(np.percentile(dds, 95)), 2), p_dd_gt20=round(float(np.mean(np.array(dds) > 20)), 3))


def _all_trades(events, maker, taker):
    """Book + dip-rung trades (entry in dev vs hidden split by entry time)."""
    pos, out = {}, []
    for e in events:
        k, sym = e["kind"], e.get("symbol")
        if k in ("rung_tp", "rung_sl", "rung_timeout") and "ret" in e and e["ret"] is not None:
            out.append((e["t"], float(e["ret"])))
            continue
        if k == "book_fill":
            q = abs(e["weight"]) / e["price"]
            pos[sym] = dict(t=e["t"], side=1 if e["side"] == "buy" else -1, qty=q, cost=q * e["price"], proceeds=0.0, fees=q * e["price"] * maker)
            continue
        o = pos.get(sym)
        if o is None:
            continue
        if k == "book_add":
            q = abs(e["weight"]) / e["price"]
            o["qty"] += q; o["cost"] += q * e["price"]; o["fees"] += q * e["price"] * maker
        elif k in ("book_reduce", "book_partial"):
            q = min(abs(e["weight"]) / e["price"], o["qty"])
            o["qty"] -= q; o["proceeds"] += q * e["price"]; o["fees"] += q * e["price"] * maker
        elif k in ("book_stop", "book_tp", "book_close"):
            o["proceeds"] += o["qty"] * e["price"]
            o["fees"] += o["qty"] * e["price"] * (taker if k == "book_stop" else maker)
            out.append((o["t"], (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]) / o["cost"]))
            pos.pop(sym)
    return out


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"),
        ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    maker0, taker0 = eu.MAKER, eu.TAKER

    g2_tab = pd.read_parquet(C / "v301_g2_table_m0.parquet")
    r2_tab = pd.read_parquet(C / "v321_r2_table_m0.parquet")
    g2_size = {(row.T, row.sym, int(row.rung)): float(row.size) for row in g2_tab.itertuples()}
    g2_tp = {(row.T, row.sym, int(row.rung)): float(row.tp) for row in g2_tab.itertuples()}
    r2_size = {(row.T, row.sym, int(row.rung)): float(row.size) for row in r2_tab.itertuples()}
    r2_tp = {(row.T, row.sym, int(row.rung)): float(row.tp) for row in r2_tab.itertuples()}

    def make_hooks(size_d, tp_d):
        def sz(i, a, r, f):
            return size_d.get((idx[i] + pd.Timedelta(hours=4), cols[a], r), 1.0)

        def tp(i, a, r, f):
            return tp_d.get((idx[i] + pd.Timedelta(hours=4), cols[a], r), 1.0)

        return sz, tp

    g2_sz, g2_tph = make_hooks(g2_size, g2_tp)
    r2_sz, r2_tph = make_hooks(r2_size, r2_tp)

    g2_events, r2_events = [], []

    def run(books, rungs, size_hook, tp_hook, band=(0.03, 0.40), cool=6, budget=BASE_BUDGET, k_off=0.25,
            win_start=5, maker=maker0, taker=taker0, stop_mode="close5", backstop=8.0, m_sleeve_sl=4.0,
            sleeve_start=16, capture=None, events=None):
        eu.MAKER, eu.TAKER = maker, taker
        old = v216.COOL
        v216.COOL = cool
        try:
            pol = v216.grid_policy(*band)
            kw = dict(v221.KW, sleeve_risk_budget=budget, size_mult=1.75, align=(1.5, 0.5))
            kw["m_sl"] = 4.0
            if m_sleeve_sl is not None:
                kw["m_sleeve_sl"] = m_sleeve_sl
            kw["sleeve_stop_mode"] = stop_mode
            if backstop is not None:
                kw["sleeve_backstop"] = backstop
            elif "sleeve_backstop" in kw:
                del kw["sleeve_backstop"]
            grid = dict(v216.GRID, k_off=k_off)
            summ = eu.summarize
            if capture is not None:
                def grab(gidx, net, eq, eq_min, g, stats, eq_max=None):
                    capture.update(idx=gidx, eq=eq.copy())
                    return summ(gidx, net, eq, eq_min, g, stats, eq_max)
                eu.summarize = grab
            ev = [] if events is None else events
            r = eu.simulate(books, opens, prep, trade=dict(grid, policy=pol, k_off=k_off), win_start=win_start,
                            events=ev, sleeve_fill_size=size_hook, sleeve_tp=tp_hook, rungs=rungs,
                            target=0.25, sleeve_start=sleeve_start, **kw)
            eu.summarize = summ
        finally:
            eu.MAKER, eu.TAKER, v216.COOL = maker0, taker0, old
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        ts = v213.trade_stats(ev)
        dev, hid = ts.get("dev", {}), ts.get("_hidden", {})
        alltr = _all_trades(ev, maker, taker)
        a0 = pd.Timestamp("2025-09-24", tz="UTC")
        dev_all = [v for t, v in alltr if t < a0]
        hid_all = [v for t, v in alltr if t >= a0]
        return {k: r[k] for k in ("monthly_dev4", "worst_dev_month_pct", "monthly_5y", "monthly_last_year",
                                  "gate_dd", "losing_years")} | {
            "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"]],
            "win_rate_dev": dev.get("win_rate"), "trades_dev": dev.get("trades"),
            "win_rate_hidden": hid.get("win_rate"), "trades_hidden": hid.get("trades"),
            "win_all_dev": round(float(sum(v > 0 for v in dev_all)) / len(dev_all), 4) if dev_all else None,
            "trades_all_dev": len(dev_all),
            "win_all_hidden": round(float(sum(v > 0 for v in hid_all)) / len(hid_all), 4) if hid_all else None,
            "trades_all_hidden": len(hid_all)}

    def run_g2(**kw):
        kw = dict(kw)
        kw.setdefault("budget", BASE_BUDGET)
        kw.setdefault("stop_mode", "close5")
        kw.setdefault("backstop", 8.0)
        kw.setdefault("m_sleeve_sl", 4.0)
        return run(cb, G2_RUNGS, g2_sz, g2_tph, **kw)

    def run_r2(**kw):
        kw = dict(kw)
        kw.setdefault("budget", BASE_BUDGET)
        kw.setdefault("stop_mode", "close5")
        kw.setdefault("backstop", 8.0)
        kw.setdefault("m_sleeve_sl", 4.0)
        return run(cb, R2_RUNGS, r2_sz, r2_tph, **kw)

    cap_g2, cap_r2 = {}, {}
    rows = {
        "G2_base": run_g2(capture=cap_g2, events=g2_events),
        "R2_base": run_r2(capture=cap_r2, events=r2_events),
    }
    g = rows["G2_base"]
    assert abs(g["monthly_dev4"] - 6.504) < 0.01, g
    assert abs(g["monthly_5y"] - 6.272) < 0.005, g
    assert abs(g["monthly_last_year"] - 5.349) < 0.005, g
    assert abs(g["gate_dd"] - 17.09) < 0.05, g
    b = rows["R2_base"]
    assert abs(b["monthly_dev4"] - 7.079) < 0.01, b
    assert abs(b["monthly_5y"] - 6.793) < 0.005, b
    assert abs(b["monthly_last_year"] - 5.655) < 0.005, b
    assert abs(b["gate_dd"] - 18.39) < 0.05, b

    specs = [
        ("cost_stress", dict(maker=0.0004, taker=0.0007 + 0.0005)),
        ("latency_15", dict(win_start=15)),
        ("latency_30", dict(win_start=30)),
        ("latency_60", dict(win_start=60)),
        ("band_lo", dict(band=(0.02, 0.30))),
        ("band_hi", dict(band=(0.04, 0.50))),
        ("cool3", dict(cool=3)),
        ("cool12", dict(cool=12)),
        ("sleeve_0.22", dict(budget=0.22)),
        ("sleeve_0.30", dict(budget=0.30)),
        ("offset_0.15", dict(k_off=0.15)),
        ("offset_0.40", dict(k_off=0.40)),
    ]
    for name, kw in specs:
        rows[f"G2_{name}"] = run_g2(**kw)
        rows[f"R2_{name}"] = run_r2(**kw)
    rows["G2_outage_backstop_only"] = run_g2(stop_mode="touch", backstop=None, m_sleeve_sl=8.0)
    rows["R2_outage_backstop_only"] = run_r2(stop_mode="touch", backstop=None, m_sleeve_sl=8.0)
    rows["G2_close_1m"] = run_g2(stop_mode="close1", backstop=8.0, m_sleeve_sl=4.0)
    rows["R2_close_1m"] = run_r2(stop_mode="close1", backstop=8.0, m_sleeve_sl=4.0)
    rows["G2_sleeve_start_21"] = run_g2(sleeve_start=21)
    rows["R2_sleeve_start_21"] = run_r2(sleeve_start=21)
    rows["G2_sleeve_start_31"] = run_g2(sleeve_start=31)
    rows["R2_sleeve_start_31"] = run_r2(sleeve_start=31)
    for k, r in rows.items():
        print(f"{k:26s} dev4 {r['monthly_dev4']:6.3f} worst {r['worst_dev_month_pct']:6.3f} 5y {r['monthly_5y']:6.3f} "
              f"last {r['monthly_last_year']:6.3f} DD {r['gate_dd']:6.2f} losing {r['losing_years']} "
              f"win {r['win_rate_dev']} n {r['trades_dev']} allwin {r['win_all_dev']} alln {r['trades_all_dev']}", flush=True)
    boot_g2 = _bootstrap(cap_g2)
    boot_r2 = _bootstrap(cap_r2)
    print("bootstrap_G2 (1-year paths from first-four-year daily returns, 30-day blocks):", boot_g2, flush=True)
    print("bootstrap_R2 (1-year paths from first-four-year daily returns, 30-day blocks):", boot_r2, flush=True)
    small_1000_g2 = _placeable(g2_events, 1000.0)
    small_2000_g2 = _placeable(g2_events, 2000.0)
    small_1000_r2 = _placeable(r2_events, 1000.0)
    small_2000_r2 = _placeable(r2_events, 2000.0)
    print("small_account_1000_G2:", {k: v for k, v in small_1000_g2.items() if k != "per_symbol"}, flush=True)
    print("small_account_2000_G2:", {k: v for k, v in small_2000_g2.items() if k != "per_symbol"}, flush=True)
    print("small_account_1000_R2:", {k: v for k, v in small_1000_r2.items() if k != "per_symbol"}, flush=True)
    print("small_account_2000_R2:", {k: v for k, v in small_2000_r2.items() if k != "per_symbol"}, flush=True)
    OUT.write_text(json.dumps({"rows": rows, "bootstrap_G2": boot_g2, "bootstrap_R2": boot_r2,
                               "bootstrap": boot_r2, "small_account_1000_G2": small_1000_g2,
                               "small_account_2000_G2": small_2000_g2, "small_account_1000_R2": small_1000_r2,
                               "small_account_2000_R2": small_2000_r2, "small_account_1000": small_1000_r2,
                               "small_account_2000": small_2000_r2,
                               "meta": {"G2": "CB (2A+2B+D)/5 = 0.8 C4 + 0.2 (D+Dq)/2, v301 G2 lookup bar-open, rungs (2.5,3,3.5,4), budget 0.26, size_mult 1.75, align (1.5,0.5), close5/m_sleeve_sl 4.0/backstop 8.0, grid_policy(0.03,0.40), win_start 5",
                                        "R2": "same books/rules, v321 R2 lookup bar-open, rungs (2.5,3,3.5,4,5)",
                                        "outage": "touch m_sleeve_sl=8.0, no backstop", "close_1m": "close1 + backstop 8.0, m_sleeve_sl 4.0",
                                        "sleeve_start": "dip-ladder first fill minute (base 16; 21/31 = 5/15 min late)"}},
                              indent=1))


if __name__ == "__main__":
    main()
