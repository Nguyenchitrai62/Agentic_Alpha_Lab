"""Execution-realism stress test of engine_user for the deployed pipelines (system audit 2026-10-03).

Replays every pipeline of backend/history_tm.py with exactly its deployed setup (research books, KW_OVERRIDE, walk-forward agent
tables, trade policy, minute-5 rule) and adds engine_user's default-neutral stress hooks one at a time and combined:
  base   the audited replay (its dev4 must equal history_tm.PIPELINES' research value)
  F1     sleeve_fill_minute_stop      a dip rung's stop / native backstop is also checked in its fill minute
  T2/T5  fill_through_bps 2 / 5       every limit fill needs a 2 / 5 bp trade-through (queue, Binance-vs-Bybit basis)
  S50/S100 stop_slip 0.5 / 1.0        market stops fill half-way / at the far end of the fill minute's range
  L10    timeout_exit_minute 10       dip rungs open at the bar end exit at minute 10 of the next bar (L5 for the R2 bot)
  FUND   actual signed Binance funding (SIDE ROW, replaces the adverse 0.01%/8h on longs)
  PESS   F1 + T2 + S50 + L10 (L5 for R2);  PESS+FUND;  R2 only: L1 and PESS_L1 (bot exiting 1 minute after the close)
Nothing here chooses anything: the most recent year is reported only. Usage:
  python research/diagnostics/system_audit/engine_stress/engine_stress.py --pipes v367 v321     (one JSON per pipeline)
  python research/diagnostics/system_audit/engine_stress/engine_stress.py --merge               (engine_stress.json + .csv)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT))
import backend.history_tm as H  # noqa: E402

PIPES = ["v367", "v362", "v342", "v340", "v315", "v321"]
NAMES = {"v367": "M5", "v362": "M4", "v342": "M3", "v340": "M2", "v315": "M1", "v321": "R2 BOT"}
DEV0, HID0 = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC")
FUND_ARCHIVE = ROOT / "data/raw/binance_premium_20260928"   # Binance public archive, settled funding (to 2026-08-31)
FUND_API = ROOT / "data/raw/cx_funding_20260925"            # Binance API funding history (to 2026-09-24), extends the archive


def setup(pipe: str):
    """Mirror of backend.history_tm.simulate's setup (same books, kwargs, agent tables and trade policy)."""
    v221 = H._load(f"v221_stress_{pipe}", H.RD / "v221/v221_grid_hysteresis.py")
    fw = H._load(f"forward_v205_stress_{pipe}", H.ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    fn, dev4 = H.PIPELINES[pipe]
    books = getattr(fw, fn)(eu).reindex(books154.index).fillna(0.0)[cols]
    prep = eu.prepare(books154, opens)
    kw = dict(v221.KW, **H.KW_OVERRIDE.get(pipe, {}))
    if pipe in ("v301", "v321", "v340", "v342", "v362", "v367"):
        tab = pd.read_parquet(H.G2_TABLE if pipe == "v301" else H.R2_TABLE)
        keys = [(pd.Timestamp(t), s, int(r)) for t, s, r in zip(tab["T"], tab["sym"], tab["rung"])]
        lsz, ltp = dict(zip(keys, tab["size"].astype(float))), dict(zip(keys, tab["tp"].astype(float)))
        idx = books.index
        rmap = H.M3_R2_RUNG if pipe in ("v340", "v342", "v362", "v367") else {}
        kw["sleeve_fill_size"] = lambda i, a, r, f: lsz.get((idx[i] + pd.Timedelta(hours=4), cols[a], rmap.get(r, r)), 1.0)
        kw["sleeve_tp"] = lambda i, a, r, f: ltp.get((idx[i] + pd.Timedelta(hours=4), cols[a], rmap.get(r, r)), 1.0)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    if pipe in ("v315", "v340", "v342", "v362", "v367"):
        grid_pol = trade["policy"]
        trade = dict(trade, n_valid=3, policy=lambda i, a, st: {"open": 0.75} if st["pos"] == 0 else grid_pol(i, a, st))
        if pipe == "v367":
            pol5 = trade["policy"]
            trade["policy"] = lambda i, a, st: "tighten" if st["pos"] != 0 and st["sgn"] == 0 and st["upnl"] < 0 else pol5(i, a, st)
        if pipe in ("v340", "v342", "v362", "v367"):
            trade["book_mult"] = 0.75
    return eu, v221, books, opens, prep, kw, trade, cols, dev4


def load_funding(cols):
    """Actual signed Binance funding per settlement (archive; API history appended after the archive's last settlement)."""
    ser, check = {}, {}
    for s in cols:
        a = pd.read_parquet(FUND_ARCHIVE / f"{s}_funding.parquet")
        sa = pd.Series(a["last_funding_rate"].to_numpy(float), index=pd.DatetimeIndex(a["calc_time"]).floor("min"))
        b = pd.read_parquet(FUND_API / f"binance_{s[:-4]}.parquet")
        sb = pd.Series(b["fundingRate"].to_numpy(float), index=pd.DatetimeIndex(b["fundingTime"]).floor("min"))
        sa, sb = sa[~sa.index.duplicated()], sb[~sb.index.duplicated()]
        common = sa.index.intersection(sb.index)
        check[s] = dict(archive_end=str(sa.index.max()), api_end=str(sb.index.max()), overlap=len(common),
                        max_abs_diff=float((sa[common] - sb[common]).abs().max()) if len(common) else None,
                        appended=int((sb.index > sa.index.max()).sum()))
        ser[s] = pd.concat([sa, sb[sb.index > sa.index.max()]])
    return pd.DataFrame(ser).sort_index(), check


def metrics(res, events, trade_stats):
    ts = trade_stats(events)
    out = {k: res[k] for k in ("monthly_5y", "monthly_dev4", "monthly_last_year", "dd_4h", "dd_1m", "gate_dd", "losing_years")}
    dev_years = [y["monthly_pct"] for y in res["yearly"][:4]]
    out["yearly_monthly"] = [y["monthly_pct"] for y in res["yearly"]]
    out["worst_dev_year_monthly"] = min(dev_years)
    out["losing_dev_years"] = sum(1 for y in res["yearly"][:4] if y["net_pct"] < 0)
    out["win_book_dev"], out["win_book_hidden"] = ts.get("dev", {}).get("win_rate"), ts.get("_hidden", {}).get("win_rate")
    out["trades_book_dev"], out["trades_book_hidden"] = ts.get("dev", {}).get("trades"), ts.get("_hidden", {}).get("trades")
    rungs = [(pd.Timestamp(e["t"]), float(e["ret"])) for e in events if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and "ret" in e]
    for key, lo, hi, part in (("dev", DEV0, HID0, "dev"), ("hidden", HID0, pd.Timestamp("2100-01-01", tz="UTC"), "_hidden")):
        rr = [r for t, r in rungs if lo <= t < hi]  # as backend.history_tm.build: rungs by exit time, engine net return
        nb, wb = ts.get(part, {}).get("trades") or 0, ts.get(part, {}).get("win_rate") or 0.0
        n = nb + len(rr)
        out[f"win_all_{key}"] = round((wb * nb + sum(r > 0 for r in rr)) / n, 4) if n else None
        out[f"rungs_{key}"] = len(rr)
    st = res["stats"]
    out["stats"] = {k: st.get(k) for k in ("fills", "stops", "tps", "limit_exits", "rungs", "rung_stops", "rung_tps", "fill_minute_stops",
                                           "fees", "funding", "liq")}
    out["n_events"] = len(events)
    return out


def rows_for(pipe, fr):
    lat = 5 if pipe == "v321" else 10
    f1, t2, t5 = dict(sleeve_fill_minute_stop=True), dict(fill_through_bps=2.0), dict(fill_through_bps=5.0)
    s50, s100, lx = dict(stop_slip=0.5), dict(stop_slip=1.0), dict(timeout_exit_minute=lat)
    pess = {**f1, **t2, **s50, **lx}
    rows = {"base": {}, "F1": f1, "T2": t2, "T5": t5, "S50": s50, "S100": s100, f"L{lat}": lx, "FUND": dict(funding_rates=fr),
            "PESS": pess, "PESS+FUND": {**pess, "funding_rates": fr}}
    if pipe == "v321":  # extra bot-latency rows (added after the L5 row showed a cliff): a bot exiting 1 minute after the close
        rows["L1"] = dict(timeout_exit_minute=1)
        rows["PESS_L1"] = {**f1, **t2, **s50, "timeout_exit_minute": 1}
    return rows


def run_pipe(pipe, fr, fcheck):
    t0 = time.time()
    eu, v221, books, opens, prep, kw, trade, cols, dev4 = setup(pipe)
    out = dict(pipeline=pipe, name=NAMES[pipe], research_dev4=dev4, funding_check=fcheck,
               settings=dict(sleeve=kw.get("sleeve", True), sleeve_stop_mode=kw.get("sleeve_stop_mode", "touch"),
                             rungs=list(kw.get("rungs", eu.RUNGS)), win_start=5), rows={})
    for name, extra in rows_for(pipe, fr).items():
        events = []
        res = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, **kw, **extra)
        if name == "base" and abs(res["monthly_dev4"] - dev4) > 0.01:
            raise RuntimeError(f"{pipe}: base replay dev4 {res['monthly_dev4']} != research {dev4}")
        out["rows"][name] = dict(metrics(res, events, v221.v216.v213.trade_stats),
                                 hooks={k: (v if k != "funding_rates" else "binance_actual_signed") for k, v in extra.items()})
        r = out["rows"][name]
        print(f"{pipe} {name:10s} 5y {r['monthly_5y']:6.3f} dev4 {r['monthly_dev4']:6.3f} last {r['monthly_last_year']:6.3f} "
              f"DD {r['gate_dd']:5.2f} worst {r['worst_dev_year_monthly']:6.3f} win {r['win_book_dev']}/{r['win_all_dev']} "
              f"({time.time() - t0:.0f}s)", flush=True)
    out["seconds"] = round(time.time() - t0, 1)
    (OUT / f"result_{pipe}.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def merge():
    res = {p: json.loads((OUT / f"result_{p}.json").read_text()) for p in PIPES if (OUT / f"result_{p}.json").exists()}
    recs = []
    for p, d in res.items():
        for row, r in d["rows"].items():
            recs.append(dict(pipeline=p, name=d["name"], row=row, **{k: r[k] for k in (
                "monthly_5y", "monthly_dev4", "monthly_last_year", "gate_dd", "losing_years", "worst_dev_year_monthly",
                "win_book_dev", "win_book_hidden", "win_all_dev", "win_all_hidden")}))
    pd.DataFrame(recs).to_csv(OUT / "engine_stress_table.csv", index=False)
    (OUT / "engine_stress.json").write_text(json.dumps(dict(
        created="2026-10-03", engine="research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py",
        data_range="live 2021-09-24 .. 2026-09-23 (five anchors; the most recent year is report-only)",
        costs="maker 0.0002 / taker 0.00055; funding adverse 0.0001/8h on longs except FUND rows (actual signed Binance funding)",
        pipelines=res), indent=1, default=str))
    print(pd.DataFrame(recs).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipes", nargs="*", default=[])
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    if a.pipes:
        fr, fcheck = load_funding(["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"])
        for p in a.pipes:
            run_pipe(p, fr, fcheck)
    if a.merge:
        merge()
