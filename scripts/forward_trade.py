"""Live trade plan + prospective paper trading of the executable TRADE MODE pipeline (research output only - no orders).

The v205 books (research books until the first prospective advisor row, then the logged live rows) drive the engine_user trade
mode with a trader policy (default: the v216 grid trader; `--policy configs/trade_policy.json` for a learned parameter set).
The engine replays every holding bar from FREEZE up to the bar in progress (its missing minutes are held at the last price, so
nothing after `now` can fill), which gives, per coin, the resting order, the open position with its current SL/TP and any resting
add / reduce / exit order - i.e. exactly what a trader or a bot should have on the exchange right now - plus the event log and the
paper equity since FREEZE.

  python scripts/forward_trade.py                # -> artifacts/research/advisor_shadow/trade_plan.json
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
FREEZE = pd.Timestamp("2026-09-28T08:00:00Z")  # first traded holding bar of the deployed rules (v218 D2, frozen 2026-09-28 ~05 UTC)
OUT = ROOT / "artifacts/research/advisor_shadow/trade_plan.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
DEFAULT = dict(name="v218_D2 (v216 grid trader + dip sleeve budget 0.15, rung x1.75)", theta_open=0.05, k_off=0.25, b_abs=0.03,
               b_rel=0.40, cool=6, be_k=2.0, book_mult=1.0, sleeve_risk_budget=0.15, size_mult=1.75)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CS_START = pd.Timestamp("2026-09-30T00:00:00Z")  # v295 CS paper window (first bar after deployment)


def cs_size_hook(grid, cur_bar, start, now):
    """sleeve_fill_size hook of the v295 CS pipeline + the current bar's size per coin and rung (for the plan)."""
    from agentic_alpha_lab.data.binance_usdm import fetch_klines
    from agentic_alpha_lab.data.coverage import require_closed_coverage
    import requests
    sa = _load("v295_size_agent_tm", ROOT / "scripts/v295_size_agent.py")
    frozen = sa.load()
    sess = requests.Session()
    o4, k1 = {}, {}
    for s in SYMS:
        a = fetch_klines(s, "4h", (start - pd.Timedelta(days=200)).to_pydatetime(), now.to_pydatetime(), session=sess)
        require_closed_coverage(a, start - pd.Timedelta(days=200), now, "4h")
        a["open_time"] = pd.to_datetime(a["open_time"], utc=True)
        o4[s] = a.set_index("open_time")["open"].astype(float)
        m = fetch_klines(s, "1m", (start - pd.Timedelta(days=2)).to_pydatetime(), now.to_pydatetime(), session=sess)
        require_closed_coverage(m, start - pd.Timedelta(days=2), now, "1min")
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        k1[s] = m.drop_duplicates("open_time").set_index("open_time")[["open", "high", "low", "close"]].astype(float)
    o4 = pd.DataFrame(o4)
    if cur_bar not in o4.index:  # the bar in progress: its open is the first 1m open
        o4.loc[cur_bar] = [float(k1[s]["open"].get(cur_bar, np.nan)) for s in o4.columns]
        o4 = o4.sort_index()
    ls = sa.LiveState(o4, k1)
    cache = {}

    def mult(s, T, r):
        key = (s, T, r)
        if key not in cache:
            x = ls.features(s, T, r, 0)
            cache[key] = sa.multiplier(x, frozen) if T >= start else 1.0
        return cache[key]

    def hook(i, a, r, f):
        return mult(SYMS[a], grid[i] + pd.Timedelta(hours=4), r)
    cur = {s: {str(k): mult(s, cur_bar, r) for r, k in enumerate(sa.RUNGS)} for s in SYMS}
    return hook, cur


G2_START = pd.Timestamp("2026-09-30T00:00:00Z")  # v301 G2 paper window (first bar after its deployment)
R2_START = pd.Timestamp("2026-10-03T00:00:00Z")  # v321 R2 paper window (first bar after its deployment)
M1_START = pd.Timestamp("2026-10-03T04:00:00Z")  # v315 M1 MANUAL paper window (first bar after its deployment)
M3_START = pd.Timestamp("2026-10-03T08:00:00Z")  # v342 M3 MANUAL paper window (first bar after its deployment)


