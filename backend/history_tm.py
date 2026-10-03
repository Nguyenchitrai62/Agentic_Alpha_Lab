"""Walk-forward history of the EXECUTABLE trade-mode pipelines (what the site's trade plans actually do), per pipeline.

For each paper pipeline (D2 = v205 books, T3 = v233, W2 = v236, O1 = v240) the audited research books are replayed through
engine_user's trade mode with the deployed settings (v216 G2 grid trader, v218 D2 sleeve settings, minute-5 rule, limit entries /
adjustments / exits, SL market, TP limit, Bybit fees, adverse funding). The engine's events and per-bar state become the three
tables the history page reads, under source = 'tm_<pipeline>':
  orders   one row per discrete trade (first limit fill -> exit) and per dip bid, with the real SL / TP at the exit, the average
           entry, adds, the exit reason (TP / SL / break-even SL / limit close / dip timeout) and the net result after fees
  runs + run_books   per bar and coin: the target, the resting order price, the held position, its average entry and the live SL / TP
  trades   every engine event (fills, adds, reduces, SL moves, stops, take-profits, dip rungs)
  equity   the walk-forward equity curve
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
MAKER, TAKER = 0.0002, 0.00055
H4 = 4 * 3600_000
PIPELINES = {  # pipeline key -> (research-books function in scripts/forward_v205.py, expected dev4 %/month for a sanity check)
    "v266": ("research_books_o1", 6.130),  # O1 + 5m-close dip stops + 8-sigma native backstop (v266 B1)
    "v269": ("research_books_o1", 6.026),  # O1 + 5m-close dip stops at 4 sigma + 8-sigma native backstop (v269 M1)
    "v285": ("research_books_d2", 5.864),  # 0.8 O1 + 0.2 Coinbase-premium member, C4 rules (v285 D2)
    "v295": ("research_books_d2", 6.168),  # CB + v295 size agent (walk-forward multipliers, sized at the bar open)
    "v301": ("research_books_d2", 6.504),  # CB + v301 G2 size + take-profit agents at the bar open, dip budget 0.26
    "v321": ("research_books_d2", 7.079),  # CB + v321 R2: ladder 2.5..5.0 sigma, agents fitted on every rung depth, budget 0.26
    "v315": ("research_books_d2", 2.956),  # MANUAL M1: CB book only (no dip ladder), pullback entry 0.75 sigma_4h, orders valid 3 bars
    "v340": ("research_books_d2", 5.23),  # MANUAL M2: M1 book x0.75 + ONE human-placeable dip limit per coin (3.0 sigma, native 8-sigma stop; v340 RA2)
    "v342": ("research_books_d2", 6.233),
    "v362": ("research_books_d2", 6.392),
    "v367": ("research_books_d2", 6.015),  # MANUAL M5: M4 + loss_act tighten (book win ~0.66; v367 post-hoc goal-1 fitness)   # MANUAL M4: M3 with book SL 5 / TP 10 sigma_d (v362 dev4-selected)   # MANUAL M3: M1 book x0.75 + two human-placeable dip limits (3.0 / 4.0 sigma, native 8-sigma stop)
}
KW_OVERRIDE = {"v240": {"sleeve_risk_budget": 0.18},
               "v266": {"sleeve_risk_budget": 0.18, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0},
               "v269": {"sleeve_risk_budget": 0.18, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0},
               "v285": {"sleeve_risk_budget": 0.18, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0},
               "v295": {"sleeve_risk_budget": 0.18, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0},
               "v301": {"sleeve_risk_budget": 0.26, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0},
               "v321": {"sleeve_risk_budget": 0.26, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0, "m_sleeve_sl": 4.0,
                        "rungs": (2.5, 3.0, 3.5, 4.0, 5.0)},
               "v315": {"sleeve": False},
               "v340": {"sleeve_risk_budget": 0.26, "sleeve_stop_mode": "touch", "m_sleeve_sl": 8.0, "size_mult": 4.375, "rungs": (3.0,)},
               "v342": {"sleeve_risk_budget": 0.26, "sleeve_stop_mode": "touch", "m_sleeve_sl": 8.0, "size_mult": 4.375, "rungs": (3.0, 4.0)},
               "v362": {"sleeve_risk_budget": 0.26, "sleeve_stop_mode": "touch", "m_sleeve_sl": 8.0, "size_mult": 4.375, "rungs": (3.0, 4.0),
                        "m_sl": 5.0, "m_tp": 10.0},
               "v367": {"sleeve_risk_budget": 0.26, "sleeve_stop_mode": "touch", "m_sleeve_sl": 8.0, "size_mult": 4.375, "rungs": (3.0, 4.0),
                        "m_sl": 5.0, "m_tp": 10.0}}
M3_R2_RUNG = {0: 1, 1: 3}  # M3 rung index -> the R2 table's rung index (R2 ladder 2.5 / 3.0 / 3.5 / 4.0 / 5.0)
SIZE_TABLE = ROOT / "artifacts/research/engine_real/v295_size_mult_m0.parquet"  # research/diagnostics/s1_exec/s1_cache.py
G2_TABLE = ROOT / "artifacts/research/engine_real/v301_g2_table_m0.parquet"  # research/diagnostics/g2_exec/g2_cache.py
R2_TABLE = ROOT / "artifacts/research/engine_real/v321_r2_table_m0.parquet"  # research/diagnostics/r2_exec/r2_cache.py


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ms(t) -> int:
    return int(pd.Timestamp(t).value // 1_000_000)


def simulate(pipe: str):
    v221 = _load(f"v221_hist_{pipe}", RD / "v221/v221_grid_hysteresis.py")
    fw = _load(f"forward_v205_hist_{pipe}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    fn, dev4 = PIPELINES[pipe]
    books = getattr(fw, fn)(eu).reindex(books154.index).fillna(0.0)[cols]
    prep = eu.prepare(books154, opens)
    events, bars = [], []
    kw = dict(v221.KW, **KW_OVERRIDE.get(pipe, {}))
    if pipe == "v295":  # walk-forward size multipliers of the v295 size agent (one per holding bar, coin and rung)
        tab = pd.read_parquet(SIZE_TABLE)
        look = {(pd.Timestamp(t), s, int(r)): float(m) for t, s, r, m in zip(tab["T"], tab["sym"], tab["rung"], tab["mult"])}
        idx = books.index
        kw["sleeve_fill_size"] = lambda i, a, r, f: look.get((idx[i] + pd.Timedelta(hours=4), cols[a], r), 1.0)
    if pipe in ("v301", "v321", "v340", "v342", "v362", "v367"):  # walk-forward size + take-profit decisions of the G2 / R2 agents (one per holding bar, coin and rung)
        tab = pd.read_parquet(G2_TABLE if pipe == "v301" else R2_TABLE)
        keys = [(pd.Timestamp(t), s, int(r)) for t, s, r in zip(tab["T"], tab["sym"], tab["rung"])]
        lsz, ltp = dict(zip(keys, tab["size"].astype(float))), dict(zip(keys, tab["tp"].astype(float)))
        idx = books.index
        rmap = M3_R2_RUNG if pipe in ("v340", "v342", "v362", "v367") else {}
        kw["sleeve_fill_size"] = lambda i, a, r, f: lsz.get((idx[i] + pd.Timedelta(hours=4), cols[a], rmap.get(r, r)), 1.0)
        kw["sleeve_tp"] = lambda i, a, r, f: ltp.get((idx[i] + pd.Timedelta(hours=4), cols[a], rmap.get(r, r)), 1.0)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    if pipe in ("v315", "v340", "v342", "v362", "v367"):  # MANUAL M1 / M3: pullback entry limit 0.75 sigma_4h, orders valid 3 bars; in-position grid unchanged
        grid_pol = trade["policy"]
        trade = dict(trade, n_valid=3, policy=lambda i, a, st: {"open": 0.75} if st["pos"] == 0 else grid_pol(i, a, st))
        if pipe == "v367":  # M5: a losing position whose signal goes flat gets its stop tightened instead of a close
            pol5 = trade["policy"]
            trade["policy"] = lambda i, a, st: "tighten" if st["pos"] != 0 and st["sgn"] == 0 and st["upnl"] < 0 else pol5(i, a, st)
        if pipe in ("v340", "v342", "v362", "v367"):  # M2 / M3: book positions x0.75 (signal threshold unscaled), the risk moved to the two dip limits
            trade["book_mult"] = 0.75
    res = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=events, bars=bars, **kw)
    if abs(res["monthly_dev4"] - dev4) > 0.01:
        raise RuntimeError(f"{pipe}: replay dev4 {res['monthly_dev4']} != research {dev4}")
    res["trade_stats"] = v221.v216.v213.trade_stats(events)  # book trades after fees: dev years / most recent year
    return res, events, bars, cols


def build_orders(events: list[dict], open_reason: str = "Đang mở") -> list[tuple]:
    """Discrete trades and dip bids from trade-mode events. Tuple = orders columns (see INSERT below)."""
    out, pos, rung = [], {}, {}
    for e in sorted(events, key=lambda x: x["t"]):
        k, s, t = e["kind"], e["symbol"], _ms(e["t"])
        if k == "rung_fill":
            rung[s] = e
            continue
        if k in ("rung_tp", "rung_sl", "rung_timeout") and s in rung:
            f = rung.pop(s)
            reason = {"rung_tp": "TP", "rung_sl": "SL", "rung_timeout": "Hết giờ"}[k]
            ret = float(e.get("ret", e["price"] / f["price"] - 1))
            fees = MAKER + (MAKER if k == "rung_tp" else TAKER)
            out.append((s, "dip", "LONG", _ms(pd.Timestamp(f["t"]).floor("4h")) - H4, _ms(f["t"]), f["price"], None, None,
                        abs(f["weight"]), 0, t, e["price"], reason, round(100 * (ret - fees), 4), f["price"], 1, "limit"))
            continue
        if k == "book_fill":
            q = abs(e["weight"]) / e["price"]
            side = 1 if e["side"] == "buy" else -1
            ago = int(e.get("issued_bars_ago", 0) or 0)
            sig = _ms(pd.Timestamp(e["t"]).floor("4h")) - H4 - ago * H4
            pos[s] = dict(t=t, sig=sig, side=side, entry=e["price"], qty=q, qin=q, cost=q * e["price"], proceeds=0.0,
                          fees=q * e["price"] * MAKER, adds=0, fills=1, w=abs(e["weight"]), size=abs(e["weight"]), sl=e.get("sl"),
                          tp=e.get("tp"), be=False)
            continue
        o = pos.get(s)
        if o is None:
            continue
        if k == "book_add":
            q = abs(e["weight"]) / e["price"]
            o["qty"] += q; o["qin"] += q; o["cost"] += q * e["price"]; o["fees"] += q * e["price"] * MAKER
            o["adds"] += 1; o["fills"] += 1
            o["w"] += abs(e["weight"]); o["size"] = max(o["size"], o["w"])
        elif k in ("book_reduce", "book_partial"):
            q = min(abs(e["weight"]) / e["price"], o["qty"])
            o["qty"] -= q; o["proceeds"] += q * e["price"]; o["fees"] += q * e["price"] * MAKER
            o["w"] = max(0.0, o["w"] - abs(e["weight"]))
        elif k == "sl_move":
            o["sl"] = e["price"]
            if str(e.get("why", "")).startswith("break-even"):
                o["be"] = True
        elif k in ("book_stop", "book_tp", "book_close"):
            o["proceeds"] += o["qty"] * e["price"]
            o["fees"] += o["qty"] * e["price"] * (TAKER if k == "book_stop" else MAKER)
            net = (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]) / o["cost"]
            if k == "book_stop":
                reason = "SL hoà vốn" if o["be"] else "SL"
            else:
                reason = "TP" if k == "book_tp" else "Đóng limit"
            avg = o["cost"] / o["qin"]
            out.append((s, "book", "LONG" if o["side"] > 0 else "SHORT", o["sig"], o["t"], o["entry"], o["sl"], o["tp"], round(o["size"], 6),
                        o["adds"], t, e["price"], reason, round(100 * net, 4), avg, o["fills"], "limit"))
            pos.pop(s)
    for s, o in pos.items():  # still open
        out.append((s, "book", "LONG" if o["side"] > 0 else "SHORT", o["sig"], o["t"], o["entry"], o["sl"], o["tp"], round(o["size"], 6),
                    o["adds"], None, None, open_reason, None, o["cost"] / o["qin"], o["fills"], "limit"))
    return out


def build(pipe: str, db) -> str:
    res, events, bars, cols = simulate(pipe)
    src = f"tm_{pipe}"
    orders = build_orders(events, open_reason="Hết dữ liệu mô phỏng")  # replay ends with the research data (2026-09-23)
    summary = {k: res[k] for k in ("monthly_5y", "monthly_dev4", "monthly_last_year", "dd_4h", "dd_1m", "gate_dd", "losing_years")}
    summary["yearly"] = [(y["anchor"], y["net_pct"], y["dd_1m_pct"]) for y in res["yearly"]]
    ts = res.get("trade_stats", {})
    summary["win_dev"], summary["win_hidden"] = ts.get("dev", {}).get("win_rate"), ts.get("_hidden", {}).get("win_rate")
    summary["trades_dev"], summary["trades_hidden"] = ts.get("dev", {}).get("trades"), ts.get("_hidden", {}).get("trades")
    # all trades (book + dip rungs): the BOT goal's win rate; rungs counted by exit time, engine net return (fees included)
    dev0, hid0 = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC")
    rungs = [(pd.Timestamp(e["t"]), float(e["ret"])) for e in events if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and "ret" in e]
    for key, lo, hi, part in (("dev", dev0, hid0, "dev"), ("hidden", hid0, pd.Timestamp("2100-01-01", tz="UTC"), "_hidden")):
        rr = [r for t, r in rungs if lo <= t < hi]
        nb, wb = ts.get(part, {}).get("trades") or 0, ts.get(part, {}).get("win_rate") or 0.0
        n = nb + len(rr)
        summary[f"win_all_{key}"] = round((wb * nb + sum(r > 0 for r in rr)) / n, 4) if n else None
        summary[f"rungs_{key}"] = len(rr)
    with db.write() as c:
        c.execute("DELETE FROM run_books WHERE run_id IN (SELECT id FROM runs WHERE source = ?)", (src,))
        for tb in ("runs", "trades", "equity", "orders"):
            c.execute(f"DELETE FROM {tb} WHERE source = ?", (src,))
        c.executemany("INSERT INTO orders(source, symbol, kind, side, signal_t, entry_t, entry_px, sl, tp, size, adds, exit_t, exit_px, "
                      "exit_reason, pnl_pct, avg_px, fills, entry_type) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      [(src,) + o for o in orders])
        now = db.now_ms()
        for b in bars:
            t = _ms(b["t"])
            rid = c.execute("INSERT INTO runs(source, decision_time, pipeline, created_at, scale, governor, gross) VALUES(?,?,?,?,?,?,?)",
                            (src, t, pipe, now, b["scale"], b["governor"], float(np.abs(b["target"]).sum()))).lastrowid
            recs = []
            for j, sym in enumerate(cols):
                w, o, q, ae = b["target"][j], b["open"][j], b["qty"][j], b["entry"][j]
                held = q * o if np.isfinite(o) else 0.0
                if abs(held) > 1e-6 and np.isfinite(ae):
                    pos = (held, ae, b["sl"][j], b["tp"][j])
                else:
                    pos = (0.0, None, None, None)
                pend = b["pending"][j]
                side = "LONG" if w > 0.005 else ("SHORT" if w < -0.005 else "FLAT")
                recs.append((rid, sym, side, w, pend if np.isfinite(pend) else None, None, None, None, None, None) + pos)
            c.executemany("INSERT INTO run_books(run_id, symbol, side, weight, entry, sl, tp, confidence, strength, members_agree, "
                          "held, avg_entry, pos_sl, pos_tp) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recs)
        c.executemany("INSERT INTO trades(source, t, symbol, kind, side, price, weight, extra) VALUES(?,?,?,?,?,?,?,?)",
                      [(src, _ms(e["t"]), e["symbol"], e["kind"], e.get("side"), e.get("price"), e.get("weight"),
                        json.dumps({k: v for k, v in e.items() if k not in ("t", "symbol", "kind", "side", "price", "weight")}, default=str))
                       for e in events])
        c.executemany("INSERT INTO equity(source, t, equity) VALUES(?, ?, ?)", [(src, _ms(b["t"]) + H4, b["equity"]) for b in bars])
        c.execute("INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (f"summary_{src}", json.dumps(summary)))
    n_book = sum(1 for o in orders if o[1] == "book")
    return f"{src}: {len(bars)} bars, {n_book} trades, {len(orders) - n_book} dip bids, 5y {summary['monthly_5y']}%/month"


def store_paper(pipe: str, plan: dict, db) -> str:
    """The prospective paper window of a trade plan (since its freeze) as orders / runs + run_books / trades under 'paper_<pipe>'."""
    src = f"paper_{pipe}"
    events = [dict(e, t=pd.Timestamp(e["t"])) for e in plan.get("events", [])]
    orders = build_orders(events)
    bars = plan.get("bars", [])
    syms = list(plan.get("coins", {}).keys()) or ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    with db.write() as c:
        c.execute("DELETE FROM run_books WHERE run_id IN (SELECT id FROM runs WHERE source = ?)", (src,))
        for tb in ("runs", "trades", "orders"):
            c.execute(f"DELETE FROM {tb} WHERE source = ?", (src,))
        c.executemany("INSERT INTO orders(source, symbol, kind, side, signal_t, entry_t, entry_px, sl, tp, size, adds, exit_t, exit_px, "
                      "exit_reason, pnl_pct, avg_px, fills, entry_type) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      [(src,) + o[:16] + ("paper",) for o in orders])
        now = db.now_ms()
        for b in bars:
            rid = c.execute("INSERT INTO runs(source, decision_time, pipeline, created_at, scale, governor, gross) VALUES(?,?,?,?,?,?,?)",
                            (src, _ms(b["t"]), pipe, now, None, None, None)).lastrowid
            recs = []
            for j, sym in enumerate(syms):
                w, o, q, ae = (b[k][j] for k in ("target", "open", "qty", "entry"))
                held = (q or 0.0) * o if o else 0.0
                pos = (held, ae, b["sl"][j], b["tp"][j]) if abs(held) > 1e-6 and ae else (0.0, None, None, None)
                w = w or 0.0
                side = "LONG" if w > 0.005 else ("SHORT" if w < -0.005 else "FLAT")
                recs.append((rid, sym, side, w, b["pending"][j], None, None, None, None, None) + pos)
            c.executemany("INSERT INTO run_books(run_id, symbol, side, weight, entry, sl, tp, confidence, strength, members_agree, "
                          "held, avg_entry, pos_sl, pos_tp) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recs)
        c.executemany("INSERT INTO trades(source, t, symbol, kind, side, price, weight, extra) VALUES(?,?,?,?,?,?,?,?)",
                      [(src, _ms(e["t"]), e["symbol"], e["kind"], e.get("side"), e.get("price"), e.get("weight"),
                        json.dumps({k: v for k, v in e.items() if k not in ("t", "symbol", "kind", "side", "price", "weight")}, default=str))
                       for e in events])
    return f"{src}: {len(bars)} bars, {len(orders)} orders"
