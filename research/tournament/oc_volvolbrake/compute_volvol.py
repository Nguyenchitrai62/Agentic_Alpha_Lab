"""oc_volvolbrake gate computation (frozen PLAN.md definitions).

hourly BTC -> 4h closes on the standard grid -> r/RV6/D/f -> per-anchor
q90/q85 over [A-372d, A-7d) -> gate tables + control constants.

Causality: C4(T) uses the hourly bar starting at T-1h (END <= T);
r(T) = log(C4(T)/C4(T-4h)); RV6(T) = std of 6 returns ending <= T;
D(d) = RV6(d 00:00); f(T) = std of 30 D on days strictly before date(T).
Thresholds use only T in [A-372d, A-7d).

Usage:
  python compute_volvol.py        # full build (resume-safe caches in tmp/)
Run directly or via heavy_slot when RAM is tight.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from volvol_rule import ANCH5, anchor_of, control_mult

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
TMP = HERE / "tmp"
GRID_START = pd.Timestamp("2020-08-04 00:00", tz="UTC")
GRID_END = pd.Timestamp("2026-09-23 20:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
EMBARGO = pd.Timedelta(days=7)
NORM_WIN = pd.Timedelta(days=372)
MIN_NORM = 1000
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")


def build_4h_closes_btc(h: pd.DataFrame) -> pd.Series:
    """BTC 4h closes on the standard grid (float32).

    C4(T) = hourly close of the bar starting at T-1h (END <= T).
    """
    hb = h[h["sym"] == "BTCUSDT"].copy()
    hb["t"] = pd.to_datetime(hb["t"], utc=True)
    piv = hb.set_index("t")["close"].sort_index().astype(np.float32)
    grid = pd.date_range(GRID_START, GRID_END, freq="4h", tz="UTC")
    need = grid - pd.Timedelta(hours=1)
    sub = piv.reindex(need)
    sub.index = grid
    return sub


def compute_rvf(c4: pd.Series) -> pd.DataFrame:
    """r(T), RV6(T), D(d), f(T) per standard-grid bar (causal; NaN where undefined)."""
    closes = c4.to_numpy(dtype=float)
    n = len(c4)
    r = np.full(n, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.log(closes[1:] / closes[:-1])
    lr[~np.isfinite(lr)] = np.nan
    r[1:] = lr
    rv6 = np.full(n, np.nan)
    for t in range(5, n):
        w = r[t - 5:t + 1]
        if np.all(np.isfinite(w)):
            rv6[t] = float(np.std(w, ddof=1))
    idx = c4.index
    # daily RV: RV6 at 00:00 UTC bars
    is_mid = (idx.hour == 0) & (idx.minute == 0)
    dmap: dict[pd.Timestamp, float] = {}
    for t, v in zip(idx[is_mid], rv6[is_mid]):
        dmap[t.normalize()] = float(v)
    days = idx.normalize()
    f = np.full(n, np.nan)
    uniq_days = pd.DatetimeIndex(sorted(dmap.keys()))
    dvals = np.array([dmap[d] for d in uniq_days], dtype=float)
    # map day -> position in uniq_days
    pos = {d: i for i, d in enumerate(uniq_days)}
    for t in range(n):
        d = days[t]
        i = pos.get(d, None)
        if i is None or i < 30:
            continue
        w = dvals[i - 30:i]
        if np.all(np.isfinite(w)):
            f[t] = float(np.std(w, ddof=1))
    return pd.DataFrame({"T": idx, "r": r, "rv6": rv6, "f": f})


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    c4 = build_4h_closes_btc(h)
    del h
    rdf = compute_rvf(c4)
    rdf.to_parquet(TMP / "rvf_std.parquet", index=False)

    anch = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
    anch_ns = np.array([a.value for a in anch], dtype=np.int64)
    T = pd.to_datetime(rdf["T"], utc=True)
    T_ns = T.values.astype("datetime64[ns]").astype(np.int64)
    f = rdf["f"].to_numpy(dtype=float)

    thresholds = {}
    for i, A in enumerate(anch):
        lo = A - NORM_WIN
        hi = A - EMBARGO
        m = (T >= lo) & (T < hi)
        pf = f[m]
        pf = pf[np.isfinite(pf)]
        q90 = float(np.quantile(pf, 0.90)) if len(pf) >= MIN_NORM else float("nan")
        q85 = float(np.quantile(pf, 0.85)) if len(pf) >= MIN_NORM else float("nan")
        thresholds[str(A.date())] = {
            "q90": q90, "q85": q85,
            "n_f": int(len(pf)),
        }
    (TMP / "thresholds.json").write_text(json.dumps(thresholds, indent=1))

    y = anchor_of(T_ns, anch_ns)
    q90v = np.array([thresholds[str(anch[i].date())]["q90"] for i in y])
    q85v = np.array([thresholds[str(anch[i].date())]["q85"] for i in y])
    v1 = np.isfinite(f) & np.isfinite(q90v) & (f > q90v)
    v2 = np.isfinite(f) & np.isfinite(q85v) & (f > q85v)
    pre = (T < CUTOFF).to_numpy()
    v1[pre] = False
    v2[pre] = False
    gates = pd.DataFrame({"T": T, "v1": v1, "v2": v2, "f": f})
    gates.to_parquet(TMP / "gates_std.parquet", index=False)

    controls = {}
    for i, A in enumerate(anch):
        m = (T >= A) & (T < A + YEAR)
        sh1 = float(v1[m].mean()) if int(m.sum()) else 0.0
        sh2 = float(v2[m].mean()) if int(m.sum()) else 0.0
        controls[str(A.date())] = {
            "share_v1": sh1, "share_v2": sh2,
            "m_c1": control_mult(sh1), "m_c2": control_mult(sh2),
            "n_bars": int(m.sum()),
        }
    (TMP / "controls.json").write_text(json.dumps(controls, indent=1))
    print("thresholds:", json.dumps(thresholds, indent=1), flush=True)
    print("controls:", json.dumps(controls, indent=1), flush=True)
    print(f"gate rates: v1={v1.mean():.4f} v2={v2.mean():.4f} n={len(v1)}", flush=True)


if __name__ == "__main__":
    main()
