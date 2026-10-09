"""oc_usdtdepeg: pure 1h-bar backtest mechanics (no I/O).

Fixed rule (PLAN.md): signal on 1h close < trigger -> resting limit BUY at
L = close - 0.0001 valid 4 bars -> exits TP (limit, strict trade-through) /
stop (market, touch, STOP FIRST) / 72-bar cap close (taker). One position at
a time; new signals ignored while PENDING or IN_POSITION.

Bars: df rows sorted by time with columns open/high/low/close (floats).
Windows counted in BARS. All comparisons use the bar's own OHLC only.
"""

from __future__ import annotations


def simulate(rows, trigger: float, tp: float, stop: float,
             maker: float, taker: float) -> tuple[list[dict], list[dict]]:
    """Run the state machine over all bars.

    rows: sequence of dicts with keys open/high/low/close (float) and
        t (comparable timestamp, carried through untouched).
    Returns (events, incomplete): filled positions with full exit info;
    incomplete = signals whose entry window or holding cap runs past the
    end of the panel (excluded from sums, listed).
    """
    n = len(rows)
    events: list[dict] = []
    incomplete: list[dict] = []
    i = 0
    while i < n:
        c = float(rows[i]["close"])
        if not (c < trigger):
            i += 1
            continue
        # SIGNAL at bar i (uses only close_i, known at bar i's close).
        sig_t = rows[i]["t"]
        limit = c - 0.0001
        # PENDING: entry window bars i+1 .. i+4, strict trade-through.
        fill = None
        for j in range(i + 1, min(i + 5, n)):
            if float(rows[j]["low"]) < limit:
                fill = j
                break
        if fill is None:
            if i + 4 >= n:
                incomplete.append({"signal_t": sig_t, "why": "entry_window_cut"})
                i = n
                continue
            i += 1  # unfilled: signal consumed, back to FLAT at next bar
            continue
        # IN_POSITION: exits monitored from the FILL bar itself (conservative).
        exit_kind = None
        exit_px = None
        exit_j = None
        last = min(fill + 72, n - 1)
        for j in range(fill, last + 1):
            lo = float(rows[j]["low"])
            hi = float(rows[j]["high"])
            if lo <= stop:
                exit_kind, exit_px, exit_j = "stop", stop, j
                break
            if hi > tp:
                exit_kind, exit_px, exit_j = "tp", tp, j
                break
        if exit_kind is None:
            if fill + 72 >= n:
                incomplete.append({"signal_t": sig_t, "fill_t": rows[fill]["t"],
                                   "why": "cap_cut"})
                i = n
                continue
            exit_kind, exit_px, exit_j = "cap", float(rows[fill + 72]["close"]), fill + 72
        fee_out = maker if exit_kind == "tp" else taker
        net = (exit_px - limit) / limit - maker - fee_out
        events.append({
            "signal_t": sig_t, "fill_t": rows[fill]["t"],
            "exit_t": rows[exit_j]["t"],
            "signal_i": i, "fill_i": fill, "exit_i": exit_j,
            "limit": limit, "exit_px": exit_px, "exit": exit_kind,
            "net": net,
        })
        i = exit_j + 1  # one position at a time: resume after exit
    return events, incomplete


def summarize(events: list[dict]) -> dict:
    """Standalone stats for a list of filled events."""
    n = len(events)
    if n == 0:
        return {"n": 0, "win": 0.0, "mean_bps": 0.0, "sum": 0.0,
                "worst": 0.0, "best": 0.0, "tp": 0, "sl": 0, "cap": 0}
    nets = [e["net"] for e in events]
    wins = sum(1 for x in nets if x > 0)
    return {
        "n": n,
        "win": round(wins / n, 4),
        "mean_bps": round(sum(nets) / n * 1e4, 2),
        "sum": round(sum(nets), 6),
        "worst": round(min(nets) * 1e4, 1),
        "best": round(max(nets) * 1e4, 1),
        "tp": sum(1 for e in events if e["exit"] == "tp"),
        "sl": sum(1 for e in events if e["exit"] == "stop"),
        "cap": sum(1 for e in events if e["exit"] == "cap"),
    }


def renet(events: list[dict], maker: float, taker: float) -> list[float]:
    """Recompute nets for the same fills under different fees (retail row)."""
    out = []
    for e in events:
        fee_out = maker if e["exit"] == "tp" else taker
        out.append((e["exit_px"] - e["limit"]) / e["limit"] - maker - fee_out)
    return out