def live_state(start, now, cls=None):
    """4h opens (200 days) + 1m klines (2 days) of the majors -> v295 LiveState (shared by the CS and G2 agents)."""
    from agentic_alpha_lab.data.binance_usdm import fetch_klines
    from agentic_alpha_lab.data.coverage import require_closed_coverage
    import requests
    sa = _load("v295_size_agent_ls", ROOT / "scripts/v295_size_agent.py")
    sess = requests.Session()
    o4, k1 = {}, {}
    for s in SYMS:
        a = fetch_klines(s, "4h", (start - pd.Timedelta(days=200)).to_pydatetime(), now.to_pydatetime(), session=sess)
        require_closed_coverage(a, start - pd.Timedelta(days=200), now, "4h")
        a["open_time"] = pd.to_datetime(a["open_time"], utc=True)
        o4[s] = a.set_index("open_time")["open"].astype(float)
        m = fetch_klines(s, "1m", (start - pd.Timedelta(days=2)).to_pydatetime(), now.to_pydatetime(), session=sess)
        require_closed_coverage(m, start - pd.Timedelta(days=2), now, "1min")
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        k1[s] = m.drop_duplicates("open_time").set_index("open_time")[["open", "high", "low", "close"]].astype(float)
    o4 = pd.DataFrame(o4)
    cur_bar = now.floor("4h")
    if cur_bar not in o4.index:  # the bar in progress: its open is the first 1m open
        o4.loc[cur_bar] = [float(k1[s]["open"].get(cur_bar, np.nan)) for s in o4.columns]
        o4 = o4.sort_index()
    return (cls or sa.LiveState)(o4, k1)


def g2_hooks(grid, cur_bar, start, now, agents="v301_dip_agents"):
    """sleeve_fill_size + sleeve_tp hooks of the v301 G2 (or v321 R2) pipeline + the current bar's size / TP per coin and rung (for the plan)."""
    ga = _load(f"{agents}_tm", ROOT / f"scripts/{agents}.py")
    fz = ga.load()
    ls = live_state(start, now, getattr(ga, "LiveState", None))
    cache = {}

    def dec(s, T, r):
        key = (s, T, r)
        if key not in cache:
            if T < start:
                cache[key] = (1.0, 1.0)
            else:
                x = ls.features(s, T, r, 0)
                cache[key] = (ga.size_multiplier(x, fz), ga.tp_multiple(x, fz))
        return cache[key]

    def size_hook(i, a, r, f):
        return dec(SYMS[a], grid[i] + pd.Timedelta(hours=4), r)[0]

    def tp_hook(i, a, r, f):
        return dec(SYMS[a], grid[i] + pd.Timedelta(hours=4), r)[1]
    cur = {s: {str(k): {"size": dec(s, cur_bar, r)[0], "tp": dec(s, cur_bar, r)[1]} for r, k in enumerate(ga.RUNGS)} for s in SYMS}
    return size_hook, tp_hook, cur


