"""Blind cash-carry replication (PART A, spec-only).

Spec (docs/opencode/OPENCODE_CARRY_AUDIT.md PART A):
- Data: data/raw/qbasis_20261003 (Binance quarterly 1h closes; USD-M BTCUSDT/ETHUSDT
  quarterlies) + spot closes for BTC/ETH from the 1m majors archives
  (BTC: data/raw/btc_intraday_20260924/klines_1m_*.parquet,
   ETH: data/raw/majors_intraday_20260924/ETHUSDT_1m_*.parquet, aggregated to 1h).
  NOTE: the 1m majors archives are USD-M perp 1m; aggregated to 1h they serve as the
  spot proxy here (spot_majors_20260925 1h files end in 2019/2020 and cannot cover the
  2021-2026 window; spot_majors 4h spot is exact-spot but 4h resolution, so the 1m->1h
  proxy preserves the spec's 1h timing). Documented as a limitation.
- Roll schedule: per coin sort quarterly deliveries D (parsed from contract code
  YYMMDD as 20YY-MM-DD 08:00 UTC). For NEXT contract C_j (front C_{j-1}):
  H_theory = D_{j-1} - 7 days; H = H_theory, or the first available hour of the
  series if H_theory precedes data (max(first F bar +1h, first spot-1h bar +1h)).
- Basis: annualised = ln(F/S) * 365 / days_to_delivery, with F,S = last CLOSED 1h
  bar strictly before H (open_time < H), days = (D_j - H)/86400.
- ENTER only if basis >= 4%/yr. Pair = spot long + quarterly short, equal notional 1.0.
- Fees: spot 0.1% per side (entry+exit), futures 0.055% entry + 0.02% delivery.
  Total = 0.00275. Return on allocated =
  (S_exit/S_entry - 1) + (F_entry - F_settle)/F_entry - fees.
- Exit at delivery: S_exit = spot 1h close of the delivery hour (open_time == D_j,
  fallback last <= D_j); F_settle = last futures 1h close at or before D_j
  (open_time <= D_j).
- Window: entries with entry time in [2021-09-24, 2026-09-24). Per-trade rows +
  per-anchor-year sums (years [09-24,09-24)) -> replication.json.

Causality: entry uses only bars with open_time < H; exit uses bars <= D_j (after entry).
No forward returns inspected beyond the mechanical exit at delivery.
"""
import glob
import json
import math
import os
import re
from datetime import datetime, timezone, timedelta

import pandas as pd

QBASIS_DIR = "data/raw/qbasis_20261003"
BTC_1M_PATTERN = "data/raw/btc_intraday_20260924/klines_1m_*.parquet"
ETH_1M_PATTERN = "data/raw/majors_intraday_20260924/ETHUSDT_1m_*.parquet"
OUT_DIR = "research/tournament/carry_audit"

WINDOW_START = pd.Timestamp("2021-09-24", tz="UTC")
WINDOW_END = pd.Timestamp("2026-09-24", tz="UTC")  # exclusive
THRESHOLD = 0.04
FEES = 0.001 + 0.001 + 0.00055 + 0.0002  # 0.00275


def parse_delivery(code_yymmdd: str) -> pd.Timestamp:
    yy = int(code_yymmdd[0:2])
    mm = int(code_yymmdd[2:4])
    dd = int(code_yymmdd[4:6])
    return pd.Timestamp(datetime(2000 + yy, mm, dd, 8, 0, tzinfo=timezone.utc))


def load_futures(coin: str):
    """Load um quarterly 1h closes for coin (BTC/ETH). Returns list of dicts sorted by D."""
    files = sorted(glob.glob(os.path.join(QBASIS_DIR, f"um_{coin}USDT_*_1h.parquet")))
    contracts = []
    for f in files:
        m = re.search(r"(\d{6})_1h\.parquet$", f)
        assert m, f
        code = m.group(1)
        d = parse_delivery(code)
        df = pd.read_parquet(f, columns=["open_time", "close"])
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df = df.sort_values("open_time").reset_index(drop=True)
        contracts.append({
            "contract": f"{coin}USDT_{code}",
            "code": code,
            "delivery": d,
            "file": os.path.basename(f),
            "bars": df,
        })
    contracts.sort(key=lambda c: c["delivery"])
    return contracts


def build_spot_1h_from_1m(pattern: str) -> pd.DataFrame:
    """Aggregate 1m (open_time, close) to 1h closes: 1h open_time=hour floor, close=last 1m close."""
    files = sorted(glob.glob(pattern))
    assert files, pattern
    parts = []
    for f in files:
        df = pd.read_parquet(f, columns=["open_time", "close"])
        parts.append(df)
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)
    m["hour"] = m["open_time"].dt.floor("h")
    # last 1m close within each hour = close of :59 bar
    g = m.groupby("hour", sort=True)["close"].last().reset_index()
    g = g.rename(columns={"hour": "open_time"})
    g = g.sort_values("open_time").reset_index(drop=True)
    return g[["open_time", "close"]]


def last_close_strictly_before(bars: pd.DataFrame, h: pd.Timestamp):
    sub = bars[bars["open_time"] < h]
    if sub.empty:
        return None, None
    row = sub.iloc[-1]
    return row["close"], row["open_time"]


