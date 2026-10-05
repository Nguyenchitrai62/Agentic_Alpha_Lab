"""Paper evidence comparison tool (oc_papercmp).

Reads (read-only, single process, JSON only - no market/1m data):
  artifacts/bot/paper/exchange.json (+ runner.log, state.json)
  artifacts/bot/paper_d18/exchange.json (+ runner.log, state.json)
  artifacts/research/advisor_shadow/trade_plan_v376.json

Prints per-source tables and saves artifacts/research/paper_compare.json:
  hourly equity curve since start, return %, max DD, fills by kind
  (book entry / dip / tp / stop / market exit), win rate of closed pieces
  (execs grouped by link prefix), and R2-4P bot vs plan divergence
  (return difference, fills present in one but not the other).

Paper only: never places orders, never touches the network.
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAPER_EX = ROOT / "artifacts" / "bot" / "paper" / "exchange.json"
PAPER_RUN = ROOT / "artifacts" / "bot" / "paper" / "runner.log"
PAPER_STATE = ROOT / "artifacts" / "bot" / "paper" / "state.json"
D18_EX = ROOT / "artifacts" / "bot" / "paper_d18" / "exchange.json"
D18_RUN = ROOT / "artifacts" / "bot" / "paper_d18" / "runner.log"
D18_STATE = ROOT / "artifacts" / "bot" / "paper_d18" / "state.json"
PLAN_P = ROOT / "artifacts" / "research" / "advisor_shadow" / "trade_plan_v376.json"
DEFAULT_OUT = ROOT / "artifacts" / "research" / "paper_compare.json"

ENTRY_BUCKETS = ("book_entry", "dip")
EXIT_BUCKETS = ("tp", "stop", "market_exit")


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def equity_stats(curve):
    """Return stats for an [[ts, eq], ...] curve (copied through verbatim)."""
    pts = [[ts, _f(v)] for ts, v in (curve or [])]
    if not pts:
        return {"n_points": 0, "start": None, "end": None,
                "start_equity": None, "end_equity": None,
                "return_pct": 0.0, "max_dd_pct": 0.0, "curve": []}
    eqs = [v for _, v in pts]
    first, last = eqs[0], eqs[-1]
    ret = 100.0 * (last - first) / first if first else 0.0
    peak, worst = eqs[0], 0.0
    for v in eqs:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return {"n_points": len(pts), "start": pts[0][0], "end": pts[-1][0],
            "start_equity": first, "end_equity": last,
            "return_pct": ret, "max_dd_pct": 100.0 * worst, "curve": pts}


def piece_of(link):
    """Piece id = orderLinkId minus the final E/T/S/M/X char (matches state.json)."""
    if isinstance(link, str) and len(link) > 1 and link[-1] in "ETSMX":
        return link[:-1]
    return link


def classify_exec(link, state_links):
    """Map an exec orderLinkId to (bucket, piece).

    state_links: {link: (kind, piece, meta_kind)} from state.json; fallback is
    the naming rule b*E=book entry, d*E=dip, *T=tp, *S=stop, *M/*X=market exit.
    """
    info = (state_links or {}).get(link)
    if info is not None:
        kind, piece, meta = info
        if kind == "entry":
            bucket = "book_entry" if meta == "book" else "dip" if meta == "dip" else "dip"
            if meta not in ("book", "dip"):
                bucket = "book_entry" if str(link).startswith("b") else "dip"
        elif kind == "tp":
            bucket = "tp"
        elif kind == "stop":
            bucket = "stop"
        else:
            bucket = "market_exit"
        return bucket, piece or piece_of(link)
    link = str(link)
    last = link[-1:] if link else ""
    if last == "E":
        bucket = "book_entry" if link.startswith("b") else "dip"
    elif last == "T":
        bucket = "tp"
    elif last == "S":
        bucket = "stop"
    elif last in ("M", "X"):
        bucket = "market_exit"
    else:
        bucket = "market_exit"
    return bucket, piece_of(link)


def load_state_links(state_path):
    """Return {link: (kind, piece, meta_kind)} from a bot state.json."""
    try:
        st = json.loads(Path(state_path).read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for link, rec in (st.get("links") or {}).items():
        o = (rec or {}).get("order") or {}
        out[link] = (o.get("kind"), o.get("piece") or piece_of(link),
                      (o.get("meta") or {}).get("kind"))
    return out


def piece_symbol(piece, state_path=None, orders=None):
    """Best-effort symbol for a piece (from state links or exchange orders)."""
    return None  # resolved by caller via exec order map


def summarize_bot(name, ex_path, run_path, state_path):
    ex = json.loads(Path(ex_path).read_text())
    state_links = load_state_links(state_path)
    orders = ex.get("orders") or {}
    # symbol per piece from state links' order records + exchange orders fallback
    piece_sym = {}
    try:
        st = json.loads(Path(state_path).read_text())
        for link, rec in (st.get("links") or {}).items():
            o = (rec or {}).get("order") or {}
            if o.get("piece") and o.get("symbol"):
                piece_sym.setdefault(o["piece"], o["symbol"])
    except (OSError, ValueError):
        pass
    for link, o in orders.items():
        p = piece_of(link)
        if isinstance(o, dict) and o.get("symbol"):
            piece_sym.setdefault(p, o["symbol"])

    execs = ex.get("execs") or []
    fills = Counter()
    EntryCost, ExitProv = {}, {}
    EntryN, ExitN = Counter(), Counter()
    EntrySym = {}
    for e in execs:
        link = e.get("orderLinkId", "")
        bucket, piece = classify_exec(link, state_links)
        fills[bucket] += 1
        qty, px = _f(e.get("execQty")), _f(e.get("execPrice"))
        sym = piece_sym.get(piece)
        if bucket in ENTRY_BUCKETS:
            EntryCost[piece] = EntryCost.get(piece, 0.0) + qty * px
            EntryN[piece] += 1
            if sym:
                EntrySym[piece] = sym
        elif bucket in EXIT_BUCKETS:
            ExitProv[piece] = ExitProv.get(piece, 0.0) + qty * px
            ExitN[piece] += 1
    pieces = set(list(EntryCost) + list(ExitProv))
    closed = sorted(p for p in pieces if p in EntryCost and p in ExitProv)
    wins = sum(1 for p in closed if ExitProv[p] > EntryCost[p])
    by_symbol = Counter(EntrySym.get(p, "?") for p in EntryCost)

    # runner.log action counts (runner.log mirrors actions.jsonl)
    actions = Counter()
    try:
        for line in Path(run_path).read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                actions[json.loads(line).get("op", "?")] += 1
            except ValueError:
                actions["unparsed"] += 1
    except OSError:
        pass

    eq = equity_stats(ex.get("equity_curve"))
    return {
        "name": name,
        "equity_curve": eq["curve"],
        "n_points": eq["n_points"],
        "start": eq["start"],
        "end": eq["end"],
        "start_equity": eq["start_equity"],
        "end_equity": eq["end_equity"],
        "return_pct": eq["return_pct"],
        "max_dd_pct": eq["max_dd_pct"],
        "fees": ex.get("fees"),
        "funding_paid": ex.get("funding_paid"),
        "cash": ex.get("cash"),
        "equity0": ex.get("equity0"),
        "fills_by_kind": {k: fills.get(k, 0) for k in
                          ("book_entry", "dip", "tp", "stop", "market_exit")},
        "fills_total": sum(fills.values()),
        "execs_total": len(execs),
        "pieces": {"total": len(pieces), "closed": len(closed),
                   "open": len(pieces) - len(closed), "wins": wins,
                   "losses": len(closed) - wins,
                   "win_rate": (wins / len(closed)) if closed else None,
                   "closed_ids": closed},
        "entries_by_symbol": dict(by_symbol),
        "actions": dict(actions),
    }


def summarize_plan(plan_path):
    d = json.loads(Path(plan_path).read_text())
    eq = equity_stats(d.get("equity_curve"))
    evs = d.get("events") or []
    by_kind = Counter(e.get("kind", "?") for e in evs)
    fills = [e for e in evs if str(e.get("kind", "")).endswith("_fill")]
    by_sym = Counter(e.get("symbol", "?") for e in fills)
    return {
        "name": "plan_v376",
        "equity_curve": eq["curve"],
        "n_points": eq["n_points"],
        "start": eq["start"],
        "end": eq["end"],
        "start_equity": eq["start_equity"],
        "end_equity": eq["end_equity"],
        "return_pct": eq["return_pct"],
        "max_dd_pct": eq["max_dd_pct"],
        "net_return_pct_field": d.get("net_return_pct"),
        "pipeline": d.get("pipeline"),
        "events_by_kind": dict(by_kind),
        "book_fills": [{"t": e.get("t"), "symbol": e.get("symbol"),
                        "price": e.get("price")} for e in fills],
        "book_fills_by_symbol": dict(by_sym),
    }


def divergence(bot, plan):
    """R2-4P bot (paper) vs plan: return gap + per-symbol fill reconciliation."""
    syms = sorted(set(list(bot.get("entries_by_symbol", {})) +
                      list(plan.get("book_fills_by_symbol", {}))))
    per_symbol, only_bot, only_plan = {}, [], []
    for s in syms:
        b = int(bot.get("entries_by_symbol", {}).get(s, 0))
        p = int(plan.get("book_fills_by_symbol", {}).get(s, 0))
        m = min(b, p)
        per_symbol[s] = {"bot_entries": b, "plan_fills": p, "matched": m,
                         "only_in_bot": b - m, "only_in_plan": p - m}
    bot_ids = list((bot.get("pieces") or {}).get("closed_ids", [])) + [
        p for p in (bot.get("entries_by_symbol", {})) ]
    return {
        "bot": "paper",
        "plan": "plan_v376",
        "return_diff_pp": bot["return_pct"] - plan["return_pct"],
        "bot_return_pct": bot["return_pct"],
        "plan_return_pct": plan["return_pct"],
        "per_symbol": per_symbol,
        "fills_only_in_bot_ids": sorted(bot.get("pieces", {}).get("closed_ids", [])) +
        [f"open-piece-symbol:{s}" for s in syms
         if per_symbol[s]["only_in_bot"] > 0],
        "fills_only_in_plan": [f for f in plan.get("book_fills", [])
                                if f.get("symbol") in
                                [s for s in syms if per_symbol[s]["only_in_plan"] > 0]],
        "note": ("Link-id spaces are disjoint by construction (bot piece ids vs "
                 "plan t|symbol|price events); reconciliation is per-symbol "
                 "min-matched counts."),
    }


def build_report(paper_ex=PAPER_EX, paper_run=PAPER_RUN, paper_state=PAPER_STATE,
                 d18_ex=D18_EX, d18_run=D18_RUN, d18_state=D18_STATE,
                 plan_p=PLAN_P):
    bot = summarize_bot("paper", paper_ex, paper_run, paper_state)
    d18 = summarize_bot("paper_d18", d18_ex, d18_run, d18_state)
    plan = summarize_plan(plan_p)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {"paper": str(paper_ex), "paper_log": str(paper_run),
                   "paper_d18": str(d18_ex), "paper_d18_log": str(d18_run),
                   "plan": str(plan_p)},
        "sources": {"paper": bot, "paper_d18": d18, "plan_v376": plan},
        "divergence": {"r2_4p_vs_plan": divergence(bot, plan)},
    }


def print_tables(rep):
    for key in ("paper", "paper_d18", "plan_v376"):
        s = rep["sources"][key]
        print(f"== {key} ==")
        print(f"  curve: {s['n_points']} pts {s['start']} -> {s['end']}")
        print(f"  start={s['start_equity']} end={s['end_equity']} "
              f"return={s['return_pct']:.4f}% maxDD={s['max_dd_pct']:.4f}%")
        if key.startswith("paper"):
            print(f"  fills: {s['fills_by_kind']} total={s['fills_total']} "
                  f"execs={s['execs_total']}")
            p = s["pieces"]
            print(f"  pieces: total={p['total']} closed={p['closed']} "
                  f"wins={p['wins']} win_rate={p['win_rate']}")
            print(f"  actions: {s['actions']}")
            print(f"  fees={s['fees']} funding_paid={s['funding_paid']}")
        else:
            print(f"  events: {s['events_by_kind']}")
        print()
    d = rep["divergence"]["r2_4p_vs_plan"]
    print("== divergence R2-4P bot (paper) vs plan_v376 ==")
    print(f"  return_diff_pp={d['return_diff_pp']:.4f} "
          f"(bot {d['bot_return_pct']:.4f}% - plan {d['plan_return_pct']:.4f}%)")
    for s, r in d["per_symbol"].items():
        print(f"  {s}: bot={r['bot_entries']} plan={r['plan_fills']} "
              f"matched={r['matched']} only_bot={r['only_in_bot']} "
              f"only_plan={r['only_in_plan']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    rep = build_report()
    print_tables(rep)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1, default=str))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
