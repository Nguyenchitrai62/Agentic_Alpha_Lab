"""Prospective paper log of the frozen v172 dip-reversal sleeve rule (research only, no orders, public REST only).

Frozen rule (v172, crash-aware costs, k = 4 as chosen walk-forward for the 2025 anchor): for each 4h holding bar T of
BTC/ETH/SOL/BNB/XRP USD-M perps, sigma = std of the 360 4h open-to-open returns ending at the decision bar (T - 4h);
the first minute m in 16..238 whose 1m close <= open(T) * (1 - 4 sigma) triggers a long entry at the minute m+1 open
* (1 + s_in); exit at the next 4h open * (1 - s_out); s = max(0.0002, 0.25 * (high - low) / open) of the fill minute;
taker fee 0.0005 per side; the long pays the funding settled at the exit open. Size 0.25 of equity per event.
Only holding bars that start at or after FREEZE count (the rule was fixed before that data existed).
Recomputed from FREEZE on every run (idempotent); writes
artifacts/research/advisor_shadow/dip_sleeve_forward.json.

  python scripts/dip_sleeve_forward.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from agentic_alpha_lab.data.binance_usdm import fetch_klines

FREEZE = pd.Timestamp("2026-09-26T16:00:00Z")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
K, SIZE, TAKER = 4.0, 0.25, 0.0005
OUT = Path("artifacts/research/advisor_shadow/dip_sleeve_forward.json")


def slip(row) -> float:
    return max(0.0002, 0.25 * (float(row["high"]) - float(row["low"])) / float(row["open"]))


def funding(sym: str, start: pd.Timestamp, sess) -> pd.Series:
    r = sess.get("https://fapi.binance.com/fapi/v1/fundingRate",
                 params={"symbol": sym, "startTime": int(start.timestamp() * 1000), "limit": 1000}, timeout=60)
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return pd.Series(dtype=float)
    t = pd.to_datetime([int(x["fundingTime"]) for x in rows], unit="ms", utc=True).floor("min")
    return pd.Series([float(x["fundingRate"]) for x in rows], index=t)


def events_for(sym: str, sess) -> list[dict]:
    now = datetime.now(timezone.utc)
    k4 = fetch_klines(sym, "4h", (FREEZE - timedelta(days=70)).to_pydatetime(), now, session=sess)
    k4["open_time"] = pd.to_datetime(k4["open_time"], utc=True)
    o = k4.set_index("open_time")["open"].astype(float)
    ret = o.pct_change()
    m1 = fetch_klines(sym, "1m", FREEZE.to_pydatetime(), now, session=sess)
    m1["open_time"] = pd.to_datetime(m1["open_time"], utc=True)
    m1 = m1.drop_duplicates("open_time").set_index("open_time")
    fr = funding(sym, FREEZE, sess)
    out = []
    for T in o.index[o.index >= FREEZE]:
        nxt = T + pd.Timedelta(hours=4)
        if nxt not in o.index:
            break  # exit price not yet available
        hist = ret[ret.index <= T - pd.Timedelta(hours=4)].tail(360)
        if hist.count() < 120:
            continue
        sig = float(hist.std())
        bar = m1[(m1.index >= T) & (m1.index < nxt)]
        off = ((bar.index - T).total_seconds() // 60).astype(int)
        bar = bar.assign(off=off)
        thr = o[T] * (1 - K * sig)
        hit = bar[(bar["off"] >= 16) & (bar["off"] <= 238) & (bar["close"].astype(float) <= thr)]
        if hit.empty:
            continue
        m = int(hit["off"].iloc[0])
        ent = bar[bar["off"] == m + 1]
        ex = m1[m1.index == nxt]
        if ent.empty or ex.empty:
            continue
        e_px = float(ent["open"].iloc[0]) * (1 + slip(ent.iloc[0]))
        x_px = float(o[nxt]) * (1 - slip(ex.iloc[0]))
        f = float(fr.get(nxt, 0.0))
        r = x_px / e_px - 1 - 2 * TAKER - f
        out.append(dict(symbol=sym, bar_open=T.isoformat(), trigger_minute=m, sigma=round(sig, 6), entry=e_px, exit=x_px,
                        funding=f, net_return=round(r, 6)))
    return out


def main():
    sess = requests.Session()
    ev = []
    if datetime.now(timezone.utc) >= (FREEZE + pd.Timedelta(hours=8)).to_pydatetime():
        for s in SYMS:
            ev.extend(events_for(s, sess))
    ev.sort(key=lambda e: e["bar_open"])
    eq = 1.0
    by_bar: dict[str, float] = {}
    for e in ev:
        by_bar[e["bar_open"]] = by_bar.get(e["bar_open"], 0.0) + SIZE * e["net_return"]
    for b in sorted(by_bar):
        eq *= 1 + by_bar[b]
    out = {"rule": "v172 frozen dip sleeve, k=4, crash-aware slippage, size 0.25", "freeze": FREEZE.isoformat(),
           "scored_until": datetime.now(timezone.utc).isoformat(), "events": ev, "n_events": len(ev),
           "sleeve_cum_return_pct": round(100 * (eq - 1), 3)}
    OUT.write_text(json.dumps(out, indent=1))
    print(f"dip sleeve forward: {len(ev)} events since {FREEZE.isoformat()}, cum {out['sleeve_cum_return_pct']}%")


if __name__ == "__main__":
    main()