def last_close_at_or_before(bars: pd.DataFrame, d: pd.Timestamp):
    sub = bars[bars["open_time"] <= d]
    if sub.empty:
        return None, None
    row = sub.iloc[-1]
    return row["close"], row["open_time"]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    spot_1h = {}
    spot_1h["BTC"] = build_spot_1h_from_1m(BTC_1M_PATTERN)
    spot_1h["ETH"] = build_spot_1h_from_1m(ETH_1M_PATTERN)

    trades = []
    for coin in ["BTC", "ETH"]:
        contracts = load_futures(coin)
        spot = spot_1h[coin]
        first_spot_open = spot["open_time"].iloc[0]
        for j in range(1, len(contracts)):
            front = contracts[j - 1]
            nxt = contracts[j]
            d_prev = front["delivery"]
            d_next = nxt["delivery"]
            h_theory = d_prev - timedelta(days=7)
            # first available hour: need a closed bar before H in both series
            first_f_open = nxt["bars"]["open_time"].iloc[0]
            earliest = max(first_f_open + timedelta(hours=1),
                           first_spot_open + timedelta(hours=1))
            # ceil to hour
            earliest = earliest.floor("h")
            if earliest < max(first_f_open, first_spot_open) + timedelta(hours=1):
                earliest = earliest + timedelta(hours=1)
            h = h_theory
            if h < earliest:
                h = earliest
            # H must be strictly after first bars and strictly before delivery
            if h >= d_next:
                continue
            if not (WINDOW_START <= h < WINDOW_END):
                continue
            f_entry, f_bar_time = last_close_strictly_before(nxt["bars"], h)
            s_entry, s_bar_time = last_close_strictly_before(spot, h)
            if f_entry is None or s_entry is None:
                continue
            if not (f_entry > 0 and s_entry > 0):
                continue
            days = (d_next - h).total_seconds() / 86400.0
            if days <= 0:
                continue
            basis = math.log(float(f_entry) / float(s_entry)) * 365.0 / days
            if basis < THRESHOLD:
                continue
            f_settle, f_settle_bar = last_close_at_or_before(nxt["bars"], d_next)
            # spot exit: bar with open_time == delivery hour, fallback last <= D
            exact = spot[spot["open_time"] == d_next]
            if not exact.empty:
                s_exit = exact.iloc[-1]["close"]
                s_exit_bar = d_next
            else:
                s_exit, s_exit_bar = last_close_at_or_before(spot, d_next)
            if f_settle is None or s_exit is None:
                continue
            ret = (float(s_exit) / float(s_entry) - 1.0) + \
                  ((float(f_entry) - float(f_settle)) / float(f_entry)) - FEES
            trades.append({
                "coin": coin,
                "contract": nxt["contract"],
                "entry_time": h.isoformat(),
                "entry_hour": h.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "delivery": d_next.isoformat(),
                "days_to_delivery": days,
                "S_entry": float(s_entry),
                "F_entry": float(f_entry),
                "S_entry_bar": pd.Timestamp(s_bar_time).isoformat(),
                "F_entry_bar": pd.Timestamp(f_bar_time).isoformat(),
                "basis_ann": basis,
                "S_exit": float(s_exit),
                "F_settle": float(f_settle),
                "S_exit_bar": pd.Timestamp(s_exit_bar).isoformat(),
                "F_settle_bar": pd.Timestamp(f_settle_bar).isoformat(),
                "fees": FEES,
                "return": ret,
            })

    trades.sort(key=lambda t: (t["entry_time"], t["coin"]))
    # per-anchor-year sums: years starting 09-24
    year_starts = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in [2021, 2022, 2023, 2024, 2025, 2026]]
    per_year = {}
    for i in range(5):
        ys, ye = year_starts[i], year_starts[i + 1]
        key = f"{ys.date()}..{ye.date()}"
        s = sum(t["return"] for t in trades
                if ys <= pd.Timestamp(t["entry_time"]) < ye)
        n = sum(1 for t in trades
                if ys <= pd.Timestamp(t["entry_time"]) < ye)
        per_year[key] = {"sum_return": s, "n_trades": n}
    total = sum(t["return"] for t in trades)
    out = {
        "spec": "OPENCODE_CARRY_AUDIT PART A (blind, spec-only)",
        "data": {
            "futures": "data/raw/qbasis_20261003 um_BTCUSDT_*/um_ETHUSDT_*_1h.parquet (USD-M quarterlies)",
            "spot": "1m majors archives aggregated to 1h (BTC: btc_intraday_20260924/klines_1m_*.parquet; ETH: majors_intraday_20260924/ETHUSDT_1m_*.parquet). NOTE: these are USD-M perp 1m used as spot proxy; spot_majors_20260925 1h ends 2019/2020 so cannot cover window.",
            "note": "deliveries parsed from contract code YYMMDD as 08:00 UTC; F_settle=last futures 1h close <= D; S_exit=spot 1h close of delivery hour (fallback last <= D)",
        },
        "params": {
            "roll": "H = front_delivery - 7d (or first available hour)",
            "basis_formula": "ln(F/S)*365/days, F/S = last CLOSED 1h bar strictly before H",
            "threshold": THRESHOLD,
            "fees": {"spot_per_side": 0.001, "fut_entry": 0.00055, "fut_delivery": 0.0002, "total": FEES},
            "return_formula": "(S_exit/S_entry-1)+(F_entry-F_settle)/F_entry-fees",
            "window": "[2021-09-24, 2026-09-24)",
        },
        "causality": "entry uses only bars with open_time < H; exit uses bars <= D (after entry). No bar >= H used for entry.",
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "n_trades": len(trades),
        "total_return_sum": total,
        "per_anchor_year": per_year,
        "trades": trades,
    }
    with open(os.path.join(OUT_DIR, "replication.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {os.path.join(OUT_DIR, 'replication.json')}: {len(trades)} trades, total {total:.6f}")
    for k, v in per_year.items():
        print(f"  {k}: n={v['n_trades']} sum={v['sum_return']:.6f}")


if __name__ == "__main__":
    main()
