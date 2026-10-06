"""Daily 30-day time-series-momentum (TSMOM) sleeve for a future optional bot flag.

Research rule (research/tournament/oc_tsmom/{PLAN.md,REPORT.md,run_tsmom.py},
idea #36, verdict NOT PROMISING — the 0.25x overlay lifts return 5/5 years but
worsens max yearly DD 5/5, corr +0.17..+0.47 with the base): at each UTC day
close D, signal(sym,D) = sign of the 30-day close-to-close return
C(D)/C(D-30)-1 over BTC+ETH; position = signal x min(0.10/vol, 1.0) where vol
is the realised 30d vol of daily log returns annualised with sqrt(365), held
over the next day E = D+1 and entered at the day-E open O(E).

This module is the executable mirror of that rule as pure functions (no I/O,
no network, no keys):

  signal(daily_closes) -> {sym: -1|0|+1}
  target_weights(signals, vols, vol_target=0.10, cap=1.0, sleeve_weight=0.25)
  orders(targets, positions, prices, equity, now, atr=None, instruments=None,
         tp_mult=None) -> list[mirror.Order]

Causality: signal/weights at close D use only closes <= D; the rebalance
executes at the next day open E (limit resting from E 00:05 UTC, never in the
first 5 minutes per the user trade rule).

Execution (user trade rules: limit entries preferred, market only for
stops/exits — a daily rebalance uses limit orders near the open with an
expiry, no chasing):

- One LIMIT rebalance order per coin, resting from day open + 5 min until
  23:55 UTC the same day (meta valid_until; the runner cancels afterwards and
  never chases). Buy limits sit 5 bps BELOW the day-open price, sell limits
  5 bps ABOVE it.
- reduce_only=True (kind "reduce") when the order shrinks an open position
  toward the target (same direction, smaller size, or flatten to zero);
  otherwise kind "entry", reduce_only=False.
- Every non-zero target position carries a protective market stop at 3 x
  daily ATR from the day open (kind "stop", reduce-only, hedge-mode
  positionIdx: longs 1 / shorts 2). Stops are Market by construction
  (mirror.Order kind "stop" -> to_exchange orderType Market).
- DEVIATION from the dip/book rule (documented): no take-profit by default —
  this is a trend sleeve that lets winners run. Pass tp_mult=6.0 for the
  optional take-profit limit at 6 x ATR from the open (kind "tp").
- Sizing: qty = |target_weight * equity / open - current_qty_coins|; the
  change is skipped when below the lot / notional minimum (default 5 USDT,
  else the instrument's min_notional / min_qty). Rounding uses the existing
  exchange-unit helper bot.bybit_v5.round_step (qty down to qty_step, prices
  to tick: buys down / sells up so a limit is never worse than the plan).

Gate costs (for the caller/REPORT, not charged here): rebalance pays taker
0.055% on |dpos|, longs pay 0.01%/8h funding (shorts zero).
"""

from __future__ import annotations

import math

import pandas as pd

from bot import mirror

try:
    from bot.bybit_v5 import round_step
except Exception:  # pragma: no cover - pure fallback when imported standalone
    round_step = None  # type: ignore

COINS = ("BTCUSDT", "ETHUSDT")
LOOKBACK = 30  # 30-day return needs closes C(D-30)..C(D): 31 closes
LIMIT_BPS = 0.0005  # 5 bps offset from the day open
STOP_ATR_MULT = 3.0  # protective stop distance
VALID_FROM_MIN = 5  # user rule: nothing rests/fills in the first 5 minutes
MIN_NOTIONAL_DEFAULT = 5.0  # Bybit USDT-perp minimum when no instrument known


# --------------------------------------------------------------------------
def _closes_list(v):
    try:
        import pandas as _pd

        if isinstance(v, _pd.Series):
            return [float(x) for x in v.tolist()]
    except Exception:
        pass
    try:
        return [float(x) for x in list(v)]
    except (TypeError, ValueError):
        return []


def signal(daily_closes) -> dict[str, int]:
    """30-day sign per coin: +1 if C(D)/C(D-30)-1 > 0, -1 if < 0, else 0.

    daily_closes: {sym -> sequence of daily closes oldest..newest} (newest =
      C(D)), or a DataFrame indexed by day with one column per coin (uses the
      last 31 rows). Needs 31 finite closes; any NaN/non-positive in
      C(D-30)..C(D), a zero C(D-30), or < 31 closes -> 0 (flat).
    Only closes <= D are read (causal by construction: the caller passes the
    series truncated at D).
    """
    try:
        import pandas as _pd

        if isinstance(daily_closes, _pd.DataFrame):
            src = {c: daily_closes[c].tolist() for c in daily_closes.columns}
        else:
            src = dict(daily_closes or {})
    except (TypeError, ValueError, AttributeError):
        return {}
    out: dict[str, int] = {}
    for sym, seq in src.items():
        xs = _closes_list(seq)
        if len(xs) < LOOKBACK + 1:
            out[sym] = 0
            continue
        win = xs[-(LOOKBACK + 1):]
        if any(x is None or not math.isfinite(x) or x <= 0 for x in win):
            out[sym] = 0
            continue
        r = win[-1] / win[0] - 1.0
        out[sym] = 1 if r > 0 else (-1 if r < 0 else 0)
    return out


