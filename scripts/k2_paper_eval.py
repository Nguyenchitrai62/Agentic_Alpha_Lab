"""Offline evaluator: Kronos K2 dip tilt applied to a paper runner's REAL dip fills.

Joins closed dip pieces from a paper runner dir (actions.jsonl / exchange.json /
state.json, parsing reused from scripts/paper_report.py) to prospective Kronos
rows in artifacts/research/kronos_shadow/kronos_features_live.parquet on
(sym, shift=phase, T=holding-bar open decoded from the dip piece id
bot/mirror.py dip_pid). Counterfactual K2 P&L = k2_mult x piece net P&L,
normalised by the mean k2_mult of the joined prospective pieces (equal average
exposure).

Read-only: never touches processes, never writes into artifacts/.

Usage:
  python scripts/k2_paper_eval.py [--runner artifacts/bot/paper_d17bfg2]
    [--kronos artifacts/research/kronos_shadow/kronos_features_live.parquet]
    [--corrections artifacts/research/advisor_shadow/paper_corrections.json]
    [--json [out.json]]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]

# Reuse paper_report parsing (assignment requirement).
_PR_SPEC = importlib.util.spec_from_file_location(
    "paper_report", ROOT / "scripts" / "paper_report.py")
paper_report = importlib.util.module_from_spec(_PR_SPEC)
sys.modules["paper_report"] = paper_report
_PR_SPEC.loader.exec_module(paper_report)

MAKER, TAKER = 0.0002, 0.00055

DIP_PID_RE = re.compile(r"^d(\d+)(BTC|ETH|SOL|BNB|XRP)(\d+)([0-9a-z]+)$")
_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def t36_to_timestamp(s: str) -> pd.Timestamp:
    n = 0
    for ch in s:
        n = n * 36 + _B36.index(ch)
    return pd.Timestamp(n * 60, unit="s", tz="UTC")


def parse_dip_pid(pid: str):
    """Return (phase:int, symbol:str, rung:float, T:Timestamp) or None."""
    m = DIP_PID_RE.match(str(pid))
    if not m:
        return None
    try:
        phase = int(m.group(1))
        sym = m.group(2) + "USDT"
        rung = int(m.group(3)) / 10.0
        bar = t36_to_timestamp(m.group(4))
    except (ValueError, IndexError):
        return None
    return phase, sym, rung, bar


def ms_to_ts(ms) -> pd.Timestamp | None:
    try:
        return pd.Timestamp(int(ms), unit="ms", tz="UTC")
    except (TypeError, ValueError):
        return None


def fee_rate_for(link: str, state_links: dict) -> float:
    info = (state_links or {}).get(link)
    if info is not None:
        kind = info[0]
        if kind in ("entry", "tp", "add"):
            return MAKER
        if kind == "reduce":
            return TAKER  # dip market exits (X) and book market reduces
        if kind == "stop":
            return TAKER
    s = str(link)
    if s.endswith("E") or s.endswith("T"):
        return MAKER
    return TAKER


def build_exit_reasons(actions) -> tuple[dict, dict]:
    """Return (orderLinkId->reason, piece->last_reason) from market_exit actions."""
    by_link, by_piece = {}, {}
    for r in actions or []:
        if (r or {}).get("op") != "market_exit":
            continue
        reason = (r or {}).get("reason") or "market"
        payload = (r or {}).get("payload") or {}
        link = payload.get("orderLinkId")
        piece = (r or {}).get("piece")
        if link:
            by_link[str(link)] = str(reason)
        if piece:
            by_piece[str(piece)] = str(reason)
    return by_link, by_piece


def load_dip_pieces(runner: Path) -> list[dict]:
    """Closed dip pieces with entry/exit totals, gross/net P&L and timings.

    Parsing mirrors paper_report.summarize_dir: execs from exchange.json when
    present (else actions fill records), entry vs exit via classify_exec,
    side from the ledger. Fees: maker 0.0002 for entry/TP limits, taker
    0.00055 for stops/market exits (bot/paper.py). Net = gross - fees.
    """
    runner = Path(runner)
    actions = paper_report.load_actions(runner / "actions.jsonl")
    if actions is None:
        actions = []
    state = paper_report.load_json(runner / "state.json") or {}
    exchange = paper_report.load_json(runner / "exchange.json")
    ledger = state.get("ledger") or {}
    state_links = paper_report.load_state_links(state)
    reasons_by_link, reasons_by_piece = build_exit_reasons(actions)

    entry_qty, entry_cost, entry_time = {}, {}, {}
    entry_fees = defaultdict(float)
    exit_qty, exit_val, exit_time = {}, {}, {}
    exit_fees = defaultdict(float)
    exit_links: dict[str, list] = defaultdict(list)

    execs = (exchange or {}).get("execs") if isinstance(exchange, dict) else None
    if execs:
        for e in execs:
            link = str(e.get("orderLinkId", ""))
            is_entry, kb, piece = paper_report.classify_exec(link, state_links)
            try:
                qty, px = float(e["execQty"]), float(e["execPrice"])
            except (TypeError, ValueError, KeyError):
                continue
            if qty <= 0:
                continue
            ts = ms_to_ts(e.get("execTime"))
            rate = fee_rate_for(link, state_links)
            if is_entry:
                entry_qty[piece] = entry_qty.get(piece, 0.0) + qty
                entry_cost[piece] = entry_cost.get(piece, 0.0) + qty * px
                entry_fees[piece] += qty * px * rate
                if ts is not None and (piece not in entry_time or ts < entry_time[piece]):
                    entry_time[piece] = ts
            else:
                exit_qty[piece] = exit_qty.get(piece, 0.0) + qty
                exit_val[piece] = exit_val.get(piece, 0.0) + qty * px
                exit_fees[piece] += qty * px * rate
                exit_links[piece].append(link)
                if ts is not None and (piece not in exit_time or ts > exit_time[piece]):
                    exit_time[piece] = ts
    else:
        for r in actions:
            if (r or {}).get("op") != "fill":
                continue
            link = str((r or {}).get("link") or "")
            is_entry, kb, piece = paper_report.classify_exec(link, state_links)
            try:
                qty, px = float(r["qty"]), float(r["price"])
            except (TypeError, ValueError, KeyError):
                continue
            if qty <= 0:
                continue
            ts = paper_report.parse_ts(r.get("t"))
            rate = fee_rate_for(link, state_links)
            if is_entry:
                entry_qty[piece] = entry_qty.get(piece, 0.0) + qty
                entry_cost[piece] = entry_cost.get(piece, 0.0) + qty * px
                entry_fees[piece] += qty * px * rate
                if ts is not None and (piece not in entry_time or ts < entry_time[piece]):
                    entry_time[piece] = ts
            else:
                exit_qty[piece] = exit_qty.get(piece, 0.0) + qty
                exit_val[piece] = exit_val.get(piece, 0.0) + qty * px
                exit_fees[piece] += qty * px * rate
                exit_links[piece].append(link)
                if ts is not None and (piece not in exit_time or ts > exit_time[piece]):
                    exit_time[piece] = ts

    pieces = []
    for piece in set(list(entry_qty) + list(exit_qty)):
        if paper_report.piece_kind_of(piece, state_links, ledger) != "dip":
            continue
        eq, xq = entry_qty.get(piece, 0.0), exit_qty.get(piece, 0.0)
        if eq <= 0 or xq <= 0:
            continue  # open or entry-less; no realised P&L
        pc = ledger.get(piece) or {}
        if not (pc.get("qty", 0) == 0 or xq >= eq > 0):
            continue  # still open
        parsed = parse_dip_pid(piece)
        if parsed is not None:
            phase, sym, rung, bar = parsed
        else:
            try:
                phase = int(pc.get("phase"))
            except (TypeError, ValueError):
                continue
            sym = pc.get("symbol")
            if sym is None:
                continue
            rung, bar = None, None
        side = int(pc["side"]) if pc.get("side") in (1, -1) else 1
        avg = entry_cost[piece] / eq
        gross = side * (exit_val[piece] - avg * xq)
        fees = entry_fees.get(piece, 0.0) + exit_fees.get(piece, 0.0)
        links = exit_links.get(piece, [])
        if any(str(v).endswith("T") for v in links):
            reason = "take_profit"
        elif any(str(v).endswith("S") for v in links):
            reason = "stop"
        else:
            reason = None
            for v in links:
                if v in reasons_by_link:
                    reason = reasons_by_link[v]
                    break
            if reason is None:
                reason = reasons_by_piece.get(str(piece), "market")
        try:
            fill_px = entry_cost[piece] / eq
        except ZeroDivisionError:
            fill_px = None
        try:
            exit_px = exit_val[piece] / xq if xq else None
        except ZeroDivisionError:
            exit_px = None
        pieces.append({
            "piece": piece, "symbol": sym, "phase": int(phase),
            "rung": rung, "T": bar,
            "fill_qty": eq, "fill_price": fill_px,
            "entry_time": entry_time.get(piece),
            "exit_qty": xq, "exit_price": exit_px,
            "exit_time": exit_time.get(piece), "exit_reason": reason,
            "pnl_gross": gross, "fees": fees, "pnl": gross - fees,
        })
    return pieces


def load_kronos(path: Path) -> dict:
    """Map (sym, shift, T) -> {'k2_mult': float, 'prospective': bool} (prefer prospective)."""
    df = pd.read_parquet(path)
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
            k2 = float(r["k2_mult"])
        except (KeyError, TypeError, ValueError):
            continue
        if "mode" in df.columns:
            prosp = str(r.get("mode")) == "prospective"
        else:
            prosp = bool(r.get("is_prospective", False))
        key = (sym, shift, t.isoformat())
        prev = out.get(key)
        if prev is None or (prosp and not prev["prospective"]):
            out[key] = {"k2_mult": k2, "prospective": prosp}
    return out


def week_start(t) -> str | None:
    try:
        ts = pd.Timestamp(t)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    monday = (ts - pd.Timedelta(days=ts.weekday())).floor("D")
    return monday.date().isoformat()


def evaluate(runner, kronos_path, corrections_path=None) -> dict:
    runner = Path(runner)
    pieces = load_dip_pieces(runner)
    kronos = load_kronos(kronos_path)
    corrections = paper_report.load_corrections(
        Path(corrections_path) if corrections_path else None)
    windows = paper_report.windows_for_dir(corrections, runner.name)

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

    excluded, evaluable = [], []
    for p in pieces:
        if in_window(p.get("exit_time")):
            excluded.append(p)
        else:
            evaluable.append(p)

    joined, joined_other, unjoined = [], [], []
    for p in evaluable:
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
        row = kronos.get(key) if key else None
        if row is None:
            unjoined.append(p)
        elif row["prospective"]:
            joined.append({**p, "k2_mult": row["k2_mult"]})
        else:
            joined_other.append({**p, "k2_mult": row["k2_mult"]})

    if joined:
        mean_k2 = sum(p["k2_mult"] for p in joined) / len(joined)
    else:
        mean_k2 = None
    base_sum, k2_sum = 0.0, 0.0
    for p in joined:
        p["k2_pnl"] = p["pnl"] * p["k2_mult"] / mean_k2 if mean_k2 else None
        base_sum += p["pnl"]
        k2_sum += p["k2_pnl"]
    by_coin: dict[str, dict] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "k2_pnl": 0.0})
    by_week: dict[str, dict] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "k2_pnl": 0.0})
    for p in joined:
        c = by_coin[p["symbol"]]
        c["n"] += 1
        c["pnl"] += p["pnl"]
        c["k2_pnl"] += p["k2_pnl"]
        w = week_start(p.get("T")) or "n/a"
        b = by_week[w]
        b["n"] += 1
        b["pnl"] += p["pnl"]
        b["k2_pnl"] += p["k2_pnl"]

    return {
        "runner": str(runner),
        "kronos_path": str(kronos_path),
        "n_closed_dip": len(pieces),
        "n_excluded_correction": len(excluded),
        "excluded_pnl": sum(p["pnl"] for p in excluded),
        "n_evaluable": len(evaluable),
        "n_joined_prospective": len(joined),
        "n_joined_nonprospective": len(joined_other),
        "joined_nonprospective_pnl": sum(p["pnl"] for p in joined_other),
        "n_unjoined": len(unjoined),
        "unjoined_pnl": sum(p["pnl"] for p in unjoined),
        "mean_k2": mean_k2,
        "sum_pnl": base_sum,
        "sum_k2_pnl": k2_sum,
        "diff": (k2_sum - base_sum) if joined else 0.0,
        "by_coin": dict(sorted(by_coin.items())),
        "by_week": dict(sorted(by_week.items())),
        "windows": [f"{s.isoformat()}..{e.isoformat()}" for s, e in windows],
    }


def format_text(res: dict) -> str:
    L = [
        f"runner: {res['runner']}",
        f"closed dip pieces: {res['n_closed_dip']} "
        f"(excluded correction: {res['n_excluded_correction']} pnl {res['excluded_pnl']:+.2f}; "
        f"evaluable: {res['n_evaluable']})",
        f"joined prospective: {res['n_joined_prospective']} | "
        f"joined late/backfill (apart): {res['n_joined_nonprospective']} "
        f"(pnl {res['joined_nonprospective_pnl']:+.2f}) | "
        f"unjoined (no kronos row): {res['n_unjoined']} "
        f"(pnl {res['unjoined_pnl']:+.2f})",
        f"correction windows: {', '.join(res['windows']) or 'none'}",
    ]
    if res["n_joined_prospective"]:
        L.append(f"mean k2_mult: {res['mean_k2']:.4f}")
        L.append(f"sum P&L (net, USDT): {res['sum_pnl']:+.2f}")
        L.append(f"sum K2 P&L normalised (net, USDT): {res['sum_k2_pnl']:+.2f}")
        L.append(f"difference K2-base: {res['diff']:+.2f}")
        L.append("per coin (n, pnl, k2_pnl): " + "; ".join(
            f"{k}: n={v['n']} {v['pnl']:+.2f}/{v['k2_pnl']:+.2f}"
            for k, v in res["by_coin"].items()))
        L.append("per week (T week, n, pnl, k2_pnl): " + "; ".join(
            f"{k}: n={v['n']} {v['pnl']:+.2f}/{v['k2_pnl']:+.2f}"
            for k, v in res["by_week"].items()))
    else:
        L.append("no prospective-joined pieces: K2 counterfactual n/a (sample too small).")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="K2 dip tilt offline evaluator.")
    ap.add_argument("--runner", default=str(ROOT / "artifacts/bot/paper_d17bfg2"))
    ap.add_argument("--kronos", default=str(
        ROOT / "artifacts/research/kronos_shadow/kronos_features_live.parquet"))
    ap.add_argument("--corrections", default=str(
        ROOT / "artifacts/research/advisor_shadow/paper_corrections.json"))
    ap.add_argument("--json", nargs="?", const="-", default=None,
                    help="write JSON to PATH (bare --json prints to stdout)")
    a = ap.parse_args(argv)
    res = evaluate(Path(a.runner), Path(a.kronos),
                   Path(a.corrections) if a.corrections else None)
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
