"""V2 2021-2026 rebuild at the depth-scaled grid (heavy CPU, perp 1m).

VERBATIM compute_placebo_dip.build_base core (same START 2020-08-01 grid, same perp
1m stores btc_intraday_20260924 + majors_intraday_20260924, same bar opens sampled at
grid offsets, same sigma pct_change rolling-360/min_periods-120/shift-1, same
TRADE_START/YEAR_END, same n_vector DETECT_K=2.5, same live 16..238 strict
trade-through, same TP legs 0.9/1.0/1.1, same kept iff y09/y10/y11 ALL finite, same
gate costs/settle/stop-first), with ONLY these frozen changes: RUNGS_V2=(2.5,3.5,4.5,
5.5), per-rung M_SL STOPS_V2=(4,5,6,7) (backstop still 8.0), w = B1 x m' with
MULTS_V2=4/(k'+s'). Kinds (mu=1.0 exit reason) recorded. Resume-safe per-coin
checkpoints in MY tmp. Via heavy_slot, one coin in RAM at a time, float32.
Heartbeat every 600 s.
Output: tmp/ledger_v2_2021.npz (phase/coin/year/bar_time/rung/w/y10/kind) +
tmp/bt_v2_2021.npy.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"

sys.path.insert(0, str(HERE))
from riskparity_rule import (  # noqa: E402
    BACKSTOP,
    RUNGS_V2,
    STOPS_V2,
    find_fill,
    outcome_mu_v2,
    parity_mults_V2,
)

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
LIVE_A, LIVE_B = 16, 238
DETECT_K = 2.5
MULTS_V2 = parity_mults_V2()
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PHASES = (0, 1, 2, 3)
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
HB_S = 600
KIND_CODES = {"backstop": 0, "tp": 1, "stop": 2, "time": 3}


def year_of(t0) -> int | None:
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def n_vector(close_others: np.ndarray, open_others: np.ndarray,
             sigma_others: np.ndarray) -> np.ndarray:
    W = close_others.shape[1]
    n = np.zeros(W, dtype=np.int64)
    for i in range(close_others.shape[0]):
        o, sg = float(open_others[i]), float(sigma_others[i])
        if not (np.isfinite(o) and np.isfinite(sg)) or o <= 0 or sg <= 0:
            continue
        thr = o * (1 - DETECT_K * sg)
        if not np.isfinite(thr):
            continue
        c = close_others[i]
        n += (np.isfinite(c) & (c <= thr)).astype(np.int64)
    return n


def load_oc(sym: str):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    del parts
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    idx = pd.date_range(START, END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m
    return idx, O, C


def load_hl(sym: str, idx):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "high", "low"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    del parts
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    m = m.set_index("open_time").reindex(idx)
    H = m["high"].to_numpy(dtype=np.float32)
    L = m["low"].to_numpy(dtype=np.float32)
    del m
    return H, L


def main() -> None:
    t0 = time.time()
    last_hb = t0
    TMP.mkdir(parents=True, exist_ok=True)
    print(f"V2 grid rungs={RUNGS_V2} stops={STOPS_V2} "
          f"mults={[round(MULTS_V2[i], 6) for i in range(4)]} backstop={BACKSTOP}",
          flush=True)
    O, C, base_idx = {}, {}, None
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)

    grids = {}
    for p in PHASES:
        off = p * 60
        nb = (n_all - off) // 240
        t0g = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in MAJORS:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb)
              if TRADE_START <= t0g[j] < YEAR_END and (off + j * 240 + 240) < n_all]
        grids[p] = dict(off=off, nb=nb, t0=t0g, opens=opens_bar, sig=sig_bar, js=js)
        print(f"shift {p}: nb={nb} traded={len(js)}", flush=True)
    del opens_bar, sig_bar

    coin_ix = {s: i for i, s in enumerate(MAJORS)}
    allF = {k: [] for k in ("phase", "coin", "year", "bar_time", "rung", "w", "y10", "kind")}
    allBT: list = []
    for sym in MAJORS:
        ck = TMP / f"ledger_v2_2021_{sym}.npz"
        if ck.exists():
            d = np.load(ck)
            for k in allF:
                allF[k].extend(d[k].tolist())
            allBT.extend(np.load(TMP / f"bt_v2_2021_{sym}.npy", allow_pickle=True).tolist())
            print(f"{sym}: cached fills={len(d['w'])}", flush=True)
            continue
        H, L = load_hl(sym, base_idx)
        La, Ha = L, H
        others = [b for b in MAJORS if b != sym]
        Oa, Ca = O[sym], C[sym]
        F = {k: [] for k in allF}
        BT: list = []
        for p in PHASES:
            g = grids[p]
            off, t0g = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            n_fill = 0
            for j in g["js"]:
                bt = t0g[j]
                o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                base = off + j * 240
                o2m = Oa[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                if yi is None:
                    continue
                low_win = La[base + LIVE_A:base + LIVE_B + 1].astype(float)
                if others:
                    cmat = np.stack([C[b][base + LIVE_A - 1:base + LIVE_B].astype(float)
                                     for b in others])
                    oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                    ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                    nvec = n_vector(cmat, oo, ss)
                else:
                    nvec = np.zeros(LIVE_B - LIVE_A + 1, dtype=np.int64)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for vi, (k, msl) in enumerate(zip(RUNGS_V2, STOPS_V2)):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = LIVE_A + ib
                    nf = int(nvec[ib])
                    r09, _, _ = outcome_mu_v2(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 0.9, o2, settle, msl)
                    r10, _, kd = outcome_mu_v2(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.0, o2, settle, msl)
                    r11, _, _ = outcome_mu_v2(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, 1.1, o2, settle, msl)
                    if not (np.isfinite(r09) and np.isfinite(r10) and np.isfinite(r11)):
                        continue
                    n_fill += 1
                    F["phase"].append(p)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(yi)
                    F["bar_time"].append(off + j * 240)
                    F["rung"].append(vi)
                    F["w"].append((1.0 / (1 + nf)) * MULTS_V2[vi])
                    F["y10"].append(float(r10))
                    F["kind"].append(KIND_CODES[kd])
                    BT.append(bt)
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha
        arr = {k: np.array(v) for k, v in F.items()}
        for k in ("phase", "coin", "year", "bar_time", "rung", "kind"):
            arr[k] = arr[k].astype(np.int64)
        for k in ("w", "y10"):
            arr[k] = arr[k].astype(np.float64)
        np.savez_compressed(ck, **arr)
        np.save(TMP / f"bt_v2_2021_{sym}.npy", np.array(BT, dtype=object))
        for k in allF:
            allF[k].extend(F[k])
        allBT.extend(BT)
        print(f"{sym}: fills={len(BT)} elapsed {(time.time() - t0) / 60:.1f}min", flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] build_v2_2021 alive {last_hb - t0:.0f}s", flush=True)
    led = {k: np.array(v) for k, v in allF.items()}
    for k in ("phase", "coin", "year", "bar_time", "rung", "kind"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    np.savez_compressed(TMP / "ledger_v2_2021.npz", **led)
    np.save(TMP / "bt_v2_2021.npy", np.array(allBT, dtype=object))
    print(f"saved V2 2021 ledger n={len(led['w'])} "
          f"per-year={[int((led['year'] == y).sum()) for y in range(5)]} "
          f"runtime {(time.time() - t0) / 60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
