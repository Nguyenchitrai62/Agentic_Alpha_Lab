"""Paper trade plan of ONE clock-shifted sub-book of the multi-phase BOT pipeline R2-4P (registry v376) - research output only, no orders.

R2-4P = the v321 R2 BOT strategy run as four sub-books on 4h clocks shifted by s = 0 / 1 / 2 / 3 hours (holding bars start at
T = k * 4h + s h UTC: 00/04/08.., 01/05/09.., 02/06/10.., 03/07/11..), each with 1/4 of the capital, never rebalanced
(research/parallel/rounds/parallel-20260906-r2/v376: dev4 5.24 %/month, most recent year 3.90, conservative DD 18.8 on that year).
This script produces the plan of the phase-s sub-book in the SAME JSON format as scripts/forward_trade.py (coins with state / order /
position / dips, events, equity_curve, net_return_pct, decision_bar, next_decision, freeze ...), reusing forward_trade.py / forward_v205.py.
Differences from the standard plan (= research/diagnostics/phase_offset_full + phase_agents, the v376 harness):
  - engine inputs on the shifted grid: decision rows t = T - 4h on the phase-s lattice; bar open = the first 1m open of the shifted bar
    (Binance 1h kline opens for the history, the 1m minute-0 open wherever 1m klines are loaded); sigma_4h from those shifted opens
    (rolling 360 bars, min 120) - forward_v205.build_prep on the shifted grid;
  - books: the standard book rows (live: forward_v205.live_books 0.8 O1 + 0.2 CB, as forward_trade does for v321_R2) forward-filled to the
    shifted decision times: the book of shifted row t_s = the latest standard row r <= t_s (r is published at r + 4h + a few minutes and
    used at t_s + 4h + 5 min >= r + 5h, so it exists);
  - R2 dip agents: forward_trade.g2_hooks with the frozen v321 models, state at the close of minute 0 of the SHIFTED bar (LiveState fed
    with the shifted opens; hour feature = the shifted bar's hour, as the v376 tables);
  - funding: the adverse long funding is paid on the holding bar that CONTAINS a settlement 00/08/16 UTC (phase_offset_full.settle_flags;
    identical to the standard rule at s = 0).
Paper start (configs frozen 2026-10-04 ~00:30 UTC, at implementation): the first shifted bar of every phase after the implementation
window, i.e. 2026-10-04 04:00 / 05:00 / 06:00 / 07:00 UTC for s = 0 / 1 / 2 / 3 (PHASE_START).

  python scripts/forward_trade_phase.py --candidate v321_R2 --phase 1          # -> artifacts/research/advisor_shadow/trade_plan_v376_s1.json
  python scripts/forward_trade_phase.py --phase 2 --research-books --from 2025-07-01T02:00Z --to 2025-09-20T02:00Z --minutes archive
      # replay check on known data: research books + the per-phase research agent table (tests/test_forward_trade_phase.py)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT_DIR = ROOT / "artifacts/research/advisor_shadow"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
PHASES = (0, 1, 2, 3)
PHASE_START = {s: pd.Timestamp("2026-10-04T04:00:00Z") + pd.Timedelta(hours=s) for s in PHASES}
PIPELINE_ID = "v376"
WARMUP = pd.Timedelta(days=90)        # engine grid before the first traded bar (vol target / sigma warm-up), as forward_trade
OPEN_HISTORY = pd.Timedelta(days=200)  # shifted bar opens for the agents' state (v295 LiveState: sigma 360 + vol regime 540 bars)
K1_HISTORY = pd.Timedelta(days=2)      # 1m klines before the first traded bar (sp30 / 24h high of the agents' state)
CANDIDATES = {"v321_R2": dict(
    agents="v321_r2_dip_agents",
    policy={"sleeve_risk_budget": 0.26, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0,
            "name": "v376 R2-4P sub-book: v321 R2 (CB + dip ladder 2.5/3/3.5/4/5 sigma, size + TP agents, budget 0.26, C4 rules) on a shifted 4h clock"},
    pipeline="v376 R2-4P: R2 on four 4h clocks shifted 0/1/2/3 h, 1/4 capital each (this file = one sub-book)")}
RESEARCH_TABLES = (ROOT / "research/diagnostics/phase_agents/tables", RD / "v376/tables_hidden")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ shifted grid helpers (no network)
def phase_floor(t, s: int) -> pd.Timestamp:
    """Start of the phase-s 4h bar containing t (bars start at k * 4h + s h UTC)."""
    sh = pd.Timedelta(hours=s)
    return (pd.Timestamp(t) - sh).floor("4h") + sh


def on_phase(t, s: int) -> bool:
    return phase_floor(t, s) == pd.Timestamp(t)


def shifted_grid(start, last_t, s: int) -> pd.DatetimeIndex:
    """Decision rows of the phase-s engine: from start - 90 days to last_t, every 4h on the phase-s lattice (holding bar = row + 4h)."""
    first = phase_floor(pd.Timestamp(start) - WARMUP, s)
    return pd.date_range(first, phase_floor(last_t, s), freq="4h")


def settle_flags(idx: pd.DatetimeIndex) -> np.ndarray:
    """True when a funding settlement (00/08/16 UTC) lies in the holding bar (idx + 4h, idx + 8h] (= phase_offset_full.settle_flags)."""
    end = idx + pd.Timedelta(hours=8)
    return np.asarray(end.floor("8h") > idx + pd.Timedelta(hours=4))


def books_on_grid(std_books: pd.DataFrame, grid: pd.DatetimeIndex) -> pd.DataFrame:
    """Standard-grid book rows -> the shifted decision rows. First exactly as forward_trade on the standard grid (reindex + ffill + 0),
    then the latest standard row r <= t_s for every shifted row t_s (identity at s = 0)."""
    std_grid = pd.date_range(grid[0].floor("4h"), grid[-1].floor("4h"), freq="4h")
    std = std_books.reindex(std_grid).ffill().fillna(0.0)
    return std.reindex(grid, method="ffill").fillna(0.0)[SYMS]


def opens_from_minutes(k1: dict, s: int) -> pd.DataFrame:
    """Shifted bar opens = the 1m open of minute 0 of every phase-s bar (NaN where that minute is missing)."""
    out = {}
    for sym in SYMS:
        o = k1[sym]["open"]
        t = o.index
        out[sym] = o[(t == phase_floor_index(t, s))]
    return pd.DataFrame(out).sort_index()


def phase_floor_index(t: pd.DatetimeIndex, s: int) -> pd.DatetimeIndex:
    sh = pd.Timedelta(hours=s)
    return (t - sh).floor("4h") + sh


def opens_from_hours(k1h: dict, s: int) -> pd.DataFrame:
    """Shifted bar opens from 1h klines: the open of the 1h kline that starts the phase-s bar (= its first 1m open)."""
    out = {}
    for sym in SYMS:
        o = k1h[sym]["open"]
        out[sym] = o[((o.index.hour - s) % 4 == 0)]
    return pd.DataFrame(out).sort_index()


def merge_opens(op_h: pd.DataFrame, op_m: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """1h-kline opens overwritten by the 1m minute-0 opens where both exist; returns the comparison (data check)."""
    both = op_h.index.intersection(op_m.index)
    a, b = op_h.loc[both], op_m.loc[both]
    rel = (a / b - 1).abs().to_numpy()
    chk = {"bars_compared": int(len(both)), "max_rel_diff_1h_vs_1m": float(np.nanmax(rel)) if rel.size and np.isfinite(rel).any() else None}
    out = op_h.combine_first(op_m)
    out.update(op_m)
    return out.sort_index(), chk


# ------------------------------------------------------------------ data
def market_rest(start, now, s: int):
    """Public Binance USD-M klines: 1h (200 days, for the shifted opens) + 1m (from start - 2 days); coverage as forward_v205.market."""
    from agentic_alpha_lab.data.binance_usdm import fetch_klines
    from agentic_alpha_lab.data.coverage import require_closed_coverage
    import requests
    sess = requests.Session()
    k1h, k1 = {}, {}
    h0, m0 = pd.Timestamp(start) - OPEN_HISTORY, pd.Timestamp(start) - K1_HISTORY
    for sym in SYMS:
        a = fetch_klines(sym, "1h", h0.to_pydatetime(), now.to_pydatetime(), session=sess)
        require_closed_coverage(a, h0, now, "1h")
        a["open_time"] = pd.to_datetime(a["open_time"], utc=True)
        k1h[sym] = a.drop_duplicates("open_time").set_index("open_time")[["open"]].astype(float)
        m = fetch_klines(sym, "1m", m0.to_pydatetime(), now.to_pydatetime(), session=sess)
        require_closed_coverage(m, m0, now, "1min")
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        k1[sym] = m.drop_duplicates("open_time").set_index("open_time")[["open", "high", "low", "close"]].astype(float)
    opens, chk = merge_opens(opens_from_hours(k1h, s), opens_from_minutes(k1, s))
    return opens, k1, chk


def market_archive(start, now, s: int):
    """Replay data from the local public 1m archive (data/raw/*_intraday_20260924, as research/diagnostics/phase_offset_dips.minutes)."""
    t0, t1 = pd.Timestamp(start) - OPEN_HISTORY, pd.Timestamp(now)
    k1 = {}
    for sym in SYMS:
        d = ROOT / ("data/raw/btc_intraday_20260924" if sym == "BTCUSDT" else "data/raw/majors_intraday_20260924")
        parts = []
        for y in range(t0.year, t1.year + 1):
            f = d / (f"klines_1m_{y}.parquet" if sym == "BTCUSDT" else f"{sym}_1m_{y}.parquet")
            if f.exists():
                parts.append(pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]))
        m = pd.concat(parts)
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
        k1[sym] = m[(m.index >= t0) & (m.index < t1)].astype(float)
    opens = opens_from_minutes(k1, s)
    m0 = pd.Timestamp(start) - K1_HISTORY
    k1 = {sym: m[m.index >= m0] for sym, m in k1.items()}
    return opens, k1, {"source": "archive (opens = 1m minute-0 opens)"}


# ------------------------------------------------------------------ agents
def table_hooks(path, grid, cur_bar, rungs):
    """Research mode: the per-phase walk-forward agent table (T, sym, rung, size, tp) keyed by the shifted holding bar (as history_tm)."""
    tab = pd.read_parquet(path)
    keys = [(pd.Timestamp(t), sy, int(r)) for t, sy, r in zip(tab["T"], tab["sym"], tab["rung"])]
    lsz, ltp = dict(zip(keys, tab["size"].astype(float))), dict(zip(keys, tab["tp"].astype(float)))

    def size_hook(i, a, r, f):
        return lsz.get((grid[i] + pd.Timedelta(hours=4), SYMS[a], r), 1.0)

    def tp_hook(i, a, r, f):
        return ltp.get((grid[i] + pd.Timedelta(hours=4), SYMS[a], r), 1.0)
    cur = {sy: {str(k): {"size": lsz.get((cur_bar, sy, r), 1.0), "tp": ltp.get((cur_bar, sy, r), 1.0)} for r, k in enumerate(rungs)} for sy in SYMS}
    return size_hook, tp_hook, cur


def default_table(s: int, t) -> Path:
    for d in RESEARCH_TABLES:
        p = d / f"r2_table_s{s}.parquet"
        if p.exists() and pd.Timestamp(pd.read_parquet(p, columns=["T"])["T"].max()) >= pd.Timestamp(t):
            return p
    return RESEARCH_TABLES[-1] / f"r2_table_s{s}.parquet"


# ------------------------------------------------------------------ the plan
def build(phase: int, start, now, candidate="v321_R2", research=False, minutes="rest", table=None, policy=None) -> dict:
    """Engine replay of the phase-s sub-book from `start` to `now` -> the plan dict (+ '_internal' with grid / equity / events / data check)."""
    s = int(phase)
    start, now = pd.Timestamp(start), pd.Timestamp(now)
    if not on_phase(start, s):
        raise ValueError(f"start {start} is not a phase-{s} bar start (bars start at k * 4h + {s} h UTC)")
    ft = _load("forward_trade_ph", ROOT / "scripts/forward_trade.py")
    fw = _load("forward_v205_ph", ROOT / "scripts/forward_v205.py")
    eu = _load("engine_user_ph", RD / "engine_user/engine_user.py")
    v212 = _load("v212_ph", RD / "v212/v212_trade_scaling.py")
    cfg = CANDIDATES[candidate]
    p = dict(ft.DEFAULT)
    p.update(policy or {})
    p.update(cfg["policy"])  # the candidate's audited rules win (as forward_trade's per-candidate overrides)
    books = fw.research_books_d2(eu)
    books_src = "research books (replay check)"
    if not research:  # 0.8 x the O1 advisor rows + 0.2 x the live Coinbase member (rows present in both), as forward_trade v321_R2
        lo1, lcb = fw.live_books("v240_O1"), fw.live_books("v285_CB")
        common = lo1.index.intersection(lcb.index)
        lb = 0.8 * lo1.loc[common] + 0.2 * lcb.loc[common]
        books = pd.concat([books[books.index < lb.index.min()] if len(lb) else books, lb]).sort_index()
        books_src = "standard live rows (0.8 v240_O1 + 0.2 v285_CB) forward-filled to the shifted decision times"
    opens, k1, data_chk = (market_archive if minutes == "archive" else market_rest)(start, now, s)
    cur_bar = phase_floor(now, s)                 # shifted holding bar in progress
    last_t = cur_bar - pd.Timedelta(hours=4)      # its decision row
    grid = shifted_grid(start, last_t, s)
    books = books_on_grid(books, grid)
    prep = fw.build_prep(opens, k1, grid)
    prep["settle"] = settle_flags(grid)           # adverse long funding on the bar that contains a settlement
    last_px = np.array([k1[sy]["close"].iloc[-1] for sy in SYMS])
    # the bar in progress: its open is the first 1m open; it ends "now" at the last price (missing minutes hold it), as forward_trade
    prep["o1"][-1] = prep["O"][-1, 0]
    if len(grid) > 1:
        prep["o2"][-2] = prep["O"][-1, 0]
    prep["o2"][-1] = last_px
    eu.v110.START, eu.v110.END = start - pd.Timedelta(hours=4), pd.Timestamp("2100-01-01", tz="UTC")
    trade = dict(v212.T2, max_adds=99, theta=p["theta_open"], k_off=p["k_off"], be_k=p["be_k"], book_mult=p["book_mult"],
                 policy=ft.grid_policy(p), **({"n_valid": p["n_valid"]} if "n_valid" in p else {}))
    events, state, bars, cap = [], {}, [], {}

    def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(eq=eq, eq_min=eq_min, eq_max=eq_max, stats=stats)
        return {}
    eu.summarize = grab
    kw = dict(fw.KW, sleeve_risk_budget=p["sleeve_risk_budget"], size_mult=p["size_mult"],
              **{k: p[k] for k in ("sleeve_stop_mode", "sleeve_backstop", "m_sleeve_sl", "sleeve", "m_sl", "m_tp") if k in p})
    ga_path = ROOT / f"scripts/{cfg['agents']}.py"
    rungs = _load(f"{cfg['agents']}_rungs_ph", ga_path).RUNGS
    if research:
        tab = Path(table) if table else default_table(s, cur_bar)
        size_hook, tp_hook, dip_size = table_hooks(tab, grid, cur_bar, rungs)
        data_chk["agent_table"] = str(tab.relative_to(ROOT)) if tab.is_relative_to(ROOT) else str(tab)
    else:  # frozen agents, decided once at the shifted bar open (state at the close of its minute 0)
        size_hook, tp_hook, dip_size = ft.g2_hooks(grid, cur_bar, start, now, cfg["agents"], market=(opens, k1))
    kw["sleeve_fill_size"], kw["sleeve_tp"], kw["rungs"] = size_hook, tp_hook, rungs
    eu.simulate(books, opens.reindex(grid), prep, trade=trade, win_start=5, events=events, bars=bars, state_out=state, **kw)
    events = [e for e in events if e["t"] <= now]
    dips = ft.current_dips(eu, prep, bars, events, p, kw, dip_size, cur_bar)
    live = np.asarray(grid >= start - pd.Timedelta(hours=4))
    eq = cap["eq"][live]
    coins = {}
    for j, sy in enumerate(SYMS):
        c = {"symbol": sy, "price": float(last_px[j]), "target_weight": float(books[sy].iloc[-1])}
        q = float(state["qty"][j])
        if q != 0:
            side = 1 if q > 0 else -1
            c["state"] = "position"
            c["position"] = {"side": "LONG" if side > 0 else "SHORT", "weight": abs(q) * float(last_px[j]),
                             "avg_entry": float(state["entry"][j]), "sl": float(state["sl"][j]), "tp": float(state["tp"][j]),
                             "break_even": bool(state["be"][j]), "opened": str(grid[int(state["open_i"][j])] + pd.Timedelta(hours=4))
                             if state["open_i"][j] >= 0 else None,
                             "upnl_pct": 100 * side * (float(last_px[j]) / float(state["entry"][j]) - 1)}
            if state["ak"][j] != 0:
                kind = "add" if state["ak"][j] > 0 else ("close" if state["aw"][j] >= 1.0 else "reduce")
                c["order"] = {"kind": kind, "side": "BUY" if state["ak"][j] * side > 0 else "SELL", "price": float(state["apx"][j]),
                              "amount": float(state["aw"][j]), "valid_until": str(grid[min(int(state["aexp"][j]) - 1, len(grid) - 1)] + pd.Timedelta(hours=8))}
        elif state["side"][j] != 0:
            c["state"] = "pending"
            c["order"] = {"kind": "open", "side": "BUY" if state["side"][j] > 0 else "SELL", "price": float(state["px"][j]),
                          "weight": float(state["w"][j]), "issued": str(grid[int(state["issued"][j])] + pd.Timedelta(hours=4)),
                          "valid_until": str(grid[min(int(state["exp"][j]) - 1, len(grid) - 1)] + pd.Timedelta(hours=8)),
                          "sl_if_filled": float(state["px"][j] * (1 - np.sign(state["side"][j]) * float(kw.get("m_sl", 4.0)) * state["psd"][j])),
                          "tp_if_filled": float(state["px"][j] * (1 + np.sign(state["side"][j]) * float(kw.get("m_tp") or 2 * kw.get("m_sl", 4.0)) * state["psd"][j]))}
        else:
            c["state"] = "flat"
        c["dips"] = dips.get(sy, [])
        c["dip_size"] = dip_size.get(sy)
        coins[sy] = c
    ret = float(eq[-1] - 1) if len(eq) else 0.0
    plan = {"pipeline": cfg["pipeline"], "pipeline_id": PIPELINE_ID, "candidate": candidate, "phase": s, "phase_offset_h": s,
            "grid": f"4h bars starting at {s:02d}/{s + 4:02d}/{s + 8:02d}/.. UTC", "capital_share": 0.25,
            "policy": p, "freeze": str(start), "generated_at": now.isoformat(),
            "decision_bar": str(cur_bar), "next_decision": str(cur_bar + pd.Timedelta(hours=4, minutes=5)),
            "net_return_pct": round(100 * ret, 3), "coins": coins, "books_source": books_src, "data_check": data_chk,
            "events": [dict(t=str(e["t"]), symbol=e["symbol"], kind=e["kind"], side=e["side"], price=round(e["price"], 6),
                            weight=round(e.get("weight", 0.0), 5), why=e.get("why"), agent=e.get("agent"),
                            **{k: e[k] for k in ("sl", "tp", "issued_bars_ago", "ret", "rung") if k in e}) for e in events if e["t"] >= start],
            "bars": [dict(t=str(b["t"]), **{k: [None if not np.isfinite(x) else round(float(x), 8) for x in b[k]]
                                           for k in ("target", "open", "qty", "entry", "sl", "tp", "pending")})
                     for b in bars if b["t"] >= start],
            "equity_curve": [(str(t + pd.Timedelta(hours=8)), round(float(v), 6)) for t, v in zip(grid[live], eq)],
            "rules": f"phase +{s}h sub-book of R2-4P (1/4 capital, never rebalanced): limit entries/adjustments/exits valid 8h, no fill in the "
                     "first 5 minutes after the shifted 4h close, SL market / TP limit on every position, break-even at +2 sigma_d, R2 dip "
                     "ladder (5m-close bot stop at 4 sigma + 8-sigma native backstop), Bybit fees, adverse funding on the bar containing a "
                     "settlement. Research output only."}
    plan["_internal"] = dict(grid=grid, eq=cap["eq"], eq_min=cap["eq_min"], events=events, stats=cap["stats"], books=books, prep=prep)
    return plan


def waiting_plan(phase: int, start, now, candidate="v321_R2") -> dict:
    """Before the phase's first traded bar: an empty plan that says when trading starts (as forward_trade)."""
    cfg = CANDIDATES[candidate]
    return {"pipeline": cfg["pipeline"], "pipeline_id": PIPELINE_ID, "candidate": candidate, "phase": phase, "phase_offset_h": phase,
            "capital_share": 0.25, "policy": cfg["policy"], "freeze": str(start), "generated_at": now.isoformat(),
            "decision_bar": str(phase_floor(now, phase)), "next_decision": str(start + pd.Timedelta(minutes=5)), "net_return_pct": 0.0,
            "coins": {sy: {"symbol": sy, "state": "flat", "note": "chưa tới giờ bắt đầu", "dips": []} for sy in SYMS},
            "events": [], "bars": [], "equity_curve": []}


def out_path(phase: int) -> Path:
    return OUT_DIR / f"trade_plan_{PIPELINE_ID}_s{phase}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default="v321_R2", choices=sorted(CANDIDATES))
    ap.add_argument("--phase", type=int, required=True, choices=PHASES, help="clock shift in hours (bars start at k * 4h + phase h UTC)")
    ap.add_argument("--from", dest="start", default=None, help="first traded holding bar (default PHASE_START[phase])")
    ap.add_argument("--to", dest="now", default=None, help="replay 'now' (default: the current time)")
    ap.add_argument("--policy", default=None, help="JSON with policy parameters (as forward_trade; the candidate's rules override)")
    ap.add_argument("--research-books", action="store_true", help="replay check: research books + the per-phase research agent table")
    ap.add_argument("--minutes", default="rest", choices=["rest", "archive"], help="1m source (archive = local public archive, replay only)")
    ap.add_argument("--table", default=None, help="research agent table (default: phase_agents / v376 tables_hidden r2_table_s<phase>)")
    ap.add_argument("--out", default=None, help="output path (default artifacts/research/advisor_shadow/trade_plan_v376_s<phase>.json)")
    args = ap.parse_args()
    s = args.phase
    start = pd.Timestamp(args.start) if args.start else PHASE_START[s]
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    now = pd.Timestamp(args.now) if args.now else pd.Timestamp(datetime.now(timezone.utc))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    dest = Path(args.out) if args.out else out_path(s)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if now < start:
        plan = waiting_plan(s, start, now, args.candidate)
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(plan, indent=1), encoding="utf-8")
        tmp.replace(dest)
        print(f"trade plan v376 phase {s}: trading starts at {start}")
        return
    policy = json.loads(Path(args.policy).read_text()) if args.policy else None
    plan = build(s, start, now, args.candidate, research=args.research_books, minutes=args.minutes, table=args.table, policy=policy)
    plan.pop("_internal")
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(plan, indent=1, default=str), encoding="utf-8")
    tmp.replace(dest)  # atomic: the backend never reads a half-written plan
    print(f"trade plan v376 phase {s} {now:%Y-%m-%d %H:%M} UTC (bar {plan['decision_bar']}):",
          {sy: c["state"] for sy, c in plan["coins"].items()}, f"paper net {plan['net_return_pct']}%")


if __name__ == "__main__":
    main()
