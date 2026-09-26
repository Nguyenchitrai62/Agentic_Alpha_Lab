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

# Realistic-cost (`real`) block (2026-09-26, matches research engine
# `research/parallel/rounds/parallel-20260906-r2/engine_real/engine_real.py`):
# - Perp execution per weight change (v135 10 bps limit on 1m data): D=0.001,
#   maker fee 0.0002 at p0*(1-/+D) on trade-through in minutes 2..14, else taker
#   fee 0.0005 at p15 +/- 0.0002. Cost vs p0 = |dw|*fee + dw*(fill/p0-1).
# - Spot legs: taker fee 0.001 per unit of weight change, no price offset.
# - Funding: actual signed Binance USD-M funding per symbol; a settlement at S
#   is paid by the weight held at S, i.e. settlements in (t, tn] are paid by the
#   weight held over [t, tn), so a settlement exactly at a decision bar open is
#   paid by the PREVIOUS weight. Replaces the flat long-only 0.00005 per bar.
# - Minimum order notional at a 10,000 USDT account (BTCUSDT 100, ETHUSDT 20,
#   others 5 USDT): a per-symbol weight change smaller than the minimum that
#   does not close the position is not sent (the leg keeps its previous weight).
#   Notional uses current equity (starts at 1.0 = 10,000 USDT).
# - Unpriced bars (1m execution stats not yet available at a bar where a perp
#   weight change is due) are skipped: no equity change and previous weights are
#   kept, so a later rerun with complete data scores them. Bars without a due
#   perp change are scored from 4h opens as before.
# - Maker share = maker |dw| volume / total perp |dw| volume (0.0 if no fills).
REAL_PERP_OFFSET = 0.001
REAL_PERP_MAKER_FEE = 0.0002
REAL_PERP_TAKER_FEE = 0.0005
REAL_PERP_TAKER_SLIP = 0.0002
REAL_SPOT_FEE = 0.001
REAL_ACCOUNT_USDT = 10_000.0
REAL_MIN_NOTIONAL = {"BTCUSDT": 100.0, "ETHUSDT": 20.0}
REAL_DEFAULT_MIN_NOTIONAL = 5.0

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


def _real_min_notional(symbol: str) -> float:
    return float(REAL_MIN_NOTIONAL.get(symbol, REAL_DEFAULT_MIN_NOTIONAL))


def real_perp_fill(dw: float, stat: dict) -> tuple[float, float, bool]:
    """Return (fill_price, fee, is_maker) for a perp weight change (assignment rule 1).

    `stat` carries p0/lo/hi/p15 for the execution window [T, T+16min).
    Buy (dw>0): maker at p0*(1-0.001)/fee 0.0002 if lo < p0*(1-0.001), else
    taker at p15*(1+0.0002)/fee 0.0005. Sell symmetric.
    """
    p0 = float(stat["p0"])
    if dw > 0:
        if float(stat["lo"]) < p0 * (1.0 - REAL_PERP_OFFSET):
            return p0 * (1.0 - REAL_PERP_OFFSET), REAL_PERP_MAKER_FEE, True
        return float(stat["p15"]) * (1.0 + REAL_PERP_TAKER_SLIP), REAL_PERP_TAKER_FEE, False
    if float(stat["hi"]) > p0 * (1.0 + REAL_PERP_OFFSET):
        return p0 * (1.0 + REAL_PERP_OFFSET), REAL_PERP_MAKER_FEE, True
    return float(stat["p15"]) * (1.0 - REAL_PERP_TAKER_SLIP), REAL_PERP_TAKER_FEE, False


def _valid_exec_stat(stat) -> bool:
    if not isinstance(stat, dict):
        return False
    try:
        p0, p15 = float(stat["p0"]), float(stat["p15"])
        float(stat["lo"])
        float(stat["hi"])
    except (KeyError, TypeError, ValueError):
        return False
    return p0 > 0 and p15 > 0


