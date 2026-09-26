"""Prospective advisory-log paper scorer (research only, no orders).

Scores `artifacts/research/advisor_shadow/shadow.jsonl` as paper trading, per
candidate, under the research execution convention:

- A row decided at 4h bar close T holds from the open of the next 4h bar
  (T + 1 ms) until the next logged decision of the same candidate replaces it.
- Returns come from Binance USD-M 4h opens (perp legs) and Binance spot 4h
  opens (spot legs), both public REST, no keys.
- Costs: 0.0002 per unit of weight change. Long funding 0.00005 per 4h bar on
  long perp gross; short funding is zero.
- A candidate gap (missing decision bar) keeps the previous weights.
- Candidates whose `note` contains "UNGOVERNED" also get a governed version
  with weights multiplied by g = clip((0.20 - DD)/0.10, 0, 1), where DD is the
  paper (governed) equity drawdown from its 90-day peak lagged 2 bars
  (v110 rule: 90d = 540 4h bars, g = 1 for the first 2 scored bars).

The scoring core (`extract_weights`, `parse_decisions`, `score_candidate`,
`governor_multiplier`) is network-free so tests can use synthetic logs/prices.

Usage:
    .venv/Scripts/python.exe scripts/forward_scorer.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "artifacts/research/advisor_shadow/shadow.jsonl"
OUT_PATH = ROOT / "artifacts/research/advisor_shadow/forward_score.json"

COST_PER_UNIT = 0.0002
LONG_FUNDING_PER_BAR = 0.00005
GOV_WINDOW_BARS = 90 * 6  # 90 days of 4h bars
GOV_CAP = 0.20
GOV_BAND = 0.10

SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"


def governor_multiplier(drawdown: float) -> float:
    """v110 exposure multiplier: clip((0.20 - DD)/0.10, 0, 1)."""
    g = (GOV_CAP - drawdown) / GOV_BAND
    return float(min(1.0, max(0.0, g)))


def extract_weights(row: dict) -> tuple[dict, dict] | None:
    """Return (perp_weights, spot_weights) for a log row, or None if no weight.

    Portfolio candidates carry `perp_weight`/`spot_weight` dicts (scored as
    given: perp as directional exposure, spot as long spot exposure).
    BTC single-asset candidates carry `target_fraction`, or
    `size_fraction_of_equity` with `target_position` (sign).
    """
    perp = row.get("perp_weight")
    if isinstance(perp, dict):
        spot = row.get("spot_weight") or {}
        spot = spot if isinstance(spot, dict) else {}
        return ({str(k): float(v) for k, v in perp.items()},
                {str(k): float(v) for k, v in spot.items()})
    if row.get("target_fraction") is not None:
        return ({"BTCUSDT": float(row["target_fraction"])}, {})
    if row.get("size_fraction_of_equity") is not None and row.get("target_position") is not None:
        size = float(row["size_fraction_of_equity"])
        try:
            pos = float(row["target_position"])
        except (TypeError, ValueError):
            return None
        sign = 0.0 if pos == 0 else (1.0 if pos > 0 else -1.0)
        return ({"BTCUSDT": sign * size}, {})
    return None


def parse_decisions(rows: list[dict]) -> dict:
    """Group prospective rows by candidate into sorted, deduped decisions.

    Returns {candidate: {"decisions": [{"eff", "perp", "spot"}], "first",
    "last", "n_decisions", "ungoverned"}} where `eff` (effective open) is the
    decision bar close + 1 ms. Duplicate decision closes keep the last log.
    Rows without weights are ignored.
    """
    grouped: dict[str, dict[str, dict]] = {}
    ungoverned: dict[str, bool] = {}
    for row in rows:
        if row.get("mode") != "prospective":
            continue
        if "candidate" not in row or "decision_bar_close" not in row:
            continue
        weights = extract_weights(row)
        if weights is None:
            continue
        cand = str(row["candidate"])
        close = pd.Timestamp(row["decision_bar_close"])
        if close.tzinfo is None:
            close = close.tz_localize("UTC")
        else:
            close = close.tz_convert("UTC")
        eff = close + pd.Timedelta(milliseconds=1)
        logged_raw = row.get("logged_at")
        try:
            logged = pd.Timestamp(logged_raw) if logged_raw else close
        except (ValueError, TypeError):
            logged = close
        perp, spot = weights
        grouped.setdefault(cand, {})[close.isoformat()] = {
            "eff": eff, "perp": perp, "spot": spot, "logged": logged,
        }
        note = row.get("note") or ""
        if "UNGOVERNED" in str(note):
            ungoverned[cand] = True
    out = {}
    for cand, by_close in grouped.items():
        decs = sorted(by_close.values(), key=lambda d: d["eff"])
        closes = sorted(by_close.keys())
        out[cand] = {
            "decisions": [{"eff": d["eff"], "perp": d["perp"], "spot": d["spot"]} for d in decs],
            "first": closes[0],
            "last": closes[-1],
            "n_decisions": len(decs),
            "ungoverned": bool(ungoverned.get(cand, False)),
        }
    return out


def score_candidate(decisions: list[dict], grid: list, perp_open: dict,
                    spot_open: dict, cost_rate: float = COST_PER_UNIT,
                    funding_per_bar: float = LONG_FUNDING_PER_BAR,
                    governed: bool = False,
                    gov_window: int = GOV_WINDOW_BARS) -> dict:
    """Score one candidate's decisions over a 4h-open grid (compounded equity).

    `grid` is the sorted master list of bar open times; `perp_open`/`spot_open`
    map symbol -> {open_time: open price}. A decision holds from the first grid
    open at/after its effective time until replaced (gaps keep old weights).
    Grid intervals without a following open (trailing unpriced bar) are never
    entered, so no fill happens before the next open.
    """
    eff = sorted(decisions, key=lambda d: d["eff"])
    grid = sorted(grid)
    equity = 1.0
    eq_after: list[float] = []
    g_series: list[float] = []
    turnover = 0.0
    gross_sum = 0.0
    cost_sum = 0.0
    fund_sum = 0.0
    scored = 0
    prev_perp: dict = {}
    prev_spot: dict = {}
    di = 0
    for j in range(len(grid) - 1):
        t, tn = grid[j], grid[j + 1]
        while di < len(eff) and eff[di]["eff"] <= t:
            di += 1
        if di == 0:
            continue  # no decision yet: flat, unscored
        held = eff[di - 1]
        g = 1.0
        if governed and len(eq_after) >= 2:
            jj = len(eq_after) - 2  # equity lagged 2 bars
            lo = max(0, jj - gov_window + 1)
            peak = max(1.0, max(eq_after[lo:jj + 1]))
            g = governor_multiplier(1.0 - eq_after[jj] / peak)
        w_p = {k: v * g for k, v in held["perp"].items()}
        w_s = {k: v * g for k, v in held["spot"].items()}
        delta = sum(abs(w_p.get(k, 0.0) - prev_perp.get(k, 0.0))
                    for k in set(prev_perp) | set(w_p))
        delta += sum(abs(w_s.get(k, 0.0) - prev_spot.get(k, 0.0))
                     for k in set(prev_spot) | set(w_s))
        turnover += delta
        cost = cost_rate * delta
        gross = 0.0
        for sym, w in w_p.items():
            m = perp_open.get(sym, {})
            if w and t in m and tn in m and m[t]:
                gross += w * (m[tn] / m[t] - 1.0)
        for sym, w in w_s.items():
            m = spot_open.get(sym, {})
            if w and t in m and tn in m and m[t]:
                gross += w * (m[tn] / m[t] - 1.0)
        funding = funding_per_bar * sum(max(v, 0.0) for v in w_p.values())
        equity *= 1.0 + gross - cost - funding
        eq_after.append(equity)
        g_series.append(g)
        gross_sum += gross
        cost_sum += cost
        fund_sum += funding
        scored += 1
        prev_perp, prev_spot = w_p, w_s
    curve = [1.0] + eq_after
    running_peak = 1.0
    max_dd = 0.0
    for e in curve:
        running_peak = max(running_peak, e)
        max_dd = max(max_dd, 1.0 - e / running_peak)
    return {
        "bars_held": scored,
        "cum_net_return_pct": (equity - 1.0) * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "turnover": turnover,
        "gross_return_pct": gross_sum * 100.0,
        "cost_drag_pct": cost_sum * 100.0,
        "funding_drag_pct": fund_sum * 100.0,
        "mean_g": sum(g_series) / len(g_series) if g_series else 1.0,
        "equity_last": equity,
    }


def fetch_perp_opens(symbols: list[str], start: datetime, end: datetime) -> dict:
    """Fetch closed Binance USD-M 4h opens per symbol (public REST, no keys)."""
    from agentic_alpha_lab.data.binance_usdm import fetch_klines

    out = {}
    for sym in sorted(set(symbols)):
        frame = fetch_klines(sym, "4h", start, end)
        opens = {}
        for t, o in zip(frame["open_time"], frame["open"]):
            ts = pd.Timestamp(t)
            key = ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC")
            opens[key] = float(o)
        out[sym] = opens
    return out


def fetch_spot_opens(symbols: list[str], start: datetime, end: datetime) -> dict:
    """Fetch closed Binance spot 4h opens per symbol (public REST, no keys)."""
    import requests

    session = requests.Session()
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    out = {}
    for sym in sorted(set(symbols)):
        rows: list = []
        cursor = start_ms
        while cursor < end_ms:
            resp = session.get(SPOT_KLINES_URL, params={
                "symbol": sym.upper(), "interval": "4h",
                "startTime": cursor, "endTime": end_ms, "limit": 1000,
            }, timeout=60)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            rows.extend(batch)
            nxt = int(batch[-1][0]) + 14_400_000
            if nxt <= cursor:
                raise RuntimeError("spot pagination did not advance")
            cursor = nxt
            if len(batch) < 1000:
                break
        opens = {}
        for b in rows:
            if int(b[6]) < now_ms:  # closed bars only; trailing unpriced bar skipped
                ts = pd.Timestamp(int(b[0]), unit="ms", tz="UTC")
                opens[ts] = float(b[1])
        out[sym] = opens
    return out


def main() -> int:
    if not LOG_PATH.exists():
        print(f"no advisory log at {LOG_PATH}")
        return 1
    rows = [json.loads(line) for line in LOG_PATH.read_text().splitlines() if line.strip()]
    parsed = parse_decisions(rows)
    if not parsed:
        print("no prospective decisions with weights")
        return 1
    perp_syms = {"BTCUSDT"}
    spot_syms: set[str] = set()
    for info in parsed.values():
        for d in info["decisions"]:
            perp_syms.update(d["perp"].keys())
            spot_syms.update(d["spot"].keys())
    first_eff = min(d["eff"] for info in parsed.values() for d in info["decisions"])
    start = (first_eff - timedelta(hours=4)).to_pydatetime()
    end = datetime.now(timezone.utc)
    perp_open = fetch_perp_opens(sorted(perp_syms), start, end)
    spot_open = fetch_spot_opens(sorted(spot_syms), start, end) if spot_syms else {}
    all_maps = list(perp_open.values()) + list(spot_open.values())
    grid = sorted({t for m in all_maps for t in m if t >= first_eff})
    # Keep only opens at/after the first effective decision; the trailing open
    # without a next open is skipped inside score_candidate.
    result = {
        "generated_at": end.isoformat(),
        "log": str(LOG_PATH),
        "cost_per_unit_weight_change": COST_PER_UNIT,
        "long_funding_per_4h_bar": LONG_FUNDING_PER_BAR,
        "governor": ("g=clip((0.20-DD)/0.10,0,1); DD from 90-day (540-bar) "
                     "governed-equity peak lagged 2 bars; g=1 for first 2 bars"),
        "n_log_rows": len(rows),
        "candidates": {},
    }
    for cand in sorted(parsed):
        info = parsed[cand]
        raw = score_candidate(info["decisions"], grid, perp_open, spot_open,
                              governed=False)
        entry = {
            "first_decision": info["first"],
            "last_decision": info["last"],
            "n_decisions": info["n_decisions"],
            "bars_held": raw["bars_held"],
            "cum_net_return_pct": round(raw["cum_net_return_pct"], 4),
            "max_drawdown_pct": round(raw["max_drawdown_pct"], 4),
            "turnover": round(raw["turnover"], 6),
            "gross_return_pct": round(raw["gross_return_pct"], 4),
            "cost_drag_pct": round(raw["cost_drag_pct"], 4),
            "funding_drag_pct": round(raw["funding_drag_pct"], 4),
            "governed": None,
        }
        if info["ungoverned"]:
            gov = score_candidate(info["decisions"], grid, perp_open, spot_open,
                                  governed=True)
            entry["governed"] = {
                "bars_held": gov["bars_held"],
                "cum_net_return_pct": round(gov["cum_net_return_pct"], 4),
                "max_drawdown_pct": round(gov["max_drawdown_pct"], 4),
                "turnover": round(gov["turnover"], 6),
                "mean_g": round(gov["mean_g"], 4),
            }
        result["candidates"][cand] = entry
        line = (f'{cand}: n={entry["n_decisions"]} bars={entry["bars_held"]} '
                f'net={entry["cum_net_return_pct"]}% dd={entry["max_drawdown_pct"]}% '
                f'turn={entry["turnover"]}')
        if entry["governed"]:
            line += (f' | governed net={entry["governed"]["cum_net_return_pct"]}% '
                     f'dd={entry["governed"]["max_drawdown_pct"]}% '
                     f'mean_g={entry["governed"]["mean_g"]}')
        print(line)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=1))
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
