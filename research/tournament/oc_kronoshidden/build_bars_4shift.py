"""Build 4h OHLCV bars for the 5 majors on FOUR clock grids (shift s = 0,1,2,3 h).

1m sources (all Binance USD-M):
- alts: data/raw/majors_intraday_20260924/{SYM}_1m_{YYYY}.parquet (2020..2026)
- BTC : data/raw/btc_intraday_20260924/klines_1m_{YYYY}.parquet (2019..2026)
- cross-checks (NOT primary): data/raw/btc_1m_hidden_20260924/klines_1m.parquet
  (BTC duplicate 2025-09-23 .. 2026-09-24), data/raw/majors_1m_oos_20261006/
  ({SYM}_1m_oos.parquet, 2026-09-24 .. 2026-10-05, no quote_volume),
  data/raw/binance_usdm/BTCUSDT/5m/ (5m snapshot Aug-Sep 2026, not used).
Bars: T_s = floor((open_time - s h) / 4h) * 4h + s h, from 2020-08-01 to the
last complete 4h bar (1m ends 2026-09-23 23:59 -> last complete T = 2026-09-23
20:00 shift 0). amount = quote_volume sum. Junction gaps/dups reported.

Usage: python build_bars_4shift.py   (run through heavy_slot, >0.4 GB)
"""
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "bars_4h_4shift.parquet"
LOG = HERE / "bars_4shift_coverage.txt"
START = pd.Timestamp("2020-08-01", tz="UTC")
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
COLS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume"]
LINES = []


def log(s):
    LINES.append(s)
    print(s, flush=True)


def files_1m(sym):
    if sym == "BTCUSDT":
        pat = "klines_1m_20*.parquet"
        d = ROOT / "data/raw/btc_intraday_20260924"
    else:
        pat = f"{sym}_1m_20*.parquet"
        d = ROOT / "data/raw/majors_intraday_20260924"
    return sorted(d.glob(pat))


def main():
    log("source map (primary 1m files):")
    for sym in MAJORS:
        for f in files_1m(sym):
            log(f"  {sym} {f.name}")
    log("cross-checks: btc_1m_hidden_20260924/klines_1m.parquet (BTC "
        "2025-09-23..2026-09-24 dup); majors_1m_oos_20261006/*_1m_oos.parquet "
        "(2026-09-24..2026-10-05, no quote_volume, extension only); "
        "binance_usdm/BTCUSDT/5m/* (5m snapshot, NOT used for 4h bars)")
    allbars = []
    for sym in MAJORS:
        parts = []
        prev_max = None
        for f in files_1m(sym):
            m = pd.read_parquet(f, columns=COLS)
            m = m.sort_values("open_time").reset_index(drop=True)
            if prev_max is not None:
                overlap = int((m.open_time <= prev_max).sum())
                gap = m.open_time.min() - prev_max
                log(f"  junction {sym} {f.name}: overlap={overlap} "
                    f"gap_after_prev={gap}")
                assert overlap == 0, f"duplicate at junction {f}"
                assert gap == pd.Timedelta(minutes=1), f"gap at junction {f}"
            dup = int(m.open_time.duplicated().sum())
            step = m.open_time.diff().dropna()
            gaps = int((step > pd.Timedelta(minutes=1)).sum())
            log(f"  {sym} {f.name}: rows={len(m)} range={m.open_time.min()}.."
                f"{m.open_time.max()} dups={dup} gaps={gaps}")
            assert dup == 0
            prev_max = m.open_time.max()
            parts.append(m)
        m = pd.concat(parts).drop_duplicates("open_time").sort_values(
            "open_time").reset_index(drop=True)
        log(f"{sym}: total 1m rows={len(m)} "
            f"{m.open_time.min()}..{m.open_time.max()}")
        # cross-check BTC hidden duplicate over the overlap
        if sym == "BTCUSDT":
            h = pd.read_parquet(
                ROOT / "data/raw/btc_1m_hidden_20260924/klines_1m.parquet",
                columns=["open_time", "close"])
            j = m.merge(h, on="open_time", suffixes=("", "_h"))
            j = j[j.close_h.notna()]
            agree = float((j.close == j.close_h).mean())
            log(f"  BTC hidden overlap: {len(j)} shared minutes, "
                f"close agreement={agree:.6f}")
        for s in (0, 1, 2, 3):
            sh = pd.Timedelta(hours=s)
            T = ((m.open_time - sh).dt.floor("4h") + sh)
            g = m.groupby(T)
            b = pd.DataFrame({
                "open": g.open.first(), "high": g.high.max(),
                "low": g.low.min(), "close": g.close.last(),
                "volume": g.volume.sum(), "amount": g.quote_volume.sum(),
                "nmin": g.size()}).reset_index().rename(columns={"index": "T"})
            b = b.rename(columns={b.columns[0]: "T"})
            b["sym"], b["shift"] = sym, s
            allbars.append(b)
            n_inc = int((b.nmin < 240).sum())
            log(f"  {sym} shift {s}: bars={len(b)} "
                f"{b['T'].min()}..{b['T'].max()} incomplete={n_inc}")
    bars = pd.concat(allbars, ignore_index=True)
    bars = bars[bars["T"] >= START].reset_index(drop=True)
    # last complete bar per (sym, shift): drop trailing incomplete bar
    mx = bars.groupby(["sym", "shift"])["T"].transform("max")
    bars = bars[~((bars["T"] == mx) & (bars.nmin < 240))].reset_index(drop=True)
    bars.to_parquet(OUT)
    log(f"saved {OUT} rows={len(bars)} (sym,shift,T + OHLCV)")
    LOG.write_text("\n".join(LINES) + "\n")
    print("coverage log ->", LOG, flush=True)


if __name__ == "__main__":
    main()
