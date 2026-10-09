"""oc_d_ddrank crash risk: stop-hit share of boosted/de-weighted fills vs base.

Ledger stores no exit reason; kinds recomputed per fill from read-only spot 1m
with VERBATIM build_ledger_presample logic at mu=1.0 (find_fill strict live
16..238; outcome_kind stop-first backstop > tp > stop; stop = {stop, backstop}).
Levels lv=O(T)*(1-k*sg(T)) with O/sg from bars_4h_presample + verbatim
compute_sigma. See PLAN caveat (bars-open vs sampled-open; fills never added/
dropped; unknown counted, rates over known only). One coin's 1m slice in RAM
at a time (float32). Run via heavy_slot. Heartbeat 600 s.
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
PST = ROOT / "research/tournament/oc_presampletilt"
SPOT = ROOT / "data/raw/spot_1m_presample_20261007"
BARS = PST / "bars_4h_presample.parquet"

sys.path.insert(0, str(HERE))
from ddrank_rule import LIVE_A, LIVE_B, RUNGS, compute_sigma, find_fill, outcome_kind  # noqa: E402

MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
HB_S = 600
KIND_CODES = {"backstop": 0, "tp": 1, "stop": 2, "time": 3, "unknown": -1}


def load_dd_lut():
    d = pd.read_parquet(HERE / "ddrank_mult_presample.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    lut = {}
    grid = {}
    for (sym, s), sub in d.groupby(["sym", "shift"]):
        sub = sub.sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        grid[(str(sym), int(s))] = (t_ns, sub["mult_V1"].to_numpy(float),
                                    sub["mult_V2"].to_numpy(float))
        for t, a, e in zip(sub["T"], sub["mult_V1"], sub["mult_V2"]):
            lut[(str(sym), int(s), pd.Timestamp(t))] = (float(a), float(e))
    return lut, grid


def mult_at(sym, shift, t, lut, grid, variant):
    hit = lut.get((sym, int(shift), pd.Timestamp(t)))
    if hit is not None:
        return hit[0] if variant == "V1" else hit[1]
    key = (sym, int(shift))
    if key not in grid:
        return 1.0
    t_ns, a, e = grid[key]
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return 1.0
    return float((a if variant == "V1" else e)[pos])


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
    lut, grid = load_dd_lut()
    sym_of = np.array([MAJORS4[int(c)] for c in led["coin"]])

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
            k = RUNGS[int(led["rung"][i])]
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
        print(f"{sym}: done elapsed {(time.time()-t0)/60:.1f}min", flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] compute_stop alive elapsed {last_hb-t0:.0f}s", flush=True)

    n_unknown = int((kinds == KIND_CODES["unknown"]).sum())
    print(f"kinds unknown={n_unknown} (level={n_unknown_level} window={n_unknown_window})", flush=True)
    (HERE / "tmp").mkdir(exist_ok=True)
    np.savez_compressed(HERE / "tmp/stop_kinds.npz", kind=kinds)

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    stop = (kinds == KIND_CODES["stop"]) | (kinds == KIND_CODES["backstop"])
    tp = kinds == KIND_CODES["tp"]
    known = kinds != KIND_CODES["unknown"]
    out = {"config": {
        "stop": "kind in {stop, backstop} verbatim outcome_mu mu=1.0 (close5 4sg + 8sg backstop + TP + timeout; stop-first)",
        "levels": "lv=O(T)*(1-k*sg(T)) bars opens + verbatim compute_sigma; see PLAN caveat",
        "unknown": int(n_unknown)}, "per_year": []}
    for y in range(4):
        my = (yr == y) & known
        row = {"year": LEG_ORDER[y], "n_fills": int((yr == y).sum()),
               "n_known": int(my.sum()),
               "base_stop_rate": round(float(stop[my].mean()), 4) if my.any() else None,
               "base_tp_rate": round(float(tp[my].mean()), 4) if my.any() else None}
        idx_y = np.where(yr == y)[0]
        for variant in ("V1", "V2"):
            mv = np.array([mult_at(sym_of[i], int(ph[i]), bt_all[i], lut, grid, variant)
                           for i in idx_y], dtype=float)
            for grp, val in (("boosted", 1.25), ("deweighted", 0.75)):
                if variant == "V2" and grp == "deweighted":
                    continue
                is_g = mv == val
                row[f"{variant}_{grp}_share"] = round(float(is_g.mean()), 4)
                if is_g.any() and known[idx_y][is_g].any():
                    mb = idx_y[is_g]
                    sel = known[mb]
                    row[f"{variant}_{grp}_stop_rate"] = round(float(stop[mb][sel].mean()), 4)
                    row[f"{variant}_{grp}_tp_rate"] = round(float(tp[mb][sel].mean()), 4)
                    row[f"{variant}_{grp}_stop_delta"] = round(
                        float(stop[mb][sel].mean()) - float(stop[my].mean()), 4)
                else:
                    row[f"{variant}_{grp}_stop_rate"] = None
                    row[f"{variant}_{grp}_tp_rate"] = None
                    row[f"{variant}_{grp}_stop_delta"] = None
        out["per_year"].append(row)
        print(row, flush=True)
    for variant in ("V1", "V2"):
        mv_all = np.array([mult_at(sym_of[i], int(ph[i]), bt_all[i], lut, grid, variant)
                           for i in range(n)], dtype=float)
        is_b = (mv_all == 1.25) & known
        d = {"boosted_share": round(float((mv_all == 1.25).mean()), 4),
             "base_stop_rate": round(float(stop[known].mean()), 4),
             "boosted_stop_rate": round(float(stop[is_b].mean()), 4) if is_b.any() else None,
             "stop_delta": round(float(stop[is_b].mean()) - float(stop[known].mean()), 4)
             if is_b.any() else None}
        if variant == "V1":
            is_d = (mv_all == 0.75) & known
            d.update({"deweighted_share": round(float((mv_all == 0.75).mean()), 4),
                      "deweighted_stop_rate": round(float(stop[is_d].mean()), 4) if is_d.any() else None,
                      "deweighted_delta": round(float(stop[is_d].mean()) - float(stop[known].mean()), 4)
                      if is_d.any() else None})
        out[f"{variant}_pooled"] = d
        print(variant, d, flush=True)
    (HERE / "tmp/stop_presample.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/stop_kinds.npz + tmp/stop_presample.json", flush=True)


if __name__ == "__main__":
    main()
