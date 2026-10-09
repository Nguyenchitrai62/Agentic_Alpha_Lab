"""V1 crash risk 2021-2026: stop-hit share per rung group + parity-weighted vs base.

Kinds recomputed HERE per k2placebo fill from the read-only perp 1m stores with
VERBATIM compute_placebo_dip logic at mu=1.0 (find_fill strict live 16..238;
stop-first backstop > tp > stop; "hit the stop" = kind in {stop, backstop}).
Levels lv = O(T)*(1-k*sg(T)) with O/sg from oc_kronoshidden/bars_4h_4shift opens +
the VERBATIM build_base sigma (pct_change rolling-360/min_periods-120/shift-1).
DISCLOSED CAVEAT: the ledger's O/sg were sampled as 1m-open-at-bar on its own grid
while this recompute uses the frozen bars open series; fills are never added/dropped
(kinds only); unknowns counted, rates over known kinds only.
Groups (frozen): shallow {0,1}, mid {2}, deep {3,4}. Pooled parity-weighted stop share
uses V1 mults as weights. One coin's 1m slice in RAM at a time (float32).
Run via heavy_slot. Heartbeat 600 s.
Output: tmp/kind_v1_2021.npz + tmp/stop_v1_2021.json.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2 = ROOT / "research/tournament/oc_k2placebo"
KH = ROOT / "research/tournament/oc_kronoshidden"

sys.path.insert(0, str(HERE))
from riskparity_rule import (  # noqa: E402
    LIVE_A, LIVE_B, RUNGS_V1, find_fill, outcome_kind, parity_mults_V1,
)

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
HB_S = 600
KIND_CODES = {"backstop": 0, "tp": 1, "stop": 2, "time": 3, "unknown": -1}
GROUPS = {"shallow": (0, 1), "mid": (2,), "deep": (3, 4)}


def load_1m(sym: str, t_min, t_max):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path(f"data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"])
             for f in files]
    m = pd.concat(parts, ignore_index=True)
    del parts
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= t_min) & (m["open_time"] <= t_max)]
    full_idx = pd.date_range(m["open_time"].min().floor("min"),
                             m["open_time"].max().ceil("min"), freq="1min")
    m = m.set_index("open_time").reindex(full_idx)
    out = {k: m[k].to_numpy(dtype=np.float32) for k in ("open", "high", "low", "close")}
    return full_idx, out


def main() -> None:
    t0 = time.time()
    last_hb = t0
    led = dict(np.load(K2 / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    bt_all = np.load(K2 / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded k2placebo ledger n={n}", flush=True)

    bars = pd.read_parquet(KH / "bars_4h_4shift.parquet",
                           columns=["sym", "shift", "T", "open"])
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    os_lut = {}
    for sym in MAJORS:
        for s in (0, 1, 2, 3):
            sub = bars[(bars["sym"] == sym) & (bars["shift"] == s)].sort_values("T")
            oo = sub["open"].to_numpy(dtype=float)
            sg = pd.Series(oo).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            for t, o, g in zip(pd.to_datetime(sub["T"], utc=True), oo, sg):
                os_lut[(sym, s, pd.Timestamp(t))] = (float(o), float(g))
    del bars
    print("built O/sg lookup", flush=True)

    mult_map = parity_mults_V1()
    kinds = np.full(n, KIND_CODES["unknown"], dtype=np.int64)
    n_unknown_level = 0
    n_unknown_window = 0

    for ci, sym in enumerate(MAJORS):
        idx_fill = np.where(led["coin"] == ci)[0]
        if len(idx_fill) == 0:
            continue
        t_lo = pd.to_datetime([bt_all[i] for i in idx_fill], utc=True).min() - pd.Timedelta(days=2)
        t_hi = pd.to_datetime([bt_all[i] for i in idx_fill], utc=True).max() + pd.Timedelta(days=2)
        print(f"loading 1m {sym} fills={len(idx_fill)}", flush=True)
        full_idx, d = load_1m(sym, max(t_lo, START), min(t_hi, END))
        o, h, lo, c = d["open"], d["high"], d["low"], d["close"]
        del d
        base = full_idx[0]
        for i in idx_fill:
            T = pd.Timestamp(bt_all[i])
            if T.tzinfo is None:
                T = T.tz_localize("UTC")
            s = int(led["phase"][i])
            o1, sg = os_lut.get((sym, s, T), (np.nan, np.nan))
            k = RUNGS_V1[int(led["rung"][i])]
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                n_unknown_level += 1
                continue
            lv = o1 * (1 - k * sg)
            if not np.isfinite(lv) or lv <= 0:
                n_unknown_level += 1
                continue
            off = int((T - base).total_seconds() // 60)
            if off < 0 or off + 240 > len(full_idx):
                n_unknown_window += 1
                continue
            low_win = lo[off + LIVE_A:off + LIVE_B + 1].astype(float)
            if not np.isfinite(low_win).any():
                n_unknown_window += 1
                continue
            ib = find_fill(low_win, lv)
            if ib is None:
                n_unknown_window += 1
                continue
            f = LIVE_A + ib
            Ha = h[off:off + 240].astype(float)
            La = lo[off:off + 240].astype(float)
            Ca = c[off:off + 240].astype(float)
            Oa = o[off:off + 240].astype(float)
            kinds[i] = KIND_CODES[outcome_kind(Ha, La, Ca, Oa, f, lv, sg)]
        del o, h, lo, c
        print(f"{sym}: done elapsed {(time.time() - t0) / 60:.1f}min", flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] kind_v1_2021 alive {last_hb - t0:.0f}s", flush=True)

    n_unknown = int((kinds == KIND_CODES["unknown"]).sum())
    print(f"kinds: unknown={n_unknown} (level={n_unknown_level} window={n_unknown_window})",
          flush=True)
    inv = {v: k for k, v in KIND_CODES.items()}
    print(Counter(inv[int(v)] for v in kinds), flush=True)

    (HERE / "tmp").mkdir(exist_ok=True)
    np.savez_compressed(HERE / "tmp/kind_v1_2021.npz", kind=kinds)

    yr = led["year"].astype(int)
    ru = led["rung"].astype(int)
    pw = np.array([mult_map[int(r)] for r in ru], dtype=float)
    stop = (kinds == KIND_CODES["stop"]) | (kinds == KIND_CODES["backstop"])
    tp = kinds == KIND_CODES["tp"]
    known = kinds != KIND_CODES["unknown"]

    out = {"config": {
        "stop": "kind in {stop, backstop} VERBATIM build_base mu=1.0 base 4sg stops",
        "levels": "lv=O(T)*(1-k*sg(T)) bars_4h_4shift + verbatim build_base sigma",
        "groups": {g: list(v) for g, v in GROUPS.items()},
        "unknown": int(n_unknown),
    }, "per_year": []}
    for y in range(5):
        my = (yr == y) & known
        row = {"year": ANCH5[y], "n_fills": int((yr == y).sum()),
               "n_known": int(my.sum()),
               "base_stop_rate": round(float(stop[my].mean()), 4) if my.any() else None,
               "base_tp_rate": round(float(tp[my].mean()), 4) if my.any() else None}
        for g, members in GROUPS.items():
            gm = my & np.isin(ru, members)
            row[f"{g}_stop_rate"] = round(float(stop[gm].mean()), 4) if gm.any() else None
            row[f"{g}_tp_rate"] = round(float(tp[gm].mean()), 4) if gm.any() else None
        wsum = float(pw[my].sum())
        pstop = float((pw[my] * stop[my]).sum() / wsum) if wsum else float("nan")
        row["parity_stop_rate"] = round(pstop, 4)
        row["parity_stop_delta"] = round(pstop - float(stop[my].mean()), 4) if my.any() else None
        out["per_year"].append(row)
        print(row, flush=True)
    wsum_all = float(pw[known].sum())
    pstop_all = float((pw[known] * stop[known]).sum() / wsum_all)
    out["pooled"] = {
        "base_stop_rate": round(float(stop[known].mean()), 4),
        "parity_stop_rate": round(pstop_all, 4),
        "stop_delta": round(pstop_all - float(stop[known].mean()), 4),
        "fail": bool(pstop_all - float(stop[known].mean()) > 0.01)}
    print(out["pooled"], flush=True)
    (HERE / "tmp/stop_v1_2021.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/kind_v1_2021.npz + tmp/stop_v1_2021.json", flush=True)


if __name__ == "__main__":
    main()
