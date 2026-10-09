"""oc_hlspread signal + descriptive (SHORT-SPAN, light: 4h + funding only, no 1m).

PLAN-fixed (see PLAN.md). Causal definitions:
  HL rows -> 8h windows by floor(time,8h), SUM per window (handles 8h/hourly
  cadence; windows with no HL row skipped, never imputed).
  Draw[w] = HL8[w] - Binance settled 8h rate at w (inner join).
  D(T) = mean(Draw) over last 21 windows with w+8h <= T (fully settled).
  z(T) = (D(T)-mean1y)/std1y over prior D(T') in [T-365d,T), min 720 finite.
  Gate: z>+1.5 -> long x0.5; z<-1.5 -> short x0.5; NaN -> 1.0.

Descriptive (2023-05-01 .. <2025-09-24 decisions only): per coin Spearman IC
of z vs next-24h/7d vol-normalised forward open-to-open return + |z|>1.5 share.

Outputs (ONLY research/tournament/oc_hlspread/):
  panel.parquet (T,sym,D,z,gate_long,gate_short), descriptive.csv, tmp/signal_info.json

Run: .venv/Scripts/python.exe research/tournament/oc_hlspread/compute_panel.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
HL_DIR = ROOT / "data" / "raw" / "hyperliquid_20261007"
BIN_DIR = ROOT / "data" / "raw" / "binance_premium_20260928"
OPENS = ROOT / "artifacts" / "research" / "engine_real" / "opens_v154.parquet"

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
SYM = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "BNB": "BNBUSDT", "XRP": "XRPUSDT"}

NS_8H = 8 * 3600 * 10**9
NS_365D = 365 * 24 * 3600 * 10**9
MIN_D_BARS = 720  # 120 days of 4h bars
NWIN = 21  # 7 days of 8h settlements
TH = 1.5
DESC_LO = pd.Timestamp("2023-05-01", tz="UTC")
DESC_HI = pd.Timestamp("2025-09-24", tz="UTC")  # decisions strictly before this


def hl_8h(hl: pd.DataFrame) -> pd.DataFrame:
    """Sum HL hourly fundingRates into 8h windows. Pure (tested)."""
    df = hl.copy()
    df["win"] = df["time"].dt.floor("8h")
    g = df.groupby("win")
    out = pd.DataFrame({
        "win": sorted(df["win"].unique()),
        "hl_sum": g["fundingRate"].sum().values,
        "hl_n": g["fundingRate"].size().values,
    })
    return out.sort_values("win").reset_index(drop=True)


def build_draw(coin: str):
    """Draw[w] = HL8 - Binance8 for one coin. Returns (draw df, hl, bn)."""
    hl = pd.read_parquet(HL_DIR / f"HL_{coin}_funding_1h.parquet")
    bn = pd.read_parquet(BIN_DIR / f"{SYM[coin]}_funding.parquet")
    bn = bn.rename(columns={"calc_time": "win", "last_funding_rate": "bin_sum"})
    bn["win"] = pd.to_datetime(bn["win"], utc=True).dt.floor("8h")
    h8 = hl_8h(hl)
    m = h8.merge(bn[["win", "bin_sum"]], on="win", how="inner")
    m["draw"] = m["hl_sum"] - m["bin_sum"]
    return m.sort_values("win").reset_index(drop=True), hl, bn


def compute_D(grid_ns: np.ndarray, win_ns: np.ndarray, draw: np.ndarray) -> np.ndarray:
    """D(T) = mean of last 21 Draw windows with w <= T-8h. Pure (tested)."""
    D = np.full(len(grid_ns), np.nan)
    j = np.searchsorted(win_ns, grid_ns - NS_8H, side="right") - 1
    cs = np.concatenate([[0.0], np.cumsum(draw)])
    for i in range(len(grid_ns)):
        jj = j[i]
        if jj >= NWIN - 1:
            D[i] = (cs[jj + 1] - cs[jj + 1 - NWIN]) / NWIN
    return D


def compute_z(D: np.ndarray, grid_ns: np.ndarray) -> np.ndarray:
    """z(T) from strictly prior D in [T-365d,T), min 720 finite. Pure (tested)."""
    n = len(D)
    finite = np.isfinite(D)
    d0 = np.where(finite, D, 0.0)
    cs = np.concatenate([[0.0], np.cumsum(d0)])
    csq = np.concatenate([[0.0], np.cumsum(d0 * d0)])
    cnt = np.concatenate([[0], np.cumsum(finite.astype(np.int64))])
    z = np.full(n, np.nan)
    for i in range(n):
        left = int(np.searchsorted(grid_ns, grid_ns[i] - NS_365D, side="left"))
        c = int(cnt[i] - cnt[left])
        if c >= MIN_D_BARS and np.isfinite(D[i]):
            s = float(cs[i] - cs[left])
            sq = float(csq[i] - csq[left])
            mean = s / c
            var = (sq - s * s / c) / (c - 1) if c > 1 else np.nan
            if np.isfinite(var) and var > 0:
                z[i] = (D[i] - mean) / np.sqrt(var)
    return z


def main() -> None:
    opens = pd.read_parquet(OPENS)
    grid = pd.to_datetime(opens.index, utc=True).sort_values()
    grid_ns = grid.values.astype("datetime64[ns]").astype(np.int64)
    print(f"grid {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    panels = []
    overlap_ends = []
    for coin in COINS:
        sym = SYM[coin]
        m, hl, bn = build_draw(coin)
        win_ns = m["win"].values.astype("datetime64[ns]").astype(np.int64)
        draw = m["draw"].to_numpy(float)
        D = compute_D(grid_ns, win_ns, draw)
        z = compute_z(D, grid_ns)
        df = pd.DataFrame({"T": grid, "sym": sym, "D": D, "z": z})
        df["gate_long"] = np.isfinite(z) & (z > TH)
        df["gate_short"] = np.isfinite(z) & (z < -TH)
        panels.append(df)
        overlap_ends.append(str(m["win"].iloc[-1]))
        nD = int(np.isfinite(D).sum())
        nz = int(np.isfinite(z).sum())
        print(f"{coin}: windows {len(m)} D-bars {nD} z-bars {nz} "
              f"first-D {grid[np.isfinite(D)][0] if nD else None} "
              f"first-z {grid[np.isfinite(z)][0] if nz else None}", flush=True)

    panel = pd.concat(panels, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")
    print(f"saved panel.parquet {len(panel)} rows", flush=True)

    # ---- descriptive (decisions in [2023-05-01, 2025-09-24)) ----
    rows = []
    for coin in COINS:
        sym = SYM[coin]
        sub = panel[panel["sym"] == sym].sort_values("T").reset_index(drop=True)
        op = pd.to_numeric(opens[sym].reindex(pd.to_datetime(sub["T"], utc=True)).values, errors="coerce")
        sub["open"] = op
        ret4 = sub["open"] / sub["open"].shift(1) - 1.0
        vol = ret4.rolling(180, min_periods=60).std()
        f24 = sub["open"].shift(-6) / sub["open"] - 1.0
        f7d = sub["open"].shift(-42) / sub["open"] - 1.0
        sub["fwd24n"] = f24 / (vol * np.sqrt(6))
        sub["fwd7dn"] = f7d / (vol * np.sqrt(42))
        msk = (pd.to_datetime(sub["T"], utc=True) >= DESC_LO) & (pd.to_datetime(sub["T"], utc=True) < DESC_HI)
        d = sub[msk].copy()
        finite_z = d["z"].notna()
        share = float((d.loc[finite_z, "z"].abs() > TH).mean()) if finite_z.sum() else float("nan")
        share_p = float((d.loc[finite_z, "z"] > TH).mean()) if finite_z.sum() else float("nan")
        share_m = float((d.loc[finite_z, "z"] < -TH).mean()) if finite_z.sum() else float("nan")
        out = {"coin": coin, "n_dec": int(len(d)), "n_z": int(finite_z.sum()),
               "share_abs15": round(share, 6) if np.isfinite(share) else None,
               "share_p15": round(share_p, 6) if np.isfinite(share_p) else None,
               "share_m15": round(share_m, 6) if np.isfinite(share_m) else None}
        for col, nm in (("fwd24n", "ic24"), ("fwd7dn", "ic7d")):
            dd = d[np.isfinite(d["z"].to_numpy()) & np.isfinite(d[col].to_numpy())]
            if len(dd) >= 10:
                ic = float(pd.Series(dd["z"].to_numpy()).corr(pd.Series(dd[col].to_numpy()), method="spearman"))
            else:
                ic = float("nan")
            out[nm] = round(ic, 4) if np.isfinite(ic) else None
            out[nm + "_n"] = int((np.isfinite(d["z"].to_numpy()) & np.isfinite(d[col].to_numpy())).sum())
        rows.append(out)
        print(out, flush=True)

    desc = pd.DataFrame(rows)
    desc.to_csv(HERE / "descriptive.csv", index=False)
    info = {"overlap_end_binance": "2026-08-31 16:00 UTC (last settled window; window end 2026-09-01 00:00 UTC)",
            "overlap_ends_per_coin": overlap_ends,
            "descriptive_window": "[2023-05-01, 2025-09-24 decisions)",
            "note": "SHORT-SPAN: no dev4 selection; thresholds fixed in PLAN.md"}
    (HERE / "tmp" / "signal_info.json").write_text(json.dumps(info, indent=1))
    print("saved descriptive.csv + tmp/signal_info.json", flush=True)


if __name__ == "__main__":
    main()
