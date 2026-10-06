"""Paper-vs-plan divergence (ops_divergence): go-live criterion (c).

Compares each paper bot's hourly equity_curve (exchange.json) with the
research plan's own paper equity over the same hours and reports divergence
in percentage points per elapsed month, fill reconciliation counts, and a
PASS/FAIL verdict vs the 1.5 pp/month go-live threshold (once >= 14 days
elapsed, else "too early").

Where the backend stores the v376 plan's paper path (documented here because
this script relies on it):
  - kv key ``trade_plan_v376`` in ``artifacts/web/app.db`` (SQLite kv table),
    mirrored to the file ``artifacts/research/advisor_shadow/trade_plan_v376.json``
    (this script reads the file mirror; same content as the kv value);
  - merged by ``backend/multiphase.py:merge()`` from the four sub-plans
    ``trade_plan_v376_s{0..3}`` (kv + same artifacts dir);
  - the per-trade paper window is also stored as DB rows with source
    ``paper_v376`` (``backend/multiphase.py:store_paper``; trades/orders tables).
  - ``tm_v376`` equity in the DB is the long research replay, NOT the paper
    window, and is never used here.
  - the plan only simulates the v376 R2-4P configuration. Bot dirs running any
    other configuration (e.g. dip-mult 1.7 / gross cap, corr-size, bear-book,
    G2K20) have "no plan path"; they are compared against the closest plan
    path (v376 R2-4P) with that label so the mismatch is explicit.

Usage:
  python scripts/paper_divergence.py artifacts/bot/paper_d17bf [...]
  python scripts/paper_divergence.py artifacts/bot/paper artifacts/bot/paper_d17bf --json out.json

Read-only (except the optional --json output file). No network, no keys,
never touches .env. Go-live rule: docs/DEPLOYMENT_PLAN_VI.md s2.3(c).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "artifacts" / "research" / "advisor_shadow" / "trade_plan_v376.json"
THRESHOLD_PP_MONTH = 1.5  # go-live criterion (c): paper-vs-plan divergence <= 1.5 pp/month
MIN_DAYS = 14.0  # verdict only once >= 14 days elapsed
DAYS_PER_MONTH = 365.25 / 12  # 30.4375, mean calendar month
CLOSEST_PLAN_LABEL = "v376 R2-4P (closest; bot config not simulated by plan)"
# Only the plain R2-4P paper bot mirrors the v376 plan config 1:1.
SAME_CONFIG_DIRS = {"paper"}


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


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def piece_of(link):
    if isinstance(link, str) and len(link) > 1 and link[-1] in "ETSMX":
        return link[:-1]
    return link


def load_bot(bot_dir):
    """Read a paper bot dir (exchange.json + state.json). Never raises."""
    d = Path(bot_dir)
    ex, state = {}, {}
    try:
        ex = json.loads((d / "exchange.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        state = json.loads((d / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    curve = []
    for row in (ex.get("equity_curve") or []):
        try:
            t, v = parse_ts(row[0]), float(row[1])
        except (TypeError, ValueError, IndexError):
            continue
        if t is not None:
            curve.append((t, v))
    curve.sort()
    # piece -> symbol from state links, fallback to exchange orders
    piece_sym = {}
    for link, rec in ((state.get("links") or {}).items()):
        o = (rec or {}).get("order") or {}
        if o.get("piece") and o.get("symbol"):
            piece_sym.setdefault(o["piece"], o["symbol"])
    for link, o in ((ex.get("orders") or {}).items()):
        if isinstance(o, dict) and o.get("symbol"):
            piece_sym.setdefault(piece_of(link), o["symbol"])
    entries, exits = [], Counter()
    for e in ex.get("execs") or []:
        link = str(e.get("orderLinkId", ""))
        last = link[-1:] if link else ""
        try:
            ms = int(str(e.get("execTime", "")))
            et = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        except (TypeError, ValueError):
            et = None
        if last == "E":
            entries.append({"t": et, "symbol": piece_sym.get(piece_of(link), "?"),
                            "dip": link.startswith("d"), "book": link.startswith("b")})
        elif last in ("T", "S", "M", "X"):
            exits[last] += 1
    return {"curve": curve, "entries": entries, "exits": dict(exits),
            "fees": ex.get("fees"), "has_exchange": bool(ex)}


def load_plan(plan_path):
    """Read the v376 plan paper path (file mirror of kv trade_plan_v376)."""
    d = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    curve = []
    for row in (d.get("equity_curve") or []):
        try:
            t, v = parse_ts(row[0]), float(row[1])
        except (TypeError, ValueError, IndexError):
            continue
        if t is not None:
            curve.append((t, v))
    curve.sort()
    fills = []
    for e in d.get("events") or []:
        if e.get("kind") != "book_fill":
            continue
        t = parse_ts(e.get("t"))
        if t is not None:
            fills.append({"t": t, "symbol": e.get("symbol", "?")})
    return {"curve": curve, "fills": fills,
            "net_return_pct": d.get("net_return_pct"), "pipeline": d.get("pipeline")}


def plan_window(curve, t0, t1):
    """Plan equity slice for the bot window: ffill anchor at/before t0 .. last point <= t1."""
    if not curve or t0 is None or t1 is None:
        return []
    anchor = None
    for t, v in curve:
        if t <= t0:
            anchor = (t, v)
    if anchor is None:
        for t, v in curve:
            if t >= t0:
                anchor = (t, v)
                break
    pts = [anchor] if anchor is not None else []
    for t, v in curve:
        if anchor is not None and t <= anchor[0]:
            continue
        if t <= t1:
            pts.append((t, v))
    return pts


def summarize(bot_dir, plan, plan_label_detail="trade_plan_v376"):
    name = Path(bot_dir).name
    bot = load_bot(bot_dir)
    same_config = name in SAME_CONFIG_DIRS
    cfg = "same-config v376 R2-4P" if same_config else "no plan path; closest: " + CLOSEST_PLAN_LABEL
    res = {"bot": name, "dir": str(bot_dir), "config": cfg,
           "plan": plan_label_detail if same_config else plan_label_detail + " (closest, labelled)"}
    curve = bot["curve"]
    if len(curve) < 2:
        res.update(status="no bot curve (need >= 2 equity points)", verdict="too early")
        return res
    t0, t1 = curve[0][0], curve[-1][0]
    days = (t1 - t0).total_seconds() / 86400
    first, last = curve[0][1], curve[-1][1]
    bot_ret = (last - first) / first if first else 0.0
    res.update(t0=t0.isoformat(), t1=t1.isoformat(), days=round(days, 3),
               bot_return_pct=round(100 * bot_ret, 4))
    seg = plan_window(plan["curve"], t0, t1)
    if len(seg) < 2 or seg[0][0] == seg[-1][0]:
        res.update(status="no overlapping plan equity for bot window", verdict="too early",
                   plan_points=len(seg))
        return res
    p0, p1 = seg[0][1], seg[-1][1]
    plan_ret = (p1 - p0) / p0 if p0 else 0.0
    div_pp = 100 * (bot_ret - plan_ret)
    div_pm = div_pp * DAYS_PER_MONTH / days if days > 0 else None
    res.update(plan_points=len(seg), plan_return_pct=round(100 * plan_ret, 4),
               div_pp=round(div_pp, 4),
               div_pp_per_month=None if div_pm is None else round(div_pm, 4))
    # fills in the same window: bot entry execs vs plan book_fill events
    bent = [e for e in bot["entries"] if e["t"] is None or (t0 <= e["t"] <= t1)]
    pfill = [f for f in plan["fills"] if t0 <= f["t"] <= t1]
    cb, cp = Counter(e["symbol"] for e in bent), Counter(f["symbol"] for f in pfill)
    per_symbol, only_bot, only_plan = {}, 0, 0
    for s in sorted(set(cb) | set(cp)):
        m = min(cb.get(s, 0), cp.get(s, 0))
        per_symbol[s] = {"bot_entries": cb.get(s, 0), "plan_fills": cp.get(s, 0),
                         "matched": m, "only_in_bot": cb.get(s, 0) - m,
                         "only_in_plan": cp.get(s, 0) - m}
        only_bot += cb.get(s, 0) - m
        only_plan += cp.get(s, 0) - m
    res.update(bot_entry_fills=len(bent), plan_book_fills=len(pfill),
               fills_only_in_bot=only_bot, fills_only_in_plan=only_plan,
               per_symbol=per_symbol, bot_exits=bot["exits"])
    if days < MIN_DAYS:
        res["verdict"] = "too early"
    else:
        res["verdict"] = "PASS" if abs(div_pm) <= THRESHOLD_PP_MONTH else "FAIL"
    return res


def format_row(r):
    if r.get("status"):
        return (f"{r['bot']}: {r['status']} | config: {r['config']} | verdict={r['verdict']}")
    return (f"{r['bot']}: {r['days']}d {r['t0']} -> {r['t1']} | config: {r['config']} | "
            f"bot={r['bot_return_pct']}% plan={r['plan_return_pct']}% "
            f"div={r['div_pp']}pp ({r['div_pp_per_month']}pp/month) | "
            f"fills only-bot={r['fills_only_in_bot']} only-plan={r['fills_only_in_plan']} "
            f"(bot entries={r['bot_entry_fills']}, plan book_fills={r['plan_book_fills']}) | "
            f"verdict={r['verdict']}")


def main(argv=None):
    global THRESHOLD_PP_MONTH, MIN_DAYS
    ap = argparse.ArgumentParser(description="Paper bot vs research-plan divergence (go-live criterion c).")
    ap.add_argument("dirs", nargs="+", help="paper bot dirs (each with exchange.json)")
    ap.add_argument("--plan", default=str(DEFAULT_PLAN), help="v376 plan paper path (file mirror of kv trade_plan_v376)")
    ap.add_argument("--json", default=None, help="write full JSON report to PATH")
    ap.add_argument("--threshold", type=float, default=THRESHOLD_PP_MONTH)
    ap.add_argument("--min-days", type=float, default=MIN_DAYS)
    a = ap.parse_args(argv)
    THRESHOLD_PP_MONTH, MIN_DAYS = a.threshold, a.min_days
    try:
        plan = load_plan(a.plan)
    except (OSError, ValueError) as exc:
        print(f"cannot load plan paper path {a.plan}: {exc}", file=sys.stderr)
        return 2
    rows = [summarize(d, plan) for d in a.dirs]
    for r in rows:
        print(format_row(r))
    if a.json:
        Path(a.json).write_text(json.dumps({"plan": a.plan, "rows": rows}, indent=1, default=str) + "\n",
                                 encoding="utf-8")
        print(f"saved {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
