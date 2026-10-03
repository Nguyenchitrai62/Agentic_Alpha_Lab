"""Skew found by the parity audit: the live flow stores data/raw/aggflow_20260928{,_orders}/{SYM}_flow_4h.parquet count every bar
2026-09-01 00:00 .. 2026-09-29 20:00 twice (taker notional / kline quote volume = 2.000; the 2026-09-29 snapshot
data/raw/aggflow_20260929_orders has 1.000). This script (read-only) checks that halving those rows reproduces the snapshot, measures the
effect on the six v236 flow features at the live decision bars, and replays the live A set (v240_a_models) as of every logged v240_O1 bar with
the corrected flow to measure the effect on the book rows and to test whether it explains the replay-vs-log differences.
Output: parity/flow_doubling_impact.json.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(HERE))
import rest_cache as rc  # noqa: E402

D0, D1 = pd.Timestamp("2026-09-01", tz="UTC"), pd.Timestamp("2026-09-29 20:00", tz="UTC")
COLS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    out = {"doubled_range": [str(D0), str(D1)], "snapshot_check": {}, "feature_effect": {}}
    live = _load("dbl_aggflow_live", ROOT / "scripts/aggflow_live.py")
    for s in rc.SYMS:
        a = pd.read_parquet(live.OUT_ORDERS / f"{s}_flow_4h.parquet").fillna(0.0)
        b = pd.read_parquet(ROOT / "data/raw/aggflow_20260929_orders" / f"{s}_flow_4h.parquet").fillna(0.0)
        j = a.index.intersection(b.index)
        j = j[(j >= D0) & (j <= D1)]
        out["snapshot_check"][s] = {"bars": len(j), "max_abs_diff_after_halving": float((a.loc[j] / 2 - b.loc[j][a.columns]).abs().max().max())}
    orig = live.combined_flow

    def corrected(sym, now=None, orders=False):
        f = orig(sym, now, orders).copy()
        m = (f.index >= D0) & (f.index <= D1)
        f.loc[m] = f.loc[m] / 2
        return f
    flo = _load("dbl_flow_features", ROOT / "research/parallel/rounds/parallel-20260906-r2/v236/flow_features.py")
    shadow = [json.loads(x) for x in open(ROOT / "artifacts/research/advisor_shadow/shadow.jsonl", encoding="utf-8") if x.startswith("{")]
    logged = {pd.Timestamp(r["decision_bar_close"]): r for r in shadow if r.get("candidate") == "v240_O1" and not r.get("error") and "members" in r}
    bars = pd.DatetimeIndex(sorted(T + pd.Timedelta(milliseconds=1) - pd.Timedelta(hours=4) for T in logged))
    for s in rc.SYMS:
        fd, fc = flo.flow_features(s, bars, orig(s, orders=True)), flo.flow_features(s, bars, corrected(s, orders=True))
        out["feature_effect"][s] = {c: {"max_abs_diff": round(float((fd[c] - fc[c]).abs().max()), 4), "std_doubled": round(float(fd[c].std()), 4),
                                        "mean_doubled": round(float(fd[c].mean()), 4), "mean_corrected": round(float(fc[c].mean()), 4)}
                                    for c in flo.FL}
    # replay the A set with corrected flow (same REST emulation as feature_parity.py)
    K4, K1D, FR = rc.market_data(pd.Timestamp("2026-10-03 12:00", tz="UTC"))
    v240 = _load("dbl_v240_advisor", ROOT / "scripts/v240_advisor.py")
    v233a, seta = v240.v233a, v240.seta
    import agentic_alpha_lab.data.binance_usdm as bu
    bu.fetch_klines = lambda symbol, interval, start, end=None, session=None: (K4 if interval == "4h" else K1D)[symbol].pipe(
        lambda d: d[(d.open_time >= pd.Timestamp(start)) & (d.open_time <= pd.Timestamp(end))].reset_index(drop=True).copy())
    seta.funding_asof = lambda session, sym: FR[sym][FR[sym].fundingTime <= pd.Timestamp(os.environ["ADVISOR_ASOF"])].tail(1000).reset_index(drop=True)

    def tv():
        T = pd.Timestamp(os.environ["ADVISOR_ASOF"])
        rows = []
        for sym in v233a.SYMS:
            b = K4[sym]
            b = b[b.close_time <= T].tail(1499).reset_index(drop=True)
            rows.append(pd.concat([pd.DataFrame({"t": b["open_time"], "sym": sym}), v233a.tvm.tv_features(b)], axis=1))
        return pd.concat(rows, ignore_index=True)
    v233a.live_tv = tv
    rep = {}
    for variant, fn in (("doubled", orig), ("corrected", corrected)):
        v240.live.combined_flow = fn
        for T in sorted(logged):
            os.environ["ADVISOR_ASOF"] = str(T)
            a = seta.advise()
            rep.setdefault(variant, {})[T] = a
    os.environ.pop("ADVISOR_ASOF", None)
    rows = []
    for T, r in sorted(logged.items()):
        lp = r["members"]["v144_tv_orderflow"]
        d, c = rep["doubled"][T], rep["corrected"][T]
        bk = lambda x: np.array([(x["perp_weight"][s] + x["spot_weight"][s]) / (0.8 * x["portfolio_scale"]) for s in COLS])
        rows.append({"bar_close": str(T), "logged_at": r["logged_at"][:16], "mode": r["mode"],
                     "log_vs_doubled_Aperp": round(max(abs(lp[s] - d["perp_weight"][s]) for s in COLS), 4),
                     "log_vs_corrected_Aperp": round(max(abs(lp[s] - c["perp_weight"][s]) for s in COLS), 4),
                     "A_book_doubled_minus_corrected_maxabs": round(float(np.abs(bk(d) - bk(c)).max()), 4),
                     "A_book_mean_abs": round(float(np.abs(bk(c)).mean()), 4)})
    out["replay_rows"] = rows
    out["summary"] = {"A_book_effect_max": max(x["A_book_doubled_minus_corrected_maxabs"] for x in rows),
                      "A_book_effect_mean": round(float(np.mean([x["A_book_doubled_minus_corrected_maxabs"] for x in rows])), 4),
                      "O1_row_effect_max (A weight 0.5)": round(0.5 * max(x["A_book_doubled_minus_corrected_maxabs"] for x in rows), 4),
                      "D2_row_effect_max (0.8 x 0.5)": round(0.4 * max(x["A_book_doubled_minus_corrected_maxabs"] for x in rows), 4),
                      "rows_logged_before_2026-10-02T05:00_matching_corrected (<=1e-4)": sum(
                          1 for x in rows if x["logged_at"] < "2026-10-02T05:00" and x["log_vs_corrected_Aperp"] <= 1e-4),
                      "rows_logged_before_2026-10-02T05:00": sum(1 for x in rows if x["logged_at"] < "2026-10-02T05:00"),
                      "rows_logged_after_matching_doubled (<=1e-4)": sum(1 for x in rows if x["logged_at"] >= "2026-10-02T05:00"
                                                                          and x["log_vs_doubled_Aperp"] <= 1e-4),
                      "rows_logged_after": sum(1 for x in rows if x["logged_at"] >= "2026-10-02T05:00")}
    (HERE / "flow_doubling_impact.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in ("snapshot_check", "summary")}, indent=1))


if __name__ == "__main__":
    main()
