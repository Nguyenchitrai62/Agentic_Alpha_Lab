"""v279: SIZE the dip rung at the fill by how fast the price fell into it (a consistent dev fact never used for sizing).

Why: the dev-only intrabar diagnostic (research/diagnostics/dip_intrabar) found that fills after FAST drops revert better than fills after
slow grinds, with the same sign in all four dev years - but every speed bucket was profitable, so the filters built on it (v220, v235,
v243) could only lose. A trader uses such information for SIZE, not for skipping: bid more into a violent flush, less into a slow grind.
The size is decided at the fill minute from data up to the minute before (engine hook sleeve_fill_size).
Fixed before running.
Environment = v269 M1 (O1 books, dip stops on 5m closes at 4 sigma + 8-sigma native backstop, sleeve budget 0.18, v218 D2 settings).
Speed = 30-minute log return to minute f-1 over sigma_1m * sqrt(30), sigma_1m = std of 1m log returns over the previous 24 h (v248's
definition). Terciles per anchor year Y from the fills of the recording run (M1) whose bar ended before Y - 7 days (from 2021-09-24); 2021
uses multiplier 1. Multipliers (fast / middle / slow):
  F1_speed_13_07   1.3 / 1.0 / 0.7
  F2_speed_15_05   1.5 / 1.0 / 0.5
The risk budget still caps the sleeve. Reference: v269 M1 (must reproduce dev4 6.026). SELECTION = robust criterion among F1, F2; the
most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v279/v279_fill_speed_sizing.py
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
EMBARGO = pd.Timedelta(days=7)
M1 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)
VARIANTS = {"F1_speed_13_07": (1.3, 1.0, 0.7), "F2_speed_15_05": (1.5, 1.0, 0.5)}


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
    KW = dict(v221.KW, **M1)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    t_hold = idx + pd.Timedelta(hours=4)
    Cm = prep["C"]
    flat = Cm.reshape(-1, Cm.shape[2]).astype(float)
    lr = np.diff(np.log(flat), axis=0, prepend=np.nan)
    sig1 = pd.DataFrame(lr).rolling(1440, min_periods=720).std().to_numpy()

    def speed(i, a, f):
        k = i * 240 + f - 1
        if k < 30 or not np.isfinite(sig1[k, a]) or sig1[k, a] <= 0:
            return 0.0
        return float(np.log(flat[k, a] / flat[k - 30, a]) / (sig1[k, a] * np.sqrt(30)))

    def run(hook=None, ev=None):
        return eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=hook, **KW)

    rec = []

    def recorder(i, a, r, f):
        rec.append((i, speed(i, a, f)))
        return 1.0
    r0 = run(recorder)
    assert abs(r0["monthly_dev4"] - 6.026) < 0.002, "the recording run must reproduce v269 M1"
    I = np.array([x[0] for x in rec])
    S = np.array([x[1] for x in rec])
    bar_end = t_hold[I] + pd.Timedelta(hours=4)
    thr = {}
    for j in range(1, len(anchors)):
        tr = np.asarray((bar_end < anchors[j] - EMBARGO) & (t_hold[I] >= anchors[0]))
        thr[j] = (float(np.percentile(S[tr], 33.3)), float(np.percentile(S[tr], 66.7)))
    out = {"version": "v279", "fills_seen": int(len(S)), "thresholds": {str(anchors[j].date()): thr[j] for j in thr}, "rows": {}, "trades": {}}
    print("fills seen", len(S), "terciles", out["thresholds"], flush=True)

    def year(i):
        t = t_hold[i]
        return max(jj for jj, a0 in enumerate(anchors) if t >= a0) if t >= anchors[0] else 0

    def sizer(mults):
        def hook(i, a, r, f):
            jj = year(i)
            if jj == 0:
                return 1.0
            s = speed(i, a, f)
            lo, hi = thr[jj]
            return mults[0] if s <= lo else (mults[2] if s >= hi else mults[1])
        return hook

    for key, hook in [("v269_M1", None)] + [(k, sizer(v)) for k, v in VARIANTS.items()]:
        ev = []
        r = run(hook, ev)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], flush=True)
    sel = v204.robust_select({k: out["rows"][k] for k in VARIANTS})
    s_ = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
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
    (HERE / "v279_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