def target_weights(signals, vols, vol_target: float = 0.10, cap: float = 1.0,
                   sleeve_weight: float = 0.25) -> dict[str, float]:
    """Vol-targeted sleeve weights as fractions of TOTAL account equity.

    weight(sym) = sleeve_weight * signal(sym) * min(vol_target/vol(sym), cap).
    vols use the research definition (std of 30 daily log returns, ddof=1,
    x sqrt(365)). Missing/NaN/non-positive vol or a zero signal -> 0.
    Default sleeve_weight=0.25 reproduces the research overlay
    r_c = r_b + 0.25 * r_s (per-coin max = 0.25 x total equity at cap).
    """
    out: dict[str, float] = {}
    try:
        items = list((signals or {}).items())
    except AttributeError:
        return {}
    vols = vols or {}
    for sym, s in items:
        try:
            si = int(s)
        except (TypeError, ValueError):
            out[sym] = 0.0
            continue
        if si not in (-1, 0, 1):
            si = 1 if si > 0 else (-1 if si < 0 else 0)
        if si == 0:
            out[sym] = 0.0
            continue
        try:
            v = float(vols.get(sym)) if isinstance(vols, dict) else float("nan")
        except (TypeError, ValueError):
            v = float("nan")
        if not math.isfinite(v) or not v > 0:
            out[sym] = 0.0
            continue
        try:
            vt, cp, sw = float(vol_target), float(cap), float(sleeve_weight)
        except (TypeError, ValueError):
            out[sym] = 0.0
            continue
        if not (vt > 0 and cp > 0 and sw >= 0):
            out[sym] = 0.0
            continue
        out[sym] = si * min(vt / v, cp) * sw
    return out


# --------------------------------------------------------------------------
def _day_bounds(now) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    ts = pd.Timestamp(now)
    day = ts.tz_convert("UTC").floor("D") if ts.tzinfo is not None else ts.tz_localize("UTC").floor("D")
    return day, day + pd.Timedelta(minutes=VALID_FROM_MIN), day + pd.Timedelta(hours=23, minutes=55)


def _round_qty(qty: float, step: str | None) -> float:
    if step is None or round_step is None:
        return float(qty)
    try:
        return float(round_step(qty, str(step)))
    except (TypeError, ValueError, ArithmeticError):
        return float(qty)


def _round_px(px: float, tick: str | None, up: bool) -> float:
    if tick is None or round_step is None:
        return float(px)
    try:
        return float(round_step(px, str(tick), up=up))
    except (TypeError, ValueError, ArithmeticError):
        return float(px)


