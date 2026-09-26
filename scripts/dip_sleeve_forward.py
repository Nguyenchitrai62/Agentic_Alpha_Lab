"""Prospective paper log of the frozen v172 dip-reversal sleeve rule (research only, no orders, public REST only).

Two frozen rules are logged side by side (both chosen walk-forward for the 2025 anchor, fixed before FREEZE):
- "limit" (v175/v176, k = 3.5): a resting bid at open(T) * (1 - k sigma), live in minutes 16..238, filled at the bid
  on a 1m trade-through (low < bid) with maker fee 0.0002; exit as below.
- "taker" (v172, k = 4), described next.
For each 4h holding bar T of
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
FREEZE_LADDER = pd.Timestamp("2026-09-26T20:00:00Z")  # v183 ladder + TP rule frozen from this bar
RUNGS = (2.5, 3.0, 3.5, 4.0)
FREEZE_V197 = pd.Timestamp("2026-09-27T00:00:00Z")  # v197 ladder: TP 1 sigma (maker), SL 5 sigma (market), frozen from this bar
M_SL_V197 = 5.0
TAKER_USER = 0.00055  # Bybit VIP0 (AGENTS.md gate cost model)
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
K, K_LIMIT, SIZE, TAKER, MAKER = 4.0, 3.5, 0.25, 0.0005, 0.0002
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
        ex = m1[m1.index == nxt]
        if ex.empty:
            continue
        x_px = float(o[nxt]) * (1 - slip(ex.iloc[0]))
        f = float(fr.get(nxt, 0.0))
        live = bar[(bar["off"] >= 16) & (bar["off"] <= 238)]
        bid = o[T] * (1 - K_LIMIT * sig)
        fill = live[live["low"].astype(float) < bid]
        if not fill.empty:
            r = x_px / bid - 1 - MAKER - TAKER - f
            out.append(dict(rule="limit", symbol=sym, bar_open=T.isoformat(), trigger_minute=int(fill["off"].iloc[0]),
                            sigma=round(sig, 6), entry=bid, exit=x_px, funding=f, net_return=round(r, 6)))
        if T >= FREEZE_LADDER:
            for k in RUNGS:
                lv = o[T] * (1 - k * sig)
                fl = live[live["low"].astype(float) < lv]
                if fl.empty:
                    continue
                fmin = int(fl["off"].iloc[0])
                tp = lv * (1 + sig)
                later = bar[(bar["off"] > fmin) & (bar["high"].astype(float) > tp)]
                if not later.empty:
                    r = tp / lv - 1 - 2 * MAKER
                    xmin = int(later["off"].iloc[0])
                else:
                    r = x_px / lv - 1 - MAKER - TAKER - f
                    xmin = 240
                out.append(dict(rule="ladder_tp", symbol=sym, bar_open=T.isoformat(), rung_k=k, fill_minute=fmin,
                                exit_minute=xmin, sigma=round(sig, 6), entry=lv, net_return=round(r, 6)))
                if T >= FREEZE_V197:
                    sl = lv * (1 - M_SL_V197 * sig)
                    after = bar[bar["off"] > fmin]
                    hs = after["low"].astype(float) <= sl
                    ht = after["high"].astype(float) > tp
                    hit = hs | ht
                    if hit.any():
                        row = after[hit].iloc[0]
                        xm = int(row["off"])
                        if float(row["low"]) <= sl:
                            r2 = min(sl, float(row["open"])) / lv - 1 - MAKER - TAKER_USER
                        else:
                            r2 = tp / lv - 1 - 2 * MAKER
                    else:
                        xm = 240
                        r2 = float(o[nxt]) / lv - 1 - MAKER - TAKER_USER - (0.0001 if nxt.hour in (0, 8, 16) else 0.0)
                    out.append(dict(rule="ladder_v197", symbol=sym, bar_open=T.isoformat(), rung_k=k, fill_minute=fmin,
                                    exit_minute=xm, sigma=round(sig, 6), entry=lv, net_return=round(r2, 6)))
        thr = o[T] * (1 - K * sig)
        hit = live[live["close"].astype(float) <= thr]
        if hit.empty:
            continue
        m = int(hit["off"].iloc[0])
        ent = bar[bar["off"] == m + 1]
        if ent.empty:
            continue
        e_px = float(ent["open"].iloc[0]) * (1 + slip(ent.iloc[0]))
        r = x_px / e_px - 1 - 2 * TAKER - f
        out.append(dict(rule="taker", symbol=sym, bar_open=T.isoformat(), trigger_minute=m, sigma=round(sig, 6), entry=e_px,
                        exit=x_px, funding=f, net_return=round(r, 6)))
    return out


def main():
    sess = requests.Session()
    ev = []
    if datetime.now(timezone.utc) >= (FREEZE + pd.Timedelta(hours=8)).to_pydatetime():
        for s in SYMS:
            ev.extend(events_for(s, sess))
    ev.sort(key=lambda e: e["bar_open"])
    summary = {}
    for rule in ("limit", "taker", "ladder_tp", "ladder_v197"):
        size = SIZE / len(RUNGS) if rule in ("ladder_tp", "ladder_v197") else SIZE
        eq = 1.0
        by_bar: dict[str, float] = {}
        for e in ev:
            if e["rule"] == rule:
                by_bar[e["bar_open"]] = by_bar.get(e["bar_open"], 0.0) + size * e["net_return"]
        for b in sorted(by_bar):
            eq *= 1 + by_bar[b]
        summary[rule] = {"n_events": sum(e["rule"] == rule for e in ev), "sleeve_cum_return_pct": round(100 * (eq - 1), 3)}
    out = {"rules": {"limit": "v175/v176 resting bid k=3.5, maker on trade-through", "taker": "v172 k=4 crash-aware taker",
                     "ladder_tp": "v183 ladder 2.5/3/3.5/4 sigma, TP at L(1+sigma) maker, else next 4h open taker (per-rung log; the "
                                  "open-notional budget is applied when scoring with equity), frozen from FREEZE_LADDER",
                     "ladder_v197": "v197 rungs under the user's rules: TP 1 sigma (maker), SL 5 sigma (market, taker 0.055%), else next 4h open "
                                    "(taker, adverse long funding); per-rung log, stop-risk budget applied when scoring; frozen from FREEZE_V197"},
           "freeze_ladder": FREEZE_LADDER.isoformat(),
           "size": SIZE, "freeze": FREEZE.isoformat(), "scored_until": datetime.now(timezone.utc).isoformat(),
           "summary": summary, "events": ev}
    OUT.write_text(json.dumps(out, indent=1))
    print(f"dip sleeve forward since {FREEZE.isoformat()}: {summary}")


if __name__ == "__main__":
    main()
