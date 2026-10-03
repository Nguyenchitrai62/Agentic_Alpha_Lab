"""Bybit-vs-Binance 1m execution comparison, research only (no orders placed).

a) Per symbol and calendar year: percentiles (1/5/50/95/99) of the minute close
   basis bybit/binance - 1 in bps, same for high/low; share of minutes with
   |close basis| > 5 / 10 bps. Plain price comparison: uses the full overlap.
b) Execution agreement on the simulated orders of pipeline M5
   (artifacts/research/system_audit/events_v367.parquet) and R2
   (events_v321.parquet). DEV DATA ONLY (event minute t < 2025-09-14): for every
   book_fill / rung_fill, does Bybit trade through the same limit price
   (buy: low_bybit < price; sell: high_bybit > price) in the same minute t, in
   t..t+2, or at any minute until the order would expire (book: t..t+60 per the
   60-minute resting rule; rung: t..t+240, i.e. up to the next 4h open)? For
   book_stop / rung_sl does Bybit reach the stop the same minute, and for
   book_tp / rung_tp does Bybit reach the TP the same minute?

Outputs (this folder): basis_by_symbol_year.csv, execution_agreement.csv,
agreement_summary.json, SUMMARY.md.

  python research/diagnostics/bybit_vs_binance/compare_bybit_binance.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
BTC_BINANCE = ROOT / "data/raw/btc_intraday_20260924"
MAJ_BINANCE = ROOT / "data/raw/majors_intraday_20260924"
EVENTS = {"M5": ROOT / "artifacts/research/system_audit/events_v367.parquet",
          "R2": ROOT / "artifacts/research/system_audit/events_v321.parquet"}
OUT = Path(__file__).resolve().parent

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
MS = 60_000
DEV_CUTOFF = pd.Timestamp("2025-09-14", tz="UTC")  # strategy-outcome stats use t < this
BOOK_EXPIRY_MIN = 60   # book limit orders rest 60 minutes (engine_real convention)
RUNG_EXPIRY_MIN = 240  # dip rungs rest until TP or the next 4h open


def load_bybit(symbol: str) -> pd.DataFrame:
    df = pd.read_parquet(BYBIT_DIR / f"{symbol}_1m.parquet",
                         columns=["open_time", "high", "low", "close"])
    return df.sort_values("open_time").reset_index(drop=True)


def load_binance(symbol: str) -> pd.DataFrame:
    if symbol == "BTCUSDT":
        files = sorted(BTC_BINANCE.glob("klines_1m_20*.parquet"))
    else:
        files = sorted(MAJ_BINANCE.glob(f"{symbol}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "high", "low", "close"]) for f in files]
    df = pd.concat(parts, ignore_index=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True).astype("int64") // 1_000_000
    return df.sort_values("open_time").reset_index(drop=True)


def part_a_basis() -> pd.DataFrame:
    rows = []
    for sym in SYMBOLS:
        bb = load_bybit(sym)
        bn = load_binance(sym)
        m = bb.merge(bn, on="open_time", suffixes=("_bb", "_bn"))
        m["year"] = pd.to_datetime(m["open_time"], unit="ms", utc=True).dt.year
        for year, g in m.groupby("year"):
            r = {"symbol": sym, "year": int(year), "n_minutes": int(len(g))}
            for col in ("close", "high", "low"):
                bps = (g[f"{col}_bb"] / g[f"{col}_bn"] - 1.0) * 1e4
                for p in (1, 5, 50, 95, 99):
                    r[f"{col}_p{p}"] = float(np.percentile(bps, p))
            ab = ((m.loc[g.index, "close_bb"] / m.loc[g.index, "close_bn"] - 1.0).abs() * 1e4)
            r["share_abs_gt5bps"] = float((ab > 5).mean())
            r["share_abs_gt10bps"] = float((ab > 10).mean())
            rows.append(r)
    return pd.DataFrame(rows).sort_values(["symbol", "year"]).reset_index(drop=True)


class MinuteIndex:
    """searchsorted-based OHLC lookup on a sorted 1m frame (open_time ms int)."""

    def __init__(self, df: pd.DataFrame):
        self.t = df["open_time"].to_numpy()
        self.lo = df["low"].to_numpy(dtype=float)
        self.hi = df["high"].to_numpy(dtype=float)

    def window(self, t0_ms: int, t1_ms: int):
        i0 = int(np.searchsorted(self.t, t0_ms, side="left"))
        i1 = int(np.searchsorted(self.t, t1_ms, side="right")) - 1
        if i1 < i0 or i0 >= len(self.t) or self.t[i0] > t1_ms:
            return None
        i1 = min(i1, len(self.t) - 1)
        return self.lo[i0:i1 + 1].min(), self.hi[i0:i1 + 1].max()

    def same_minute(self, t_ms: int):
        w = self.window(t_ms, t_ms)
        return w  # None when the venue has no bar there


def fill_agrees(side: str, low: float, high: float, price: float) -> bool:
    return (low < price) if side == "buy" else (high > price)


def stop_agrees(side: str, low: float, high: float, price: float) -> bool:
    # long stop exits sell on low touch; short stop exits buy on high touch
    return (low <= price) if side == "sell" else (high >= price)


def tp_agrees(side: str, low: float, high: float, price: float) -> bool:
    # long TP exits sell on high touch; short TP exits buy on low touch
    return (high >= price) if side == "sell" else (low <= price)


def part_b_agreement() -> tuple[pd.DataFrame, dict]:
    FILL_KINDS = ("book_fill", "rung_fill")
    STOP_KINDS = ("book_stop", "rung_sl")
    TP_KINDS = ("book_tp", "rung_tp")
    bb_cache: dict[str, MinuteIndex] = {}
    bn_cache: dict[tuple[str, int], MinuteIndex] = {}

    def bb(sym: str) -> MinuteIndex:
        if sym not in bb_cache:
            bb_cache[sym] = MinuteIndex(load_bybit(sym))
        return bb_cache[sym]

    def bn(sym: str, year: int) -> MinuteIndex:
        if (sym, year) not in bn_cache:
            df = load_binance(sym)
            y = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.year
            bn_cache[(sym, year)] = MinuteIndex(df[y == year].reset_index(drop=True))
        return bn_cache[(sym, year)]

    rows = []
    for pipe, path in EVENTS.items():
        ev = pd.read_parquet(path)
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        dev = ev[ev["t"] < DEV_CUTOFF].copy()
        dev["t_ms"] = (dev["t"].astype("int64") // 1_000_000).astype("int64")
        dev["year"] = dev["t"].dt.year
        kinds = [k for k in list(FILL_KINDS) + list(STOP_KINDS) + list(TP_KINDS)
                 if k in set(dev["kind"])]
        for kind in kinds:
            sub = dev[dev["kind"] == kind]
            expiry = (BOOK_EXPIRY_MIN if kind.startswith("book_") else RUNG_EXPIRY_MIN)
            for (sym, year), g in sub.groupby(["symbol", "year"]):
                n = len(g)
                n_data = n_same = n_t2 = n_exp = n_bn_confirm = 0
                for t_ms, side, price in zip(g["t_ms"], g["side"], g["price"]):
                    w0 = bb(sym).same_minute(int(t_ms))
                    if w0 is None:
                        continue
                    n_data += 1
                    blo, bhi = w0
                    wb = bn(sym, int(year)).same_minute(int(t_ms))
                    if wb is not None:
                        if kind in FILL_KINDS and fill_agrees(side, wb[0], wb[1], price):
                            n_bn_confirm += 1
                        elif kind in STOP_KINDS and stop_agrees(side, wb[0], wb[1], price):
                            n_bn_confirm += 1
                        elif kind in TP_KINDS and tp_agrees(side, wb[0], wb[1], price):
                            n_bn_confirm += 1
                    if kind in STOP_KINDS:
                        check = stop_agrees
                    elif kind in TP_KINDS:
                        check = tp_agrees
                    else:
                        check = fill_agrees
                    if check(side, blo, bhi, price):
                        n_same += 1
                    if kind in FILL_KINDS:
                        w2 = bb(sym).window(int(t_ms), int(t_ms) + 2 * MS)
                        we = bb(sym).window(int(t_ms), int(t_ms) + expiry * MS)
                        if w2 is not None and fill_agrees(side, w2[0], w2[1], price):
                            n_t2 += 1
                        if we is not None and fill_agrees(side, we[0], we[1], price):
                            n_exp += 1
                r = {"pipeline": pipe, "kind": kind, "symbol": sym, "year": int(year),
                     "n_binance": n, "n_with_bybit": n_data,
                     "binance_confirm_rate": n_bn_confirm / n_data if n_data else float("nan"),
                     "agree_same": n_same / n_data if n_data else float("nan")}
                if kind in FILL_KINDS:
                    r["agree_t2"] = n_t2 / n_data if n_data else float("nan")
                    r["agree_expiry"] = n_exp / n_data if n_data else float("nan")
                    r["not_filled_bybit"] = n_data - n_exp
                else:
                    r["agree_t2"] = float("nan")
                    r["agree_expiry"] = float("nan")
                    r["not_filled_bybit"] = 0
                rows.append(r)
    detail = pd.DataFrame(rows).sort_values(["pipeline", "kind", "symbol", "year"]).reset_index(drop=True)
    pooled = {}
    for pipe in EVENTS:
        for kind in list(FILL_KINDS) + list(STOP_KINDS) + list(TP_KINDS):
            d = detail[(detail["pipeline"] == pipe) & (detail["kind"] == kind)]
            if len(d) == 0:
                continue
            nd = int(d["n_with_bybit"].sum())
            pooled[f"{pipe}.{kind}"] = {
                "n_binance": int(d["n_binance"].sum()), "n_with_bybit": nd,
                "agree_same": float((d["agree_same"] * d["n_with_bybit"]).sum() / nd) if nd else None,
                "agree_expiry": float((d["agree_expiry"] * d["n_with_bybit"]).sum() / nd)
                if (nd and kind in FILL_KINDS) else None,
                "not_filled_bybit": int(d["not_filled_bybit"].sum()),
            }
    return detail, pooled


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    basis = part_a_basis()
    basis.to_csv(OUT / "basis_by_symbol_year.csv", index=False)
    print(f"basis rows={len(basis)}", flush=True)
    detail, pooled = part_b_agreement()
    detail.to_csv(OUT / "execution_agreement.csv", index=False)
    (OUT / "agreement_summary.json").write_text(json.dumps(
        {"dev_cutoff": "2025-09-14 (event minute t < cutoff)",
         "expiry_windows_min": {"book": BOOK_EXPIRY_MIN, "rung": RUNG_EXPIRY_MIN},
         "pooled": pooled}, indent=1))
    print(f"agreement rows={len(detail)}", flush=True)
    for k, v in pooled.items():
        print(k, json.dumps(v), flush=True)


if __name__ == "__main__":
    main()
