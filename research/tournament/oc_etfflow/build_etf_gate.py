"""oc_etfflow: build S5 / trailing p5-p10 gate panel (causal, PLAN-pinned).

Availability: F(D) known from D+1 08:00 UTC. For book row T (4h bar open time,
close = T+4h): D*(T) = max trading day D with D+1 08:00 UTC <= T+4h.
S5(T) = sum of F over last 5 trading days <= D*(T) (NaN if <5 published).
H(T) = last 250 S5 values over distinct prior trading days (D < D*(T),
finite S5, most recent first); require >=120 else gate OFF.
T1_ON = S5 < p5(H); T2_ON = S5 < p10(H). z diagnostic only.

Grid: standard book rows = artifacts/research/engine_real/member_A_O1_orders
index (10950 bars 2021-09-24..2026-09-23 20:00 UTC). Rows before the first
published availability are OFF (NaN S5 / short history).

  .venv/Scripts/python.exe research/tournament/oc_etfflow/build_etf_gate.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
DATA = ROOT / "data/raw/etf_flows_20261007"
CACHE = ROOT / "artifacts/research/engine_real"
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)


def load_flows() -> pd.DataFrame:
    b = pd.read_csv(DATA / "btc_etf_flows_daily.csv", parse_dates=["date"])
    e = pd.read_csv(DATA / "eth_etf_flows_daily.csv", parse_dates=["date"])
    b["date"] = pd.to_datetime(b["date"], utc=True)
    e["date"] = pd.to_datetime(e["date"], utc=True)
    m = pd.merge(b.rename(columns={"total_net_flow_usd_m": "btc"}),
                 e.rename(columns={"total_net_flow_usd_m": "eth"}),
                 on="date", how="outer").sort_values("date")
    m["btc"] = m["btc"].fillna(0.0)
    # ETH missing before launch 2024-07-23 = no fund -> 0.0; after launch a
    # missing date means no trading day (excluded from index below).
    eth_days = set(pd.to_datetime(
        pd.read_csv(DATA / "eth_etf_flows_daily.csv")["date"]).dt.date)
    # Keep rows where at least one side published (outer join already does).
    m["eth"] = m["eth"].fillna(0.0)
    m["F"] = m["btc"] + m["eth"]
    m = m[(m["date"] >= pd.Timestamp("2024-01-11", tz="UTC")) &
          (m["date"] < CAP)].reset_index(drop=True)
    m["avail"] = m["date"] + pd.Timedelta(days=1) + pd.Timedelta(hours=8)
    # avail = D+1 08:00 UTC: date is midnight UTC of D, so +32h.
    return m


def main() -> None:
    fl = load_flows()
    dates = fl["date"].to_numpy()
    avail = fl["avail"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    F = fl["F"].to_numpy(float)
    # S5 per trading day (sum of last 5 F, NaN if <5).
    S5d = np.full(len(fl), np.nan)
    for i in range(len(fl)):
        if i >= 4:
            S5d[i] = float(F[i - 4:i + 1].sum())

    grid = pd.read_parquet(CACHE / "member_A_O1_orders.parquet").index
    grid = pd.to_datetime(grid, utc=True).sort_values()
    closes = (grid + pd.Timedelta(hours=4)).values.astype("datetime64[ns]").astype(np.int64)

    # D*(T): last trading day with avail <= close(T).
    pos = np.searchsorted(avail, closes, side="right") - 1
    out = []
    # Distinct-day S5 history: list of (day_idx) in order; H(T) = S5d of last
    # 250 distinct days strictly before D*(T).
    for gi, t in enumerate(grid):
        di = int(pos[gi])
        if di < 0:
            out.append((t, None, np.nan, np.nan, np.nan, np.nan, 0, False, False))
            continue
        dstar = str(pd.Timestamp(dates[di]).date())
        s5 = float(S5d[di]) if np.isfinite(S5d[di]) else np.nan
        # history: distinct days j < di with finite S5d, last 250.
        lo = max(0, di - 400)  # wide enough to collect 250 finite
        hist = [S5d[j] for j in range(di - 1, lo - 1, -1) if np.isfinite(S5d[j])]
        hist = hist[:250]
        # keep chronological for percentile (order irrelevant); use as-is.
        n = len(hist)
        if np.isfinite(s5) and n >= 120:
            h = np.array(hist[::-1])  # oldest->newest, content same set
            p5 = float(np.percentile(h, 5, method="linear"))
            p10 = float(np.percentile(h, 10, method="linear"))
            med = float(np.median(h))
            spread = float(np.percentile(h, 90, method="linear") - np.percentile(h, 10, method="linear"))
            z = float((s5 - med) / max(spread, 1e-9))
            t1 = bool(s5 < p5)
            t2 = bool(s5 < p10)
        else:
            p5 = p10 = z = np.nan
            t1 = t2 = False
        out.append((t, dstar, s5, p5, p10, z, n, t1, t2))
    panel = pd.DataFrame(out, columns=["T", "Dstar", "S5", "p5", "p10", "z", "n_hist", "T1_on", "T2_on"])
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    # Diagnostics per anchor year (signal only, not engine outcomes).
    bounds = ANCHORS + [LAST_BOUND]
    print(f"flows: {len(fl)} trading days {fl['date'].min().date()}..{fl['date'].max().date()}")
    print(f"panel: {len(panel)} bars; T1_on={int(panel['T1_on'].sum())} T2_on={int(panel['T2_on'].sum())}")
    for k, a0 in enumerate(ANCHORS):
        m = (panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])
        seg = panel[m]
        weeks = seg["T"].dt.strftime("%Y-%W")[seg["T1_on"] | seg["T2_on"]].nunique() if len(seg) else 0
        w1 = seg["T"].dt.strftime("%Y-%W")[seg["T1_on"]].nunique() if len(seg) else 0
        w2 = seg["T"].dt.strftime("%Y-%W")[seg["T2_on"]].nunique() if len(seg) else 0
        print(f"{a0.date()}: n={int(m.sum())} T1bars={int(seg['T1_on'].sum())} "
              f"T2bars={int(seg['T2_on'].sum())} T1weeks={w1} T2weeks={w2} "
              f"meanMult_T1={1 - 0.5 * seg['T1_on'].mean():.4f} meanMult_T2={1 - 0.5 * seg['T2_on'].mean():.4f}")
    # First gate dates (to show short-span onset).
    first1 = panel[panel["T1_on"]]["T"].min()
    first2 = panel[panel["T2_on"]]["T"].min()
    print(f"first T1 gate: {first1}; first T2 gate: {first2}")


if __name__ == "__main__":
    main()
