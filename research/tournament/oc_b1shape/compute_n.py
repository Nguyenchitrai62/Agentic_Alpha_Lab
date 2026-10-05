"""oc_b1shape: compute n per majors R2-rung fill (one coin of 1m in RAM at a time).

For fill (sym s, bar open T, fill offset f): for each OTHER major c:
  sigma_c(T) = sample std (ddof=1) of trailing 360 4h open-to-open simple
    returns ending at bar T (min 120; NaN -> no detection),
  O_c(T) = 1m open at minute T,
  close_c(f-1) = 1m close at minute T+(f-1),
  det25 = close <= O*(1-2.5*sigma); det20 = close <= O*(1-2.0*sigma).
n25/n20 = counts over the 4 others; btc_det = BTC-det25 flag (non-BTC fills).

Output: fills_n.parquet (one row per majors R2 fill, all dates).
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
EXT = ROOT / "research/tournament/ext/fills_U_ext.parquet"
OUT = Path(__file__).parent / "fills_n.parquet"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
END = pd.Timestamp("2026-09-24", tz="UTC")

ONE_M = {
    "BTCUSDT": "data/raw/btc_intraday_20260924/klines_1m_*.parquet",
    "ETHUSDT": "data/raw/majors_intraday_20260924/ETHUSDT_1m_*.parquet",
    "SOLUSDT": "data/raw/majors_intraday_20260924/SOLUSDT_1m_*.parquet",
    "BNBUSDT": "data/raw/majors_intraday_20260924/BNBUSDT_1m_*.parquet",
    "XRPUSDT": "data/raw/majors_intraday_20260924/XRPUSDT_1m_*.parquet",
}


def load_1m(sym: str) -> pd.DataFrame:
    fs = sorted(glob.glob(str(ROOT / ONE_M[sym])))
    parts = []
    for f in fs:
        d = pd.read_parquet(f, columns=["open_time", "open", "close"])
        d = d[d.open_time < END]
        parts.append(d)
    m = pd.concat(parts, ignore_index=True).drop_duplicates("open_time").sort_values("open_time")
    m["open"] = m["open"].astype("float32")
    m["close"] = m["close"].astype("float32")
    return m.reset_index(drop=True)


def sigma_on_grid(m: pd.DataFrame) -> pd.DataFrame:
    """4h opens + trailing sigma per grid bar (float64 math, small frame)."""
    g = m[(m.open_time.dt.minute == 0) & (m.open_time.dt.hour % 4 == 0)].copy()
    g = g.sort_values("open_time").reset_index(drop=True)
    o = g["open"].to_numpy(dtype="float64")
    ret = np.full(len(o), np.nan)
    ret[1:] = o[1:] / o[:-1] - 1.0
    sig = pd.Series(ret).rolling(360, min_periods=120).std(ddof=1).to_numpy()
    return pd.DataFrame({"T": g["open_time"].to_numpy(), "O": o, "sig": sig})


def main():
    fills = pd.read_parquet(EXT)
    fills["Bx"] = fills.t_fill - pd.to_timedelta(fills.f, unit="min")
    fills["k"] = fills.x1
    m = fills[fills.sym.isin(MAJORS) & fills.k.isin(R2)].copy().reset_index(drop=True)
    print("majors R2 fills:", len(m), flush=True)
    tx = m["Bx"]
    print("on-grid share:", float(((tx.dt.minute == 0) & (tx.dt.hour % 4 == 0)).mean()), flush=True)
    print("f range:", int(m.f.min()), int(m.f.max()), flush=True)

    n25 = np.zeros(len(m), dtype=np.int8)
    n20 = np.zeros(len(m), dtype=np.int8)
    btc_det = np.zeros(len(m), dtype=np.int8)
    miss_close = np.zeros(len(m), dtype=np.int32)
    miss_bar = np.zeros(len(m), dtype=np.int32)

    for c in MAJORS:  # one coin of 1m in RAM at a time
        idx = (m.sym != c).to_numpy()
        print(f"coin {c}: queries {int(idx.sum())}", flush=True)
        m1 = load_1m(c)
        close_s = pd.Series(m1["close"].to_numpy(), index=m1["open_time"])
        grid = sigma_on_grid(m1)
        del m1
        o_s = pd.Series(grid["O"].to_numpy(), index=pd.DatetimeIndex(grid["T"], tz="UTC"))
        s_s = pd.Series(grid["sig"].to_numpy(), index=pd.DatetimeIndex(grid["T"], tz="UTC"))
        del grid
        Tq = m["Bx"][idx]
        Fq = m["f"][idx].to_numpy()
        minutes = Tq + pd.to_timedelta(Fq - 1, unit="min")
        cl = close_s.reindex(minutes.to_numpy()).to_numpy(dtype="float64")
        oo = o_s.reindex(Tq.to_numpy()).to_numpy(dtype="float64")
        sg = s_s.reindex(Tq.to_numpy()).to_numpy(dtype="float64")
        ok = np.isfinite(cl) & np.isfinite(oo) & np.isfinite(sg)
        miss_close[idx] += (~np.isfinite(cl)).astype(int)
        miss_bar[idx] += (np.isfinite(cl) & (~np.isfinite(oo) | ~np.isfinite(sg))).astype(int)
        d25 = np.zeros(len(cl), bool)
        d20 = np.zeros(len(cl), bool)
        d25[ok] = cl[ok] <= oo[ok] * (1.0 - 2.5 * sg[ok])
        d20[ok] = cl[ok] <= oo[ok] * (1.0 - 2.0 * sg[ok])
        rows = np.flatnonzero(idx)
        n25[rows[d25]] += 1
        n20[rows[d20]] += 1
        if c == "BTCUSDT":
            btc_det[rows[d25]] = 1

    out = pd.DataFrame({
        "sym": m["sym"].to_numpy(),
        "Tbar": m["Bx"].to_numpy(),
        "t_fill": m["t_fill"].to_numpy(),
        "f": m["f"].to_numpy(dtype="int32"),
        "k": m["k"].to_numpy(dtype="float64"),
        "y1.0": m["y1.0"].to_numpy(dtype="float64"),
        "n25": n25.astype("int8"),
        "n20": n20.astype("int8"),
        "btc_det": btc_det.astype("int8"),
        "miss_close_q": miss_close,
        "miss_bar_q": miss_bar,
    })
    assert out.n25.between(0, 4).all() and out.n20.between(0, 4).all()
    out.to_parquet(OUT)
    print("wrote", OUT, len(out), flush=True)
    print(out["n25"].value_counts().sort_index().to_string(), flush=True)


if __name__ == "__main__":
    main()
