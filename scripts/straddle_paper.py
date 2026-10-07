"""Prospective PAPER ledger for the weekly short-straddle sleeve with REAL Bybit option quotes (research only).

Frozen rule (docs/opencode/OPENCODE_W_ops_straddlepaper.md; copies oc_vrpstraddle V2, prices from Bybit):
every Friday at the first run >= 08:05 UTC and < 09:00 UTC, per coin (BTC, ETH),
sell 1 ATM call + 1 put on the NEXT Friday 08:00 UTC expiry at the BEST BID of
each leg (taker fee per leg min(0.0003 x S, 0.07 x price); skip the coin if a leg
has no bid). Size q = 0.5 x f x E / S floored to the Bybit lot step (skip if 0).
Hourly: mark at MARK; SL (any hourly run) buys back at ASK + taker fee when
(premium - entry fees - ask close cost) <= -premium. TP (4h-close runs only)
buys back at ASK + fee when ask close cost <= 0.3 x premium (taker fill logged,
mark-based maker version as a side field). Else settle at expiry at Bybit's
delivery price (fallback: index mean, labelled); ITM leg pays delivery fee
min(0.00015 x S, 0.125 x intrinsic). Research comparison each week: BS price at
0.97 x DVOL (Deribit public volatility-index, last closed hourly candle).

Public GET endpoints only (Bybit V5 market + Deribit public) - never signed,
never POST, never an order, never reads .env.

Usage (idempotent hourly loop; the leader starts the loop, workers use --once):

    .venv\\Scripts\\python.exe scripts/straddle_paper.py --once --dry-run
    .venv\\Scripts\\python.exe scripts/straddle_paper.py --once --equity 5000 --f 0.25 --tag straddle

State in artifacts/bot/paper_<tag>/state.json, every decision appended to
artifacts/bot/paper_<tag>/actions.jsonl. Prints the frozen rule sha256 at
start plus a one-line status. API errors use retry/backoff and never crash
the loop (logged as error actions, exit 0). --dry-run writes no state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- frozen rule

RULE_PARAMS = {
    "coins": ["BTC", "ETH"],
    "entry_weekday": "Friday",
    "entry_window_utc": ["08:05", "09:00"],
    "expiry_rule": "NEXT Friday 08:00 UTC after entry",
    "strike_rule": "listed strike nearest to S (ties -> lower)",
    "entry_fill": "sell call+put at BEST BID each leg; skip coin if a leg has no bid",
    "fee_entry_taker": "min(0.0003 x S, 0.07 x leg_price) per leg",
    "fee_close_taker": "min(0.0003 x S, 0.07 x leg_price) per leg",
    "fee_close_maker_side": "min(0.0002 x S, 0.07 x leg_price) per leg (side field only)",
    "fee_delivery": "min(0.00015 x S_settle, 0.125 x intrinsic) on the ITM leg",
    "sizing": "q = 0.5 x f x E / S per coin, floored to Bybit lot step; 0 -> skip",
    "sl": "hourly: (premium - entry_fees - ask_close_cost) <= -premium -> buy back at ASK + taker fee",
    "tp": "4h closes (00/04/08/12/16/20 UTC): ask_close_cost <= 0.3 x premium -> buy back at ASK + fee",
    "settlement": "Bybit delivery-price; fallback index mean (labelled)",
    "research_compare": "BS call+put at 0.97 x DVOL (Deribit public get_volatility_index_data, last closed 1h candle)",
    "venue": "Bybit V5 + Deribit public market endpoints only (no orders)",
}

MS_HOUR = 3_600_000
MS_DAY = 86_400_000
TP_HOURS = (0, 4, 8, 12, 16, 20)
DERIBIT_DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"


def rule_sha256() -> str:
    canon = json.dumps(RULE_PARAMS, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


# ---------------------------------------------------------------- paths

ROOT = Path(__file__).resolve().parents[1]


def state_dir_for(tag: str) -> Path:
    safe = "".join(c for c in str(tag) if c.isalnum() or c in ("-", "_")) or "straddle"
    return ROOT / "artifacts" / "bot" / f"paper_{safe}"


# ---------------------------------------------------------------- pure helpers (unit-tested, no I/O)

def in_entry_window(now_ms: int) -> bool:
    """True only on Friday 08:05:00 UTC <= t < 09:00:00 UTC."""
    d = datetime.fromtimestamp(int(now_ms) / 1000, tz=timezone.utc)
    return d.weekday() == 4 and (d.hour, d.minute) >= (8, 5) and (d.hour, d.minute) < (9, 0)


def is_tp_hour(now_ms: int) -> bool:
    """TP is checked only on 4h-close runs (00/04/08/12/16/20 UTC hours)."""
    return datetime.fromtimestamp(int(now_ms) / 1000, tz=timezone.utc).hour in TP_HOURS


def next_friday_0800_ms(now_ms: int) -> int:
    """Next Friday 08:00 UTC strictly after now (≈6.99 days on entry Friday)."""
    d = datetime.fromtimestamp(int(now_ms) / 1000, tz=timezone.utc)
    midnight = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    days_ahead = (4 - d.weekday()) % 7  # Friday == 4
    cand_ms = int(midnight.timestamp() * 1000) + days_ahead * MS_DAY + 8 * MS_HOUR
    if cand_ms <= int(now_ms):
        cand_ms += 7 * MS_DAY
    return cand_ms


def week_key(expiry_ms: int) -> str:
    return datetime.fromtimestamp(int(expiry_ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def parse_strike(symbol: str) -> float | None:
    """Bybit option symbol {BASE}-{EXP}-{STRIKE}-{C|P}-USDT -> strike float."""
    try:
        return float(str(symbol).split("-")[2])
    except (IndexError, TypeError, ValueError):
        return None


def nearest_strike(strikes: list, s: float) -> float | None:
    """Listed strike nearest to S; ties -> the lower strike."""
    try:
        s = float(s)
    except (TypeError, ValueError):
        return None
    best = None
    for k in strikes:
        try:
            k = float(k)
        except (TypeError, ValueError):
            continue
        if best is None or abs(k - s) < abs(best - s) - 1e-12 or (
                abs(abs(k - s) - abs(best - s)) <= 1e-12 and k < best):
            best = k
    return best


def floor_to_step(qty: float, step: float) -> float:
    try:
        qty, step = float(qty), float(step)
    except (TypeError, ValueError):
        return 0.0
    if not (qty > 0 and step > 0):
        return 0.0
    return round(math.floor(qty / step + 1e-9) * step, 8)


def fee_taker(leg_price: float, s: float) -> float:
    return min(0.0003 * float(s), 0.07 * float(leg_price))


def fee_maker(leg_price: float, s: float) -> float:
    return min(0.0002 * float(s), 0.07 * float(leg_price))


def delivery_fee(s_settle: float, intrinsic: float) -> float:
    intrinsic = float(intrinsic)
    if intrinsic <= 0:
        return 0.0
    return min(0.00015 * float(s_settle), 0.125 * intrinsic)


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(s: float, k: float, t: float, sigma: float) -> float:
    s, k = float(s), float(k)
    if not (s > 0 and k > 0):
        return float("nan")
    intrinsic = max(s - k, 0.0)
    if not (t > 0 and sigma > 0):
        return intrinsic
    sqt = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + 0.5 * sigma * sigma * t) / sqt
    return float(s * _ncdf(d1) - k * _ncdf(d1 - sqt))


def bs_put(s: float, k: float, t: float, sigma: float) -> float:
    s, k = float(s), float(k)
    if not (s > 0 and k > 0):
        return float("nan")
    intrinsic = max(k - s, 0.0)
    if not (t > 0 and sigma > 0):
        return intrinsic
    sqt = sigma * math.sqrt(t)
    d1 = (math.log(s / k) + 0.5 * sigma * sigma * t) / sqt
    d2 = d1 - sqt
    return float(k * _ncdf(-d2) - s * _ncdf(-d1))


def close_cost_ask(q: float, ask_c: float, ask_p: float) -> float:
    return float(q) * (float(ask_c) + float(ask_p))


def sl_triggered(premium: float, entry_fees: float, cost_to_close: float) -> bool:
    """SL when mark P&L (premium - fees - close cost) <= -premium."""
    return (float(premium) - float(entry_fees) - float(cost_to_close)) <= -float(premium)


def tp_triggered(premium: float, cost_to_close: float) -> bool:
    return float(cost_to_close) <= 0.3 * float(premium)


def settle_realised(q: float, premium: float, entry_fees: float,
                    s_settle: float, k: float) -> tuple[float, float, float]:
    """(realised PnL, intrinsic/unit, delivery fee total) for expiry settlement."""
    intrinsic = abs(float(s_settle) - float(k))
    dfee = float(q) * delivery_fee(float(s_settle), intrinsic)
    realised = float(premium) - float(entry_fees) - float(q) * intrinsic - dfee
    return realised, intrinsic, dfee


# ---------------------------------------------------------------- public I/O

def _call_public(client, path: str, tries: int = 3, **params):
    last: Exception | None = None
    for attempt in range(int(tries)):
        try:
            return client.public(path, **params)
        except Exception as exc:  # noqa: BLE001 - network flakiness, never crash the loop
            last = exc
            msg = repr(exc)
            rate = any(c in msg for c in ("10006", "429", "418"))
            if attempt + 1 >= int(tries):
                break
            time.sleep((1.5 if rate else 0.8) * (attempt + 1))
    assert last is not None
    raise last


def fetch_option_instruments(client, coin: str) -> list:
    """Trading option contracts for baseCoin (paginated); strike parsed from symbol."""
    out, cursor = [], None
    for _ in range(10):
        kw: dict = {"category": "option", "baseCoin": coin, "limit": 1000}
        if cursor:
            kw["cursor"] = cursor
        res = _call_public(client, "/v5/market/instruments-info", **kw)
        items = (res or {}).get("list", []) if isinstance(res, dict) else []
        for it in items:
            if not isinstance(it, dict) or str(it.get("status", "")) != "Trading":
                continue
            if str(it.get("baseCoin", "")).upper() != coin.upper():
                continue
            try:
                dlv = int(float(it.get("deliveryTime") or 0))
            except (TypeError, ValueError):
                continue
            if dlv <= 0:
                continue
            lot = it.get("lotSizeFilter") or {}
            try:
                step = float(lot.get("qtyStep") or 0)
            except (TypeError, ValueError):
                step = 0.0
            out.append({"symbol": str(it.get("symbol")), "coin": coin.upper(),
                        "delivery_ms": dlv, "strike": parse_strike(it.get("symbol")),
                        "otype": str(it.get("optionsType", "")),
                        "qty_step": step if step > 0 else None,
                        "deliveryFeeRate": str(it.get("deliveryFeeRate", ""))})
        cursor = (res or {}).get("nextPageCursor") if isinstance(res, dict) else None
        if not cursor:
            break
    return out


def fetch_option_tickers(client, coin: str) -> dict:
    """symbol -> ticker row for baseCoin (single public call, filtered locally)."""
    res = _call_public(client, "/v5/market/tickers", category="option", baseCoin=coin)
    rows = (res or {}).get("list", []) if isinstance(res, dict) else []
    out = {}
    for r in rows:
        if isinstance(r, dict) and r.get("symbol"):
            out[str(r["symbol"])] = r
    return out


def _fnum(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def leg_quotes(row: dict | None) -> dict | None:
    """(bid, ask, mark, bidIV, markIV) or None when the row is unusable."""
    if not isinstance(row, dict):
        return None
    bid, ask = _fnum(row.get("bid1Price")), _fnum(row.get("ask1Price"))
    try:
        mark = float(row.get("markPrice") or 0)
    except (TypeError, ValueError):
        mark = 0.0
    if not (mark > 0):
        return None
    return {"bid": bid, "ask": ask, "mark": mark,
            "bid_iv": _fnum(row.get("bid1Iv")), "mark_iv": _fnum(row.get("markIv"))}


def ref_price_from_tickers(rows: list) -> tuple[float | None, str]:
    """S = underlyingPrice preferred, else indexPrice, from option tickers."""
    for key, src in (("underlyingPrice", "underlying"), ("indexPrice", "index")):
        for r in rows:
            v = _fnum((r or {}).get(key))
            if v:
                return v, src
    return None, "missing"


def fetch_dvol(currency: str, now_ms: int) -> float | None:
    """Last CLOSED hourly DVOL candle (Deribit public); None on any failure."""
    try:
        url = (f"{DERIBIT_DVOL_URL}?currency={currency}&resolution=3600"
               f"&end_timestamp={int(now_ms)}")
        req = urllib.request.Request(url, headers={"User-Agent": "straddle-paper/1.0"})
        with urllib.request.urlopen(req, timeout=10) as fh:
            doc = json.loads(fh.read().decode("utf-8", "replace"))
        data = (doc.get("result") or {}).get("data") or []
        closed = [r for r in data
                  if isinstance(r, (list, tuple)) and len(r) >= 5
                  and int(r[0]) + MS_HOUR <= int(now_ms)]
        row = closed[-1] if closed else (data[-1] if data else None)
        return float(row[4]) if row else None
    except Exception:  # noqa: BLE001 - comparison only, never crash the loop
        return None


def fetch_delivery_price(client, coin: str, symbol: str):
    """(price, source) or (None, None); source delivery-price | index-fallback."""
    try:
        res = _call_public(client, "/v5/market/delivery-price",
                           category="option", baseCoin=coin)
        rows = (res or {}).get("list", []) if isinstance(res, dict) else []
        for r in rows:
            if isinstance(r, dict) and str(r.get("symbol", "")) == symbol:
                try:
                    px = float(r.get("deliveryPrice") or 0)
                except (TypeError, ValueError):
                    continue
                if px > 0:
                    return px, "delivery-price"
    except Exception:  # noqa: BLE001 - fall through to the labelled fallback
        pass
    return None, None


# ---------------------------------------------------------------- ledger

def blank_state(tag: str, equity: float, f: float) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "tag": tag, "equity_arg": float(equity), "f": float(f),
        "rule": dict(RULE_PARAMS), "rule_sha256": rule_sha256(),
        "created_at": now, "updated_at": now,
        "positions": {}, "history": [], "entered_weeks": [],
        "equity_curve": [],
        "totals": {"n_entered": 0, "n_skipped": 0, "realised_pnl": 0.0, "fees_paid": 0.0},
    }


def load_state(path: Path, tag: str, equity: float, f: float) -> dict:
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(st, dict) and isinstance(st.get("positions"), dict):
            st.setdefault("history", [])
            st.setdefault("entered_weeks", [])
            st.setdefault("equity_curve", [])
            tot = st.setdefault("totals", {})
            for k, v in (("n_entered", 0), ("n_skipped", 0),
                         ("realised_pnl", 0.0), ("fees_paid", 0.0)):
                tot.setdefault(k, v)
            st["rule"] = dict(RULE_PARAMS)
            st["rule_sha256"] = rule_sha256()
            return st
    except (OSError, ValueError):
        pass
    return blank_state(tag, equity, f)


def save_state(path: Path, st: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    st["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")
    import os

    os.replace(tmp, path)


def log_action(actions_path: Path, rec: dict, dry_run: bool = False) -> None:
    if dry_run:
        return
    actions_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"t": datetime.now(timezone.utc).isoformat(), **rec}
    with actions_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def mark_equity(st: dict, now_ms: int, equity: float) -> float:
    """Paper equity mark = arg equity + realised + sum(open unrealised); upserts the hour."""
    open_u = sum(float(p.get("unrealised") or 0.0) for p in (st.get("positions") or {}).values())
    eq = float(equity) + float(st["totals"]["realised_pnl"]) + open_u
    hour_ms = (int(now_ms) // MS_HOUR) * MS_HOUR
    hour_iso = datetime.fromtimestamp(hour_ms / 1000, tz=timezone.utc).isoformat()
    curve = st.setdefault("equity_curve", [])
    pt = {"t": hour_iso, "equity_mark": round(eq, 4),
          "realised": round(float(st["totals"]["realised_pnl"]), 4),
          "open_unrealised": round(open_u, 4)}
    if curve and curve[-1].get("t") == hour_iso:
        curve[-1] = pt  # restart-safe: same hour overwrites, never duplicates
    else:
        curve.append(pt)
    return eq


# ---------------------------------------------------------------- one pass

def _dvol_of(dvol_fetcher, currency: str, now_ms: int):
    if dvol_fetcher is not None:
        try:
            return dvol_fetcher(currency, now_ms)
        except Exception:  # noqa: BLE001
            return None
    return fetch_dvol(currency, now_ms)


def run_once(client, sdir: Path, equity: float, f: float, tag: str,
             now_ms: int | None = None, dvol_fetcher=None,
             dry_run: bool = False) -> dict:
    """One idempotent hourly pass. Never raises on API errors (logs + status)."""
    now_ms = int(now_ms) if now_ms is not None else int(time.time() * 1000)
    now_iso = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).isoformat()
    sdir = Path(sdir)
    state_path = sdir / "state.json"
    actions_path = sdir / "actions.jsonl"
    st = load_state(state_path, tag, equity, f)
    st["equity_arg"] = float(equity)
    st["f"] = float(f)
    counts = {"entered": 0, "settled": 0, "skipped": 0, "errors": 0, "holding": 0}
    flat_no_window = False

    target_expiry = next_friday_0800_ms(now_ms)
    target_week = week_key(target_expiry)
    entry_open = in_entry_window(now_ms)
    tp_open = is_tp_hour(now_ms)

    for coin in RULE_PARAMS["coins"]:
        pos = (st["positions"] or {}).get(coin)

        # ---- fetch this coin's tickers once per pass
        try:
            tickers = fetch_option_tickers(client, coin)
        except Exception as exc:  # noqa: BLE001
            counts["errors"] += 1
            log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                       "call": "tickers", "note": str(exc)[:300]}, dry_run)
            continue

        # ---- manage an open position
        if pos:
            call_q = leg_quotes(tickers.get(pos["call_symbol"]))
            put_q = leg_quotes(tickers.get(pos["put_symbol"]))
            if call_q is None or put_q is None or call_q["ask"] is None or put_q["ask"] is None:
                counts["errors"] += 1
                log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                           "note": "missing ask/mark quotes; retry next run"}, dry_run)
                continue
            s_now, _ = ref_price_from_tickers(
                [tickers.get(pos["call_symbol"]), tickers.get(pos["put_symbol"])])
            s_now = s_now or float(pos["S_ref"])
            q, prem = float(pos["q"]), float(pos["premium"])
            ask_cost = close_cost_ask(q, call_q["ask"], put_q["ask"])

            # ---- expiry settlement
            if now_ms >= int(pos["expiry_ms"]):
                s_set, src = fetch_delivery_price(client, coin, pos["call_symbol"])
                if s_set is None:
                    rows = [tickers.get(pos["call_symbol"]), tickers.get(pos["put_symbol"])]
                    vals = [v for k in ("underlyingPrice", "indexPrice")
                            for v in [_fnum((r or {}).get(k))] if v]
                    if vals:
                        s_set, src = sum(vals) / len(vals), "index-fallback"
                if s_set is None:
                    counts["errors"] += 1
                    log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                               "note": "expiry due but no settlement/index price"}, dry_run)
                    continue
                realised, intr, dfee = settle_realised(q, prem, float(pos["entry_fees"]),
                                                       float(s_set), float(pos["K"]))
                st["history"].append({**pos, "status": "settled", "reason": "expired",
                                     "S_settle": float(s_set), "settle_source": src,
                                     "settled_at": now_iso, "realised_pnl": round(realised, 6)})
                st["positions"].pop(coin, None)
                st["totals"]["realised_pnl"] = round(float(st["totals"]["realised_pnl"]) + realised, 6)
                st["totals"]["fees_paid"] = round(
                    float(st["totals"]["fees_paid"]) + float(pos["entry_fees"]) + dfee, 6)
                counts["settled"] += 1
                log_action(actions_path, {"op": "settle", "tag": tag, "coin": coin,
                                           "week": pos.get("week"), "S_settle": float(s_set),
                                           "source": src, "intrinsic": round(intr, 4),
                                           "realised_pnl": round(realised, 4)}, dry_run)
                continue

            # ---- stop-loss (every hourly run): buy back at the ASK + taker fee
            if sl_triggered(prem, float(pos["entry_fees"]), ask_cost):
                cfee = fee_taker(call_q["ask"], s_now) + fee_taker(put_q["ask"], s_now)
                realised = prem - float(pos["entry_fees"]) - ask_cost - cfee
                st["history"].append({**pos, "status": "closed", "reason": "sl",
                                     "closed_at": now_iso,
                                     "close_ask_c": call_q["ask"], "close_ask_p": put_q["ask"],
                                     "close_fees": round(cfee, 6),
                                     "realised_pnl": round(realised, 6)})
                st["positions"].pop(coin, None)
                st["totals"]["realised_pnl"] = round(float(st["totals"]["realised_pnl"]) + realised, 6)
                st["totals"]["fees_paid"] = round(
                    float(st["totals"]["fees_paid"]) + float(pos["entry_fees"]) + cfee, 6)
                counts["settled"] += 1
                log_action(actions_path, {"op": "close", "tag": tag, "coin": coin,
                                           "reason": "sl", "week": pos.get("week"),
                                           "realised_pnl": round(realised, 4)}, dry_run)
                continue

            # ---- take-profit (4h closes only): buy back at the ASK + fee
            if tp_open and tp_triggered(prem, ask_cost):
                cfee = fee_taker(call_q["ask"], s_now) + fee_taker(put_q["ask"], s_now)
                realised = prem - float(pos["entry_fees"]) - ask_cost - cfee
                mark_cost = float(q) * (call_q["mark"] + put_q["mark"])
                maker_side = mark_cost + fee_maker(call_q["mark"], s_now) + fee_maker(put_q["mark"], s_now)
                st["history"].append({**pos, "status": "closed", "reason": "tp",
                                     "closed_at": now_iso,
                                     "close_ask_c": call_q["ask"], "close_ask_p": put_q["ask"],
                                     "close_fees": round(cfee, 6),
                                     "maker_side_cost": round(maker_side, 6),
                                     "realised_pnl": round(realised, 6)})
                st["positions"].pop(coin, None)
                st["totals"]["realised_pnl"] = round(float(st["totals"]["realised_pnl"]) + realised, 6)
                st["totals"]["fees_paid"] = round(
                    float(st["totals"]["fees_paid"]) + float(pos["entry_fees"]) + cfee, 6)
                counts["settled"] += 1
                log_action(actions_path, {"op": "close", "tag": tag, "coin": coin,
                                           "reason": "tp", "week": pos.get("week"),
                                           "realised_pnl": round(realised, 4),
                                           "maker_side_cost": round(maker_side, 4)}, dry_run)
                continue

            # ---- hold: mark at MARK prices
            mark_cost = float(q) * (call_q["mark"] + put_q["mark"])
            pos["last_mark_c"] = call_q["mark"]
            pos["last_mark_p"] = put_q["mark"]
            pos["last_mark_iv_c"] = call_q["mark_iv"]
            pos["last_mark_iv_p"] = put_q["mark_iv"]
            pos["unrealised"] = round(prem - float(pos["entry_fees"]) - mark_cost, 4)
            counts["holding"] += 1
            log_action(actions_path, {"op": "mark", "tag": tag, "coin": coin,
                                       "week": pos.get("week"),
                                       "unrealised": pos["unrealised"]}, dry_run)
            continue

        # ---- flat: entry only inside the Friday window (idempotent per week)
        if not entry_open:
            d = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
            if d.weekday() == 4 and (d.hour, d.minute) >= (9, 0):
                counts["skipped"] += 1
                log_action(actions_path, {"op": "skip", "tag": tag, "coin": coin,
                                           "week": target_week,
                                           "note": "entry window 08:05-09:00 missed; skip the week"},
                           dry_run)
            else:
                flat_no_window = True
                log_action(actions_path, {"op": "wait", "tag": tag, "coin": coin,
                                           "note": "no entry window (flat, outside Fri 08:05-09:00)"},
                           dry_run)
            continue

        week_id = f"{coin}:{target_week}"
        if week_id in (st.get("entered_weeks") or []):
            counts["skipped"] += 1
            log_action(actions_path, {"op": "skip", "tag": tag, "coin": coin,
                                       "week": target_week,
                                       "note": "already entered this week; no double entry"},
                       dry_run)
            continue
        try:
            contracts = [c for c in fetch_option_instruments(client, coin)
                         if int(c["delivery_ms"]) == int(target_expiry)]
        except Exception as exc:  # noqa: BLE001
            counts["errors"] += 1
            log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                       "call": "instruments-info", "note": str(exc)[:300]}, dry_run)
            continue
        if not contracts:
            counts["skipped"] += 1
            st["totals"]["n_skipped"] = int(st["totals"].get("n_skipped", 0)) + 1
            log_action(actions_path, {"op": "skip", "tag": tag, "coin": coin,
                                       "week": target_week,
                                       "note": "no Trading contracts for the next-Friday expiry"},
                       dry_run)
            continue
        exp_rows = [tickers.get(c["symbol"]) for c in contracts]
        exp_rows = [r for r in exp_rows if isinstance(r, dict)]
        s_ref, s_src = ref_price_from_tickers(exp_rows)
        if s_ref is None:
            counts["errors"] += 1
            log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                       "note": "no underlying/index price in tickers"}, dry_run)
            continue
        strikes = sorted({float(c["strike"]) for c in contracts if c.get("strike") is not None})
        k = nearest_strike(strikes, s_ref)
        call_c = next((c for c in contracts if float(c["strike"] or -1) == k
                       and c["otype"].lower().startswith("call")), None)
        put_c = next((c for c in contracts if float(c["strike"] or -1) == k
                      and c["otype"].lower().startswith("put")), None)
        if call_c is None or put_c is None:
            counts["skipped"] += 1
            log_action(actions_path, {"op": "skip", "tag": tag, "coin": coin,
                                       "week": target_week,
                                       "note": f"no call+put pair listed at strike {k}"}, dry_run)
            continue
        cq, pq = leg_quotes(tickers.get(call_c["symbol"])), leg_quotes(tickers.get(put_c["symbol"]))
        if cq is None or pq is None or cq["bid"] is None or pq["bid"] is None:
            counts["skipped"] += 1
            st["totals"]["n_skipped"] = int(st["totals"].get("n_skipped", 0)) + 1
            log_action(actions_path, {"op": "skip", "tag": tag, "coin": coin,
                                       "week": target_week, "strike": k,
                                       "note": "a leg has no bid; skip the coin for the week"},
                       dry_run)
            continue
        step = call_c.get("qty_step") or put_c.get("qty_step") or (0.01 if coin == "BTC" else 0.1)
        q = floor_to_step(0.5 * float(f) * float(equity) / float(s_ref), float(step))
        if q <= 0:
            counts["skipped"] += 1
            log_action(actions_path, {"op": "skip", "tag": tag, "coin": coin,
                                       "week": target_week,
                                       "note": "qty rounds to 0 at the lot step; skip"}, dry_run)
            continue
        premium = float(q) * (float(cq["bid"]) + float(pq["bid"]))
        efee = fee_taker(cq["bid"], s_ref) + fee_taker(pq["bid"], s_ref)
        dvol = _dvol_of(dvol_fetcher, coin, now_ms)
        t_yrs = (int(target_expiry) - int(now_ms)) / (365.0 * 86_400_000.0)
        bs_prem = None
        if dvol is not None and dvol > 0:
            sig = 0.97 * float(dvol) / 100.0
            bs_prem = float(q) * (bs_call(s_ref, k, t_yrs, sig) + bs_put(s_ref, k, t_yrs, sig))
        st["positions"][coin] = {
            "coin": coin, "call_symbol": call_c["symbol"], "put_symbol": put_c["symbol"],
            "K": float(k), "S_ref": float(s_ref), "S_source": s_src,
            "expiry_ms": int(target_expiry), "week": target_week,
            "entry_time": now_iso, "q": float(q),
            "bid_c": float(cq["bid"]), "bid_p": float(pq["bid"]),
            "ask_c_entry": float(cq["ask"]) if cq["ask"] else None,
            "ask_p_entry": float(pq["ask"]) if pq["ask"] else None,
            "bid_iv_c": cq["bid_iv"], "bid_iv_p": pq["bid_iv"],
            "mark_iv_c": cq["mark_iv"], "mark_iv_p": pq["mark_iv"],
            "premium": round(premium, 6), "entry_fees": round(float(efee), 6),
            "equity_entry": float(equity), "f": float(f),
            "dvol_at_entry": dvol, "bs_premium_097dvol": bs_prem,
            "t_years": round(t_yrs, 6),
            "last_mark_c": float(cq["mark"]), "last_mark_p": float(pq["mark"]),
            "unrealised": round(premium - float(efee) - float(q) * (float(cq["mark"]) + float(pq["mark"])), 4),
        }
        st.setdefault("entered_weeks", [])
        if week_id not in st["entered_weeks"]:
            st["entered_weeks"].append(week_id)
        st["totals"]["n_entered"] = int(st["totals"].get("n_entered", 0)) + 1
        counts["entered"] += 1
        log_action(actions_path, {"op": "entry", "tag": tag, "coin": coin,
                                   "week": target_week,
                                   "call": call_c["symbol"], "put": put_c["symbol"],
                                   "K": k, "S_ref": float(s_ref), "q": float(q),
                                   "premium": round(premium, 4),
                                   "entry_fees": round(float(efee), 4),
                                   "bid_iv": [cq["bid_iv"], pq["bid_iv"]],
                                   "mark_iv": [cq["mark_iv"], pq["mark_iv"]],
                                   "dvol": dvol, "bs_premium_097dvol":
                                       round(bs_prem, 4) if bs_prem is not None else None},
                   dry_run)

    eq_mark = mark_equity(st, now_ms, float(equity))
    if not dry_run:
        save_state(state_path, st)
    open_n = len(st.get("positions") or {})
    base = (f"straddle_paper tag={tag} open={open_n} entered={counts['entered']} "
            f"settled={counts['settled']} skipped={counts['skipped']} "
            f"errors={counts['errors']} realised={float(st['totals']['realised_pnl']):+.2f} "
            f"equity_mark={eq_mark:.2f}")
    if open_n == 0 and counts["entered"] == 0 and counts["settled"] == 0 and flat_no_window:
        base += " no entry window"
    return {"status": "ok", "summary": base, **counts}


def build_client(base: str = "mainnet"):
    """Public-only Bybit client (no keys, GET /v5/market/* only)."""
    sys.path.insert(0, str(ROOT))
    from bot.bybit_v5 import MAINNET, TESTNET, Bybit

    return Bybit(None, None, base=MAINNET if base == "mainnet" else TESTNET)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prospective paper ledger: weekly short straddle on REAL Bybit option quotes (public endpoints only, never places orders).")
    ap.add_argument("--once", action="store_true", help="single pass then exit (hourly loop/CRON mode)")
    ap.add_argument("--equity", type=float, default=5000.0)
    ap.add_argument("--f", type=float, default=0.25, help="fraction of equity; q = 0.5 x f x E / S per coin")
    ap.add_argument("--tag", default="straddle")
    ap.add_argument("--base", choices=("mainnet", "testnet"), default="mainnet")
    ap.add_argument("--interval", type=float, default=3600.0, help="loop interval seconds when --once is off")
    ap.add_argument("--state-dir", default=None, help="override state dir (tests)")
    ap.add_argument("--dry-run", action="store_true", help="no state write")
    a = ap.parse_args(argv)
    print(f"straddle_paper rule_sha256={rule_sha256()} rule={json.dumps(RULE_PARAMS, sort_keys=True)}", flush=True)
    if not (a.f > 0 and a.f <= 1):
        print("straddle_paper: --f must be in (0, 1]", flush=True)
        return 2
    sdir = Path(a.state_dir) if a.state_dir else state_dir_for(a.tag)
    try:
        client = build_client(a.base)
    except Exception as exc:  # noqa: BLE001
        print(f"straddle_paper tag={a.tag} status=error note=client: {str(exc)[:160]}", flush=True)
        return 0
    if a.once:
        try:
            res = run_once(client, sdir, float(a.equity), float(a.f), a.tag, dry_run=bool(a.dry_run))
        except Exception as exc:  # noqa: BLE001 - never crash the loop
            print(f"straddle_paper tag={a.tag} status=error note={str(exc)[:160]}", flush=True)
            return 0
        print(res.get("summary", res.get("status")), flush=True)
        return 0
    while True:
        try:
            res = run_once(client, sdir, float(a.equity), float(a.f), a.tag, dry_run=bool(a.dry_run))
            print(res.get("summary", res.get("status")), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"straddle_paper tag={a.tag} status=error note={str(exc)[:160]}", flush=True)
        time.sleep(float(a.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
