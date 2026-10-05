"""Read-only health check for running bots (no I/O besides reading state files, no network, no keys).

Usage:
  python scripts/bot_health.py artifacts/bot/paper_d17bf [more dirs] [--interval 20] [--json]

Reads, per dir, actions.jsonl, state.json and (paper mode) exchange.json, prints a
compact report and exits 0 (ok), 1 (warnings) or 2 (critical):

  last cycle age .......... critical if > 3 x interval or > 5 min
  plan age vs bar schedule  warning if the plan is older than 4h30m
  24h op counts ........... place / amend / cancel / fill / market_exit / stale_plan / errors
  unprotected pieces ...... critical: open piece without BOTH a resting stop and take-profit
  ledger vs exchange qty .. critical: piece qty disagrees with the exchange position
  rate-limit / API errors . reported (warning when seen in the last 24h)
  equity .................. now vs start and max DD of the hourly equity_curve
  fills ................... dip / book fills in the last 24h + win/loss of closed pieces
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CRITICAL_CYCLE_S = 300.0          # 5 minutes
PLAN_STALE_H = 4.5                # a 4h plan is valid until the next bar plan (+ delay)
WINDOW_H = 24.0                   # counting window for ops / fills / errors

ERROR_OPS = ("error", "cycle_error")
COUNT_OPS = ("place", "amend", "cancel", "fill", "market_exit", "stale_plan")


def parse_ts(x):
    if x is None:
        return None
    try:
        t = datetime.fromisoformat(str(x))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_actions(path: Path):
    recs = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except ValueError:
            continue
    return recs


def piece_kind(links: dict, link: str) -> str | None:
    """dip / book classification of an action link via state-links metadata, else the pid prefix."""
    info = (links or {}).get(link) or {}
    order = info.get("order") or {}
    meta = order.get("meta") or {}
    kind = meta.get("kind")
    if kind in ("dip", "book"):
        return kind
    piece = order.get("piece") or ""
    if piece.startswith("d"):
        return "dip"
    if piece.startswith("b"):
        return "book"
    return None


def open_piece_exits(pid: str, links: dict, exchange_orders: dict | None):
    """(stop_ok, tp_ok) for an open piece: resting stop + take-profit on the exchange
    (paper), else the runner's resting set in state.json; matched via link metadata
    with a {pid}S / {pid}T suffix fallback."""
    if exchange_orders is not None:
        pool = []
        for link, o in exchange_orders.items():
            info = (links or {}).get(link) or {}
            order = info.get("order") or {}
            if order.get("piece") == pid:
                kind = order.get("kind")
            elif link == pid + "S":
                kind = "stop"
            elif link == pid + "T":
                kind = "tp"
            else:
                continue
            pool.append((link, o, kind))
    else:
        pool = []
        for link, info in (links or {}).items():
            if not info.get("rest"):
                continue
            order = info.get("order") or {}
            if order.get("piece") == pid:
                pool.append((link, info.get("rest") or {}, order.get("kind")))
    stop_ok = any(k == "stop" for _, _, k in pool)
    tp_ok = any(k == "tp" for _, _, k in pool)
    return stop_ok, tp_ok


def piece_pnl(ledger: dict, links: dict, execs: list):
    """Realized PnL per piece from exchange execs joined via state-links metadata.

    Returns {pid: dict(side, entry_qty, entry_avg, exit_qty, pnl)}; longs: pnl =
    exit proceeds minus avg-entry cost of the exited qty (mirrored for shorts).
    """
    out = {}
    for e in execs or []:
        link = e.get("orderLinkId") or ""
        info = (links or {}).get(link) or {}
        order = info.get("order") or {}
        pid = order.get("piece") or ""
        if not pid:
            continue
        try:
            qty, px = float(e["execQty"]), float(e["execPrice"])
        except (TypeError, ValueError, KeyError):
            continue
        if qty <= 0:
            continue
        d = out.setdefault(pid, {"entry_qty": 0.0, "entry_cost": 0.0, "exit_qty": 0.0, "exit_px_qty": 0.0})
        if order.get("kind") in ("entry", "add"):
            d["entry_qty"] += qty
            d["entry_cost"] += qty * px
        else:  # reduce / tp / stop / market-exit links shrink the piece
            d["exit_qty"] += qty
            d["exit_px_qty"] += qty * px
    res = {}
    for pid, d in out.items():
        avg = d["entry_cost"] / d["entry_qty"] if d["entry_qty"] > 0 else None
        side = None
        pc = (ledger or {}).get(pid) or {}
        if pc.get("side") in (1, -1):
            side = int(pc["side"])
        if avg is None or side is None:
            pnl = None
        else:
            pnl = side * (d["exit_px_qty"] - avg * d["exit_qty"])
        res[pid] = {"side": side, "entry_qty": d["entry_qty"], "exit_qty": d["exit_qty"], "pnl": pnl}
    return res


def check_dir(d: Path, plan: dict | None, now: datetime, interval: float) -> dict:
    rep = {"dir": str(d), "status": "ok", "problems": [], "warnings": []}
    actions = load_actions(d / "actions.jsonl")
    state = load_json(d / "state.json")
    exchange = load_json(d / "exchange.json")
    if actions is None:
        rep["status"] = "critical"
        rep["problems"].append("missing actions.jsonl")
        actions = []
    if state is None:
        rep["warnings"].append("missing state.json")
        state = {}
    ledger = state.get("ledger") or {}
    links = state.get("links") or {}

    # last cycle age
    times = [t for t in (parse_ts(r.get("t")) for r in actions) if t is not None]
    # the runner logs only on changes; state.json is rewritten every cycle, so its write time is the heartbeat
    sp = d / "state.json"
    if sp.exists():
        mt = datetime.fromtimestamp(sp.stat().st_mtime, tz=timezone.utc)
        if mt <= now:  # ignore when an explicit --now lies before the file write (tests / replays)
            times.append(mt)
    last_t = max(times) if times else None
    rep["last_cycle"] = last_t.isoformat() if last_t else None
    age_s = (now - last_t).total_seconds() if last_t else None
    rep["cycle_age_s"] = age_s
    if age_s is None:
        rep["status"] = "critical"
        rep["problems"].append("no timestamped actions: runner may be down")
    elif age_s > 3 * interval or age_s > CRITICAL_CYCLE_S:
        rep["status"] = "critical"
        rep["problems"].append(f"last cycle {age_s / 60:.1f}m ago (>3x{interval:g}s or >5m)")

    # plan age vs the 4h bar schedule
    gen = parse_ts((plan or {}).get("generated_at")) if plan else None
    rep["plan_generated_at"] = gen.isoformat() if gen else None
    rep["plan_age_h"] = (now - gen).total_seconds() / 3600 if gen else None
    if gen is None:
        rep["warnings"].append("plan generated_at unknown")
    elif rep["plan_age_h"] > PLAN_STALE_H:
        if rep["status"] == "ok":
            rep["status"] = "warning"
        rep["warnings"].append(f"plan age {rep['plan_age_h']:.1f}h (>4h30m)")

    # op counts in the last 24h
    cutoff = now - timedelta(hours=WINDOW_H)
    recent = [r for r in actions if (parse_ts(r.get("t")) or now) >= cutoff]
    counts = {op: 0 for op in COUNT_OPS}
    counts["errors"] = 0
    err_notes, rate_limited = [], 0
    for r in recent:
        op = r.get("op")
        if op in counts:
            counts[op] += 1
        elif op in ERROR_OPS:
            counts["errors"] += 1
        else:
            counts.setdefault("other", 0)
            counts["other"] += 1
        if op in ERROR_OPS:
            note = str(r.get("note") or r.get("call") or op)
            err_notes.append(note[:120])
            if "rate limit" in note.lower() or "10006" in note:
                rate_limited += 1
    rep["counts_24h"] = counts
    rep["errors_24h"] = err_notes[:5]
    rep["rate_limit_24h"] = rate_limited
    if counts["errors"]:
        if rep["status"] == "ok":
            rep["status"] = "warning"
        rep["warnings"].append(f"{counts['errors']} API errors in 24h ({rate_limited} rate-limit)")

    # open pieces must carry BOTH a stop and a take-profit
    ex_orders = exchange.get("orders") if isinstance(exchange, dict) else None
    unprotected = []
    for pid, pc in ledger.items():
        if not isinstance(pc, dict) or not pc.get("qty", 0) > 0:
            continue
        stop_ok, tp_ok = open_piece_exits(pid, links, ex_orders)
        if not (stop_ok and tp_ok):
            missing = "/".join(x for x, ok in (("stop", stop_ok), ("tp", tp_ok)) if not ok)
            unprotected.append(f"{pid}({pc.get('symbol')}:no-{missing})")
    rep["open_pieces"] = sum(1 for v in ledger.values() if isinstance(v, dict) and v.get("qty", 0) > 0)
    rep["unprotected"] = unprotected
    if unprotected:
        rep["status"] = "critical"
        rep["problems"].append(f"open without stop+TP: {', '.join(unprotected)}")

    # ledger qty vs the exchange position (paper truth)
    mismatches = []
    if isinstance(exchange, dict):
        led_qty: dict = {}
        for pid, pc in ledger.items():
            if not isinstance(pc, dict) or not pc.get("qty", 0) > 0:
                continue
            idx = 1 if pc.get("side", 1) > 0 else 2
            led_qty[f"{pc.get('symbol')}|{idx}"] = led_qty.get(f"{pc.get('symbol')}|{idx}", 0.0) + float(pc["qty"])
        ex_qty = {}
        for k, p in (exchange.get("pos") or {}).items():
            try:
                q = float(p.get("qty", 0.0))
            except (TypeError, ValueError, AttributeError):
                q = 0.0
            if isinstance(k, str) and "|" in k:
                ex_qty[k] = q
        for k in sorted(set(led_qty) | {x for x, q in ex_qty.items() if q > 0}):
            if abs(led_qty.get(k, 0.0) - ex_qty.get(k, 0.0)) > 1e-9:
                mismatches.append(f"{k}:ledger={led_qty.get(k, 0.0):g} exch={ex_qty.get(k, 0.0):g}")
    else:
        rep["warnings"].append("no exchange.json: qty cross-check skipped")
    rep["qty_mismatch"] = mismatches
    if mismatches:
        rep["status"] = "critical"
        rep["problems"].append(f"qty disagreement: {', '.join(mismatches)}")

    # equity now vs start + max DD of the hourly curve
    if isinstance(exchange, dict):
        curve = exchange.get("equity_curve") or []
        pts = []
        for row in curve:
            try:
                pts.append((parse_ts(row[0]), float(row[1])))
            except (TypeError, ValueError, IndexError):
                continue
        pts = [(t, v) for t, v in pts if t is not None]
        eq0 = exchange.get("equity0")
        eq_now = pts[-1][1] if pts else None
        peak, max_dd = None, 0.0
        for _, v in pts:
            peak = v if peak is None or v > peak else peak
            if peak > 0:
                max_dd = max(max_dd, (peak - v) / peak)
        rep["equity0"], rep["equity_now"] = eq0, eq_now
        rep["equity_pnl"] = (eq_now - eq0) if eq_now is not None and eq0 is not None else None
        rep["max_dd"] = max_dd
        rep["funding_paid"], rep["fees"] = exchange.get("funding_paid"), exchange.get("fees")
    else:
        rep.update({"equity0": None, "equity_now": None, "equity_pnl": None, "max_dd": None,
                    "funding_paid": None, "fees": None})

    # dip / book fills in the last 24h + win/loss of pieces closed in the window
    fills = [r for r in recent if r.get("op") == "fill"]
    dip_fills = sum(1 for r in fills if piece_kind(links, r.get("link") or "") == "dip")
    book_fills = sum(1 for r in fills if piece_kind(links, r.get("link") or "") == "book")
    rep["fills_24h"] = {"dip": dip_fills, "book": book_fills, "other": len(fills) - dip_fills - book_fills}
    wins, losses, closed_pnl = 0, 0, 0.0
    wl_detail = []
    if isinstance(exchange, dict):
        execs = [e for e in (exchange.get("execs") or [])
                 if parse_ts(datetime.fromtimestamp(int(e.get("execTime", 0)) / 1000, tz=timezone.utc)) >= cutoff]
        for pid, d in piece_pnl(ledger, links, execs).items():
            pc = ledger.get(pid) or {}
            if d["exit_qty"] <= 0 or d["pnl"] is None:
                continue
            if not (pc.get("qty", 0) == 0 or d["exit_qty"] >= d["entry_qty"] > 0):
                continue  # only closed pieces
            closed_pnl += d["pnl"]
            if d["pnl"] > 0:
                wins += 1
            else:
                losses += 1
            wl_detail.append(f"{pid}:{d['pnl']:+.2f}")
    rep["closed_24h"] = {"wins": wins, "losses": losses, "pnl": round(closed_pnl, 2), "pieces": wl_detail[:10]}
    return rep


def fmt_money(v):
    return "n/a" if v is None else f"{v:,.2f}"


def fmt_report(rep: dict) -> str:
    age = rep["cycle_age_s"]
    age_s = "never" if age is None else (f"{age:.0f}s" if age < 600 else f"{age / 60:.1f}m")
    c = rep["counts_24h"]
    ops = " ".join(f"{k}={c.get(k, 0)}" for k in ("place", "amend", "cancel", "fill", "market_exit", "stale_plan", "errors"))
    lines = [
        f"[{rep['status'].upper()}] {rep['dir']} last_cycle={rep['last_cycle']} (age {age_s})",
        f"  plan={rep['plan_generated_at']} age={rep['plan_age_h']:.1f}h"
        if rep["plan_age_h"] is not None else "  plan=unknown",
        f"  24h ops: {ops} rate_limit={rep['rate_limit_24h']}",
        f"  open={rep['open_pieces']} unprotected={rep['unprotected'] or 'none'} qty_mismatch={rep['qty_mismatch'] or 'none'}",
        f"  equity {fmt_money(rep['equity_now'])} vs {fmt_money(rep['equity0'])} "
        f"(pnl {fmt_money(rep['equity_pnl'])}) maxDD={rep['max_dd'] * 100:.2f}%" if rep["max_dd"] is not None
        else "  equity n/a (no exchange.json)",
        f"  fills24h dip={rep['fills_24h']['dip']} book={rep['fills_24h']['book']} other={rep['fills_24h']['other']} "
        f"closed W/L={rep['closed_24h']['wins']}/{rep['closed_24h']['losses']} pnl={rep['closed_24h']['pnl']:+.2f}",
    ]
    for p in rep["problems"]:
        lines.append(f"  CRITICAL: {p}")
    for w in rep["warnings"]:
        lines.append(f"  warning: {w}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only health check for running bots.")
    ap.add_argument("dirs", nargs="+", help="bot state dirs (actions.jsonl, state.json, exchange.json)")
    ap.add_argument("--interval", type=float, default=20.0, help="bot loop interval in seconds (default 20)")
    ap.add_argument("--plan", default="artifacts/research/advisor_shadow/trade_plan_v376.json",
                    help="merged trade plan path for the plan-age check")
    ap.add_argument("--now", default=None, help="reference time ISO (default: now UTC; for tests)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    a = ap.parse_args(argv)
    now = parse_ts(a.now) if a.now else datetime.now(timezone.utc)
    root = Path(__file__).resolve().parents[1]
    plan_path = Path(a.plan) if Path(a.plan).is_absolute() else root / a.plan
    plan = load_json(plan_path)
    if plan is None:
        print(f"warning: cannot read plan {plan_path}", file=sys.stderr)
    reps = [check_dir(Path(d), plan, now, a.interval) for d in a.dirs]
    if a.json:
        print(json.dumps({"now": now.isoformat(), "dirs": reps}, indent=1, default=str))
    else:
        print("\n".join(fmt_report(r) for r in reps))
    if any(r["status"] == "critical" for r in reps):
        return 2
    if any(r["status"] == "warning" for r in reps):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
