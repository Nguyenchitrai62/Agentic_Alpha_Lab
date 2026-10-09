"""oc_d_poststop: pre-sample replica join + gains + placebos + stop rates (CPU-only).

Frozen (see PLAN.md): join fills to poststop_mult_presample.parquet (exact + causal
ffill, missing -> 1.0); per-year base/boosted/realised/norm/gain (4-phase means);
timing + block-42 placebos per (year, shift, coin) with 1000 perms (seeds 20261007+y /
20261008+y, y = 0..3); stop-rate table from tmp/stop_kinds_x.npz kinds.
Output: tmp/poststop_presample.json. Heartbeat every 600 s.
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

sys.path.insert(0, str(HERE))
from poststop_rule import phase_mean_sums

MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
HB_S = 600


def main() -> None:
    t0 = time.time()
    last_hb = t0
    print("[oc_d_poststop] compute_poststop_presample start", flush=True)

    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    bt_all = np.load(PST / "tmp/bt_presample.npy", allow_pickle=True)
    n = len(w)
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)

    panel = pd.read_parquet(HERE / "poststop_mult_presample.parquet")
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    lut = {}
    grid = {}
    for sym in MAJORS4:
        for s in (0, 1, 2, 3):
            sub = panel[(panel["sym"] == sym) & (panel["shift"] == s)].sort_values("T")
            t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
            grid[(s, sym)] = (t_ns, sub["mult_V1"].to_numpy(dtype=float),
                              sub["mult_V2"].to_numpy(dtype=float))
            for t, a, b in zip(pd.to_datetime(sub["T"], utc=True),
                               sub["mult_V1"], sub["mult_V2"]):
                lut[(s, sym, pd.Timestamp(t))] = (float(a), float(b))
    del panel

    def mult_at(s, sym, t, variant):
        hit = lut.get((int(s), sym, pd.Timestamp(t)))
        if hit is not None:
            return hit[0] if variant == "V1" else hit[1]
        t_ns, m1, m2 = grid[(int(s), sym)]
        q = pd.Timestamp(t)
        if q.tzinfo is None:
            q = q.tz_localize("UTC")
        pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
        if pos < 0:
            return 1.0
        return float(m1[pos] if variant == "V1" else m2[pos])

    n_exact = 0
    mult = {}
    for variant in ("V1", "V2"):
        mm = np.empty(n)
        for i in range(n):
            T = pd.Timestamp(bt_all[i])
            if T.tzinfo is None:
                T = T.tz_localize("UTC")
            key = (int(ph[i]), MAJORS4[int(co[i])], T)
            hit = lut.get(key)
            if hit is not None:
                n_exact += (1 if variant == "V1" else 0)
                mm[i] = hit[0] if variant == "V1" else hit[1]
            else:
                mm[i] = mult_at(int(ph[i]), MAJORS4[int(co[i])], T, variant)
        mult[variant] = mm
    print(f"join: n={n} exact={n_exact} (V1 count)", flush=True)

    base_y = phase_mean_sums(ph, yr, w, yv, 4)
    out = {"config": {
        "rule": "post-stop x1.25 per (coin,shift): V1 N=7d, V2 N=3d; stop/backstop tc=T+xmin verbatim mu=1.0",
        "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK, "n_perm": N_PERM,
        "block": BLOCK,
        "normalisation": "norm(y)=boosted(y)/realised_mean(y); perm norms use the ACTUAL denominator",
        "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
        "placebo_null": "mult permutation WITHIN (year, shift, coin) time-bars (1000 uniform; block-42 chronological within (year, shift, coin))"},
        "join": {"n": int(n), "exact": int(n_exact)}}

    kk = dict(np.load(HERE / "tmp/stop_kinds_x.npz"))
    kinds = kk["kind"].astype(int)
    stop = (kinds == 0) | (kinds == 2)
    tp = kinds == 1
    known = kinds != -1

    for variant in ("V1", "V2"):
        mm = mult[variant]
        boost_y = phase_mean_sums(ph, yr, w * mm, yv, 4)
        per_year = []
        for y in range(4):
            m = yr == y
            rm = float(mm[m].mean()) if m.any() else 1.0
            per_year.append({
                "year": LEG_ORDER[y], "n_fills": int(m.sum()),
                "base": round(float(base_y[y]), 6),
                "boosted": round(float(boost_y[y]), 6),
                "realised_mean": round(rm, 6),
                "norm": round(float(boost_y[y]) / rm, 6) if rm else 0.0,
                "gain": round(float(boost_y[y]) / rm - float(base_y[y]), 6) if rm else 0.0,
                "boosted_share_fills": round(float((mm[m] == 1.25).mean()), 4)
                if m.any() else 0.0})
        out[variant] = {"per_year": per_year}
        print(f"{variant}: " + str([(r['year'], r['gain']) for r in per_year]), flush=True)

    # ---- per-(year, shift, coin) bar universes for permutations ----
    # bar key per fill: index into its (y, s, c) bar array
    bar_mults = {}   # (y, s, c) -> mult array over time-bars in year y
    bar_pos = {}     # (y, s, c) -> per-fill positions
    fill_idx_by_ysc = {}
    for y in range(4):
        for s in (0, 1, 2, 3):
            for ci, sym in enumerate(MAJORS4):
                t_ns, m1, m2 = grid[(s, sym)]
                # year interval from ledger bar times present in (y): use bt range
                idx = np.where((yr == y) & (ph == s) & (co == ci))[0]
                if len(idx) == 0:
                    continue
                # bars of this (s, sym) grid with T in the year's span: derive span
                # from the fills' own T min/max extended to grid (causal ffill-safe:
                # restrict permutation universe to grid bars within [minT, maxT] of fills)
                Ts = pd.to_datetime([bt_all[i] for i in idx], utc=True)
                lo_a, hi_a = Ts.min(), Ts.max() + pd.Timedelta(hours=4)
                keep = (t_ns >= np.int64(lo_a.value)) & (t_ns < np.int64(hi_a.value))
                barm = (m1 if True else m2)  # placeholder, set per variant below
                bar_mults[(y, s, ci)] = (t_ns[keep], m1[keep], m2[keep])
                # fill positions: exact index of each fill T in kept bars; fallback ffill
                pos = np.empty(len(idx), dtype=np.int64)
                for j, i in enumerate(idx):
                    T = pd.Timestamp(bt_all[i])
                    if T.tzinfo is None:
                        T = T.tz_localize("UTC")
                    q = np.int64(T.value)
                    e = int(np.searchsorted(t_ns[keep], q, side="left"))
                    if e < int(keep.sum()) and t_ns[keep][e] == q:
                        pos[j] = e
                    else:
                        pos[j] = int(np.searchsorted(t_ns[keep], q, side="right")) - 1
                bar_pos[(y, s, ci)] = pos
                fill_idx_by_ysc[(y, s, ci)] = idx
    print("bar universes built", flush=True)

    for variant, vkey in (("V1", 1), ("V2", 2)):
        mm = mult[variant]
        timing, block = [], []
        for y in range(4):
            rng = np.random.default_rng(SEED_TIMING + y)
            actual = float(phase_mean_sums(ph, yr, w * mm, yv, 4)[y]) / float(mm[yr == y].mean())
            denom = float(mm[yr == y].mean())
            fill_w = w[yr == y]
            fill_y = yv[yr == y]
            fill_ph = ph[yr == y]
            gidx = np.where(yr == y)[0]
            # map global fill position -> (ysc key, local j)
            perms = np.empty(N_PERM)
            # precompute per-group bar mults for this variant
            grp = {}
            for key in [k for k in bar_mults if k[0] == y]:
                _, m1k, m2k = bar_mults[key]
                grp[key] = (m1k if variant == "V1" else m2k)
            for k in range(N_PERM):
                fm = np.empty(len(gidx))
                for key, idx in fill_idx_by_ysc.items():
                    if key[0] != y:
                        continue
                    pm = rng.permutation(grp[key])
                    fm[np.searchsorted(gidx, idx)] = pm[bar_pos[key]]
                s = 0.0
                for p in (0, 1, 2, 3):
                    mp = fill_ph == p
                    s += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s / 4.0) / denom
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"{variant} timing y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] compute_poststop_presample alive elapsed {last_hb - t0:.0f}s",
                      flush=True)
        for y in range(4):
            rng = np.random.default_rng(SEED_BLOCK + y)
            actual = float(phase_mean_sums(ph, yr, w * mm, yv, 4)[y]) / float(mm[yr == y].mean())
            denom = float(mm[yr == y].mean())
            fill_w = w[yr == y]
            fill_y = yv[yr == y]
            fill_ph = ph[yr == y]
            gidx = np.where(yr == y)[0]
            grp = {}
            for key in [k for k in bar_mults if k[0] == y]:
                _, m1k, m2k = bar_mults[key]
                base_m = (m1k if variant == "V1" else m2k)
                blks = [base_m[b:b + BLOCK] for b in range(0, len(base_m), BLOCK)]
                grp[key] = blks
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = np.empty(len(gidx))
                for key, idx in fill_idx_by_ysc.items():
                    if key[0] != y:
                        continue
                    blks = grp[key]
                    order = rng.permutation(len(blks))
                    seq = np.concatenate([blks[b] for b in order]) if blks else np.array([])
                    fm[np.searchsorted(gidx, idx)] = seq[bar_pos[key]]
                s = 0.0
                for p in (0, 1, 2, 3):
                    mp = fill_ph == p
                    s += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s / 4.0) / denom
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"{variant} block y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)
        out[variant]["timing_placebo"] = timing
        out[variant]["block_placebo"] = block

    # ---- stop-rate table (same kinds) ----
    stop_out = {"per_year": []}
    for y in range(4):
        my = (yr == y) & known
        row = {"year": LEG_ORDER[y], "n_fills": int((yr == y).sum()),
               "n_known": int(my.sum()),
               "base_stop_rate": round(float(stop[my].mean()), 4) if my.any() else None,
               "base_tp_rate": round(float(tp[my].mean()), 4) if my.any() else None}
        for variant in ("V1", "V2"):
            is_b = (mult[variant] == 1.25)[yr == y]
            idx_y = np.where(yr == y)[0]
            kb = known[idx_y][is_b]
            row[f"{variant}_boosted_share"] = round(float(is_b.mean()), 4)
            if kb.any():
                mb = idx_y[is_b]
                row[f"{variant}_stop_rate"] = round(float(stop[mb][kb].mean()), 4)
                row[f"{variant}_tp_rate"] = round(float(tp[mb][kb].mean()), 4)
                row[f"{variant}_stop_delta"] = round(
                    float(stop[mb][kb].mean()) - float(stop[my].mean()), 4)
            else:
                row[f"{variant}_stop_rate"] = None
                row[f"{variant}_tp_rate"] = None
                row[f"{variant}_stop_delta"] = None
        stop_out["per_year"].append(row)
    for variant in ("V1", "V2"):
        is_b = (mult[variant] == 1.25) & known
        stop_out[f"{variant}_pooled"] = {
            "boosted_share": round(float((mult[variant] == 1.25).mean()), 4),
            "base_stop_rate": round(float(stop[known].mean()), 4),
            "boosted_stop_rate": round(float(stop[is_b].mean()), 4) if is_b.any() else None,
            "stop_delta": round(float(stop[is_b].mean()) - float(stop[known].mean()), 4)
            if is_b.any() else None}
    out["stop"] = stop_out
    print(json.dumps(stop_out, indent=1), flush=True)

    (HERE / "tmp/poststop_presample.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/poststop_presample.json", flush=True)


if __name__ == "__main__":
    main()