def orders(targets, positions=None, prices=None, equity=None, now=None,
           atr=None, instruments=None, tp_mult=None) -> list:
    """One LIMIT rebalance order per coin + protective 3xATR market stop.

    targets: {sym -> target weight fraction of total equity} (signed; output
      of target_weights). positions: {sym -> current qty in coins, signed
      (+ long / - short)}. prices: {sym -> day-open price O(E)}. equity:
      account equity in USDT. now: day-E open timestamp (UTC; orders rest
      E 00:05 -> E 23:55 UTC, meta valid_until). atr: {sym -> daily ATR in
      price units} for the 3x stop (and the optional tp_mult TP). Missing /
      non-positive ATR -> rebalance without a stop (documented; the runner
      must supply ATR so every position carries a stop). instruments:
      {sym -> {qty_step, min_qty, min_notional, tick}} for exchange-unit
      rounding and minimums (default: min notional 5 USDT, no step
      rounding). tp_mult: None (default, no take-profit — trend-sleeve
      deviation) or e.g. 6.0 for an optional TP limit at tp_mult x ATR.

    Returns a list of mirror.Order (rebalance kind "entry"/"reduce", stops
    kind "stop", optional TPs kind "tp"). Skips coins with no target change,
    bad prices/equity, or a delta below the lot / notional minimum.
    """
    targets = dict(targets or {})
    positions = dict(positions or {})
    prices = dict(prices or {})
    atr = dict(atr or {})
    instruments = dict(instruments or {}) if instruments else {}
    try:
        eq = float(equity)
    except (TypeError, ValueError):
        return []
    if not eq > 0 or now is None:
        return []
    try:
        tp_m = float(tp_mult) if tp_mult is not None else None
    except (TypeError, ValueError):
        tp_m = None
    if tp_m is not None and not tp_m > 0:
        tp_m = None

    day, valid_from, valid_until = _day_bounds(now)
    tag = day.strftime("%Y%m%d")
    out: list = []
    for sym in sorted(targets):
        try:
            tgt = float(targets[sym])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(tgt):
            continue
        try:
            ref = float(prices.get(sym))
        except (TypeError, ValueError):
            continue
        if not ref > 0:
            continue
        try:
            cur = float(positions.get(sym, 0.0))
        except (TypeError, ValueError):
            cur = 0.0
        if not math.isfinite(cur):
            cur = 0.0
        tgt_qty = tgt * eq / ref
        delta = tgt_qty - cur
        if delta == 0.0 or not math.isfinite(delta):
            continue
        side = "Buy" if delta > 0 else "Sell"
        # shrinking = moving toward (or to) zero on the same side.
        shrinking = (tgt == 0.0 and cur != 0.0) or (
            math.copysign(1.0, tgt_qty) == math.copysign(1.0, cur)
            and abs(tgt_qty) < abs(cur) - 1e-18
        ) if cur != 0.0 else False
        if tgt_qty == 0.0:
            pidx = 1 if cur > 0 else 2
        else:
            pidx = 1 if tgt_qty > 0 else 2

        inst = instruments.get(sym) or {}
        qty_step = inst.get("qty_step")
        tick = inst.get("tick")
        try:
            min_qty = float(inst.get("min_qty", 0.0) or 0.0)
        except (TypeError, ValueError):
            min_qty = 0.0
        try:
            min_not = float(inst.get("min_notional", MIN_NOTIONAL_DEFAULT) or 0.0)
        except (TypeError, ValueError):
            min_not = MIN_NOTIONAL_DEFAULT
        if not min_not > 0:
            min_not = MIN_NOTIONAL_DEFAULT

        qty = _round_qty(abs(delta), qty_step)
        if qty <= 0 or (min_qty > 0 and qty < min_qty - 1e-18):
            continue
        if qty * ref < min_not - 1e-9:
            continue  # dust change: no order (never chase)

        raw_px = ref * (1.0 - LIMIT_BPS) if side == "Buy" else ref * (1.0 + LIMIT_BPS)
        limit_px = _round_px(raw_px, tick, up=(side == "Sell"))
        if not limit_px > 0:
            continue
        kind = "reduce" if shrinking else "entry"
        link = f"tsmom-{sym}-{tag}E"
        out.append(mirror.Order(
            link, sym, side, qty, kind, price=limit_px,
            reduce_only=bool(shrinking), position_idx=pidx, piece=link,
            meta=dict(strategy="tsmom", kind="tsmom", day=str(day.date()),
                      placed_from=str(valid_from), valid_until=str(valid_until),
                      open=float(ref), target_weight=float(tgt),
                      target_qty=float(tgt_qty), current_qty=float(cur)),
        ))

        # Protection: 3 x ATR market stop over the whole NEW position.
        if tgt_qty == 0.0:
            continue  # flat target: the (reduce-only) rebalance is the exit
        try:
            a = float(atr.get(sym)) if sym in atr else float("nan")
        except (TypeError, ValueError):
            a = float("nan")
        if not math.isfinite(a) or not a > 0:
            continue  # no ATR: rebalance without a stop (runner must supply ATR)
        stop_trigger_raw = ref - STOP_ATR_MULT * a if tgt_qty > 0 else ref + STOP_ATR_MULT * a
        if not stop_trigger_raw > 0:
            continue
        # run.to_exchange convention: long-stop trigger rounds up, short down.
        stop_trigger = _round_px(stop_trigger_raw, tick, up=(tgt_qty > 0))
        stop_qty = _round_qty(abs(tgt_qty), qty_step)
        if stop_qty <= 0:
            continue
        stop_side = "Sell" if tgt_qty > 0 else "Buy"
        slink = f"tsmom-{sym}-{tag}S"
        out.append(mirror.Order(
            slink, sym, stop_side, stop_qty, "stop", trigger=stop_trigger,
            reduce_only=True, position_idx=pidx, piece=link,
            meta=dict(strategy="tsmom", kind="tsmom", day=str(day.date()),
                      valid_until=str(valid_until), atr=float(a),
                      stop_mult=STOP_ATR_MULT),
        ))
        if tp_m is not None:
            tp_raw = ref + tp_m * a if tgt_qty > 0 else ref - tp_m * a
            if tp_raw > 0:
                tp_px = _round_px(tp_raw, tick, up=(stop_side == "Sell"))
                if tp_px > 0:
                    tlink = f"tsmom-{sym}-{tag}T"
                    out.append(mirror.Order(
                        tlink, sym, stop_side, stop_qty, "tp", price=tp_px,
                        reduce_only=True, position_idx=pidx, piece=link,
                        meta=dict(strategy="tsmom", kind="tsmom",
                                  day=str(day.date()),
                                  valid_until=str(valid_until), atr=float(a),
                                  tp_mult=float(tp_m)),
                    ))
    return out