def score_candidate_real(decisions: list[dict], grid: list, perp_open: dict,
                         spot_open: dict, perp_exec: dict | None = None,
                         funding: dict | None = None,
                         governed: bool = False,
                         gov_window: int = GOV_WINDOW_BARS) -> dict:
    """Score one candidate with realistic costs (network-free; see module constants).

    `perp_exec` maps symbol -> {bar_open_time: {"p0","lo","hi","p15"}} for the
    1m execution window of each weight-change bar. `funding` maps symbol ->
    {settlement_time: rate} (signed Binance USD-M funding). A settlement at S
    is paid by the weight held over the interval (t, tn] containing S, so a
    settlement exactly at a decision bar open is paid by the PREVIOUS weight.
    Gross uses the 4h open series as in `score_candidate`; execution is measured
    vs p0. Min-notional filtering and unpriced-bar skipping follow the `real`
    rules documented above.
    """
    perp_exec = perp_exec or {}
    funding = funding or {}
    eff = sorted(decisions, key=lambda d: d["eff"])
    grid = sorted(grid)
    equity = 1.0
    eq_after: list[float] = []
    g_series: list[float] = []
    turnover = 0.0
    perp_turnover = 0.0
    maker_vol = 0.0
    gross_sum = 0.0
    exec_sum = 0.0
    fund_sum = 0.0
    scored = 0
    skipped = 0
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
        w_p_raw = {k: v * g for k, v in held["perp"].items()}
        w_s_raw = {k: v * g for k, v in held["spot"].items()}
        eq_usdt = REAL_ACCOUNT_USDT * (eq_after[-1] if eq_after else 1.0)
        # Min-notional filter (per symbol, per leg; closing to zero always sent).
        w_p: dict = {}
        for k in set(prev_perp) | set(w_p_raw):
            raw = float(w_p_raw.get(k, 0.0))
            prev = float(prev_perp.get(k, 0.0))
            if raw != 0.0 and abs(raw - prev) * eq_usdt < _real_min_notional(k):
                w_p[k] = prev
            else:
                w_p[k] = raw
        w_s: dict = {}
        for k in set(prev_spot) | set(w_s_raw):
            raw = float(w_s_raw.get(k, 0.0))
            prev = float(prev_spot.get(k, 0.0))
            if raw != 0.0 and abs(raw - prev) * eq_usdt < _real_min_notional(k):
                w_s[k] = prev
            else:
                w_s[k] = raw
        # Unpriced-bar skip: a due perp change without 1m stats waits for data.
        need_skip = False
        for k in set(prev_perp) | set(w_p):
            if abs(w_p.get(k, 0.0) - prev_perp.get(k, 0.0)) > 0.0:
                stat = (perp_exec.get(k, {}) or {}).get(t)
                if not _valid_exec_stat(stat):
                    need_skip = True
                    break
        if need_skip:
            skipped += 1
            continue
        exec_cost = 0.0
        for k in set(prev_perp) | set(w_p):
            dw = w_p.get(k, 0.0) - prev_perp.get(k, 0.0)
            if dw == 0.0:
                continue
            stat = (perp_exec.get(k, {}) or {}).get(t)
            fill, fee, maker = real_perp_fill(dw, stat)
            p0 = float(stat["p0"])
            exec_cost += abs(dw) * fee + dw * (fill / p0 - 1.0)
            perp_turnover += abs(dw)
            if maker:
                maker_vol += abs(dw)
        for k in set(prev_spot) | set(w_s):
            dw = w_s.get(k, 0.0) - prev_spot.get(k, 0.0)
            if dw == 0.0:
                continue
            exec_cost += abs(dw) * REAL_SPOT_FEE
        delta = sum(abs(w_p.get(k, 0.0) - prev_perp.get(k, 0.0))
                    for k in set(prev_perp) | set(w_p))
        delta += sum(abs(w_s.get(k, 0.0) - prev_spot.get(k, 0.0))
                     for k in set(prev_spot) | set(w_s))
        turnover += delta
        gross = 0.0
        for sym, w in w_p.items():
            m = perp_open.get(sym, {})
            if w and t in m and tn in m and m[t]:
                gross += w * (m[tn] / m[t] - 1.0)
        for sym, w in w_s.items():
            m = spot_open.get(sym, {})
            if w and t in m and tn in m and m[t]:
                gross += w * (m[tn] / m[t] - 1.0)
        fund = 0.0
        for sym, w in w_p.items():
            if not w:
                continue
            fmap = funding.get(sym, {}) or {}
            for s, rate in fmap.items():
                if s > t and s <= tn:
                    fund += w * float(rate)
        equity *= 1.0 + gross - exec_cost - fund
        eq_after.append(equity)
        g_series.append(g)
        gross_sum += gross
        exec_sum += exec_cost
        fund_sum += fund
        scored += 1
        prev_perp, prev_spot = w_p, w_s
    curve = [1.0] + eq_after
    running_peak = 1.0
    max_dd = 0.0
    for e in curve:
        running_peak = max(running_peak, e)
        max_dd = max(max_dd, 1.0 - e / running_peak)
    maker_share = (maker_vol / perp_turnover) if perp_turnover > 0 else 0.0
    return {
        "bars_held": scored,
        "bars_skipped_unpriced": skipped,
        "cum_net_return_pct": (equity - 1.0) * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "turnover": turnover,
        "gross_return_pct": gross_sum * 100.0,
        "exec_drag_pct": exec_sum * 100.0,
        "funding_drag_pct": fund_sum * 100.0,
        "maker_share": maker_share,
        "mean_g": sum(g_series) / len(g_series) if g_series else 1.0,
        "equity_last": equity,
    }