def current_dips(eu, prep, bars, events, p, kw, dip_size, cur_bar):
    """The dip ladder resting in the bar in progress, per coin: what a trader / bot should have on the exchange now (engine rules:
    rungs k x sigma_4h below the bar open, valid from minute 16 to the end of the bar, TP limit, bot stop on 5m closes, native backstop,
    rung size = vol scale x governor x size_mult x SIZE/4/S_REF x alignment with the book x the agent's size)."""
    if not bars:
        return {}
    b = bars[-1]
    o1, sg4 = prep["o1"][-1], prep["sig4"][-1]
    align = kw.get("align") or (1.0, 1.0)
    base_rn = float(b["scale"]) * float(b["governor"]) * float(p.get("size_mult", 1.0)) * eu.SIZE / 4 / eu.S_REF
    m_sl, back = float(p.get("m_sleeve_sl", kw.get("m_sleeve_sl", 5.0))), p.get("sleeve_backstop")
    close_stop = p.get("sleeve_stop_mode", "touch") != "touch"
    out = {}
    for a, s in enumerate(SYMS):
        sg = float(sg4[a])
        if not (np.isfinite(sg) and np.isfinite(o1[a])):
            continue
        tgt = float(b["target"][a])
        rows = []
        for r, k in enumerate(kw.get("rungs", eu.RUNGS)):
            d = (dip_size or {}).get(s, {}).get(str(k))
            m_size = float(d["size"] if isinstance(d, dict) else d) if d is not None else 1.0
            m_tp = float(d["tp"]) if isinstance(d, dict) else 1.0
            lv = float(o1[a]) * (1 - k * sg)
            filled = any(e["kind"] == "rung_fill" and e["symbol"] == s and cur_bar <= e["t"] < cur_bar + pd.Timedelta(hours=4)
                         and abs(float(e.get("rung", -1)) - k) < 1e-9 for e in events)
            rows.append(dict(rung=k, buy_limit=lv, tp=lv * (1 + m_tp * sg), stop=lv * (1 - m_sl * sg), stop_kind="close5" if close_stop else "touch",
                             backstop=lv * (1 - float(back) * sg) if back else None,
                             size_frac=base_rn * (align[0] if tgt > 0 else align[1]) * m_size, agent_size=m_size, agent_tp=m_tp,
                             active_from=str(cur_bar + pd.Timedelta(minutes=16)), active_until=str(cur_bar + pd.Timedelta(minutes=239)),
                             filled=bool(filled)))
        out[s] = rows
    return out


