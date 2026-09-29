"""O1 B18 robustness report (deployed pipeline) (diagnostic only - nothing is selected on it).

Rows (all on the deployed O1 books, engine_user trade mode, B18 settings unless changed):
  base                    B18 as deployed (budget 0.18).
  cost_stress             maker 0.04%, taker 0.07% + 5 bps slippage on taker fills (AGENTS.md stress row).
  latency_15/30/60        a new order may fill only from minute 15 / 30 / 60 after the 4h close (slow trader or bot).
  band_lo / band_hi       grid band max(2%, 30%) / max(4%, 50%) instead of max(3%, 40%).
  cool_3 / cool_12        size-adjustment cooldown 3 / 12 bars instead of 6.
  sleeve_0.16 / 0.20      dip-sleeve stop-risk budget 0.16 / 0.20 instead of 0.18.
  offset_0.15 / 0.40      entry/adjustment limit offset 0.15 / 0.40 sigma_4h instead of 0.25.
Plus a stationary block bootstrap (30-day blocks, 2000 draws, seed 0) of the daily returns of `base` over the first four years: the
distribution of the monthly return and of the max drawdown of a 1-year path.
Plus, for a 2000 USDT account under the Bybit lot rules, the share of base book orders and dip-rung orders placeable over the
most recent year. Reports every walk-forward year (diagnostic of the frozen deployed pipeline, not a selection).

  python research/diagnostics/o1_robustness/o1_robustness.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = Path(__file__).parent / "o1_robustness.json"

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
    base_events = []

    def run(band=(0.03, 0.40), cool=6, budget=0.18, k_off=0.25, win_start=5, maker=maker0, taker=taker0,
            capture=None, events=None):
        eu.MAKER, eu.TAKER = maker, taker
        old = v216.COOL
        v216.COOL = cool
        try:
            pol = v216.grid_policy(*band)
            kw = dict(v221.KW, sleeve_risk_budget=budget)
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

    cap = {}
    rows = {"base": run(capture=cap, events=base_events)}
    b = rows["base"]
    assert abs(b["monthly_dev4"] - 5.777) < 0.003, b
    assert abs(b["monthly_5y"] - 5.436) < 0.003, b
    assert abs(b["monthly_last_year"] - 4.082) < 0.003, b
    assert abs(b["gate_dd"] - 19.65) < 0.05, b
    rows["cost_stress"] = run(maker=0.0004, taker=0.0007 + 0.0005)
    for mm in (15, 30, 60):
        rows[f"latency_{mm}"] = run(win_start=mm)
    rows["band_lo"], rows["band_hi"] = run(band=(0.02, 0.30)), run(band=(0.04, 0.50))
    rows["cool_3"], rows["cool_12"] = run(cool=3), run(cool=12)
    rows["sleeve_0.16"], rows["sleeve_0.20"] = run(budget=0.16), run(budget=0.20)
    rows["offset_0.15"], rows["offset_0.40"] = run(k_off=0.15), run(k_off=0.40)
    for k, r in rows.items():
        print(f"{k:14s} dev4 {r['monthly_dev4']:6.3f} worst {r['worst_dev_month_pct']:6.3f} 5y {r['monthly_5y']:6.3f} "
              f"last {r['monthly_last_year']:6.3f} DD {r['gate_dd']:6.2f} losing {r['losing_years']} "
              f"win {r['win_rate_dev']} n {r['trades_dev']}", flush=True)
    # block bootstrap on the first four years of the base path
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
    boot = dict(monthly_p5=round(float(np.percentile(months, 5)), 2), monthly_p50=round(float(np.percentile(months, 50)), 2),
                monthly_p95=round(float(np.percentile(months, 95)), 2), p_monthly_ge5=round(float(np.mean(np.array(months) >= 5)), 3),
                p_loss_year=round(float(np.mean(np.array(months) < 0)), 3), dd_p50=round(float(np.percentile(dds, 50)), 2),
                dd_p95=round(float(np.percentile(dds, 95)), 2), p_dd_gt20=round(float(np.mean(np.array(dds) > 20)), 3))
    print("bootstrap (1-year paths from first-four-year daily returns, 30-day blocks):", boot, flush=True)
    small = _placeable(base_events)
    print("small_account_2000:", {k: v for k, v in small.items() if k != "per_symbol"}, flush=True)
    OUT.write_text(json.dumps({"rows": rows, "bootstrap": boot, "small_account_2000": small}, indent=1))


if __name__ == "__main__":
    main()