def fetch_perp_exec(symbols: list[str], decision_closes: list,
                    session=None) -> dict:
    """Fetch 1m execution stats per symbol for each decision bar (public REST).

    For a decision at bar close T (effective at T + 1 ms = bar open eff), the
    window is [eff, eff + 16 min): p0 = 1m open at eff, lo/hi = min low / max
    high over minute offsets 2..14, p15 = 1m open at eff + 15 min. A window
    without p0 and p15 (1m data not yet available) is left missing so the bar
    is skipped. Returns {symbol: {eff_time: {"p0","lo","hi","p15"}}}.
    """
    import requests

    sess = session or requests.Session()
    out: dict = {}
    for sym in sorted(set(symbols)):
        per: dict = {}
        for close in decision_closes:
            ts = pd.Timestamp(close)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            eff = ts + pd.Timedelta(milliseconds=1)
            eff_floor = eff.floor("min")
            start_ms = int(eff_floor.timestamp() * 1000)
            end_ms = start_ms + 16 * 60 * 1000 - 1
            resp = sess.get("https://fapi.binance.com/fapi/v1/klines", params={
                "symbol": sym.upper(), "interval": "1m",
                "startTime": start_ms, "endTime": end_ms, "limit": 16,
            }, timeout=60)
            resp.raise_for_status()
            rows = resp.json()
            kl = {}
            for b in rows:
                ot = pd.Timestamp(int(b[0]), unit="ms", tz="UTC")
                off = int((ot - eff_floor).total_seconds() // 60)
                kl[off] = {"open": float(b[1]), "high": float(b[2]),
                           "low": float(b[3])}
            if 0 in kl and 15 in kl:
                mid = [kl[o] for o in range(2, 15) if o in kl]
                if mid:
                    per[eff] = {"p0": kl[0]["open"],
                                "lo": min(k["low"] for k in mid),
                                "hi": max(k["high"] for k in mid),
                                "p15": kl[15]["open"]}
        out[sym] = per
    return out


def fetch_funding(symbols: list[str], start: datetime, end: datetime,
                 session=None) -> dict:
    """Fetch signed Binance USD-M funding per symbol (public REST, no keys).

    Returns {symbol: {settlement_time: rate}} for settlements in [start, end].
    """
    import requests

    sess = session or requests.Session()
    start_ms = int(pd.Timestamp(start).tz_convert("UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end).tz_convert("UTC").timestamp() * 1000)
    out: dict = {}
    for sym in sorted(set(symbols)):
        fmap: dict = {}
        cursor = start_ms
        while True:
            resp = sess.get("https://fapi.binance.com/fapi/v1/fundingRate", params={
                "symbol": sym.upper(), "startTime": cursor, "endTime": end_ms,
                "limit": 1000,
            }, timeout=60)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            for r in batch:
                fmap[pd.Timestamp(int(r["fundingTime"]), unit="ms", tz="UTC").floor("min")] = float(r["fundingRate"])
            nxt = int(batch[-1]["fundingTime"]) + 1
            if nxt <= cursor or len(batch) < 1000:
                if len(batch) < 1000:
                    break
                cursor = nxt
                continue
            cursor = nxt
            if cursor > end_ms:
                break
        out[sym] = fmap
    return out


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
    closes = sorted({d["eff"] - pd.Timedelta(milliseconds=1)
                     for info in parsed.values() for d in info["decisions"]})
    perp_exec = fetch_perp_exec(sorted(perp_syms), closes)
    funding = fetch_funding(sorted(perp_syms), start, end)
    result = {
        "generated_at": end.isoformat(),
        "log": str(LOG_PATH),
        "cost_per_unit_weight_change": COST_PER_UNIT,
        "long_funding_per_4h_bar": LONG_FUNDING_PER_BAR,
        "governor": ("g=clip((0.20-DD)/0.10,0,1); DD from 90-day (540-bar) "
                     "governed-equity peak lagged 2 bars; g=1 for first 2 bars"),
        "real": ("perp v135 10bps limit on 1m (maker 0.0002 else taker 0.0005 "
                 "at p15 +/- 0.0002, cost vs p0); spot taker 0.001; actual "
                 "signed USD-M funding paid by weight held at settlement "
                 "(settlement at bar open paid by previous weight); "
                 "min-notional at 10k USDT (BTC 100/ETH 20/other 5, closes "
                 "always sent); unpriced 1m bars skipped"),
        "n_log_rows": len(rows),
        "candidates": {},
    }


    def _real_entry(res: dict) -> dict:
        return {
            "bars_held": res["bars_held"],
            "bars_skipped_unpriced": res["bars_skipped_unpriced"],
            "cum_net_return_pct": round(res["cum_net_return_pct"], 4),
            "max_drawdown_pct": round(res["max_drawdown_pct"], 4),
            "turnover": round(res["turnover"], 6),
            "gross_return_pct": round(res["gross_return_pct"], 4),
            "exec_drag_pct": round(res["exec_drag_pct"], 4),
            "funding_drag_pct": round(res["funding_drag_pct"], 4),
            "maker_share": round(res["maker_share"], 4),
        }

    def _legacy_entry(raw: dict) -> dict:
        return {
            "bars_held": raw["bars_held"],
            "cum_net_return_pct": round(raw["cum_net_return_pct"], 4),
            "max_drawdown_pct": round(raw["max_drawdown_pct"], 4),
            "turnover": round(raw["turnover"], 6),
            "gross_return_pct": round(raw["gross_return_pct"], 4),
            "cost_drag_pct": round(raw["cost_drag_pct"], 4),
            "funding_drag_pct": round(raw["funding_drag_pct"], 4),
        }

    for cand in sorted(parsed):
        info = parsed[cand]
        raw = score_candidate(info["decisions"], grid, perp_open, spot_open,
                              governed=False)
        real = score_candidate_real(info["decisions"], grid, perp_open,
                                    spot_open, perp_exec, funding,
                                    governed=False)
        legacy = _legacy_entry(raw)
        entry = {
            "first_decision": info["first"],
            "last_decision": info["last"],
            "n_decisions": info["n_decisions"],
            # Backward-compatible top-level legacy numbers.
            "bars_held": legacy["bars_held"],
            "cum_net_return_pct": legacy["cum_net_return_pct"],
            "max_drawdown_pct": legacy["max_drawdown_pct"],
            "turnover": legacy["turnover"],
            "gross_return_pct": legacy["gross_return_pct"],
            "cost_drag_pct": legacy["cost_drag_pct"],
            "funding_drag_pct": legacy["funding_drag_pct"],
            "governed": None,
            "legacy": legacy,
            "real": _real_entry(real),
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
            entry["legacy"]["governed"] = dict(entry["governed"])
            gov_real = score_candidate_real(
                info["decisions"], grid, perp_open, spot_open,
                perp_exec, funding, governed=True)
            # Recompute with mean_g preserved (helper-free, explicit).
            entry["real"]["governed"] = {
                "bars_held": gov_real["bars_held"],
                "bars_skipped_unpriced": gov_real["bars_skipped_unpriced"],
                "cum_net_return_pct": round(gov_real["cum_net_return_pct"], 4),
                "max_drawdown_pct": round(gov_real["max_drawdown_pct"], 4),
                "turnover": round(gov_real["turnover"], 6),
                "gross_return_pct": round(gov_real["gross_return_pct"], 4),
                "exec_drag_pct": round(gov_real["exec_drag_pct"], 4),
                "funding_drag_pct": round(gov_real["funding_drag_pct"], 4),
                "maker_share": round(gov_real["maker_share"], 4),
                "mean_g": round(gov_real["mean_g"], 4),
            }
        else:
            entry["real"]["governed"] = None
        result["candidates"][cand] = entry
        line = (f'{cand}: n={entry["n_decisions"]} bars={entry["bars_held"]} '
                f'net={entry["cum_net_return_pct"]}% dd={entry["max_drawdown_pct"]}% '
                f'turn={entry["turnover"]}')
        if entry["governed"]:
            line += (f' | governed net={entry["governed"]["cum_net_return_pct"]}% '
                     f'dd={entry["governed"]["max_drawdown_pct"]}% '
                     f'mean_g={entry["governed"]["mean_g"]}')
        line += (f' | real net={entry["real"]["cum_net_return_pct"]}% '
                 f'dd={entry["real"]["max_drawdown_pct"]}% '
                 f'exec={entry["real"]["exec_drag_pct"]}% '
                 f'fund={entry["real"]["funding_drag_pct"]}% '
                 f'maker={entry["real"]["maker_share"]}')
        print(line)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=1))
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