def grid_policy(p):
    def pol(i, a, st):
        if st["pos"] == 0:
            return {"open": p["k_entry"]} if "k_entry" in p else "open"  # MANUAL M1: pullback entry limit k_entry x sigma_4h
        side, tg, w, valid = st["pos"], st["tg"], st["w"], st["valid"]
        if st["sgn"] == -side:
            return {"tighten": 1, "close": 1} if "close" in valid else "tighten"
        if st["sgn"] == 0:
            return "close" if "close" in valid else "hold"
        if st["since_adj"] < p["cool"]:
            return "hold"
        band = max(p["b_abs"], p["b_rel"] * abs(tg))
        diff = abs(tg) - w
        if diff > band and "add" in valid:
            return {"add": diff}
        if -diff > band and "reduce" in valid and w > 0:
            return {"reduce": min(1.0, -diff / w)}
        return "hold"
    return pol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default=None, help="JSON with the policy parameters (default: v216 grid G2)")
    ap.add_argument("--from", dest="start", default=None, help="first traded holding bar (default FREEZE)")
    ap.add_argument("--candidate", default="v151_deploy_v4", choices=["v151_deploy_v4", "v233_T3", "v236_W2", "v240_O1", "v266_B1", "v269_M1", "v285_D2", "v295_CS", "v301_G2", "v321_R2", "v315_M1", "v342_M3"],
                    help="books: v205 (v151_deploy_v4 live rows, default), the v233 T3 or the v236 W2 foundation (their live rows)")
    args = ap.parse_args()
    cand = {"v151_deploy_v4": ("research_books", OUT, "v205 books + trade mode"),
            "v233_T3": ("research_books_t3", OUT.with_name("trade_plan_v233.json"), "v233 T3 books + trade mode"),
            "v236_W2": ("research_books_w2", OUT.with_name("trade_plan_v236.json"), "v236 W2 books (T3 + whale flow) + trade mode"),
            "v240_O1": ("research_books_o1", OUT.with_name("trade_plan_v240.json"), "v240 O1 books (T3 + order-level whale flow) + trade mode"),
            "v266_B1": ("research_books_o1", OUT.with_name("trade_plan_v266.json"),
                        "v266 B1: O1 books + dip stops on 5m closes + 8-sigma native backstop"),
            "v269_M1": ("research_books_o1", OUT.with_name("trade_plan_v269.json"),
                        "v269 M1: O1 books + dip stops on 5m closes at 4 sigma + 8-sigma native backstop"),
            "v285_D2": ("research_books_d2", OUT.with_name("trade_plan_v285.json"),
                        "v285 D2: 0.8 O1 books + 0.2 Coinbase-premium member, C4 dip stops"),
            "v295_CS": ("research_books_d2", OUT.with_name("trade_plan_v295.json"),
                        "v295 CS: CB + learned dip-rung sizing (size agent trained on 35 coins, sized at the bar open)"),
            "v301_G2": ("research_books_d2", OUT.with_name("trade_plan_v301.json"),
                        "v301 G2: CB + learned dip size AND take-profit (agents trained on 35 coins, decided at the bar open), dip budget 0.26"),
            "v321_R2": ("research_books_d2", OUT.with_name("trade_plan_v321.json"),
                        "v321 R2: CB + dip ladder 2.5-5.0 sigma, size + take-profit agents trained on every rung depth (35 coins), budget 0.26"),
            "v315_M1": ("research_books_d2", OUT.with_name("trade_plan_v315.json"),
                        "v315 M1 MANUAL: CB book orders only (no dip ladder), pullback entry limit 0.75 sigma_4h valid 3 bars - for a human"),
            "v342_M3": ("research_books_d2", OUT.with_name("trade_plan_v342.json"),
                        "v342 M3 MANUAL: M1 book x0.75 + two human-placeable dip limits per coin (3.0 / 4.0 sigma, TP + native 8-sigma stop)")}
    rb_name, out_path, pipe_name = cand[args.candidate]
    p = dict(DEFAULT, **(json.loads(Path(args.policy).read_text()) if args.policy else {}))
    # per-pipeline policy overrides from audited research: O1 runs the v247 sleeve stop-risk budget 0.18 (since 2026-09-29)
    # v266 B1 (paper, since 2026-09-29): the same O1 books with dip-rung stops triggered on 5m closes + an 8-sigma native backstop
    p = dict(p, **{"v240_O1": {"sleeve_risk_budget": 0.18, "name": "v218 D2 grid trader + dip sleeve budget 0.18 (v247), rung x1.75"},
                   "v266_B1": {"sleeve_risk_budget": 0.18, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0,
                               "name": "O1 B18 + dip stops on 5m closes + 8-sigma native backstop (v266 B1)"},
                   "v269_M1": {"sleeve_risk_budget": 0.18, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0,
                               "name": "O1 B18 + dip stops on 5m closes at 4 sigma + 8-sigma native backstop (v269 M1)"},
                   "v285_D2": {"sleeve_risk_budget": 0.18, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0,
                               "name": "v285 D2: 0.8 O1 + 0.2 Coinbase-premium member books, C4 rules"},
                   "v295_CS": {"sleeve_risk_budget": 0.18, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0,
                               "name": "v295 CS: CB (v285 D2) + size agent x0.5 / x1 / x1.5 per dip rung, C4 rules"},
                   "v301_G2": {"sleeve_risk_budget": 0.26, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0,
                               "name": "v301 G2: CB + dip size agent + dip take-profit agent, sleeve budget 0.26, C4 rules"},
                   "v321_R2": {"sleeve_risk_budget": 0.26, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0,
                               "name": "v321 R2: CB + dip ladder 2.5/3/3.5/4/5 sigma, size + TP agents (all rung depths), budget 0.26, C4 rules"},
                   "v315_M1": {"sleeve": False, "k_entry": 0.75, "n_valid": 3,
                               "name": "v315 M1 MANUAL: CB book only, pullback entry 0.75 sigma_4h valid 3 bars, target 0.25, cap 2"},
                   "v342_M3": {"k_entry": 0.75, "n_valid": 3, "book_mult": 0.75, "size_mult": 4.375, "sleeve_risk_budget": 0.26,
                               "sleeve_stop_mode": "touch", "m_sleeve_sl": 8.0,
                               "name": "v342 M3 MANUAL: M1 book x0.75 + dip limits 3.0 / 4.0 sigma (R2 agents' size / TP), native 8-sigma touch stop"}}.get(args.candidate, {}))
    # D2's live Coinbase member is logged from 2026-09-29 21 UTC; its paper window starts at the next 4h bar
    start = pd.Timestamp(args.start, tz="UTC") if args.start else {"v285_D2": pd.Timestamp("2026-09-30T00:00:00Z"),
                                                                     "v295_CS": CS_START, "v301_G2": G2_START,
                                                                     "v321_R2": R2_START, "v315_M1": M1_START, "v342_M3": M3_START}.get(args.candidate, FREEZE)
    now = pd.Timestamp(datetime.now(timezone.utc))
    if now < start:  # before the first traded bar: publish an empty plan that says when trading starts
        out_path.write_text(json.dumps({"pipeline": pipe_name, "policy": p, "freeze": str(start), "generated_at": now.isoformat(),
                                   "decision_bar": str(start), "next_decision": str(start + pd.Timedelta(minutes=5)), "net_return_pct": 0.0,
                                   "coins": {s: {"symbol": s, "state": "flat", "note": "chưa tới giờ bắt đầu"} for s in SYMS},
                                   "events": [], "equity_curve": []}, indent=1))
        print("trade plan: trading starts at", start)
        return
    fw = _load("forward_v205_tm", ROOT / "scripts/forward_v205.py")
    eu = _load("engine_user_tm", RD / "engine_user/engine_user.py")
    v212 = _load("v212_tm", RD / "v212/v212_trade_scaling.py")
    books = getattr(fw, rb_name)(eu)
    if args.candidate in ("v285_D2", "v295_CS", "v301_G2", "v321_R2", "v315_M1", "v342_M3"):  # 0.8 x the O1 advisor rows + 0.2 x the live Coinbase member (rows present in both)
        lo1, lcb = fw.live_books("v240_O1"), fw.live_books("v285_CB")
        common = lo1.index.intersection(lcb.index)
        lb = 0.8 * lo1.loc[common] + 0.2 * lcb.loc[common]
    else:
        lb = fw.live_books({"v266_B1": "v240_O1", "v269_M1": "v240_O1"}.get(args.candidate, args.candidate))  # B1 / M1 trade the O1 rows
    books = pd.concat([books[books.index < lb.index.min()] if len(lb) else books, lb]).sort_index()
    opens, k1 = fw.market(start, now)
    cur_bar = now.floor("4h")                   # holding bar in progress
    last_t = cur_bar - pd.Timedelta(hours=4)    # its decision row
    grid = pd.date_range(start - pd.Timedelta(days=90), last_t, freq="4h")
    books = books.reindex(grid).ffill().fillna(0.0)
    prep = fw.build_prep(opens, k1, grid)
    last_px = np.array([k1[s]["close"].iloc[-1] for s in SYMS])
    # the bar in progress: its open is the first 1m open (4h klines only list closed bars); it ends "now" at the last price,
    # and its missing minutes hold that price, so no order can fill after now
    prep["o1"][-1] = prep["O"][-1, 0]
    if len(grid) > 1:
        prep["o2"][-2] = prep["O"][-1, 0]
    prep["o2"][-1] = last_px
    eu.v110.START, eu.v110.END = start - pd.Timedelta(hours=4), pd.Timestamp("2100-01-01", tz="UTC")
    trade = dict(v212.T2, max_adds=99, theta=p["theta_open"], k_off=p["k_off"], be_k=p["be_k"], book_mult=p["book_mult"],
                 policy=grid_policy(p), **({"n_valid": p["n_valid"]} if "n_valid" in p else {}))
    events, state, bars = [], {}, []
    cap = {}

    def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(eq=eq, stats=stats)
        return {}
    eu.summarize = grab
    kw = dict(fw.KW, sleeve_risk_budget=p["sleeve_risk_budget"], size_mult=p["size_mult"],
              **{k: p[k] for k in ("sleeve_stop_mode", "sleeve_backstop", "m_sleeve_sl", "sleeve") if k in p})
    dip_size = None
    if args.candidate == "v295_CS":  # frozen v295 size agent, each rung sized once at the bar open (state at the close of minute 0)
        size_hook, dip_size = cs_size_hook(grid, cur_bar, start, now)
        kw["sleeve_fill_size"] = size_hook
    if args.candidate == "v301_G2":  # frozen v301 size + take-profit agents, decided once at the bar open
        size_hook, tp_hook, dip_size = g2_hooks(grid, cur_bar, start, now)
        kw["sleeve_fill_size"], kw["sleeve_tp"] = size_hook, tp_hook
    if args.candidate == "v321_R2":  # frozen v321 R2 agents (fitted on every rung depth), ladder 2.5 .. 5.0 sigma, decided once at the bar open
        size_hook, tp_hook, dip_size = g2_hooks(grid, cur_bar, start, now, "v321_r2_dip_agents")
        kw["sleeve_fill_size"], kw["sleeve_tp"] = size_hook, tp_hook
        kw["rungs"] = _load("v321_rungs_tm", ROOT / "scripts/v321_r2_dip_agents.py").RUNGS
    if args.candidate == "v342_M3":  # MANUAL M3: the frozen R2 agents decide size / TP of the two bracket dip limits at the bar open
        size_hook, tp_hook, dip_size = g2_hooks(grid, cur_bar, start, now, "manual_dip_agents")
        kw["sleeve_fill_size"], kw["sleeve_tp"] = size_hook, tp_hook
        kw["rungs"] = _load("manual_rungs_tm", ROOT / "scripts/manual_dip_agents.py").RUNGS
    eu.simulate(books, opens.reindex(grid), prep, trade=trade, win_start=5, events=events, bars=bars, state_out=state, **kw)
    events = [e for e in events if e["t"] <= now]
    dips = current_dips(eu, prep, bars, events, p, kw, dip_size, cur_bar) if kw.get("sleeve", True) else {}  # MANUAL: no dip ladder
    live = np.asarray(grid >= start - pd.Timedelta(hours=4))
    eq = cap["eq"][live]
    coins = {}
    for j, s in enumerate(SYMS):
        c = {"symbol": s, "price": float(last_px[j]), "target_weight": float(books[s].iloc[-1])}
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
                          "sl_if_filled": float(state["px"][j] * (1 - np.sign(state["side"][j]) * 4 * state["psd"][j])),
                          "tp_if_filled": float(state["px"][j] * (1 + np.sign(state["side"][j]) * 8 * state["psd"][j]))}
        else:
            c["state"] = "flat"
        coins[s] = c
    ret = float(eq[-1] - 1) if len(eq) else 0.0
    for s_ in SYMS:
        coins[s_]["dips"] = dips.get(s_, [])
        if dip_size is not None:
            coins[s_]["dip_size"] = dip_size.get(s_)
    out = {"pipeline": pipe_name, "policy": p, "freeze": str(start), "generated_at": now.isoformat(),
           "decision_bar": str(cur_bar), "next_decision": str(cur_bar + pd.Timedelta(hours=4, minutes=5)),
           "net_return_pct": round(100 * ret, 3), "coins": coins,
           "events": [dict(t=str(e["t"]), symbol=e["symbol"], kind=e["kind"], side=e["side"], price=round(e["price"], 6),
                           weight=round(e.get("weight", 0.0), 5), why=e.get("why"), agent=e.get("agent"),
                           **{k: e[k] for k in ("sl", "tp", "issued_bars_ago", "ret", "rung") if k in e}) for e in events if e["t"] >= start],
           # per-bar state of the paper window (history page: held position, average entry, live SL / TP, resting order)
           "bars": [dict(t=str(b["t"]), **{k: [None if not np.isfinite(x) else round(float(x), 8) for x in b[k]]
                                          for k in ("target", "open", "qty", "entry", "sl", "tp", "pending")})
                    for b in bars if b["t"] >= start],
           "equity_curve": [(str(t + pd.Timedelta(hours=8)), round(float(v), 6)) for t, v in zip(grid[live], eq)],
           "rules": "limit entries/adjustments/exits valid 8h, no fill in the first 5 minutes after the 4h close, SL market / TP limit "
                    "on every position, break-even at +2 sigma_d, Bybit fees, adverse funding. Research output only."}
    out_path.write_text(json.dumps(out, indent=1, default=str))
    print(f"trade plan {now:%Y-%m-%d %H:%M} UTC:", {s: c["state"] for s, c in coins.items()}, f"paper net {out['net_return_pct']}%")


if __name__ == "__main__":
    main()
