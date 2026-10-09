"""V2 dip-leg replica gate: mask frozen D0+B1 replica ledger on VPIN-gated bars.

Ledger (read-only): research/tournament/oc_k2placebo/tmp/ledger.npz
  bar_time = minutes since 2020-08-01 UTC; T = base + bar_time + phase hours.
  coin 0..4 = BTC,ETH,SOL,BNB,XRP. Base per-year 4-phase-mean sums must equal
  7.718304 total (gate: n==22312; else STOP).
Rule (frozen): skip (zero) ledger rows whose (coin, phase, T) is VPIN-gated
  (latest VPIN grid T' <= T, causal; rows < 2021-09-24 never gated).
Metric: per-year 4-phase-mean sums base vs masked, dSum per year + dSum5y.
PROMISING (IDEAS5 header) iff dSum5y >= +0.273. CPU-only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
K2P = ROOT / "research/tournament/oc_k2placebo/tmp"
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
BASE = pd.Timestamp("2020-08-01", tz="UTC")
N_GATE = 22312
SUM_GATE = 7.718304
PROMISING = 0.273


def main():
    L = np.load(K2P / "ledger.npz")
    assert len(L["bar_time"]) == N_GATE, len(L["bar_time"])
    ph = L["phase"].astype(int)
    co = L["coin"].astype(int)
    yr = L["year"].astype(int)
    w = L["w"].astype(float)
    yv = L["y10"].astype(float)
    bt = L["bar_time"].astype(np.int64)
    T = np.int64(BASE.value) \
        + bt * np.int64(60_000_000_000) + ph.astype(np.int64) * np.int64(3_600_000_000_000)
    # VPIN gate grids per coin (causal asof)
    grids = {}
    for c in MAJORS:
        df = pd.read_parquet(TMP / f"vpin_{c}.parquet", columns=["T", "gate"])
        gns = pd.to_datetime(df["T"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        gv = df["gate"].to_numpy(dtype=bool)
        o = np.argsort(gns)
        grids[c] = (gns[o], gv[o])
    pos = np.zeros(len(T), dtype=bool)
    for k, c in enumerate(MAJORS):
        gns, gv = grids[c]
        m = (co == k)
        p = np.searchsorted(gns, T[m], side="right") - 1
        ok = p >= 0
        vv = np.zeros(m.sum(), dtype=bool)
        vv[ok] = gv[np.clip(p[ok], 0, len(gv) - 1)]
        # rows before 2021-09-24 never gated
        vv[T[m] < pd.Timestamp("2021-09-24", tz="UTC").value] = False
        pos[m] = vv
    print(f"gated ledger rows: {int(pos.sum())}/{len(pos)} "
          f"({100*pos.mean():.2f}%)", flush=True)
    base_y, mask_y = [], []
    for y in range(5):
        sb, sm = [], []
        for p in range(4):
            m = (ph == p) & (yr == y)
            sb.append(float((w[m] * yv[m]).sum()))
            mm = m & ~pos
            sm.append(float((w[mm] * yv[mm]).sum()))
        base_y.append(float(np.mean(sb)))
        mask_y.append(float(np.mean(sm)))
    dsum = [round(mask_y[y] - base_y[y], 6) for y in range(5)]
    dsum5 = round(float(np.sum(np.array(mask_y) - np.array(base_y))), 6)
    base5 = round(float(np.sum(base_y)), 6)
    print(f"base yearly 4-phase means: {[round(v,6) for v in base_y]} sum5y={base5}", flush=True)
    print(f"masked yearly means: {[round(v,6) for v in mask_y]}", flush=True)
    print(f"dSum per year: {dsum} dSum5y={dsum5:+.6f} (gate >= +{PROMISING})", flush=True)
    assert abs(base5 - SUM_GATE) < 0.002, (base5, SUM_GATE)
    print("base reproduction OK (7.718304 +- 0.002)", flush=True)
    out = {"base_yearly": [round(v, 6) for v in base_y], "base5y": base5,
           "masked_yearly": [round(v, 6) for v in mask_y],
           "dsum_yearly": dsum, "dsum5y": dsum5,
           "promising": bool(dsum5 >= PROMISING),
           "gated_rows": int(pos.sum()), "n": int(len(pos))}
    (TMP / "replica_gate_v2.json").write_text(json.dumps(out, indent=1))
    print("PROMISING:" if out["promising"] else "NOT PROMISING", flush=True)


if __name__ == "__main__":
    main()
