"""B1 robustness report (candidate: 5m-close dip stops + 8-sigma native backstop) (diagnostic only - nothing is selected on it).

Copied from research/diagnostics/o1_robustness/o1_robustness.py (same rows, same bootstrap, same small-account check).
Every O1 row is run twice:
  (a) O1 = the deployed O1 B18 (as in that script: touch sleeve stops), prefix "O1_".
  (b) B1 = the same plus sleeve_stop_mode="close5", sleeve_backstop=8.0 in the engine call, prefix "B1_".
Extra rows for B1 only:
  B1_outage_backstop_only   the bot is down: the close stop never fires, only the native 8-sigma touch stop
                            protects the rung (engine: sleeve_stop_mode="touch" with m_sleeve_sl=8.0).
  B1_close_1m               sleeve_stop_mode="close1" with the 8-sigma backstop (a bot watching 1m closes).
  B1_latency_close_plus5    SKIPPED: close5 trigger but the market exit fills 5 minutes later cannot be
                            implemented without editing the engine (the close-stop fill price/timing is
                            hard-coded inside engine_user.simulate); recorded under "skipped" with the reason.
The B1 base row must give dev4 6.13, gate DD 19.70, 5y 5.795, most recent year 4.464 (asserted).

  python research/diagnostics/b1_robustness/b1_robustness.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = Path(__file__).parent / "b1_robustness.json"

MIN_QTY = {"BTCUSDT": 0.001, "ETHUSDT": 0.01, "SOLUSDT": 0.1, "BNBUSDT": 0.01, "XRPUSDT": 0.1}
MIN_NOTIONAL = 5.0
SMALL_EQUITY = 2000.0
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
eu, v216, v204 = v221.eu, v221.v216, v221.v204
v213 = v221.v216.v213


def _placeable(events):
    """Share of base orders placeable at SMALL_EQUITY under the Bybit lot rules, most recent year only."""
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
            notion = w * SMALL_EQUITY
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
            notion = w * SMALL_EQUITY
            qty = notion / px
            ok = qty + 1e-12 >= MIN_QTY[sym] and notion + 1e-12 >= MIN_NOTIONAL
            rung_n += 1
            rung_ok += int(ok)
            d = per.setdefault(sym, {"book_n": 0, "book_ok": 0, "rung_n": 0, "rung_ok": 0})
            d["rung_n"] += 1
            d["rung_ok"] += int(ok)
    return {"equity_usdt": SMALL_EQUITY, "min_notional_usdt": MIN_NOTIONAL, "min_qty": MIN_QTY,
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
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(books154.index).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"),
        ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    maker0, taker0 = eu.MAKER, eu.TAKER
    o1_events, b1_events = [], []

    def run(band=(0.03, 0.40), cool=6, budget=0.18, k_off=0.25, win_start=5, maker=maker0, taker=taker0,
            stop_mode="touch", backstop=None, m_sleeve_sl=None, sleeve_budget_sl="default",
            capture=None, events=None):
        eu.MAKER, eu.TAKER = maker, taker
        old = v216.COOL
        v216.COOL = cool
        try:
            pol = v216.grid_policy(*band)
            kw = dict(v221.KW, sleeve_risk_budget=budget)
            if m_sleeve_sl is not None:
                kw["m_sleeve_sl"] = m_sleeve_sl
            if sleeve_budget_sl != "default":
                kw["sleeve_budget_sl"] = sleeve_budget_sl
            kw["sleeve_stop_mode"] = stop_mode
            if backstop is not None:
                kw["sleeve_backstop"] = backstop
            grid = dict(v216.GRID, k_off=k_off)
            summ = eu.summarize
            if capture is not None:
                def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
                    capture.update(idx=idx, eq=eq.copy())
                    return summ(idx, net, eq, eq_min, g, stats, eq_max)
                eu.summarize = grab
            ev = [] if events is None else events
            r = eu.simulate(books, opens, prep, trade=dict(grid, policy=pol, k_off=k_off), win_start=win_start,
                            events=ev, **kw)
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

    def run_o1(**kw):
        return run(stop_mode="touch", backstop=None, **kw)

    def run_b1(**kw):
        return run(stop_mode="close5", backstop=8.0, **kw)

    cap_o1, cap_b1 = {}, {}
    rows = {
        "O1_base": run_o1(capture=cap_o1, events=o1_events),
        "B1_base": run_b1(capture=cap_b1, events=b1_events),
    }
    o = rows["O1_base"]
    assert abs(o["monthly_dev4"] - 5.777) < 0.003, o
    assert abs(o["monthly_5y"] - 5.436) < 0.003, o
    assert abs(o["monthly_last_year"] - 4.082) < 0.003, o
    assert abs(o["gate_dd"] - 19.65) < 0.05, o
    b = rows["B1_base"]
    assert abs(b["monthly_dev4"] - 6.13) < 0.01, b
    assert abs(b["monthly_5y"] - 5.795) < 0.005, b
    assert abs(b["monthly_last_year"] - 4.464) < 0.005, b
    assert abs(b["gate_dd"] - 19.70) < 0.05, b

    specs = [
        ("cost_stress", dict(maker=0.0004, taker=0.0007 + 0.0005)),
        ("latency_15", dict(win_start=15)),
        ("latency_30", dict(win_start=30)),
        ("latency_60", dict(win_start=60)),
        ("band_lo", dict(band=(0.02, 0.30))),
        ("band_hi", dict(band=(0.04, 0.50))),
        ("cool_3", dict(cool=3)),
        ("cool_12", dict(cool=12)),
        ("sleeve_0.16", dict(budget=0.16)),
        ("sleeve_0.20", dict(budget=0.20)),
        ("offset_0.15", dict(k_off=0.15)),
        ("offset_0.40", dict(k_off=0.40)),
    ]
    for name, kw in specs:
        rows[f"O1_{name}"] = run_o1(**kw)
        rows[f"B1_{name}"] = run_b1(**kw)
    # B1-only extras
    rows["B1_outage_backstop_only"] = run(stop_mode="touch", backstop=None, m_sleeve_sl=8.0)
    rows["B1_close_1m"] = run(stop_mode="close1", backstop=8.0)
    skipped = {"B1_latency_close_plus5": "skipped: a +5-minute delayed fill of the close5 stop exit cannot be "
               "implemented without editing engine_user.simulate (close-stop fill timing/price is hard-coded); "
               "no engine file was edited per the assignment."}
    for k, r in rows.items():
        print(f"{k:26s} dev4 {r['monthly_dev4']:6.3f} worst {r['worst_dev_month_pct']:6.3f} 5y {r['monthly_5y']:6.3f} "
              f"last {r['monthly_last_year']:6.3f} DD {r['gate_dd']:6.2f} losing {r['losing_years']} "
              f"win {r['win_rate_dev']} n {r['trades_dev']}", flush=True)
    # stationary block bootstrap on the first four years of each base path (same template, seed 0)
    boot_o1 = _bootstrap(cap_o1)
    boot_b1 = _bootstrap(cap_b1)
    print("bootstrap_O1 (1-year paths from first-four-year daily returns, 30-day blocks):", boot_o1, flush=True)
    print("bootstrap_B1 (1-year paths from first-four-year daily returns, 30-day blocks):", boot_b1, flush=True)
    small_o1 = _placeable(o1_events)
    small_b1 = _placeable(b1_events)
    print("small_account_2000_O1:", {k: v for k, v in small_o1.items() if k != "per_symbol"}, flush=True)
    print("small_account_2000_B1:", {k: v for k, v in small_b1.items() if k != "per_symbol"}, flush=True)
    print("skipped:", skipped, flush=True)
    OUT.write_text(json.dumps({"rows": rows, "bootstrap_O1": boot_o1, "bootstrap_B1": boot_b1,
                               "bootstrap": boot_b1, "small_account_2000_O1": small_o1,
                               "small_account_2000_B1": small_b1, "small_account_2000": small_b1,
                               "skipped": skipped,
                               "meta": {"O1": "touch stops (deployed B18)", "B1": "close5 + backstop 8.0",
                                        "outage": "touch m_sleeve_sl=8.0", "close_1m": "close1 + backstop 8.0"}},
                              indent=1))


if __name__ == "__main__":
    main()
