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
    "v205": ("research_books", 5.261),
    "v233": ("research_books_t3", 5.485),
    "v236": ("research_books_w2", 5.774),
    "v240": ("research_books_o1", 5.777),  # with the v247 sleeve budget 0.18
    "v266": ("research_books_o1", 6.130),  # O1 + 5m-close dip stops + 8-sigma native backstop (v266 B1)
}
KW_OVERRIDE = {"v240": {"sleeve_risk_budget": 0.18},
               "v266": {"sleeve_risk_budget": 0.18, "sleeve_stop_mode": "close5", "sleeve_backstop": 8.0}}


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
    res = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)), win_start=5,
                      events=events, bars=bars, **dict(v221.KW, **KW_OVERRIDE.get(pipe, {})))
    if abs(res["monthly_dev4"] - dev4) > 0.01:
        raise RuntimeError(f"{pipe}: replay dev4 {res['monthly_dev4']} != research {dev4}")
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
