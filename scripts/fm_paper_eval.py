"""Weekly prospective FM evaluation: K2 (Kronos) / C2 (Chronos) dip tilt vs untitled twin.

Generalises scripts/k2_paper_eval.py (parsing for closed dip pieces is reused
from it verbatim via import; its CLI is untouched) to both feeds behind
``--feed {kronos, chronos}``:

  kronos : runner paper_d17bfg2k2, feed kronos_shadow, mult column k2_mult
  chronos: runner paper_d17bfg2ch, feed chronos_shadow, mult column c2_mult
           (chronos_shadow writes k2_mult as an exact copy of c2_mult so the
           bot flag works unchanged; the evaluator prefers c2_mult and falls
           back to k2_mult when c2_mult is absent)

For the tilt runner and its twin paper_d17bfg2 (no tilt) it reports:

(1) realised prospective comparison over COMMON uptime only (intersection of
    the two hourly equity curves): return %, max DD %, dip/book entry fills
    and closed-piece win rates restricted to that window;
(2) the counterfactual on the TWIN's own closed dip fills:
    sum(mult x piece net P&L) / mean(mult) vs sum(piece net P&L), joining on
    (sym, shift=phase, T) and using ONLY feed rows with
    mode in {prospective, late} AND is_prospective true (backfill rows never
    join, so no backfilled lookahead leaks in);
(3) a bootstrap CI over weeks (resample whole weeks with replacement);
(4) data-quality counters: twin pieces with no feed row, feed rows present
    but non-qualifying, k2_missing / k2_mult ops, outage gaps in the equity
    curve (> 125 min between hourly points), stale_plan ops span.

Read-only: never touches processes, never writes into artifacts/.

Usage:
  python scripts/fm_paper_eval.py --feed kronos [--json out.json]
  python scripts/fm_paper_eval.py --feed chronos [--json out.json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]


def _load_module(name: str, path: Path):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Reuse parsing (assignment requirement: generalise, do not fork the logic).
k2eval = _load_module("k2_paper_eval", ROOT / "scripts" / "k2_paper_eval.py")
paper_report = _load_module("paper_report", ROOT / "scripts" / "paper_report.py")

ALLOWED_MODES = ("prospective", "late")
OUTAGE_GAP_MIN = 125.0  # equity-curve steps are hourly; >125 min = a missed cycle run

FEEDS = {
    "kronos": {
        "runner": "paper_d17bfg2k2",
        "feed_rel": Path("artifacts/research/kronos_shadow/kronos_features_live.parquet"),
        "mult_col": "k2_mult",
    },
    "chronos": {
        "runner": "paper_d17bfg2ch",
        "feed_rel": Path("artifacts/research/chronos_shadow/chronos_features_live.parquet"),
        "mult_col": "c2_mult",
    },
}
TWIN_DEFAULT = "paper_d17bfg2"


def resolve_config(feed: str, runner=None, twin=None, feed_path=None,
                   mult_col=None) -> dict:
    if feed not in FEEDS:
        raise ValueError(f"--feed must be one of {sorted(FEEDS)} (got {feed!r})")
    cfg = FEEDS[feed]
    runner_p = Path(runner) if runner else ROOT / "artifacts/bot" / cfg["runner"]
    twin_p = Path(twin) if twin else ROOT / "artifacts/bot" / TWIN_DEFAULT
    feed_p = Path(feed_path) if feed_path else ROOT / cfg["feed_rel"]
    return {"feed": feed, "runner": runner_p, "twin": twin_p,
            "feed_path": feed_p, "mult_col": mult_col or cfg["mult_col"]}


def load_feed(path: Path, mult_col: str) -> tuple[dict, dict]:
    """Map (sym, shift, T_iso) -> {'mult', 'mode', 'is_prospective', 'qualified'}.

    A row qualifies iff mode in {prospective, late} AND is_prospective.
    Fallbacks when columns are absent: no is_prospective column -> fall back
    to mode == 'prospective' (k2_paper_eval semantics); no mode column ->
    fall back to bool(is_prospective). The mult column falls back to the
    other known tilt column (c2_mult <-> k2_mult). Duplicate keys prefer the
    qualifying row.
    """
    df = pd.read_parquet(path)
    cols = set(df.columns)
    mcol = mult_col if mult_col in cols else (
        "k2_mult" if "k2_mult" in cols else
        ("c2_mult" if "c2_mult" in cols else mult_col))
    if mcol not in cols:
        if len(df) == 0:
            # empty feed (tilt not started yet): no keys, nothing joins.
            return {}, {"mult_col_used": mult_col, "n_rows": 0, "n_qualified": 0}
        raise KeyError(f"mult column {mult_col!r} (or fallback) not in {path}")
    has_mode = "mode" in cols
    has_prosp = "is_prospective" in cols
    out: dict = {}
    for _, r in df.iterrows():
        try:
            sym = str(r["sym"])
            shift = int(r["shift"])
            t = pd.Timestamp(r["T"])
            if t.tzinfo is None:
                t = t.tz_localize("UTC")
            else:
                t = t.tz_convert("UTC")
        except (KeyError, TypeError, ValueError):
            continue
        try:
            mult = float(r[mcol])
        except (KeyError, TypeError, ValueError):
            continue
        mode = str(r["mode"]).strip().lower() if has_mode else ""
        try:
            prosp = bool(r["is_prospective"]) if has_prosp else None
        except (TypeError, ValueError):
            prosp = None
        if has_mode and has_prosp:
            qualified = (mode in ALLOWED_MODES) and bool(prosp)
        elif has_mode:
            qualified = (mode == "prospective")
        elif has_prosp:
            qualified = bool(prosp)
        else:
            qualified = True
        key = (sym, shift, t.isoformat())
        prev = out.get(key)
        if prev is None or (qualified and not prev["qualified"]):
            out[key] = {"mult": mult, "mode": mode,
                        "is_prospective": prosp, "qualified": qualified}
    meta = {"mult_col_used": mcol, "n_rows": len(df),
            "n_qualified": sum(1 for v in out.values() if v["qualified"])}
    return out, meta


def read_curve(runner: Path) -> list:
    ex = paper_report.load_json(Path(runner) / "exchange.json") or {}
    pts = []
    for row in ex.get("equity_curve") or []:
        try:
            t, v = paper_report.parse_ts(row[0]), float(row[1])
        except (TypeError, ValueError, IndexError):
            continue
        if t is not None:
            pts.append((t, v))
    pts.sort(key=lambda p: p[0])
    return pts


def common_window(a: list, b: list):
    if not a or not b:
        return None
    lo = max(a[0][0], b[0][0])
    hi = min(a[-1][0], b[-1][0])
    if hi <= lo:
        return None
    return lo, hi


def restrict(pts: list, lo, hi) -> list:
    return [(t, v) for t, v in pts if lo <= t <= hi]


def count_entry_fills(runner: Path, lo, hi) -> dict:
    """Dip/book entry fills with execution time inside [lo, hi]."""
    runner = Path(runner)
    state = paper_report.load_json(runner / "state.json") or {}
    exchange = paper_report.load_json(runner / "exchange.json")
    state_links = paper_report.load_state_links(state)
    dip = book = 0

    def in_w(ts) -> bool:
        return ts is not None and lo <= ts <= hi

    execs = (exchange or {}).get("execs") if isinstance(exchange, dict) else None
    if execs:
        for e in execs:
            link = str(e.get("orderLinkId", ""))
            is_entry, kb, _piece = paper_report.classify_exec(link, state_links)
            if not is_entry:
                continue
            if not in_w(k2eval.ms_to_ts(e.get("execTime"))):
                continue
            if kb == "dip":
                dip += 1
            elif kb == "book":
                book += 1
    else:
        actions = paper_report.load_actions(runner / "actions.jsonl") or []
        for r in actions:
            if (r or {}).get("op") != "fill":
                continue
            link = str((r or {}).get("link") or "")
            is_entry, kb, _p = paper_report.classify_exec(link, state_links)
            if not is_entry or not in_w(paper_report.parse_ts((r or {}).get("t"))):
                continue
            if kb == "dip":
                dip += 1
            elif kb == "book":
                book += 1
    return {"dip": dip, "book": book}


def load_closed_book(runner: Path) -> list[dict]:
    """Closed book pieces (mirror of k2eval.load_dip_pieces for kind == 'book')."""
    runner = Path(runner)
    actions = paper_report.load_actions(runner / "actions.jsonl") or []
    state = paper_report.load_json(runner / "state.json") or {}
    exchange = paper_report.load_json(runner / "exchange.json")
    ledger = state.get("ledger") or {}
    state_links = paper_report.load_state_links(state)

    entry_qty, entry_cost = {}, {}
    exit_qty, exit_val = {}, {}
    entry_fees, exit_fees = defaultdict(float), defaultdict(float)
    exit_time: dict = {}

    execs = (exchange or {}).get("execs") if isinstance(exchange, dict) else None
    if execs:
        for e in execs:
            link = str(e.get("orderLinkId", ""))
            is_entry, _kb, piece = paper_report.classify_exec(link, state_links)
            try:
                qty, px = float(e["execQty"]), float(e["execPrice"])
            except (TypeError, ValueError, KeyError):
                continue
            if qty <= 0:
                continue
            ts = k2eval.ms_to_ts(e.get("execTime"))
            rate = k2eval.fee_rate_for(link, state_links)
            if is_entry:
                entry_qty[piece] = entry_qty.get(piece, 0.0) + qty
                entry_cost[piece] = entry_cost.get(piece, 0.0) + qty * px
                entry_fees[piece] += qty * px * rate
            else:
                exit_qty[piece] = exit_qty.get(piece, 0.0) + qty
                exit_val[piece] = exit_val.get(piece, 0.0) + qty * px
                exit_fees[piece] += qty * px * rate
                if ts is not None and (piece not in exit_time or ts > exit_time[piece]):
                    exit_time[piece] = ts

    out = []
    for piece in set(list(entry_qty) + list(exit_qty)):
        if paper_report.piece_kind_of(piece, state_links, ledger) != "book":
            continue
        eq, xq = entry_qty.get(piece, 0.0), exit_qty.get(piece, 0.0)
        if eq <= 0 or xq <= 0:
            continue
        pc = ledger.get(piece) or {}
        if not (pc.get("qty", 0) == 0 or xq >= eq > 0):
            continue
        side = int(pc["side"]) if pc.get("side") in (1, -1) else 1
        avg = entry_cost[piece] / eq
        gross = side * (exit_val[piece] - avg * xq)
        fees = entry_fees.get(piece, 0.0) + exit_fees.get(piece, 0.0)
        out.append({"piece": piece, "exit_time": exit_time.get(piece),
                    "pnl": gross - fees})
    return out


def realised_stats(runner: Path, lo, hi, corrections) -> dict:
    curve = read_curve(runner)
    win = restrict(curve, lo, hi)
    stats = paper_report.equity_stats([[t.isoformat(), v] for t, v in win])
    windows = paper_report.windows_for_dir(corrections, Path(runner).name)
    raw, corr, excl = paper_report.corrected_return(
        [[t.isoformat(), v] for t, v in win], windows)
    fills = count_entry_fills(runner, lo, hi)

    def in_w(ts) -> bool:
        try:
            t = pd.Timestamp(ts)
        except (TypeError, ValueError):
            return False
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        return lo <= t <= hi

    dip_closed = [p for p in k2eval.load_dip_pieces(runner) if in_w(p.get("exit_time"))]
    book_closed = [p for p in load_closed_book(runner) if in_w(p.get("exit_time"))]

    def wr(rows):
        n = len(rows)
        w = sum(1 for p in rows if p["pnl"] > 0)
        return {"n": n, "wins": w, "losses": n - w,
                "rate": (w / n) if n else None,
                "pnl": sum(p["pnl"] for p in rows)}

    return {"curve_points": len(win),
            "return_pct": stats["return_pct"], "max_dd_pct": stats["max_dd_pct"],
            "return_pct_raw": raw, "return_pct_corrected": corr,
            "excluded_days": excl,
            "dip_fills": fills["dip"], "book_fills": fills["book"],
            "wr_dip": wr(dip_closed), "wr_book": wr(book_closed)}


def counterfactual(twin: Path, feedmap: dict, corrections) -> dict:
    pieces = k2eval.load_dip_pieces(twin)
    windows = paper_report.windows_for_dir(corrections, Path(twin).name)

    def in_window(ts) -> bool:
        if ts is None:
            return False
        try:
            t = pd.Timestamp(ts)
        except (TypeError, ValueError):
            return False
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        for ws, we in windows:
            if ws <= t <= we:
                return True
        return False

    excluded = [p for p in pieces if in_window(p.get("exit_time"))]
    evaluable = [p for p in pieces if not in_window(p.get("exit_time"))]

    joined, nonqual, unjoined = [], [], []
    for p in evaluable:
        key = None
        t = p.get("T")
        if t is not None:
            try:
                ts = pd.Timestamp(t)
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                else:
                    ts = ts.tz_convert("UTC")
                key = (p["symbol"], int(p["phase"]), ts.isoformat())
            except (TypeError, ValueError):
                key = None
        row = feedmap.get(key) if key else None
        if row is None:
            unjoined.append(p)
        elif row["qualified"]:
            joined.append({**p, "mult": row["mult"]})
        else:
            nonqual.append(p)

    mean_m = (sum(p["mult"] for p in joined) / len(joined)) if joined else None
    base_sum = sum(p["pnl"] for p in joined)
    tilt_sum = (sum(p["pnl"] * p["mult"] for p in joined) / mean_m
                if joined and mean_m else 0.0)
    by_coin: dict[str, dict] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "tilt_pnl": 0.0})
    by_week: dict[str, dict] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "tilt_pnl": 0.0})
    for p in joined:
        tp = p["pnl"] * p["mult"] / mean_m if mean_m else 0.0
        c = by_coin[p["symbol"]]
        c["n"] += 1
        c["pnl"] += p["pnl"]
        c["tilt_pnl"] += tp
        w = k2eval.week_start(p.get("T")) or "n/a"
        b = by_week[w]
        b["n"] += 1
        b["pnl"] += p["pnl"]
        b["tilt_pnl"] += tp
    return {
        "n_closed_dip": len(pieces),
        "n_excluded_correction": len(excluded),
        "excluded_pnl": sum(p["pnl"] for p in excluded),
        "n_evaluable": len(evaluable),
        "n_joined": len(joined),
        "n_nonqualifying_feed_row": len(nonqual),
        "n_missing_feed_row": len(unjoined),
        "missing_feed_pnl": sum(p["pnl"] for p in unjoined),
        "mean_mult": mean_m,
        "sum_pnl": base_sum,
        "sum_tilt_pnl": tilt_sum,
        "diff": (tilt_sum - base_sum) if joined else 0.0,
        "by_coin": dict(sorted(by_coin.items())),
        "by_week": dict(sorted(by_week.items())),
        "windows": [f"{s.isoformat()}..{e.isoformat()}" for s, e in windows],
    }


def bootstrap_ci(joined_weeks: dict, boot: int, seed: int) -> dict:
    """Week-block bootstrap of the tilt-vs-base diff. Deterministic on seed."""
    weeks = sorted(joined_weeks)
    if len(weeks) < 2:
        return {"n_weeks": len(weeks), "boot": boot, "seed": seed,
                "status": "n/a (need >= 2 weeks with joined pieces)"}
    rng = random.Random(seed)
    diffs = []
    for _ in range(boot):
        pool = []
        for _ in weeks:
            pool.extend(joined_weeks[rng.choice(weeks)])
        if not pool:
            diffs.append(0.0)
            continue
        mm = sum(m for _, m in pool) / len(pool)
        base = sum(p for p, _ in pool)
        tilt = sum(p * m for p, m in pool) / mm if mm else base
        diffs.append(tilt - base)
    diffs.sort()
    q = lambda x: diffs[min(boot - 1, max(0, int(x * boot)))]
    return {"n_weeks": len(weeks), "boot": boot, "seed": seed,
            "status": "ok",
            "mean": sum(diffs) / len(diffs),
            "ci_lo": q(0.025), "ci_hi": q(0.975),
            "p_pos": sum(1 for d in diffs if d > 0) / len(diffs)}


def quality_counters(runner: Path, curve: list) -> dict:
    actions = paper_report.load_actions(Path(runner) / "actions.jsonl") or []
    ops = Counter((r or {}).get("op") for r in actions)
    stale_ts = sorted({str((r or {}).get("generated_at"))
                       for r in actions if (r or {}).get("op") == "stale_plan"})
    stale_times = [paper_report.parse_ts((r or {}).get("t"))
                   for r in actions if (r or {}).get("op") == "stale_plan"]
    stale_times = [t for t in stale_times if t is not None]
    stale_span_h = ((max(stale_times) - min(stale_times)).total_seconds() / 3600
                    if len(stale_times) >= 2 else 0.0)
    gaps = 0
    gap_h = 0.0
    for (t0, _), (t1, _) in zip(curve[:-1], curve[1:]):
        dt_min = (t1 - t0).total_seconds() / 60
        if dt_min > OUTAGE_GAP_MIN:
            gaps += 1
            gap_h += dt_min / 60
    return {"actions_total": len(actions),
            "k2_missing_ops": int(ops.get("k2_missing", 0)),
            "k2_mult_ops": int(ops.get("k2_mult", 0)),
            "stale_plan_ops": int(ops.get("stale_plan", 0)),
            "stale_plan_versions": len(stale_ts),
            "stale_span_hours": stale_span_h,
            "outage_gaps": gaps, "outage_gap_hours": gap_h}


def evaluate(feed, runner=None, twin=None, feed_path=None,
             corrections_path=None, boot: int = 2000, seed: int = 0,
             mult_col=None) -> dict:
    cfg = resolve_config(feed, runner, twin, feed_path, mult_col)
    runner_p, twin_p, feed_p = cfg["runner"], cfg["twin"], cfg["feed_path"]
    feedmap, feedmeta = load_feed(feed_p, cfg["mult_col"])
    corrections = paper_report.load_corrections(
        Path(corrections_path) if corrections_path else None)

    rc, tc = read_curve(runner_p), read_curve(twin_p)
    window = common_window(rc, tc)
    if window is None:
        realised = {"status": "n/a (no overlapping equity-curve uptime)",
                    "runner": None, "twin": None}
        common = None
    else:
        lo, hi = window
        common = {"start": lo.isoformat(), "end": hi.isoformat(),
                  "hours": (hi - lo).total_seconds() / 3600}
        realised = {"status": "ok",
                    "runner": realised_stats(runner_p, lo, hi, corrections),
                    "twin": realised_stats(twin_p, lo, hi, corrections)}

    cf = counterfactual(twin_p, feedmap, corrections)
    # rebuild week pools from the joined set (exact piece-level mapping)
    joined_weeks: dict[str, list] = defaultdict(list)
    pieces = k2eval.load_dip_pieces(twin_p)
    wmap_windows = paper_report.windows_for_dir(corrections, twin_p.name)

    def _in_w(ts) -> bool:
        if ts is None:
            return False
        try:
            t = pd.Timestamp(ts)
        except (TypeError, ValueError):
            return False
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        return any(ws <= t <= we for ws, we in wmap_windows)

    for p in pieces:
        if _in_w(p.get("exit_time")):
            continue
        t = p.get("T")
        key = None
        if t is not None:
            try:
                ts = pd.Timestamp(t)
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                else:
                    ts = ts.tz_convert("UTC")
                key = (p["symbol"], int(p["phase"]), ts.isoformat())
            except (TypeError, ValueError):
                key = None
        row = feedmap.get(key) if key else None
        if row is not None and row["qualified"]:
            joined_weeks[k2eval.week_start(p.get("T")) or "n/a"].append(
                (p["pnl"], row["mult"]))
    ci = bootstrap_ci(dict(joined_weeks), boot, seed)

    # feed T coverage
    try:
        df = pd.read_parquet(feed_p, columns=["T"])
        fts = pd.to_datetime(df["T"], utc=True)
        feed_cov = {"t_min": fts.min().isoformat(), "t_max": fts.max().isoformat()}
    except Exception:
        feed_cov = {"t_min": None, "t_max": None}

    return {
        "feed": feed, "mult_col": feedmeta["mult_col_used"],
        "runner": str(runner_p), "twin": str(twin_p),
        "feed_path": str(feed_p),
        "feed_rows": feedmeta["n_rows"], "feed_qualified_keys": feedmeta["n_qualified"],
        "feed_coverage": feed_cov,
        "common_uptime": common,
        "realised": realised,
        "counterfactual": cf,
        "bootstrap": ci,
        "quality": {"runner": quality_counters(runner_p, rc),
                    "twin": quality_counters(twin_p, tc)},
    }


def _f2(v):
    return "n/a" if v is None else f"{v:,.2f}"


def _fp(v):
    return "n/a" if v is None else f"{v:.2f}%"


def _fwr(w):
    if w is None or w["n"] == 0:
        return "n/a (0 closed)"
    r = "n/a" if w["rate"] is None else f"{100.0 * w['rate']:.1f}%"
    return f"{r} ({w['wins']}/{w['n']}, pnl {w['pnl']:+.2f})"


def format_text(res: dict) -> str:
    L = [f"feed: {res['feed']} (mult col {res['mult_col']})",
         f"runner: {res['runner']}",
         f"twin:   {res['twin']}"]
    cu = res["common_uptime"]
    if cu is None:
        L.append("common uptime: n/a (no overlapping equity curves)")
    else:
        L.append(f"common uptime: {cu['start']} .. {cu['end']} ({cu['hours']:.1f}h)")
        for who in ("runner", "twin"):
            s = res["realised"][who]
            L.append(
                f"{who}: return { _fp(s['return_pct'])} "
                f"(corrected {_fp(s['return_pct_corrected'])}, "
                f"excl {s['excluded_days']:.2f}d) DD {_fp(s['max_dd_pct'])} "
                f"fills dip/book {s['dip_fills']}/{s['book_fills']} "
                f"win dip {_fwr(s['wr_dip'])} win book {_fwr(s['wr_book'])} "
                f"[{s['curve_points']} pts]")
    cf = res["counterfactual"]
    L.append(
        f"counterfactual on twin fills: joined {cf['n_joined']} "
        f"(evaluable {cf['n_evaluable']}, missing feed {cf['n_missing_feed_row']}, "
        f"non-qualifying {cf['n_nonqualifying_feed_row']})")
    if cf["n_joined"]:
        L.append(f"mean mult: {cf['mean_mult']:.4f}")
        L.append(f"sum P&L (net, USDT): {cf['sum_pnl']:+.2f}")
        L.append(f"sum tilt P&L normalised (net, USDT): {cf['sum_tilt_pnl']:+.2f}")
        L.append(f"difference tilt-base: {cf['diff']:+.2f}")
    else:
        L.append("no joined pieces: tilt counterfactual n/a (sample too small).")
    b = res["bootstrap"]
    if b["status"] == "ok":
        L.append(f"bootstrap over {b['n_weeks']} weeks x{b['boot']} "
                 f"(seed {b['seed']}): mean {b['mean']:+.2f} "
                 f"95% CI [{b['ci_lo']:+.2f}, {b['ci_hi']:+.2f}] "
                 f"P(diff>0) {b['p_pos']:.2f}")
    else:
        L.append(f"bootstrap: {b['status']}")
    for who in ("runner", "twin"):
        q = res["quality"][who]
        L.append(f"quality {who}: k2_missing {q['k2_missing_ops']}, "
                 f"k2_mult {q['k2_mult_ops']}, stale_plan {q['stale_plan_ops']} "
                 f"({q['stale_plan_versions']} versions, {q['stale_span_hours']:.1f}h), "
                 f"outage gaps {q['outage_gaps']} ({q['outage_gap_hours']:.1f}h)")
    L.append(f"feed rows: {res['feed_rows']} qualified keys {res['feed_qualified_keys']} "
             f"coverage {res['feed_coverage']['t_min']} .. {res['feed_coverage']['t_max']}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FM dip-tilt prospective evaluator.")
    ap.add_argument("--feed", choices=sorted(FEEDS), default="kronos")
    ap.add_argument("--runner", default=None)
    ap.add_argument("--twin", default=None)
    ap.add_argument("--feed-path", default=None)
    ap.add_argument("--mult-col", default=None)
    ap.add_argument("--corrections", default=str(
        ROOT / "artifacts/research/advisor_shadow/paper_corrections.json"))
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", nargs="?", const="-", default=None,
                    help="write JSON to PATH (bare --json prints to stdout)")
    a = ap.parse_args(argv)
    res = evaluate(a.feed, a.runner, a.twin, a.feed_path, a.corrections,
                   a.boot, a.seed, a.mult_col)
    print(format_text(res))
    if a.json is not None:
        payload = json.dumps(res, indent=1, default=str)
        if a.json == "-":
            print(payload)
        else:
            Path(a.json).write_text(payload + "\n", encoding="utf-8")
            print(f"saved {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
