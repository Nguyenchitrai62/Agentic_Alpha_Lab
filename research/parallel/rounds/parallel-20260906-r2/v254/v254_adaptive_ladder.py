"""v254: adaptive dip-ladder spacing - bids set by the CURRENT volatility (like a trader using today's ATR), not a 60-day sigma.

Why: the dip ladder rests at 2.5 / 3 / 3.5 / 4 sigma_4h below the bar open, sigma_4h = std of 4h returns over the last 60 days. After a
quiet week the 60-day sigma overstates the bar's range (bids too deep, rarely filled); after a volatility spike it understates it (bids
too shallow, caught early in a cascade, stops at 5 sigma too tight). Realized volatility from the 1m closes of the last 24 h (or the last
4h bar) relative to the same measure over 60 days rescales the ladder to the current regime. Both use the same 1m data, so the
microstructure noise cancels in the ratio; nothing is fitted.
Fixed before running.
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings otherwise). New engine option prep["sig4_sleeve"]: the 4h dip
ladder uses sigma_s instead of sigma_4h for the rung levels, the take-profit (1 sigma_s), the stop (5 sigma_s) and the budget risk; the book
(SL / TP / sizing) keeps sigma_4h. RV_h(i) = sqrt(sum of squared 1m log returns over the last h hours up to the decision-bar close / (h/4))
(per-4h units; 1m closes of the bars before the holding bar only), ratio_h = RV_h / RV_60d, clipped to [0.25, 4]:
  S1_sqrt24   sigma_s = sigma_4h * ratio_24h ** 0.5
  S2_full24   sigma_s = sigma_4h * ratio_24h
  S3_sqrt4h   sigma_s = sigma_4h * ratio_4h ** 0.5
Reference: sigma_s = sigma_4h (must reproduce v247 B18, dev4 5.777). SELECTION = robust criterion among S1..S3; the most recent year is
scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v254/v254_adaptive_ladder.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
BUDGET = 0.18
VARIANTS = {"S1_sqrt24": (24, 0.5), "S2_full24": (24, 1.0), "S3_sqrt4h": (4, 0.5)}


def rv_ratios(prep):
    """ratio_h[i, a] = RV over the last h hours up to the decision-bar close of row i / RV over the last 60 days (per-4h units).
    Cube row j holds the 1m closes of the holding bar starting at idx[j] + 4h; bars are placed on the full 4h time grid (the panel
    index has gaps) and row i reads the windows ending with the bar that starts at idx[i] (its decision bar)."""
    idx = prep["idx"]
    C = prep["C"].astype(float)  # (bars, 240, assets)
    n, _, na = C.shape
    flat = C.reshape(n * 240, na)
    r = np.diff(np.log(flat), axis=0, prepend=np.nan)
    r[::240] = np.nan  # the first minute of a cube row would span a possible gap: drop it
    per_bar = pd.DataFrame(np.nansum((r ** 2).reshape(n, 240, na), axis=1) * 240 / np.maximum(np.isfinite(r).reshape(n, 240, na).sum(axis=1), 1),
                           index=idx + pd.Timedelta(hours=4))
    per_bar[np.isfinite(r).reshape(n, 240, na).sum(axis=1) < 120] = np.nan
    full = per_bar.reindex(pd.date_range(per_bar.index[0], per_bar.index[-1], freq="4h"))
    rv60 = full.rolling(360, min_periods=180).mean()
    out = {}
    for h in (4, 24):
        rvh = full.rolling(h // 4, min_periods=h // 4).mean()
        out[h] = np.clip((rvh / rv60).reindex(idx).to_numpy(), 0.25, 4.0)
    return out


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    KW = dict(v221.KW, sleeve_risk_budget=BUDGET)
    ratios = rv_ratios(prep)
    print("ratio quantiles (5/50/95%)", {h: np.nanpercentile(v, [5, 50, 95]).round(3).tolist() for h, v in ratios.items()}, flush=True)
    out = {"version": "v254", "variants": {k: list(v) for k, v in VARIANTS.items()}, "rows": {}, "trades": {}}
    runs = [("v247_B18", None)] + list(VARIANTS.items())
    for key, spec in runs:
        ev = []
        pr = prep if spec is None else dict(prep, sig4_sleeve=np.where(np.isfinite(ratios[spec[0]]), prep["sig4"] * ratios[spec[0]] ** spec[1], prep["sig4"]))
        r = eu.simulate(books, opens, pr, trade=trade, win_start=5, events=ev, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rungs", r["stats"]["rungs"], "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "sigma_4h ladder must reproduce v247 B18"
    cands = tuple(VARIANTS)
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v254_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
