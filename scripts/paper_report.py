"""Side-by-side report for paper bots (read-only, no network, no keys).

Usage:
  python scripts/paper_report.py artifacts/bot/paper artifacts/bot/paper_d17bf ...
  python scripts/paper_report.py <dirs...> --md out.md
  python scripts/paper_report.py <dirs...> --json [out.json]

Reads ONLY files inside each given dir (actions.jsonl, state.json,
exchange.json, stdout.log); never inspects processes. Flags come only from
those files -- anything not recorded there is reported as 'n/a'.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


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


def equity_stats(curve):
    pts = []
    for row in curve or []:
        try:
            pts.append((parse_ts(row[0]), float(row[1])))
        except (TypeError, ValueError, IndexError):
            continue
    pts = [(t, v) for t, v in pts if t is not None]
    if not pts:
        return {"n": 0, "start": None, "end": None, "start_eq": None,
                "end_eq": None, "return_pct": None, "max_dd_pct": None}
    eqs = [v for _, v in pts]
    first, last = eqs[0], eqs[-1]
    ret = 100.0 * (last - first) / first if first else 0.0
    peak, worst = eqs[0], 0.0
    for v in eqs:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return {"n": len(pts), "start": pts[0][0], "end": pts[-1][0],
            "start_eq": first, "end_eq": last, "return_pct": ret,
            "max_dd_pct": 100.0 * worst}


def piece_of(link):
    if isinstance(link, str) and len(link) > 1 and link[-1] in "ETSMX":
        return link[:-1]
    return link


def load_state_links(state):
    out = {}
    for link, rec in ((state or {}).get("links") or {}).items():
        o = (rec or {}).get("order") or {}
        out[link] = (o.get("kind"), o.get("piece") or piece_of(link),
                      (o.get("meta") or {}).get("kind"))
    return out


def classify_exec(link, state_links):
    """Return (is_entry, dip_or_book_or_None, piece)."""
    info = (state_links or {}).get(link)
    if info is not None:
        kind, piece, meta = info
        if kind in ("entry", "add"):
            kb = meta if meta in ("dip", "book") else None
            if kb is None:
                kb = "book" if str(link).startswith("b") else \
                    "dip" if str(link).startswith("d") else None
            return True, kb, piece or piece_of(link)
        return False, None, piece or piece_of(link)
    link = str(link)
    last = link[-1:] if link else ""
    if last == "E":
        kb = "book" if link.startswith("b") else "dip" if link.startswith("d") else None
        return True, kb, piece_of(link)
    return False, None, piece_of(link)


def piece_kind_of(pid, state_links, ledger):
    for _link, (_k, piece, meta) in (state_links or {}).items():
        if piece == pid and meta in ("dip", "book"):
            return meta
    pc = (ledger or {}).get(pid) or {}
    if pc.get("kind") in ("dip", "book"):
        return pc["kind"]
    if str(pid).startswith("d"):
        return "dip"
    if str(pid).startswith("b"):
        return "book"
    return None


def summarize_dir(d: Path) -> dict:
    d = Path(d)
    actions = load_actions(d / "actions.jsonl")
    if actions is None:
        actions = []
    state = load_json(d / "state.json") or {}
    exchange = load_json(d / "exchange.json")
    ledger = state.get("ledger") or {}
    state_links = load_state_links(state)

    times = [t for t in (parse_ts(r.get("t")) for r in actions) if t is not None]
    eq = equity_stats((exchange or {}).get("equity_curve") if isinstance(exchange, dict) else [])
    start = min(times) if times else None
    if start is None:
        start = eq["start"]
    start_s = start.isoformat() if start else "n/a"

    # flags: only from files inside this dir, else 'n/a'
    modes = Counter(r.get("mode") for r in actions if r.get("mode"))
    mode = modes.most_common(1)[0][0] if modes else "n/a"
    name = d.name
    tag = name.split("_", 1)[1] if "_" in name else "n/a"
    bears = [r for r in actions if r.get("op") == "bear_state"]
    if bears:
        last_bear = bears[-1].get("bear")
        flags = f"mode={mode}; tag={tag}; bear-book=on(last bear={last_bear}); other-flags=n/a"
    else:
        flags = f"mode={mode}; tag={tag}; bear-book=n/a; other-flags=n/a"

    # fills: entry execs by kind; fallback to action fill ops via links
    dip_fills = book_fills = 0
    entry_qty, entry_cost, exit_qty, exit_px = {}, {}, {}, {}
    entry_sym = {}
    piece_sym = {}
    try:
        st_links_raw = (state or {}).get("links") or {}
        for link, rec in st_links_raw.items():
            o = (rec or {}).get("order") or {}
            if o.get("piece") and o.get("symbol"):
                piece_sym.setdefault(o["piece"], o["symbol"])
    except AttributeError:
        pass
    execs = (exchange or {}).get("execs") if isinstance(exchange, dict) else None
    if execs:
        for e in execs:
            link = e.get("orderLinkId", "")
            is_entry, kb, piece = classify_exec(link, state_links)
            try:
                qty, px = float(e["execQty"]), float(e["execPrice"])
            except (TypeError, ValueError, KeyError):
                continue
            if qty <= 0:
                continue
            sym = piece_sym.get(piece)
            if is_entry:
                if kb == "dip":
                    dip_fills += 1
                elif kb == "book":
                    book_fills += 1
                entry_qty[piece] = entry_qty.get(piece, 0.0) + qty
                entry_cost[piece] = entry_cost.get(piece, 0.0) + qty * px
                if sym:
                    entry_sym[piece] = sym
            else:
                exit_qty[piece] = exit_qty.get(piece, 0.0) + qty
                exit_px[piece] = exit_px.get(piece, 0.0) + qty * px
    else:
        for r in actions:
            if r.get("op") != "fill":
                continue
            link = r.get("link") or (r.get("payload") or {}).get("orderLinkId") or ""
            info = state_links.get(link)
            kb = None
            if info is not None:
                kb = info[2] if info[2] in ("dip", "book") else None
            if kb is None:
                kb = "book" if str(link).startswith("b") else \
                    "dip" if str(link).startswith("d") else None
            if kb == "dip":
                dip_fills += 1
            elif kb == "book":
                book_fills += 1

    # closed pieces: entry+exit seen and (ledger closed or exits cover entries)
    closed = []
    for piece in set(list(entry_qty) + list(exit_qty)):
        if entry_qty.get(piece, 0.0) <= 0 or exit_qty.get(piece, 0.0) <= 0:
            continue
        pc = ledger.get(piece) or {}
        if not (pc.get("qty", 0) == 0 or exit_qty[piece] >= entry_qty[piece] > 0):
            continue
        avg = entry_cost[piece] / entry_qty[piece]
        side = int(pc["side"]) if pc.get("side") in (1, -1) else 1
        pnl = side * (exit_px[piece] - avg * exit_qty[piece])
        closed.append((piece, pnl, piece_kind_of(piece, state_links, ledger)))

    def wr(rows):
        n = len(rows)
        w = sum(1 for _, p, _ in rows if p > 0)
        return {"n": n, "wins": w, "losses": n - w,
                "rate": (w / n) if n else None}

    wr_all = wr(closed)
    wr_dip = wr([r for r in closed if r[2] == "dip"])
    wr_book = wr([r for r in closed if r[2] == "book"])

    # open positions now (exchange truth; fallback ledger)
    open_pos, open_n = [], 0
    if isinstance(exchange, dict):
        for k, p in ((exchange or {}).get("pos") or {}).items():
            try:
                q = float((p or {}).get("qty", 0.0))
            except (TypeError, ValueError):
                q = 0.0
            if q > 0:
                open_pos.append(f"{k}:{q:g}")
        open_n = sum(1 for v in ledger.values()
                     if isinstance(v, dict) and (v.get("qty") or 0) > 0)
        if not open_pos:
            open_pos = [f"{pid}({(ledger[pid] or {}).get('symbol')}:{(ledger[pid] or {}).get('qty')})"
                        for pid in ledger
                        if isinstance(ledger.get(pid), dict) and ledger[pid].get("qty", 0) > 0]
    else:
        open_pos = [f"{pid}({(ledger[pid] or {}).get('symbol')}:{(ledger[pid] or {}).get('qty')})"
                    for pid in ledger
                    if isinstance(ledger.get(pid), dict) and ledger[pid].get("qty", 0) > 0]
        open_n = len(open_pos)

    cops = Counter(r.get("op") for r in actions)
    stale = int(cops.get("stale_plan", 0))
    plan_err = int(cops.get("plan_error", 0))
    errs = int(cops.get("error", 0) + cops.get("cycle_error", 0))

    fees = (exchange or {}).get("fees") if isinstance(exchange, dict) else None
    return {"dir": str(d), "name": name, "start": start_s,
            "curve_start": eq["start"].isoformat() if eq["start"] else "n/a",
            "curve_end": eq["end"].isoformat() if eq["end"] else "n/a",
            "curve_n": eq["n"], "equity_start": eq["start_eq"],
            "equity_now": eq["end_eq"], "return_pct": eq["return_pct"],
            "max_dd_pct": eq["max_dd_pct"], "dip_fills": dip_fills,
            "book_fills": book_fills, "wr_all": wr_all, "wr_dip": wr_dip,
            "wr_book": wr_book, "fees": fees, "open_n": open_n,
            "open_pos": open_pos, "stale_plan": stale,
            "plan_error": plan_err, "errors": errs, "flags": flags,
            "actions_total": len(actions)}


def _f2(v):
    return "n/a" if v is None else f"{v:,.2f}"


def _fp(v):
    return "n/a" if v is None else f"{v:.2f}%"


def _fwr(w):
    if w["n"] == 0:
        return "n/a (0 closed)"
    r = "n/a" if w["rate"] is None else f"{100.0 * w['rate']:.1f}%"
    return f"{r} ({w['wins']}/{w['n']})"


def rows_of(reps):
    return [
        ("start", lambda r: r["start"]),
        ("flags", lambda r: r["flags"]),
        ("equity now", lambda r: _f2(r["equity_now"])),
        ("return %", lambda r: _fp(r["return_pct"])),
        ("maxDD % (hourly curve)", lambda r: _fp(r["max_dd_pct"])),
        ("dip fills", lambda r: str(r["dip_fills"])),
        ("book fills", lambda r: str(r["book_fills"])),
        ("win rate all", lambda r: _fwr(r["wr_all"])),
        ("win rate dip", lambda r: _fwr(r["wr_dip"])),
        ("win rate book", lambda r: _fwr(r["wr_book"])),
        ("fees paid", lambda r: _f2(r["fees"])),
        ("open positions", lambda r: str(r["open_n"]) +
         ((" [" + ", ".join(r["open_pos"]) + "]") if r["open_pos"] else "")),
        ("stale_plan", lambda r: str(r["stale_plan"])),
        ("plan_error", lambda r: str(r["plan_error"])),
        ("errors", lambda r: str(r["errors"])),
    ]


def format_text(reps) -> str:
    rows = rows_of(reps)
    names = [r["name"] for r in reps]
    w0 = max([len("metric")] + [len(k) for k, _ in rows])
    widths = [max(len(n), max(len(fn(r)) for _, fn in rows)) for n, r in zip(names, reps)]
    head = " ".join(["metric".ljust(w0)] + [n.ljust(w) for n, w in zip(names, widths)])
    out = [head]
    for key, fn in rows:
        out.append(" ".join([key.ljust(w0)] + [fn(r).ljust(w) for r, w in zip(reps, widths)]))
    return "\n".join(out)


def format_markdown(reps) -> str:
    rows = rows_of(reps)
    names = [r["name"] for r in reps]
    out = ["| metric | " + " | ".join(names) + " |",
           "| --- | " + " | ".join("---" for _ in names) + " |"]
    for key, fn in rows:
        out.append("| " + key + " | " + " | ".join(fn(r) for r in reps) + " |")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Side-by-side report for paper bots.")
    ap.add_argument("dirs", nargs="+", help="bot state dirs")
    ap.add_argument("--md", default=None, help="write Markdown table to PATH")
    ap.add_argument("--json", nargs="?", const="-", default=None,
                    help="write JSON to PATH (bare --json prints to stdout)")
    a = ap.parse_args(argv)
    reps = [summarize_dir(Path(d)) for d in a.dirs]
    print(format_text(reps))
    if a.md:
        Path(a.md).write_text(format_markdown(reps) + "\n", encoding="utf-8")
        print(f"saved {a.md}")
    if a.json is not None:
        payload = json.dumps({"dirs": reps}, indent=1, default=str)
        if a.json == "-":
            print(payload)
        else:
            Path(a.json).write_text(payload + "\n", encoding="utf-8")
            print(f"saved {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
