"""oc_b7patient PRIMARY 1m recompute: patient exits on the pre-sample ledger.

For each of the 9731 ledger fills: rebuild fill + base/mu1.5/extended outcomes
from the read-only spot 1m store with VERBATIM ledger logic (see PLAN.md).
Boosted flag = frozen B7 window from oc_cboostpre/boost_mult_presample.parquet
(exact match on the shift grid, ffill-causal fallback; missing -> unboosted).
Outputs tmp/patient_outcomes.npz in ledger order + per-coin checkpoints.

One coin's 1m slice in RAM at a time (float32). Run via heavy_slot.
Heartbeat every 600 s. Progress print every 10 min (per-coin + periodic).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PST = ROOT / "research/tournament/oc_presampletilt"
CBP = ROOT / "research/tournament/oc_cboostpre"
SPOT = ROOT / "data/raw/spot_1m_presample_20261007"
BARS = PST / "bars_4h_presample.parquet"

sys.path.insert(0, str(HERE))
from patient_rule import (  # noqa: E402
    LIVE_A,
    LIVE_B,
    MU_BASE,
    MU_V1,
    RUNGS,
    compute_sigma,
    find_fill,
    outcome_extended,
    outcome_ret,
)

MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
SETTLE_HOURS = (0, 8, 16)
HB_S = 600
KIND_CODES = {"backstop": 0, "tp": 1, "stop": 2, "time": 3, "unknown": -1}


def load_boost_flags():
    d = pd.read_parquet(CBP / "boost_mult_presample.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    lut = {}
    grid = {}
    for s in (0, 1, 2, 3):
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        b7 = sub["mult_B7"].to_numpy(dtype=float)
        grid[s] = (t_ns, b7)
        for t, a in zip(pd.to_datetime(sub["T"], utc=True), b7):
            lut[(int(s), pd.Timestamp(t))] = float(a)
    return lut, grid


def boosted_at(shift, t, lut, grid):
    key = (int(shift), pd.Timestamp(t))
    hit = lut.get(key)
    if hit is not None:
        return hit == 1.5
    t_ns, b7 = grid[int(shift)]
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return False
    return float(b7[pos]) == 1.5


def main() -> None:
    t0 = time.time()
    last_hb = t0
    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(PST / "tmp/bt_presample.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded presample ledger n={n}", flush=True)
    assert n == 9731, n

    lut, grid = load_boost_flags()
    boosted = np.array([boosted_at(int(led["phase"][i]), bt_all[i], lut, grid)
                        for i in range(n)], dtype=bool)
    print(f"boosted share (B7 window)={boosted.mean():.4f} n_boosted={int(boosted.sum())}",
          flush=True)

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

    yb = np.full(n, np.nan)
    yv1 = np.full(n, np.nan)
    yv2 = np.full(n, np.nan)
    kb = np.full(n, KIND_CODES["unknown"], dtype=np.int64)
    kv1 = np.full(n, KIND_CODES["unknown"], dtype=np.int64)
    kv2 = np.full(n, KIND_CODES["unknown"], dtype=np.int64)
    inv = {"backstop": 0, "tp": 1, "stop": 2, "time": 3}
    n_unknown_level = 0
    n_unknown_window = 0
    n_unknown_ext = 0
    n_fill_mismatch = 0

    (HERE / "tmp").mkdir(exist_ok=True)
    for ci, sym in enumerate(MAJORS4):
        ck = HERE / "tmp" / f"outcomes_{sym}.npz"
        idx_fill = np.where(led["coin"] == ci)[0]
        if len(idx_fill) == 0:
            continue
        print(f"loading 1m {sym} fills={len(idx_fill)}", flush=True)
        m = pd.read_parquet(SPOT / f"{sym}.parquet")
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.sort_values("open_time")
        t_min = pd.to_datetime([bt_all[i] for i in idx_fill], utc=True).min() - pd.Timedelta(days=2)
        t_max = pd.to_datetime([bt_all[i] for i in idx_fill], utc=True).max() + pd.Timedelta(days=9)
        m = m[(m["open_time"] >= t_min) & (m["open_time"] <= t_max)]
        full_idx = pd.date_range(m["open_time"].min().floor("min"),
                                 m["open_time"].max().ceil("min"), freq="1min")
        m = m.set_index("open_time").reindex(full_idx)
        o = m["o"].to_numpy(dtype=np.float32)
        h = m["h"].to_numpy(dtype=np.float32)
        lo = m["l"].to_numpy(dtype=np.float32)
        c = m["c"].to_numpy(dtype=np.float32)
        base = full_idx[0]
        done = 0
        for i in idx_fill:
            T = pd.Timestamp(bt_all[i])
            if T.tzinfo is None:
                T = T.tz_localize("UTC")
            s = int(led["phase"][i])
            o1, sg = os_lut.get((sym, s, T), (np.nan, np.nan))
            k = RUNGS[int(led["rung"][i])]
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                n_unknown_level += 1
                continue
            lv = o1 * (1 - k * sg)
            if not np.isfinite(lv) or lv <= 0:
                n_unknown_level += 1
                continue
            off = int((T - base).total_seconds() // 60)
            if off < 0 or off + 480 > len(full_idx):
                # need 480 for V2 extension window; if only 240 available,
                # still do base+V1 below with a shorter guard
                if off < 0 or off + 240 > len(full_idx):
                    n_unknown_window += 1
                    continue
                has_ext = False
            else:
                has_ext = True
            low_win = lo[off + LIVE_A:off + LIVE_B + 1].astype(float)
            if not np.isfinite(low_win).any():
                n_unknown_window += 1
                continue
            ib = find_fill(low_win, lv)
            if ib is None:
                n_fill_mismatch += 1
                continue
            f = LIVE_A + ib
            Ha = h[off:off + 240].astype(float)
            La = lo[off:off + 240].astype(float)
            Ca = c[off:off + 240].astype(float)
            Oa = o[off:off + 240].astype(float)
            o2m = o[off + 240] if off + 240 < len(o) else np.nan
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            settle = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            is_b = bool(boosted[i])
            # base (mu=1.0)
            rb, _, how_b = outcome_ret(Ha, La, Ca, Oa, f, lv, sg, MU_BASE, o2, settle)
            if not np.isfinite(rb):
                n_unknown_window += 1
                continue
            yb[i] = float(rb)
            kb[i] = inv[how_b]
            # V1: mu=1.5 iff boosted
            if is_b:
                r1, _, how1 = outcome_ret(Ha, La, Ca, Oa, f, lv, sg, MU_V1, o2, settle)
                if np.isfinite(r1):
                    yv1[i] = float(r1)
                    kv1[i] = inv[how1]
                else:
                    yv1[i] = float(rb)
                    kv1[i] = inv[how_b]
            else:
                yv1[i] = float(rb)
                kv1[i] = inv[how_b]
            # V2: extend iff boosted AND base timeout AND extension data
            if is_b and how_b == "time":
                if not has_ext:
                    n_unknown_ext += 1
                    yv2[i] = float(rb)
                    kv2[i] = inv[how_b]
                else:
                    Hb = h[off + 240:off + 480].astype(float)
                    Lb = lo[off + 240:off + 480].astype(float)
                    Cb = c[off + 240:off + 480].astype(float)
                    Ob = o[off + 240:off + 480].astype(float)
                    o3m = o[off + 480] if off + 480 < len(o) else np.nan
                    o3 = float(o3m) if np.isfinite(o3m) else np.nan
                    settle_mid = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                    settle_end = (T + pd.Timedelta(hours=8)).hour in SETTLE_HOURS
                    if not np.isfinite(Hb).any() or not np.isfinite(o3):
                        n_unknown_ext += 1
                        yv2[i] = float(rb)
                        kv2[i] = inv[how_b]
                    else:
                        re, how2 = outcome_extended(Hb, Lb, Cb, Ob, lv, sg, MU_BASE,
                                                    o3, settle_mid, settle_end)
                        if np.isfinite(re):
                            yv2[i] = float(re)
                            kv2[i] = inv[how2]
                        else:
                            n_unknown_ext += 1
                            yv2[i] = float(rb)
                            kv2[i] = inv[how_b]
            else:
                yv2[i] = float(rb)
                kv2[i] = inv[how_b]
            done += 1
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] {sym} {done}/{len(idx_fill)} "
                      f"elapsed {last_hb - t0:.0f}s", flush=True)
        del m, o, h, lo, c
        np.savez_compressed(ck, idx=idx_fill, yb=yb[idx_fill], yv1=yv1[idx_fill],
                            yv2=yv2[idx_fill], kb=kb[idx_fill], kv1=kv1[idx_fill],
                            kv2=kv2[idx_fill])
        print(f"{sym}: done {done}/{len(idx_fill)} elapsed {(time.time() - t0) / 60:.1f}min "
              f"unknown_level={n_unknown_level} window={n_unknown_window} "
              f"fill_mismatch={n_fill_mismatch} ext_fallback={n_unknown_ext}", flush=True)

    n_ok = int(np.isfinite(yb).sum())
    print(f"recomputed base: ok={n_ok}/{n} unknown_level={n_unknown_level} "
          f"window={n_unknown_window} fill_mismatch={n_fill_mismatch} "
          f"ext_fallback={n_unknown_ext}", flush=True)
    # cross-check recomputed base vs ledger y10 (same join caveat as cboostpre: ~15 unknowns)
    y10 = led["w"].astype(float) * 0 + dict(np.load(PST / "tmp/ledger_presample.npz"))["y10"].astype(float)
    mk = np.isfinite(yb)
    if mk.any():
        diff = np.abs(yb[mk] - y10[mk])
        print(f"base cross-check vs ledger y10: median_abs={np.median(diff):.2e} "
              f"p99={np.quantile(diff, 0.99):.2e} exact_match={(diff < 1e-12).mean():.4f}",
              flush=True)
    np.savez_compressed(HERE / "tmp/patient_outcomes.npz", yb=yb, yv1=yv1, yv2=yv2,
                        kb=kb, kv1=kv1, kv2=kv2, boosted=boosted,
                        n_unknown_level=n_unknown_level,
                        n_unknown_window=n_unknown_window,
                        n_fill_mismatch=n_fill_mismatch,
                        n_unknown_ext=n_unknown_ext)
    print("wrote tmp/patient_outcomes.npz", flush=True)


if __name__ == "__main__":
    main()
