"""Prospective shadow log for R82 (advisory only, no order code).

Fetches closed Binance USD-M BTCUSDT public candles (no auth) and appends one
JSON line per new closed DAILY bar to
artifacts/research/ma_ribbon_shadow/shadow.jsonl.

Each line carries the daily H4 ribbon target (SMA50/SMA200 on daily closes)
and the dev-selected 4h_EMA20/200_ribbon_long target evaluated at that daily
close, plus a data hash. Earlier lines are never rewritten; the script refuses
(exit 2, no write) when the latest closed bar is already logged.

Advisory only: this module places no orders and contains no order code.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHADOW_PATH = ROOT / "artifacts" / "research" / "ma_ribbon_shadow" / "shadow.jsonl"
FAPI = "https://fapi.binance.com/fapi/v1/klines"
PROSPECTIVE_MAX_LAG_H = 36


def fetch_klines(symbol="BTCUSDT", interval="1d", limit=1000):
    """Public REST klines, no auth. Returns list of dicts (open_time, close, ...)."""
    params = urllib.parse.urlencode(
        {"symbol": symbol, "interval": interval, "limit": limit}
    )
    req = urllib.request.Request(f"{FAPI}?{params}", method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    out = []
    for k in raw:
        out.append(
            {
                "open_time": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "close_time": datetime.fromtimestamp(k[6] / 1000, tz=timezone.utc),
            }
        )
    return out


def closed_bars(bars, now=None):
    """Keep only fully closed bars (close_time <= now)."""
    now = now or datetime.now(tz=timezone.utc)
    return [b for b in bars if b["close_time"] <= now]


def sma(values, period, end):
    """Causal SMA over values[:end+1]; None during warm-up. Pure python."""
    if end + 1 < period:
        return None
    return sum(values[end - period + 1 : end + 1]) / period


def ema_series(values, span):
    """pandas-compatible EMA (adjust=False, min_periods=span), causal list."""
    k = 2.0 / (span + 1.0)
    out = [None] * len(values)
    if len(values) < span:
        return out
    seed = sum(values[:span]) / span  # pandas ewm min_periods=span seeds on SMA
    out[span - 1] = seed
    for i in range(span, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def h4_target(close, sma50, sma200):
    if sma50 is None or sma200 is None:
        return 0
    if close > sma50 and sma50 > sma200:
        return 1
    if close < sma50 and sma50 < sma200:
        return -1
    return 0


def sel_4h_ribbon_long_target(close4h, ema20, ema200):
    if ema20 is None or ema200 is None:
        return 0
    return 1 if (close4h > ema20 and ema20 > ema200) else 0


def data_hash(daily_closes_upto_t, h4_closes_upto_t):
    h = hashlib.sha256()
    h.update(json.dumps(daily_closes_upto_t, separators=(",", ":")).encode())
    h.update(b"|")
    h.update(json.dumps(h4_closes_upto_t, separators=(",", ":")).encode())
    return h.hexdigest()


def build_lines(daily, four_h):
    """One advisory record per closed daily bar (causal; uses bars <= t only)."""
    d_closes = [b["close"] for b in daily]
    h_closes = [b["close"] for b in four_h]
    h_opens = [b["open_time"] for b in four_h]
    e20 = ema_series(h_closes, 20)
    e200 = ema_series(h_closes, 200)
    lines = []
    for i, b in enumerate(daily):
        s50 = sma(d_closes, 50, i)
        s200 = sma(d_closes, 200, i)
        h4 = h4_target(b["close"], s50, s200)
        # latest closed 4h bar with open_time <= daily close_time
        j = -1
        for k, ot in enumerate(h_opens):
            if ot <= b["close_time"]:
                j = k
        if j >= 0:
            sel = sel_4h_ribbon_long_target(h_closes[j], e20[j], e200[j])
            sel_close, sel_e20, sel_e200 = h_closes[j], e20[j], e200[j]
            h_used = h_closes[: j + 1]
        else:
            sel, sel_close, sel_e20, sel_e200, h_used = 0, None, None, None, []
        lines.append(
            {
                "decision_time": b["close_time"].isoformat(),
                "daily_close": b["close"],
                "sma50": s50,
                "sma200": s200,
                "h4_target": h4,
                "sel_4h_close": sel_close,
                "sel_4h_ema20": sel_e20,
                "sel_4h_ema200": sel_e200,
                "sel_4h_ema20_200_ribbon_long": sel,
                "data_hash": data_hash(d_closes[: i + 1], h_used),
            }
        )
    return lines


def load_logged(path=SHADOW_PATH):
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    daily = closed_bars(fetch_klines("BTCUSDT", "1d", 1000))
    four_h = closed_bars(fetch_klines("BTCUSDT", "4h", 1000))
    if not daily:
        print("no closed daily bars", file=sys.stderr)
        return 2
    records = build_lines(daily, four_h)
    logged = load_logged()
    seen = {r["decision_time"] for r in logged}
    new = [r for r in records if r["decision_time"] not in seen]
    latest = records[-1]["decision_time"]
    if not new:
        print(f"refuse: latest closed bar {latest} already logged; no write",
              file=sys.stderr)
        return 2
    SHADOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=timezone.utc)
    with open(SHADOW_PATH, "a") as f:
        for r in new:
            lag_h = (now - datetime.fromisoformat(r["decision_time"])).total_seconds() / 3600
            # Only rows logged within 36h of the bar close are prospective
            # observations; older rows are backfill, never forward evidence.
            r["logged_at"] = now.isoformat()
            r["mode"] = "prospective" if lag_h <= PROSPECTIVE_MAX_LAG_H else "backfill"
            f.write(json.dumps(r) + "\n")
    print(f"appended {len(new)} line(s); latest {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
