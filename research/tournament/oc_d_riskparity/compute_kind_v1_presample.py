"""V1 crash risk: stop-hit share per rung group + parity-weighted vs base (pre-sample).

Kinds recomputed HERE per REF fill from the read-only spot 1m store with VERBATIM
build_ledger_presample logic at mu=1.0 (find_fill strict live 16..238; outcome_kind
stop-first backstop > tp > stop; "hit the stop" = kind in {stop, backstop}).
Levels lv = O(T)*(1-k*sg(T)) with O/sg from bars_4h_presample opens + VERBATIM
compute_sigma. Same DISCLOSED CAVEAT as oc_cboostpre (bars-open vs sampled-open;
fills never added/dropped; unknowns counted, rates over known kinds only).
Groups (frozen): shallow rungs {0,1}, mid {2}, deep {3,4}. Pooled parity-weighted
stop share uses V1 mults as weights (= actual tilted exposure). FAIL if pooled
parity-weighted stop rate exceeds base by > +1pp (b7breaker standard).
One coin's 1m slice in RAM at a time (float32). Run via heavy_slot. Heartbeat 600 s.
Output: tmp/kind_v1_presample.npz (kinds in ledger order) + tmp/stop_v1_presample.json.
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
PST = ROOT / "research/tournament/oc_presampletilt"
SPOT = ROOT / "data/raw/spot_1m_presample_20261007"
BARS = PST / "bars_4h_presample.parquet"

sys.path.insert(0, str(HERE))
from riskparity_rule import (  # noqa: E402
    LIVE_A, LIVE_B, RUNGS_V1, compute_sigma, find_fill, outcome_kind,
    parity_mults_V1,
)

MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
HB_S = 600
KIND_CODES = {"backstop": 0, "tp": 1, "stop": 2, "time": 3, "unknown": -1}
GROUPS = {"shallow": (0, 1), "mid": (2,), "deep": (3, 4)}


def main() -> None:
    t0 = time.time()
    last_hb = t0
    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    bt_all = np.load(PST / "tmp/bt_presample.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded presample ledger n={n}", flush=True)

    bars = pd.read_parquet(BARS)
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    os_lut = {}
    for sym in MAJORS4:
        for s in (0, 1, 2, 3):
            sub = bars[(bars["sym"] == sym) & (bars["shift"] == s)].sort_values("T")
            oo = sub["open"].to_numpy(dtype=float)
            sg = compute_sigma(oo)
            for t, o, g in zip(pd.to_datetime(sub["T"], utc=True), oo, sg):
                os_lut[(sym, s, pd.Timestamp(t))] = (float(o), float(g))
    del bars
    print("built O/sg lookup", flush=True)

    mult_map = parity_mults_V1()
    kinds = np.full(n, KIND_CODES["unknown"], dtype=np.int64)
    n_unknown_level = 0
    n_unknown_window = 0

    for ci, sym in enumerate(MAJORS4):
        idx_fill = np.where(led["coin"] == ci)[0]
        if len(idx_fill) == 0:
            continue
        print(f"loading 1m {sym} fills={len(idx_fill)}", flush=True)
        m = pd.read_parquet(SPOT / f"{sym}.parquet")
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.sort_values("open_time")
        t_min = pd.to_datetime([bt_all[i] for i in idx_fill], utc=True).min() - pd.Timedelta(days=2)
        t_max = pd.to_datetime([bt_all[i] for i in idx_fill], utc=True).max() + pd.Timedelta(days=2)
        m = m[(m["open_time"] >= t_min) & (m["open_time"] <= t_max)]
        full_idx = pd.date_range(m["open_time"].min().floor("min"),
                                 m["open_time"].max().ceil("min"), freq="1min")
        m = m.set_index("open_time").reindex(full_idx)
        o = m["o"].to_numpy(dtype=np.float32)
        h = m["h"].to_numpy(dtype=np.float32)
        lo = m["l"].to_numpy(dtype=np.float32)
        c = m["c"].to_numpy(dtype=np.float32)
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
        del m, o, h, lo, c
        print(f"{sym}: done elapsed {(time.time() - t0) / 60:.1f}min", flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] kind_v1_presample alive {last_hb - t0:.0f}s", flush=True)

    n_unknown = int((kinds == KIND_CODES["unknown"]).sum())
    print(f"kinds: unknown={n_unknown} (level={n_unknown_level} window={n_unknown_window})",
          flush=True)
    inv = {v: k for k, v in KIND_CODES.items()}
    print(Counter(inv[int(v)] for v in kinds), flush=True)

    (HERE / "tmp").mkdir(exist_ok=True)
    np.savez_compressed(HERE / "tmp/kind_v1_presample.npz", kind=kinds)

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    ru = led["rung"].astype(int)
    pw = np.array([mult_map[int(r)] for r in ru], dtype=float)
    stop = (kinds == KIND_CODES["stop"]) | (kinds == KIND_CODES["backstop"])
    tp = kinds == KIND_CODES["tp"]
    known = kinds != KIND_CODES["unknown"]

    out = {"config": {
        "stop": "kind in {stop, backstop} VERBATIM outcome_mu mu=1.0 base 4sg stops",
        "levels": "lv=O(T)*(1-k*sg(T)) bars_4h_presample + verbatim compute_sigma",
        "groups": {g: list(v) for g, v in GROUPS.items()},
        "unknown": int(n_unknown),
    }, "per_year": []}
    for y in range(4):
        my = (yr == y) & known
        row = {"year": LEG_ORDER[y], "n_fills": int((yr == y).sum()),
               "n_known": int(my.sum()),
               "base_stop_rate": round(float(stop[my].mean()), 4) if my.any() else None,
               "base_tp_rate": round(float(tp[my].mean()), 4) if my.any() else None}
        for g, members in GROUPS.items():
            gm = my & np.isin(ru, members)
            row[f"{g}_stop_rate"] = round(float(stop[gm].mean()), 4) if gm.any() else None
            row[f"{g}_tp_rate"] = round(float(tp[gm].mean()), 4) if gm.any() else None
            row[f"{g}_share"] = round(float(gm.sum() / my.sum()), 4) if my.any() else None
        # parity-weighted pooled (weights = V1 mults = tilted exposure)
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
    (HERE / "tmp/stop_v1_presample.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/kind_v1_presample.npz + tmp/stop_v1_presample.json", flush=True)


if __name__ == "__main__":
    main()
