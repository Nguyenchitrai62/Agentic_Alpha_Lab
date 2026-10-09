"""V2 pre-sample rebuild at the depth-scaled grid (heavy CPU, spot 1m).

VERBATIM oc_presampletilt/build_ledger_presample core (same ORIGIN 2020-01-01 + s h
grid, same spot store, same compute_sigma rolling-360/min_periods-120/shift-1, same
warm-up first_bar+60d, same years/coins, same n_vector DETECT_K=2.5, same live 16..238
strict trade-through, same TP legs 0.9/1.0/1.1, same kept iff y09/y10/y11 ALL finite,
same gate costs maker 0.0002/taker 0.00055/settle FUND 0.0001, same stop-first), with
ONLY these frozen changes: RUNGS_V2=(2.5,3.5,4.5,5.5), per-rung M_SL STOPS_V2=(4,5,6,7)
(backstop still 8.0), w = B1 x m' with MULTS_V2=4/(k'+s').
Kinds (mu=1.0 leg exit reason) recorded during the rebuild. Resume-safe per-leg
checkpoints in MY tmp. Via heavy_slot, one coin's 1m slice per leg in RAM, float32.
Heartbeat every 600 s.
Output: tmp/ledger_v2_presample.npz (phase/coin/year/t_ord/rung/w/y10/kind) +
tmp/bt_v2_presample.npy.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
SPOT = ROOT / "data/raw/spot_1m_presample_20261007"

sys.path.insert(0, str(HERE))
from riskparity_rule import (  # noqa: E402
    BACKSTOP,
    RUNGS_V2,
    STOPS_V2,
    compute_sigma,
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
MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
ORIGIN = pd.Timestamp("2020-01-01", tz="UTC")
PHASES = (0, 1, 2, 3)
LEGS = {
    "Y2017": (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
    "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
    "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
    "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC")),
}
LEG_IDX = {"Y2017": 0, "Y2018": 1, "Y2019": 2, "Y2020p": 3}
EPOCH = pd.Timestamp("2017-08-01", tz="UTC")
SETTLE_HOURS = (0, 8, 16)
HB_S = 600
KIND_CODES = {"backstop": 0, "tp": 1, "stop": 2, "time": 3}


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


def load_1m_spot(sym: str, start, end):
    m = pd.read_parquet(SPOT / f"{sym}.parquet")
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m[(m["open_time"] >= start) & (m["open_time"] <= end)]
    idx = pd.date_range(start, end, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    out = {k: m[k].to_numpy(dtype=np.float32) for k in ("o", "h", "l", "c")}
    del m
    return idx, out


def run_leg(leg: str):
    S, E = LEGS[leg]
    LS = S - pd.Timedelta(days=100)
    LE = E + pd.Timedelta(days=1)
    man = json.loads((SPOT / "manifest.json").read_text())["symbols"]
    store_warmup = {s: pd.Timestamp(man[s]["first_bar"]) + pd.Timedelta(days=60)
                    for s in MAJORS4}
    idx = None
    D: dict = {}
    warmup_from: dict = {}
    for sym in MAJORS4:
        ii, d = load_1m_spot(sym, LS, LE)
        if idx is None:
            idx = ii
        dd = {"open": d["o"], "high": d["h"], "low": d["l"], "close": d["c"]}
        present = np.flatnonzero(np.isfinite(dd["close"]))
        if len(present) == 0:
            print(f"{leg} {sym}: no data; absent", flush=True)
            continue
        warmup_from[sym] = store_warmup[sym]
        D[sym] = dd
        print(f"{leg} {sym}: n={len(ii)} warm={warmup_from[sym]}", flush=True)
    coins = list(D.keys())
    grids = {}
    for s in PHASES:
        base = ORIGIN + pd.Timedelta(hours=s)
        j0 = int(np.floor(((idx[0] - pd.Timedelta(hours=4)) - base).total_seconds() / 14400))
        j1 = int(np.ceil(((idx[-1] + pd.Timedelta(hours=4)) - base).total_seconds() / 14400))
        bts = base + pd.to_timedelta(np.arange(j0, j1 + 1) * 4, unit="h")
        bts = bts[(bts >= idx[0]) & (bts + pd.Timedelta(hours=4) <= idx[-1])]
        offs = ((bts - idx[0]).total_seconds() // 60).astype(int)
        ob, sg = {}, {}
        for sym in coins:
            oo = D[sym]["open"][offs].astype(float)
            ob[sym] = oo
            sg[sym] = compute_sigma(oo)
            mask = np.asarray(bts < warmup_from[sym])
            ob[sym] = np.where(mask, np.nan, ob[sym])
            sg[sym] = np.where(mask, np.nan, sg[sym])
        grids[s] = (bts, ob, sg)
    F = {k: [] for k in ("phase", "coin", "year", "t_ord", "rung", "w", "y10", "kind")}
    bt_list = []
    coin_ix = {s: i for i, s in enumerate(MAJORS4)}
    for s in PHASES:
        bts, ob, sg = grids[s]
        js = [j for j, T in enumerate(bts) if S <= T < E]
        print(f"{leg} s{s}: bars={len(js)}", flush=True)
        for j in js:
            T = bts[j]
            off = int((T - idx[0]).total_seconds() // 60)
            if off + 240 >= len(idx):
                continue
            settle = (T + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
            for sym in coins:
                o1, sgv = float(ob[sym][j]), float(sg[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sgv)) or o1 <= 0 or sgv <= 0:
                    continue
                low_win = D[sym]["low"][off + LIVE_A:off + LIVE_B + 1].astype(float)
                others = [b for b in coins if b != sym]
                if others:
                    cmat = np.stack([D[b]["close"][off + LIVE_A - 1:off + LIVE_B].astype(float)
                                     for b in others])
                    oo = np.array([float(ob[b][j]) for b in others])
                    ss = np.array([float(sg[b][j]) for b in others])
                    nvec = n_vector(cmat, oo, ss)
                else:
                    nvec = np.zeros(LIVE_B - LIVE_A + 1, dtype=np.int64)
                Ha = D[sym]["high"][off:off + 240].astype(float)
                La = D[sym]["low"][off:off + 240].astype(float)
                Ca = D[sym]["close"][off:off + 240].astype(float)
                Oa = D[sym]["open"][off:off + 240].astype(float)
                o2m = D[sym]["open"][off + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                for vi, (k, msl) in enumerate(zip(RUNGS_V2, STOPS_V2)):
                    lv = o1 * (1 - k * sgv)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = LIVE_A + ib
                    nf = int(nvec[ib])
                    r09, _, _ = outcome_mu_v2(Ha, La, Ca, Oa, f, lv, sgv, 0.9, o2, settle, msl)
                    r10, _, kd = outcome_mu_v2(Ha, La, Ca, Oa, f, lv, sgv, 1.0, o2, settle, msl)
                    r11, _, _ = outcome_mu_v2(Ha, La, Ca, Oa, f, lv, sgv, 1.1, o2, settle, msl)
                    if not (np.isfinite(r09) and np.isfinite(r10) and np.isfinite(r11)):
                        continue
                    F["phase"].append(s)
                    F["coin"].append(coin_ix[sym])
                    F["year"].append(LEG_IDX[leg])
                    F["t_ord"].append(int((T - EPOCH).total_seconds() // 60))
                    F["rung"].append(vi)
                    F["w"].append((1.0 / (1 + nf)) * MULTS_V2[vi])
                    F["y10"].append(float(r10))
                    F["kind"].append(KIND_CODES[kd])
                    bt_list.append(T)
    del D, grids
    return F, bt_list


def main() -> None:
    t0 = time.time()
    last_hb = t0
    TMP.mkdir(parents=True, exist_ok=True)
    print(f"V2 grid rungs={RUNGS_V2} stops={STOPS_V2} "
          f"mults={[round(MULTS_V2[i], 6) for i in range(4)]} backstop={BACKSTOP}",
          flush=True)
    allF = {k: [] for k in ("phase", "coin", "year", "t_ord", "rung", "w", "y10", "kind")}
    allBT: list = []
    for leg in ("Y2017", "Y2018", "Y2019", "Y2020p"):
        ck = TMP / f"ledger_v2_presample_{leg}.npz"
        if ck.exists():
            d = np.load(ck)
            for k in allF:
                allF[k].extend(d[k].tolist())
            allBT.extend(np.load(TMP / f"bt_v2_presample_{leg}.npy", allow_pickle=True).tolist())
            print(f"{leg}: cached fills={len(d['w'])}", flush=True)
            continue
        F, bt = run_leg(leg)
        arr = {k: np.array(v) for k, v in F.items()}
        for k in ("phase", "coin", "year", "t_ord", "rung", "kind"):
            arr[k] = arr[k].astype(np.int64)
        for k in ("w", "y10"):
            arr[k] = arr[k].astype(np.float64)
        np.savez_compressed(ck, **arr)
        np.save(TMP / f"bt_v2_presample_{leg}.npy", np.array(bt, dtype=object))
        for k in allF:
            allF[k].extend(F[k])
        allBT.extend(bt)
        print(f"{leg}: fills={len(bt)} elapsed {(time.time() - t0) / 60:.1f}min", flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] build_v2_presample alive {last_hb - t0:.0f}s", flush=True)
    led = {k: np.array(v) for k, v in allF.items()}
    for k in ("phase", "coin", "year", "t_ord", "rung", "kind"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    np.savez_compressed(TMP / "ledger_v2_presample.npz", **led)
    np.save(TMP / "bt_v2_presample.npy", np.array(allBT, dtype=object))
    meta = {"n_fills": int(len(led["w"])),
            "per_leg": {leg: int((led["year"] == i).sum()) for leg, i in LEG_IDX.items()},
            "rungs_v2": list(RUNGS_V2), "stops_v2": list(STOPS_V2),
            "mults_v2": [round(MULTS_V2[i], 6) for i in range(4)]}
    (TMP / "ledger_v2_presample_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"saved V2 ledger n={len(led['w'])} {meta['per_leg']} "
          f"runtime {(time.time() - t0) / 60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
