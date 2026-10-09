"""oc_b7patient SECONDARY 1m recompute: patient exits on the 2021-2026 ledger.

Same VERBATIM exit logic as the PRIMARY (PLAN.md), applied to the k2placebo
D0+B1 ledger (n == 22312) with the main 1m stores (btc + majors intraday).
O/sg sampled VERBATIM build_base (4h bar opens every 240 min per phase +
pct_change rolling-360 min_periods-120 shift-1). Boosted flag = frozen B7
window from oc_cascadeboost/boost_mult_4shift.parquet (exact + ffill-causal).
Outputs tmp/patient_outcomes_4shift.npz in ledger order.

One coin at a time (OC + HL per coin, float32). Run via heavy_slot.
Heartbeat every 600 s.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2P = ROOT / "research/tournament/oc_k2placebo"
CB = ROOT / "research/tournament/oc_cascadeboost"

sys.path.insert(0, str(HERE))
from patient_rule import (  # noqa: E402
    LIVE_A,
    LIVE_B,
    MU_BASE,
    MU_V1,
    RUNGS,
    find_fill,
    outcome_extended,
    outcome_ret,
)

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
SETTLE_HOURS = (0, 8, 16)
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
HB_S = 600
KIND_CODES = {"backstop": 0, "tp": 1, "stop": 2, "time": 3, "unknown": -1}


def load_oc(sym):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path(f"data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    idx = pd.date_range(START, END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m, parts
    return idx, O, C


def load_hl(sym, idx):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path(f"data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "high", "low"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    m = m.set_index("open_time").reindex(idx)
    H = m["high"].to_numpy(dtype=np.float32)
    L = m["low"].to_numpy(dtype=np.float32)
    del m, parts
    return H, L


def load_boost():
    d = pd.read_parquet(CB / "boost_mult_4shift.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    lut, grid = {}, {}
    for s in (0, 1, 2, 3):
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        b7 = sub["mult_B7"].to_numpy(dtype=float)
        grid[s] = (t_ns, b7)
        for t, a in zip(pd.to_datetime(sub["T"], utc=True), b7):
            lut[(int(s), pd.Timestamp(t))] = float(a)
    return lut, grid


def boosted_at(shift, t, lut, grid):
    hit = lut.get((int(shift), pd.Timestamp(t)))
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
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded ledger n={n}", flush=True)
    assert n == 22312, n

    lut, grid = load_boost()
    boosted = np.array([boosted_at(int(led["phase"][i]), bt_all[i], lut, grid)
                        for i in range(n)], dtype=bool)
    print(f"boosted share={boosted.mean():.4f}", flush=True)

    yv1 = np.full(n, np.nan)
    yv2 = np.full(n, np.nan)
    kv1 = np.full(n, KIND_CODES["unknown"], dtype=np.int64)
    kv2 = np.full(n, KIND_CODES["unknown"], dtype=np.int64)
    inv = {"backstop": 0, "tp": 1, "stop": 2, "time": 3}
    n_fallback = 0
    n_ext_fallback = 0

    (HERE / "tmp").mkdir(exist_ok=True)
    for ci, sym in enumerate(MAJORS):
        idx_fill = np.where(led["coin"] == ci)[0]
        if len(idx_fill) == 0:
            continue
        print(f"loading {sym} fills={len(idx_fill)}", flush=True)
        idx, O, C = load_oc(sym)
        H, L = load_hl(sym, idx)
        n_all = len(idx)
        # per-phase bar opens/sig (VERBATIM build_base)
        opens_bar, sig_bar, t0s = {}, {}, {}
        for p in (0, 1, 2, 3):
            off = p * 60
            nb = (n_all - off) // 240
            t0p = idx[off:off + nb * 240:240]
            ob = O[off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[p], sig_bar[p], t0s[p] = ob, sg, t0p
            pos = {int(tt.value): j for j, tt in enumerate(t0p)}
            opens_bar[f"pos_{p}"] = pos
            opens_bar[f"off_{p}"] = off
        done = 0
        for i in idx_fill:
            p = int(led["phase"][i])
            T = pd.Timestamp(bt_all[i])
            if T.tzinfo is None:
                T = T.tz_localize("UTC")
            pos = opens_bar[f"pos_{p}"].get(int(T.value))
            if pos is None:
                n_fallback += 1
                continue
            o1 = float(opens_bar[p][pos])
            sg = float(sig_bar[p][pos])
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                n_fallback += 1
                continue
            k = RUNGS[int(led["rung"][i])]
            lv = o1 * (1 - k * sg)
            if not np.isfinite(lv) or lv <= 0:
                n_fallback += 1
                continue
            off = opens_bar[f"off_{p}"]
            base = off + pos * 240
            if base + 240 > n_all:
                n_fallback += 1
                continue
            has_ext = base + 480 <= n_all
            low_win = L[base + LIVE_A:base + LIVE_B + 1].astype(float)
            ib = find_fill(low_win, lv)
            if ib is None:
                n_fallback += 1
                continue
            f = LIVE_A + ib
            Ha = H[base:base + 240].astype(float)
            La = L[base:base + 240].astype(float)
            Ca = C[base:base + 240].astype(float)
            Oa = O[base:base + 240].astype(float)
            o2m = O[base + 240]
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            settle = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            is_b = bool(boosted[i])
            if is_b:
                r1, _, how1 = outcome_ret(Ha, La, Ca, Oa, f, lv, sg, MU_V1, o2, settle)
                if np.isfinite(r1):
                    yv1[i] = float(r1)
                    kv1[i] = inv[how1]
                else:
                    n_fallback += 1
            else:
                yv1[i] = float(led["y10"][i])
                kv1[i] = KIND_CODES["unknown"]
            # V2 needs base kind to decide extension
            rb, _, how_b = outcome_ret(Ha, La, Ca, Oa, f, lv, sg, MU_BASE, o2, settle)
            if is_b and how_b == "time":
                if not has_ext:
                    n_ext_fallback += 1
                    yv2[i] = float(led["y10"][i]) if np.isfinite(led["y10"][i]) else float(rb)
                    kv2[i] = inv[how_b] if np.isfinite(rb) else KIND_CODES["unknown"]
                else:
                    Hb = H[base + 240:base + 480].astype(float)
                    Lb = L[base + 240:base + 480].astype(float)
                    Cb = C[base + 240:base + 480].astype(float)
                    Ob = O[base + 240:base + 480].astype(float)
                    o3m = O[base + 480] if base + 480 < n_all else np.nan
                    o3 = float(o3m) if np.isfinite(o3m) else np.nan
                    sm = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                    se = (T + pd.Timedelta(hours=8)).hour in SETTLE_HOURS
                    re, how2 = outcome_extended(Hb, Lb, Cb, Ob, lv, sg, MU_BASE, o3, sm, se)
                    if np.isfinite(re):
                        yv2[i] = float(re)
                        kv2[i] = inv[how2]
                    else:
                        n_ext_fallback += 1
                        yv2[i] = float(led["y10"][i])
            elif is_b:
                # boosted non-timeout: V2 = base outcome (recomputed)
                if np.isfinite(rb):
                    yv2[i] = float(rb)
                    kv2[i] = inv[how_b]
                else:
                    n_fallback += 1
            else:
                yv2[i] = float(led["y10"][i])
                kv2[i] = KIND_CODES["unknown"]
            done += 1
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] {sym} {done}/{len(idx_fill)} elapsed {last_hb - t0:.0f}s", flush=True)
        del O, C, H, L, idx
        print(f"{sym}: done {done}/{len(idx_fill)} fallback={n_fallback} ext_fb={n_ext_fallback}", flush=True)

    np.savez_compressed(HERE / "tmp/patient_outcomes_4shift.npz", yv1=yv1, yv2=yv2,
                        kv1=kv1, kv2=kv2, boosted=boosted,
                        n_fallback=n_fallback, n_ext_fallback=n_ext_fallback)
    print(f"wrote tmp/patient_outcomes_4shift.npz yv1_ok={np.isfinite(yv1).sum()} "
          f"yv2_ok={np.isfinite(yv2).sum()}", flush=True)


if __name__ == "__main__":
    main()
