"""Does price react at the user's MA Ribbon lines (SMA50 / SMA200, chart timeframe, closed bars)?

For each symbol and timeframe (bars rebuilt from real 1m data) an MA *test* happens when the
previous bar closed on one side of the level L (the SMA value of the last closed bar) and the
current bar trades to L. From the first touch minute the 1m path decides a race: price reaches
L + k*ATR in the bounce direction first ("hold") or L - k*ATR through the level first ("break")
within 20 bars of that timeframe. Placebo tests use levels at the same distance from the
previous close (distance drawn from the real MA-test distribution) that are touched in the same
way but are not an MA. Under no S/R effect both hold rates are equal.

  python scripts/masr_reaction.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("artifacts/research/masr/reaction")
TFS = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
KS = (0.5, 1.0, 2.0)
HORIZON_BARS = 20
HIDDEN_START = pd.Timestamp("2025-09-24", tz="UTC")
DEV_END = pd.Timestamp("2025-09-14", tz="UTC")


def load_1m(sym):
    d = Path("data/raw/btc_intraday_20260924") if sym == "BTCUSDT" else Path("data/raw/majors_intraday_20260924")
    pat = "klines_1m_*.parquet" if sym == "BTCUSDT" else f"{sym}_1m_*.parquet"
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in sorted(d.glob(pat))])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    return m.drop_duplicates("open_time").sort_values("open_time").set_index("open_time")


def bars_from_1m(m, rule):
    b = m.resample(rule, label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    prev = b["close"].shift(1)
    tr = np.maximum(b["high"] - b["low"], np.maximum((b["high"] - prev).abs(), (b["low"] - prev).abs()))
    b["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return b


def race(lo, hi, start, end, up, dn):
    """First passage on 1m arrays from index start (exclusive of the touch minute) to end."""
    seg_hi, seg_lo = hi[start:end], lo[start:end]
    iu = np.argmax(seg_hi >= up) if (seg_hi >= up).any() else None
    idn = np.argmax(seg_lo <= dn) if (seg_lo <= dn).any() else None
    if iu is None and idn is None:
        return 0
    if idn is None or (iu is not None and iu < idn):
        return 1
    if iu is None or idn < iu:
        return -1
    return -2  # both in the same minute: ambiguous, excluded


def tests(b, m_idx, lo1, hi1, level, side):
    """Yield (bar time, level, atr, touch minute index) for tests of `level` from `side` (+1 support, -1 resistance)."""
    prev_close = b["close"].shift(1).to_numpy()
    lvl = level.shift(1).to_numpy()  # last closed bar's MA
    lo, hi = b["low"].to_numpy(), b["high"].to_numpy()
    if side > 0:
        hit = (prev_close > lvl) & (lo <= lvl)
    else:
        hit = (prev_close < lvl) & (hi >= lvl)
    out = []
    starts = np.searchsorted(m_idx, b.index.values)
    for i in np.flatnonzero(hit & np.isfinite(lvl)):
        a = starts[i]
        e = starts[i + 1] if i + 1 < len(starts) else len(m_idx)
        seg = lo1[a:e] <= lvl[i] if side > 0 else hi1[a:e] >= lvl[i]
        if not seg.any():
            continue
        out.append((i, lvl[i], a + int(np.argmax(seg))))
    return out


def evaluate(sym, tf, rule, m, rng):
    b = bars_from_1m(m, rule)
    m_idx = m.index.values
    lo1, hi1 = m["low"].to_numpy(), m["high"].to_numpy()
    atr = b["atr"].shift(1).to_numpy()
    bar_minutes = int(pd.Timedelta(rule).total_seconds() // 60)
    rows = []
    trend = np.sign(b["close"].rolling(50).mean() - b["close"].rolling(200).mean()).shift(1).to_numpy()
    for ma in (50, 200):
        level = b["close"].rolling(ma, min_periods=ma).mean()
        for side in (1, -1):
            real = tests(b, m_idx, lo1, hi1, level, side)
            if not real:
                continue
            prev_close = b["close"].shift(1).to_numpy()
            dists = np.array([abs(prev_close[i] - L) / atr[i] for i, L, _ in real if np.isfinite(atr[i]) and atr[i] > 0])
            # placebo: random bars, fake level at a real-test distance, must be touched in that bar
            cand = np.flatnonzero(np.isfinite(atr) & np.isfinite(prev_close))
            pick = rng.choice(cand, size=min(len(cand), 6 * len(real)), replace=False)
            fake_lvl = prev_close[pick] - side * rng.choice(dists, size=len(pick)) * atr[pick]
            starts = np.searchsorted(m_idx, b.index.values)
            placebo = []
            lvl_prev = level.shift(1).to_numpy()
            for i, L in zip(pick, fake_lvl):
                if abs(L - lvl_prev[i]) < 0.25 * atr[i]:
                    continue  # too close to the real MA: not a placebo
                a = starts[i]
                e = starts[i + 1] if i + 1 < len(starts) else len(m_idx)
                seg = lo1[a:e] <= L if side > 0 else hi1[a:e] >= L
                if seg.any():
                    placebo.append((i, L, a + int(np.argmax(seg))))
                if len(placebo) >= len(real):
                    break
            for kind, events in (("ma", real), ("placebo", placebo)):
                for i, L, j in events:
                    if not (np.isfinite(atr[i]) and atr[i] > 0):
                        continue
                    end = min(j + 1 + HORIZON_BARS * bar_minutes, len(m_idx))
                    rec = dict(sym=sym, tf=tf, ma=ma, side="support" if side > 0 else "resistance", kind=kind,
                               t=b.index[i], bull=trend[i] > 0 if np.isfinite(trend[i]) else None)
                    for k in KS:
                        up, dn = L + k * atr[i], L - k * atr[i]
                        r = race(lo1, hi1, j + 1, end, up, dn)
                        rec[f"hold_{k}"] = (r == 1) if side > 0 else (r == -1)
                        rec[f"break_{k}"] = (r == -1) if side > 0 else (r == 1)
                        rec[f"amb_{k}"] = r in (0, -2)
                    rows.append(rec)
    return rows


def wilson(p, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    rows = []
    for sym in SYMS:
        m = load_1m(sym)
        for tf, rule in TFS.items():
            rows += evaluate(sym, tf, rule, m, rng)
            print(sym, tf, "events so far", len(rows), flush=True)
    df = pd.DataFrame(rows)
    df.to_parquet(OUT / "events.parquet", index=False)
    summ = []
    for (tf, ma, side, period), g in df.assign(period=np.where(df.t >= HIDDEN_START, "hidden", np.where(df.t < DEV_END, "dev", "gap"))).groupby(["tf", "ma", "side", "period"]):
        if period == "gap":
            continue
        row = dict(tf=tf, ma=ma, side=side, period=period)
        for kind in ("ma", "placebo"):
            x = g[g.kind == kind]
            for k in KS:
                dec = x[~x[f"amb_{k}"]]
                n = len(dec)
                p = float(dec[f"hold_{k}"].mean()) if n else np.nan
                row[f"{kind}_n_{k}"] = n
                row[f"{kind}_hold_{k}"] = round(p, 4) if n else np.nan
                lo, hi = wilson(p, n) if n else (np.nan, np.nan)
                row[f"{kind}_ci_{k}"] = (round(lo, 3), round(hi, 3))
        summ.append(row)
    s = pd.DataFrame(summ)
    s.to_csv(OUT / "summary.csv", index=False)
    print(s[["tf", "ma", "side", "period", "ma_n_1.0", "ma_hold_1.0", "placebo_hold_1.0", "ma_hold_0.5", "placebo_hold_0.5", "ma_hold_2.0", "placebo_hold_2.0"]].to_string())


if __name__ == "__main__":
    main()
