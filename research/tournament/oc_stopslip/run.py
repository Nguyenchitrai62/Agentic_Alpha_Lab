"""oc_stopslip run: measure the S4 stop-slip-0.5 assumption on Binance vs Bybit 1m.

DIAGNOSTIC. One process; 1m OHLC of ONE coin x BOTH venues at a time; RAM < 3 GB.
See PLAN.md (frozen before any outcome computation).

Usage: .venv/Scripts/python.exe research/tournament/oc_stopslip/run.py
Writes results.json + stops.parquet in this folder.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KPI = HERE.parent / "oc_kpi_g2"
MAKER, TAKER = 0.0002, 0.00055
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
END = YEAR_END  # hard cap: no 1m row at/after this is ever used
BIN_BTC = Path("data/raw/btc_intraday_20260924")
BIN_MAJ = Path("data/raw/majors_intraday_20260924")
BYB_DIR = Path("data/raw/bybit_linear_1m_20261004")
FLASH_WIN = 1440  # trailing minutes for the range sigma
FLASH_MIN = 720


def year_of_exit(t) -> int | None:
    t = pd.Timestamp(t)
    a4 = ANCHORS[4]
    if t > a4 + pd.Timedelta(days=365):
        return 4
    for y in range(5):
        a0 = ANCHORS[y]
        if a0 < t <= a0 + pd.Timedelta(days=365):
            return y
    if ANCHORS[0] < t <= a4:  # leap-day gap 2024-09-23..2024-09-24
        return 3
    return None


def stop_level(kind: str, price: float, ret: float) -> float:
    """Stop-level proxy (PLAN.md def 1)."""
    if kind == "book_stop":
        return float(price)
    lv = float(price) / (1.0 + float(ret))
    return float(price) + lv * (MAKER + TAKER)


def load_stops() -> pd.DataFrame:
    rows = []
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet")
        st = ev[ev["kind"].isin(["book_stop", "rung_sl"])].copy()
        st["shift"] = s
        rows.append(st)
    df = pd.concat(rows, ignore_index=True)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df = df[(df["t"] < END)].reset_index(drop=True)
    df["stop"] = [stop_level(k, p, r) for k, p, r in
                  zip(df["kind"], df["price"].to_numpy(float), df["ret"].to_numpy(float))]
    df["year"] = [year_of_exit(t) for t in df["t"]]
    df = df[np.isfinite(df["stop"].to_numpy(float)) & (df["stop"] > 0) & df["year"].notna()].reset_index(drop=True)
    df["year"] = df["year"].astype(int)
    df["stop_id"] = df.index.astype(int)
    return df[["stop_id", "shift", "t", "symbol", "kind", "side", "price", "ret", "weight", "stop", "year"]]


def load_binance(sym: str) -> pd.DataFrame:
    if sym == "BTCUSDT":
        files = sorted(BIN_BTC.glob("klines_1m_20*.parquet"))
    else:
        files = sorted(BIN_MAJ.glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    del parts
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m[m["open_time"] < END]
    m = m.drop_duplicates("open_time").sort_values("open_time").set_index("open_time")
    return m


def load_bybit(sym: str) -> pd.DataFrame:
    m = pd.read_parquet(BYB_DIR / f"{sym}_1m.parquet",
                        columns=["open_time", "open", "high", "low", "close"])
    m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
    m = m[m["open_time"] < END]
    m = m.drop_duplicates("open_time").sort_values("open_time").set_index("open_time")
    return m


def venue_stats(stops: pd.DataFrame, venues: dict) -> pd.DataFrame:
    """Per-stop venue measurements (PLAN.md defs 2-5). venues: {'bin': df, 'byb': df}."""
    out = stops.copy()
    for tag, m in venues.items():
        idx = m.index
        ii = idx.asi8
        O = m["open"].to_numpy(float)
        H = m["high"].to_numpy(float)
        L = m["low"].to_numpy(float)
        R = np.where(np.isfinite(O) & (O > 0) & np.isfinite(H) & np.isfinite(L),
                     (H - L) / np.where(O == 0, np.nan, O) * 1e4, np.nan)
        tns = stops["t"].to_numpy(dtype="datetime64[ns]").astype("int64")
        n = len(stops)
        o_md = np.full(n, np.nan)
        h_md = np.full(n, np.nan)
        l_md = np.full(n, np.nan)
        r_md = np.full(n, np.nan)
        on_md = np.full(n, np.nan)
        sig_md = np.full(n, np.nan)
        mu_md = np.full(n, np.nan)
        pos = np.searchsorted(ii, tns)
        pos_next = np.searchsorted(ii, tns + 60_000_000_000)
        has = pos < len(idx)
        hit = np.zeros(n, bool)
        hit_next = np.zeros(n, bool)
        tt = stops["t"]
        for j in range(n):
            p = pos[j]
            if p < len(idx) and idx[p] == tt.iloc[j]:
                hit[j] = True
                o_md[j], h_md[j], l_md[j], r_md[j] = O[p], H[p], L[p], R[p]
            pn = pos_next[j]
            t_next = tt.iloc[j] + pd.Timedelta(minutes=1)
            if pn < len(idx) and idx[pn] == t_next:
                hit_next[j] = True
                on_md[j] = O[pn]
            # trailing flash moments: R over [t-1440min, t)
            lo = np.searchsorted(ii, tns[j] - FLASH_WIN * 60_000_000_000)
            w = R[lo:p] if p <= len(R) else np.array([])
            w = w[np.isfinite(w)]
            # keep only rows strictly before t (positional slice already excludes t)
            if len(w) >= FLASH_MIN:
                mu_md[j] = float(np.mean(w))
                sig_md[j] = float(np.std(w, ddof=1))
        stop = stops["stop"].to_numpy(float)
        is_long = (stops["side"] == "sell").to_numpy()
        slip = np.full(n, np.nan)
        ok = np.isfinite(stop) & np.isfinite(on_md) & (stop > 0)
        slip[ok & is_long] = (stop[ok & is_long] - on_md[ok & is_long]) / stop[ok & is_long] * 1e4
        slip[ok & ~is_long] = (on_md[ok & ~is_long] - stop[ok & ~is_long]) / stop[ok & ~is_long] * 1e4
        depth = np.full(n, np.nan)
        okL = np.isfinite(stop) & (stop > 0) & np.isfinite(l_md)
        okH = np.isfinite(stop) & (stop > 0) & np.isfinite(h_md)
        depth[is_long & okL] = np.maximum(0.0, (stop[is_long & okL] - l_md[is_long & okL]) / stop[is_long & okL] * 1e4)
        depth[~is_long & okH] = np.maximum(0.0, (h_md[~is_long & okH] - stop[~is_long & okH]) / stop[~is_long & okH] * 1e4)
        s4 = 0.5 * depth
        with np.errstate(divide="ignore", invalid="ignore"):
            frac = np.where(np.isfinite(slip) & np.isfinite(s4) & (s4 > 0), slip / s4, np.nan)
        flash = (np.isfinite(r_md) & np.isfinite(mu_md) & np.isfinite(sig_md) & (sig_md > 0)
                 & (r_md > mu_md + 3 * sig_md))
        out[f"O_{tag}"] = o_md
        out[f"H_{tag}"] = h_md
        out[f"L_{tag}"] = l_md
        out[f"R_{tag}"] = r_md
        out[f"Onext_{tag}"] = on_md
        out[f"mu_{tag}"] = mu_md
        out[f"sig_{tag}"] = sig_md
        out[f"slip_{tag}"] = slip
        out[f"s4_{tag}"] = s4
        out[f"frac_{tag}"] = frac
        out[f"flash_{tag}"] = flash
        out[f"has_{tag}"] = hit
        out[f"has_next_{tag}"] = hit_next
    return out


def q(a: np.ndarray, p: float) -> float | None:
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    if not len(a):
        return None
    return round(float(np.percentile(a, p)), 2)


def agg_block(sub: pd.DataFrame, tag: str) -> dict:
    slip = sub[f"slip_{tag}"].to_numpy(float)
    s4 = sub[f"s4_{tag}"].to_numpy(float)
    frac = sub[f"frac_{tag}"].to_numpy(float)
    fin = np.isfinite(slip)
    return dict(
        n=int(len(sub)),
        n_fin=int(int(fin.sum())),
        n_missing=int(int((~np.isfinite(slip)).sum())),
        slip_median=q(slip, 50), slip_p90=q(slip, 90), slip_p99=q(slip, 99),
        slip_max=round(float(np.nanmax(slip)), 2) if fin.any() else None,
        slip_mean=round(float(np.nanmean(slip)), 2) if fin.any() else None,
        s4_median=q(s4, 50),
        frac_median=q(frac[np.isfinite(frac)], 50),
        share_flash=round(float(np.mean(sub[f"flash_{tag}"].to_numpy(bool))), 4),
        share_s4_zero=round(float(np.mean((np.isfinite(s4)) & (s4 == 0))), 4),
    )


def main():
    stops = load_stops()
    print(f"stops universe: {len(stops)} (book_stop={(stops['kind'] == 'book_stop').sum()}, "
          f"rung_sl={(stops['kind'] == 'rung_sl').sum()})", flush=True)
    per_coin_year, pooled_coin, pooled_year, cover = [], [], [], {}
    ledgers = []
    for sym in MAJORS:
        sub = stops[stops["symbol"] == sym].reset_index(drop=True)
        if not len(sub):
            continue
        mbin = load_binance(sym)
        mbyb = load_bybit(sym)
        print(f"{sym}: stops={len(sub)} bin_1m={len(mbin)} byb_1m={len(mbyb)}", flush=True)
        led = venue_stats(sub, {"bin": mbin, "byb": mbyb})
        ledgers.append(led)
        cov = {}
        for tag in ("bin", "byb"):
            cov[tag] = dict(has_bar=int(led[f"has_{tag}"].sum()),
                            has_next=int(led[f"has_next_{tag}"].sum()),
                            n_fin=int(led[f"slip_{tag}"].notna().sum()))
        cover[sym] = cov
        for y in range(5):
            syy = led[led["year"] == y]
            if not len(syy):
                continue
            for tag in ("bin", "byb"):
                per_coin_year.append(dict(sym=sym, year=y,
                                          anchor=ANCHORS[y].strftime("%Y-%m-%d"),
                                          venue=("binance" if tag == "bin" else "bybit"),
                                          **agg_block(syy, tag)))
        for tag in ("bin", "byb"):
            pooled_coin.append(dict(sym=sym, venue=("binance" if tag == "bin" else "bybit"),
                                    **agg_block(led, tag)))
        del mbin, mbyb
    led = pd.concat(ledgers, ignore_index=True)
    for y in range(5):
        syy = led[led["year"] == y]
        for tag in ("bin", "byb"):
            pooled_year.append(dict(year=y, anchor=ANCHORS[y].strftime("%Y-%m-%d"),
                                    venue=("binance" if tag == "bin" else "bybit"),
                                    **agg_block(syy, tag)))
    pool_all = {("binance" if tag == "bin" else "bybit"): agg_block(led, tag) for tag in ("bin", "byb")}
    # worst 10 by max adverse slip over venues
    led["worst"] = led[["slip_bin", "slip_byb"]].max(axis=1, skipna=True)
    w10 = led[np.isfinite(led["worst"].to_numpy(float))].sort_values("worst", ascending=False).head(10)
    worst = []
    for r in w10.itertuples():
        worst.append(dict(t=str(r.t), sym=r.symbol, kind=r.kind, side=r.side, shift=int(r.shift),
                          year=int(r.year), stop=round(float(r.stop), 6),
                          bin_O=round(float(r.O_bin), 6) if np.isfinite(r.O_bin) else None,
                          bin_H=round(float(r.H_bin), 6) if np.isfinite(r.H_bin) else None,
                          bin_L=round(float(r.L_bin), 6) if np.isfinite(r.L_bin) else None,
                          bin_Onext=round(float(r.Onext_bin), 6) if np.isfinite(r.Onext_bin) else None,
                          bin_slip=round(float(r.slip_bin), 2) if np.isfinite(r.slip_bin) else None,
                          bin_s4=round(float(r.s4_bin), 2) if np.isfinite(r.s4_bin) else None,
                          bin_frac=round(float(r.frac_bin), 3) if np.isfinite(r.frac_bin) else None,
                          bin_flash=bool(r.flash_bin),
                          byb_O=round(float(r.O_byb), 6) if np.isfinite(r.O_byb) else None,
                          byb_H=round(float(r.H_byb), 6) if np.isfinite(r.H_byb) else None,
                          byb_L=round(float(r.L_byb), 6) if np.isfinite(r.L_byb) else None,
                          byb_Onext=round(float(r.Onext_byb), 6) if np.isfinite(r.Onext_byb) else None,
                          byb_slip=round(float(r.slip_byb), 2) if np.isfinite(r.slip_byb) else None,
                          byb_s4=round(float(r.s4_byb), 2) if np.isfinite(r.s4_byb) else None,
                          byb_frac=round(float(r.frac_byb), 3) if np.isfinite(r.frac_byb) else None,
                          byb_flash=bool(r.flash_byb)))
    out = dict(
        config=dict(universe="oc_kpi_g2 events_s0..3 book_stop+rung_sl pooled over 4 shifts",
                    stop_level="book_stop: event price; rung_sl: price + lv*(MAKER+TAKER) (PLAN.md def 1)",
                    slip="adverse-positive bps vs stop: long (sell) (stop-Onext)/stop; short (buy) (Onext-stop)/stop",
                    s4="0.5 * max(0, (stop-L)/stop) longs / max(0, (H-stop)/stop) shorts, exit-minute bar, per venue",
                    frac="slip/s4 where s4>0 (1.0 = next-open fill equals the S4 assumption)",
                    flash="exit-minute range R=(H-L)/O vs trailing 1440m mean mu and std sig of R (min 720), flash = R > mu + 3*sig",
                    year="exit time in anchor year [A_k, A_k+365d), A=2021-09-24..2025-09-24 (leap gap joins Y3)",
                    binance_store="data/raw/btc_intraday_20260924 + data/raw/majors_intraday_20260924",
                    bybit_store="data/raw/bybit_linear_1m_20261004 (S5 store in v411_audit/robust_v411.py)",
                    cap="no 1m row >= 2026-09-24 00:00 UTC used",
                    note="all five years are research data; findings need prospective validation"),
        n_stops=int(len(led)),
        n_book_stop=int((led["kind"] == "book_stop").sum()),
        n_rung_sl=int((led["kind"] == "rung_sl").sum()),
        coverage=cover,
        pooled=pool_all,
        per_coin_year=per_coin_year,
        pooled_coin=pooled_coin,
        pooled_year=pooled_year,
        worst10=worst,
        caveats=[
            "events store the base-engine (stop_slip=0) fill, not the level; on gap opens the fill is the minute open, so the stop proxy is the gap open and measured slip is a lower bound there",
            "rung_sl event price is net of MAKER+TAKER; the script adds lv*(0.00075) back to recover the raw fill",
            "next-minute open is a measurement proxy for a market fill, not the engine fill (engine fills inside the exit minute)",
        ],
    )
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    led.to_parquet(HERE / "stops.parquet", index=False)
    print(f"n={len(led)} pooled bin slip_med={pool_all['binance']['slip_median']} "
          f"frac_med={pool_all['binance']['frac_median']} | "
          f"byb slip_med={pool_all['bybit']['slip_median']} frac_med={pool_all['bybit']['frac_median']}", flush=True)


if __name__ == "__main__":
    main()
