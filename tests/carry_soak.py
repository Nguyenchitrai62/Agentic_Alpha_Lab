"""Quote-fed carry soak harness (bot_carrysoak assignment; READ-ONLY vs bot/).

Replays synthetic-but-realistic spot + inverse-quarterly quotes for BTC/ETH
across the 2025-12-26 08:00 UTC quarterly delivery through bot.carry.decide /
note_exec / guard_carry, with fills simulated at quotes (entry IOC limits fill
when crossing, markets fill same-cycle -- stated sim assumption) and scripted
faults:

  F1 one leg rejected on entry (BTC fut leg) -> single-fill hedge retry
  F2 partial fill (ETH spot leg in two partials at different prices)
  F3 basis below 4 %/yr between attempts (ETH retry -> carry_abandon)
  F4 restart mid slice-window (JSON round-trip of the carry state)
  F5 missed slice bucket (BTC bucket 4 payload dropped: downtime sim)
  F6 exchange-side auto-settlement of the future (ETH safety Buy never fills)

Spot quotes are REAL 1m closes (data/raw/*intraday*20260924, full year 2025
local). Futures quotes are synthetic: F = S*exp(basis*DTE/365) with a realistic
basis path (~5.5 %/yr at entry, bybitq 2025 quarterly levels, decaying into
delivery); the F3 dip is scripted. No network, no keys, no real orders; bot/
code is never edited -- every invariant breach is REPORTED with file:line.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import carry  # noqa: E402
from scripts.carry_paper import MS_DAY, realised_pnl_pair

ROOT = Path(__file__).resolve().parents[1]
DLV_MS = 1766736000000  # 2025-12-26T08:00:00Z (BTCUSDZ25/ETHUSDZ25)
H26_MS = 1774598400000  # 2026-03-27T08:00:00Z (BTCUSDH26/ETHUSDH26)
T0_MS = DLV_MS - 9 * MS_DAY  # entry arc starts with front DTE 9 d (> 7 d roll)
END_MS = DLV_MS + 80 * 60 * 1000  # past the 60-min settle grace
EQUITY, F = 10000.0, 0.25
COINS = ("BTC", "ETH")
FUT = {"BTC": "BTCUSDZ25", "ETH": "ETHUSDZ25"}
FUT_NEXT = {"BTC": "BTCUSDH26", "ETH": "ETHUSDH26"}
SPOT = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
TICK = {"BTC": 0.1, "ETH": 0.01}
LOTS = {
    "BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1"),
    "ETHUSDT": dict(qty_step="0.01", min_qty="0.01", min_notional="5", tick="0.01"),
    "BTCUSDZ25": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1"),
    "ETHUSDZ25": dict(qty_step="0.01", min_qty="0.01", min_notional="5", tick="0.01"),
    "BTCUSDH26": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1"),
    "ETHUSDH26": dict(qty_step="0.01", min_qty="0.01", min_notional="5", tick="0.01"),
}
ALLOWED_SYMS = set(SPOT.values()) | set(FUT.values()) | set(FUT_NEXT.values())
SYM2COIN = {s: c for c, s in SPOT.items()}
SYM2COIN.update({s: c for c, s in FUT.items()})
SYM2COIN.update({s: c for c, s in FUT_NEXT.items()})


def load_spot() -> dict:
    """Real 1m spot closes for the replay span."""
    out = {}
    files = {"BTC": "data/raw/btc_intraday_20260924/klines_1m_2025.parquet",
             "ETH": "data/raw/majors_intraday_20260924/ETHUSDT_1m_2025.parquet"}
    lo, hi = T0_MS - 120 * 60 * 1000, END_MS + 5 * 60 * 1000
    for coin, rel in files.items():
        df = pd.read_parquet(ROOT / rel, columns=["open_time", "close"])
        ms = pd.to_datetime(df["open_time"], utc=True).astype("int64") // 10 ** 6
        keep = (ms >= lo) & (ms <= hi)
        out[coin] = (ms[keep].to_numpy(), df[keep]["close"].to_numpy(dtype=float))
    return out


def spot_at(spot: dict, coin: str, now_ms: int) -> float:
    ms, px = spot[coin]
    i = int(ms.searchsorted(now_ms, side="right")) - 1
    return float(px[max(i, 0)])


def script_basis(coin: str, now_ms: int, cycle: int) -> float:
    """Realistic scripted basis path (fraction/yr). F3 dip hits ETH retry."""
    dte_days = (DLV_MS - now_ms) / MS_DAY
    if cycle == 1 and coin == "ETH":
        return 0.020  # F3: below the 4 %/yr threshold on the retry
    if dte_days < 0.1:
        return max(0.002, 0.02 * dte_days)  # converge into delivery
    if dte_days < 2.0:
        return 0.030  # last-2d window: inside the real Dec-25 band
    return 0.055 + 0.004 * math.sin(cycle * 0.7 + (0.0 if coin == "BTC" else 2.1))


def quotes_for(spot: dict, coin: str, now_ms: int, cycle: int) -> dict:
    s = spot_at(spot, coin, now_ms)
    dte = max((DLV_MS - now_ms) / MS_DAY, 1e-6)
    f = s * math.exp(script_basis(coin, now_ms, cycle) * dte / 365.0)
    t = TICK[coin]
    return dict(spot_mid=s, spot_ask=s + t, spot_bid=max(s - t, t),
                fut_by_sym={FUT[coin]: dict(bid=f - t, ask=f + t, mid=f),
                            FUT_NEXT[coin]: dict(bid=f, ask=f, mid=f)})


def expiries() -> dict:
    return {c: [dict(symbol=FUT[c], category="inverse", delivery_ms=DLV_MS),
                dict(symbol=FUT_NEXT[c], category="inverse", delivery_ms=H26_MS)]
            for c in COINS}


def cycle_grid(fast: bool) -> list:
    if fast:
        ts = [T0_MS, T0_MS + 4 * 3600_000, T0_MS + 8 * 3600_000]  # entry arc
        t = DLV_MS - 40 * 60_000
        while t <= END_MS:
            ts.append(t)
            t += 5 * 60_000
        return sorted(set(ts))
    ts = []
    t = T0_MS
    while t <= T0_MS + 24 * 3600_000:  # dense entry arc
        ts.append(t)
        t += 5 * 60_000
    t = ts[-1] + 3600_000
    while t < DLV_MS - 40 * 60_000:  # hold period, coarse
        ts.append(t)
        t += 3600_000
    t = DLV_MS - 40 * 60_000
    while t <= END_MS:  # slice window + settlement, 1-min
        ts.append(t)
        t += 60_000
    return sorted(set(ts))


def run(fast: bool = False) -> dict:
    """Execute the soak. Returns {violations, faults, events, stats, history}."""
    spot = load_spot()
    exp = expiries()
    cstate: dict = {"positions": {}, "entered": [], "history": []}
    violations, faults, events = [], [], []
    settled: dict = {}
    max_unhedged = 0
    slices: list = []  # (coin, now_ms, bucket)
    n_cycles = 0
    eth_partial_pending = False

    def fail(msg: str):
        violations.append(msg)

    for cycle, now_ms in enumerate(cycle_grid(fast)):
        now = pd.Timestamp(now_ms, unit="ms", tz="UTC")
        qb = {c: quotes_for(spot, c, now_ms, cycle) for c in COINS}
        # F4: restart in the middle of the slice window (bucket 2).
        if carry._slice_bucket(now_ms, DLV_MS) == 2 and now_ms < DLV_MS \
                and "F4" not in faults:
            snap = json.dumps(cstate, sort_keys=True, default=str)
            cstate = json.loads(snap)
            assert json.dumps(cstate, sort_keys=True, default=str) == snap
            faults.append("F4")
            events.append(("F4_restart", "ALL", now_ms))
        # Complete F2's second partial before this cycle's decision.
        if eth_partial_pending:
            pos = (cstate.get("positions") or {}).get("ETH") or {}
            if pos.get("spot_link"):
                try:
                    rest = float(pos.get("qty", 0)) - float(pos.get("spot_qty_filled", 0))
                except (TypeError, ValueError):
                    rest = 0.0
                if rest > 0:
                    carry.note_exec(cstate, pos["spot_link"], rest,
                                    spot_at(spot, "ETH", now_ms))
                    faults.append("F2")
                    events.append(("F2_partial2", pos["spot_link"], now_ms))
            eth_partial_pending = False
        want, logs = carry.decide(now, EQUITY, F, cstate, exp, qb, LOTS)
        for r in logs:
            if r.get("op") == "carry_unhedged":
                try:
                    max_unhedged = max(max_unhedged, int(r.get("cycles", 0) or 0))
                except (TypeError, ValueError):
                    pass
            if r.get("op") in ("carry_settled",):
                settled[r.get("coin")] = r  # grace-path finalises inside decide
            if r.get("op") == "carry_abandon":
                if r.get("reason") == "basis_below_threshold_on_retry" and r.get("coin") == "ETH":
                    if "F3" not in faults:
                        faults.append("F3")
                        events.append(("F3_abandon", r.get("symbol"), now_ms))
                else:
                    fail(f"bot/carry.py:773 unexpected carry_abandon: {r}")
            if r.get("op") == "carry_close":
                fail(f"bot/carry.py:747 unexpected carry_close: {r}")
            if r.get("op") == "carry_slice":
                slices.append((r.get("coin"), now_ms, r.get("bucket")))
        # --- majors-only + placement validation (mock-exchange role) ---
        prices = {}
        for c in COINS:
            prices[SPOT[c]] = qb[c]["spot_mid"]
            prices[FUT[c]] = qb[c]["fut_by_sym"][FUT[c]]["mid"]
            prices[FUT_NEXT[c]] = qb[c]["fut_by_sym"][FUT_NEXT[c]]["mid"]
        _allowed, rej = carry.guard_carry(want, {}, EQUITY, prices)
        if rej:
            fail(f"tests/carry_soak.py:run guard reject cycle={cycle} rej={rej}")
        for p in want:
            if p.get("symbol") not in ALLOWED_SYMS:
                fail(f"tests/carry_soak.py:run majors-only breach: {p.get('symbol')}")
        # --- fill simulation ---
        for p in want:
            link, side = p["orderLinkId"], p.get("side")
            coin = SYM2COIN.get(p.get("symbol"))
            if coin is None:
                coin = "BTC" if "BTC" in link else ("ETH" if "ETH" in link else None)
            if coin is None:
                fail(f"tests/carry_soak.py:run un Coin link: {link}")
                continue
            q = float(p["qty"])
            pos = (cstate.get("positions") or {}).get(coin) or {}
            if p.get("orderType") == "Limit":  # entry IOC legs
                if cycle == 0 and coin == "BTC" and side == "Sell":
                    faults.append("F1")  # F1: fut leg rejected by the exchange
                    events.append(("F1_leg_reject", link, now_ms))
                    continue  # IOC cancelled, no fill, no resting order
                if cycle == 0 and coin == "ETH":
                    events.append(("F3_miss", link, now_ms))
                    continue  # F3: attempt-1 both legs miss (exchange no-cross)
                if cycle == 2 and coin == "ETH" and side == "Buy":
                    carry.note_exec(cstate, link, q / 2.0, float(p["price"]))
                    eth_partial_pending = True  # F2: first of two partials
                    events.append(("F2_partial1", link, now_ms))
                    continue
                # IOC fills iff the limit crosses the current quote.
                if side == "Buy":
                    cross = float(p["price"]) >= qb[coin]["spot_ask"] - 1e-9
                    fp = float(p["price"])
                else:
                    sym_f = pos.get("symbol", FUT[coin])
                    fb = qb[coin]["fut_by_sym"].get(sym_f,
                                                   qb[coin]["fut_by_sym"][FUT[coin]])
                    cross = float(p["price"]) <= fb["bid"] + 1e-9
                    fp = float(p["price"])
                if not cross:
                    continue  # IOC no-cross: cancelled, no resting order
                carry.note_exec(cstate, link, q, fp)
            else:  # markets (hedge / slice / remainder / settle)
                if now_ms >= DLV_MS and coin == "ETH" and side == "Buy" \
                        and p.get("category") != "spot" and "F6" not in faults:
                    faults.append("F6")  # F6: exchange auto-settled the future
                    events.append(("F6_autosettle", link, now_ms))
                    continue
                # F5: BTC bucket-4 slice dropped (downtime: never placed).
                bucket = carry._slice_bucket(now_ms, DLV_MS)
                if coin == "BTC" and bucket == 4 and now_ms < DLV_MS \
                        and p.get("category") == "spot" and side == "Sell":
                    if "F5" not in faults:
                        faults.append("F5")
                    events.append(("F5_missed_bucket", link, now_ms))
                    continue
                if p.get("category") == "spot":
                    fp = qb[coin]["spot_ask"] if side == "Buy" else qb[coin]["spot_bid"]
                elif side == "Buy":
                    sym_f = pos.get("symbol", FUT[coin])
                    fb = qb[coin]["fut_by_sym"].get(sym_f,
                                                   qb[coin]["fut_by_sym"][FUT[coin]])
                    fp = fb["ask"]
                else:
                    sym_f = pos.get("symbol", FUT[coin])
                    fb = qb[coin]["fut_by_sym"].get(sym_f,
                                                   qb[coin]["fut_by_sym"][FUT[coin]])
                    fp = fb["bid"]
                rec = carry.note_exec(cstate, link, q, fp)
                if rec and rec.get("op") == "carry_settled":
                    settled[coin] = rec
        # --- per-cycle invariants (bot/carry.py:49 MAX_UNHEDGED_CYCLES=2) ---
        for c2, p2 in (cstate.get("positions") or {}).items():
            try:
                n = int(p2.get("unhedged_cycles", 0) or 0)
            except (TypeError, ValueError):
                n = 0
            max_unhedged = max(max_unhedged, n)
            if n > carry.MAX_UNHEDGED_CYCLES:
                fail(f"bot/carry.py:736 unhedged>2 cycles: {c2} n={n} cycle={cycle}")
        n_cycles += 1

    # --- end-of-replay invariants ---
    for coin, t_ms, b in slices:
        if not (DLV_MS - carry.SLICE_WINDOW_MS <= t_ms < DLV_MS):
            fail(f"bot/carry.py:639 slice outside window: {coin} bucket={b} t={t_ms}")
    for h in cstate.get("history", []):
        coin = h.get("coin")
        try:
            sq = float(h.get("spot_qty_filled", 0) or h.get("qty", 0) or 0)
            sold = float(h.get("spot_slice_sold_qty", 0) or 0)
        except (TypeError, ValueError):
            continue
        if sq > 0 and abs(sold - sq) > 1e-9:
            fail(f"bot/carry.py:1007 sold!=filled after restart: {coin} sold={sold} filled={sq}")
        try:  # settlement P&L consistent with fills and fees (bot/carry.py:156)
            pnl, _ret = realised_pnl_pair(float(h.get("f", F)),
                                          float(h.get("equity_entry", EQUITY)),
                                          float(h.get("S_entry", 0) or h.get("S_fill", 0)),
                                          float(h.get("F_entry", 0) or h.get("F_fill", 0)),
                                          float(h.get("S_del")))
            if abs(round(pnl, 4) - float(h.get("realised_pnl", 0))) > 1e-9:
                fail(f"bot/carry.py:156 pnl mismatch: {coin} hist={h.get('realised_pnl')} "
                     f"recomputed={round(pnl, 4)}")
        except (TypeError, ValueError, KeyError) as e:
            fail(f"bot/carry.py:156 pnl recompute error: {coin} {e!r}")
    stats = dict(cycles=n_cycles, slices=len(slices), settled=sorted(settled),
                 max_unhedged=max_unhedged,
                 open_left=sorted((cstate.get("positions") or {}).keys()),
                 hist_coins=sorted(h.get("coin") for h in cstate.get("history", [])))
    return dict(violations=violations, faults=sorted(faults), events=events,
                stats=stats, history=cstate.get("history", []))


if __name__ == "__main__":
    import sys

    res = run(fast="--fast" in sys.argv)
    print(f"cycles={res['stats']['cycles']} slices={res['stats']['slices']} "
          f"settled={res['stats']['settled']} max_unhedged={res['stats']['max_unhedged']} "
          f"faults={res['faults']}")
    print(f"violations={len(res['violations'])}")
    for v in res["violations"]:
        print("VIOLATION", v)
