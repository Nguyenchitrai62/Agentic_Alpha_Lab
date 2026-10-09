"""oc_b7btceth SECONDARY: BTC/ETH-only B7 boost on the 2021-2026 ledger.

CONTAMINATED info-only leg (idea derived from cascade results covering these
years): never a selection basis. Method = same coin-mask join as the PRIMARY
(V1 BTC+ETH {0,1} / V2 BTC-only {0} on k2placebo coins
BTC/ETH/SOL/BNB/XRP = 0/1/2/3/4; B7 window read-only from
oc_cascadeboost/boost_mult_4shift.parquet; mult 1.5 iff B7-boosted AND coin in
mask else 1.0). Ledger REUSED read-only from oc_k2placebo/tmp (ledger.npz +
bt_all.npy; reproduction gate n == 22312, base sum5y == 7.718304 +- 0.002).

Per year y (5 years 2021-2026, anchors 2021-09-24..2025-09-24): base(y),
boosted_V(y), norm_V(y), gain_vs_base, gain_vs_B7 + per-coin dSum +
1000-perm timing/block placebos (seeds 20261007+y / 20261008+y, y = 0..4;
null = underlying B7 time-bar permutation WITHIN (year, shift) + deterministic
coin mask). Report dSum5y vs base and vs B7 + sum-half counts. CPU-only.
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
K2P = ROOT / "research/tournament/oc_k2placebo"
CB = ROOT / "research/tournament/oc_cascadeboost"

sys.path.insert(0, str(HERE))
from b7btceth_rule import BOOST, MASK_V1, MASK_V2  # noqa: E402 (frozen masks)

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
COINS = ("BTC", "ETH", "SOL", "BNB", "XRP")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
BASE_GATE = 7.718304
N_GATE = 22312
PHASES = (0, 1, 2, 3)
SHIFTS = (0, 1, 2, 3)
VARIANTS = ("V1", "V2")
MASKS = {"V1": frozenset(MASK_V1), "V2": frozenset(MASK_V2)}
HB_S = 600


def phase_mean_sums(ph, yr, wv, yv):
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def load_b7():
    d = pd.read_parquet(CB / "boost_mult_4shift.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {"mult_B7": sub["mult_B7"].to_numpy(dtype=float),
                        "t_ns": t_ns,
                        "T": pd.to_datetime(sub["T"], utc=True).tolist()}
        for t, a in zip(per_shift[s]["T"], per_shift[s]["mult_B7"]):
            exact[(int(s), pd.Timestamp(t))] = float(a)
    return exact, per_shift


def b7_at(shift, t, exact, per_shift):
    key = (int(shift), pd.Timestamp(t))
    hit = exact.get(key)
    if hit is not None:
        return hit
    t_ns = per_shift[int(shift)]["t_ns"]
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return 1.0
    return float(per_shift[int(shift)]["mult_B7"][pos])


def main() -> None:
    t0 = time.time()
    last_hb = t0
    assert BOOST == 1.5
    assert set(MASK_V1) == {0, 1} and set(MASK_V2) == {0}
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"
    assert set(np.unique(led["coin"])) <= {0, 1, 2, 3, 4}, np.unique(led["coin"])

    exact_b, per_shift_b = load_b7()

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    base_y = phase_mean_sums(ph, yr, w, yv)
    got5 = float(sum(base_y))
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]} sum5y={got5:.6f}",
          flush=True)
    assert abs(got5 - BASE_GATE) <= 0.002, f"base {got5} != {BASE_GATE}"

    b7 = np.array([b7_at(int(ph[i]), bt_all[i], exact_b, per_shift_b)
                   for i in range(n)], dtype=float)
    assert set(np.round(b7, 6)) <= {1.0, 1.5}
    boost_b7_y = phase_mean_sums(ph, yr, w * b7, yv)
    rm_b7 = np.array([float(b7[yr == y].mean()) for y in range(5)])
    norm_b7 = np.array([boost_b7_y[y] / rm_b7[y] for y in range(5)])

    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only",
            "boost": "oc_cascadeboost/boost_mult_4shift.parquet mult_B7 read-only + deterministic coin mask (no sizing-model change)",
            "masks": {"V1": "BTC+ETH only {0,1}", "V2": "BTC only {0}"},
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "rule": "mult_V 1.5 iff B7-boosted AND coin in mask else 1.0",
            "normalisation": "norm(y)=boosted(y)/realised_mean(y); perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "placebo_null": "UNDERLYING B7 time-bar permutation WITHIN (year, shift), deterministic coin mask per fill",
            "contamination": "SECONDARY contaminated leg (idea derived from cascade results covering these years): info only, never a selection basis",
        },
        "reproduction": {"base_sum5y_gate": BASE_GATE,
                         "base_sums": [round(v, 6) for v in base_y],
                         "base_sum5y": round(got5, 6), "n_fills": int(n),
                         "b7_norms": [round(v, 6) for v in norm_b7]},
    }

    uni = {}
    for y in range(5):
        lo = ANCH[y]
        hi = ANCH[y + 1] if y < 4 else YEAR_END
        for s in SHIFTS:
            t_ns = per_shift_b[s]["t_ns"]
            col = per_shift_b[s]["mult_B7"]
            lo_ns, hi_ns = np.int64(lo.value), np.int64(hi.value)
            m = (t_ns >= lo_ns) & (t_ns < hi_ns)
            uni[(y, s)] = col[m].astype(float)
    pos_of = {}
    for (y, s), arr in uni.items():
        t_ns = per_shift_b[s]["t_ns"]
        lo = ANCH[y]
        hi = ANCH[y + 1] if y < 4 else YEAR_END
        m = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
        idx = {int(tt): j for j, tt in enumerate(t_ns[m])}
        pos_of[(y, s)] = idx
    fill_pos = np.full(n, -1, dtype=np.int64)
    for i in range(n):
        q = pd.Timestamp(bt_all[i])
        if q.tzinfo is None:
            q = q.tz_localize("UTC")
        fill_pos[i] = pos_of[(int(yr[i]), int(ph[i]))].get(int(q.value), -1)
    assert (fill_pos >= 0).all(), f"{(fill_pos < 0).sum()} fills w/o time-bar"

    for variant in VARIANTS:
        mask = MASKS[variant]
        mult = np.array([1.5 if b7[i] == 1.5 and int(co[i]) in mask else 1.0
                         for i in range(n)], dtype=float)
        vals = sorted(set(np.round(mult, 6)))
        assert set(vals) <= {1.0, 1.5}, vals
        print(f"{variant}: boosted_share={float((mult == 1.5).mean()):.4f}", flush=True)

        boost_y = phase_mean_sums(ph, yr, w * mult, yv)
        dsum_base = float(sum(boost_y) - sum(base_y))
        dsum_b7 = float(sum(
            (boost_y[y] / float(mult[yr == y].mean())
             - float(norm_b7[y])) for y in range(5)))
        sum_ge_base = sum(1 for y in range(5)
                          if boost_y[y] / float(mult[yr == y].mean())
                          >= base_y[y] - 1e-12)
        years = []
        for y in range(5):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            norm = float(boost_y[y]) / rm if rm else 0.0
            years.append({"year": ANCH[y].date().isoformat(),
                          "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "boosted": round(float(boost_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(norm, 6),
                          "gain_vs_base": round(norm - float(base_y[y]), 6),
                          "gain_vs_B7": round(norm - float(norm_b7[y]), 6),
                          "boosted_share_fills": round(float((mult[m] == 1.5).mean()), 4)
                          if m.any() else None})
        for r in years:
            print(f"  {r['year']} base={r['base']} norm={r['norm']} "
                  f"gBase={r['gain_vs_base']} gB7={r['gain_vs_B7']}", flush=True)

        per_coin = []
        for c in range(5):
            mc_all = co == c
            rows = []
            for y in range(5):
                ss_b, ss_v = [], []
                for p in PHASES:
                    m = (ph == p) & (yr == y) & mc_all
                    ss_b.append(float((w[m] * yv[m]).sum()) if m.any() else 0.0)
                    ss_v.append(float((w[m] * mult[m] * yv[m]).sum()) if m.any() else 0.0)
                bb, vv = float(np.mean(ss_b)), float(np.mean(ss_v))
                mm = mult[(yr == y) & mc_all]
                rm_c = float(mm.mean()) if len(mm) else 1.0
                nn = vv / rm_c if rm_c else 0.0
                rows.append({"year": ANCH[y].date().isoformat(), "n": int(((yr == y) & mc_all).sum()),
                             "base": round(bb, 6), "norm": round(nn, 6),
                             "gain_vs_base": round(nn - bb, 6)})
            per_coin.append({"coin": COINS[c], "per_year": rows,
                             "sum5_norm": round(float(sum(r["norm"] for r in rows)), 6)})

        timing = []
        for y in range(5):
            rng = np.random.default_rng(SEED_TIMING + y)
            my = (yr == y)
            fm_actual = mult[my]
            actual = float(boost_y[y]) / float(fm_actual.mean())
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            fill_p = fill_pos[my]
            fill_c = co[my]
            slices = {}
            for s in SHIFTS:
                sm = fill_ph == s
                slices[s] = (np.where(sm)[0], uni[(y, s)])
            denom_y = float(fm_actual.mean())
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                pb7 = np.empty(my.sum())
                for s in SHIFTS:
                    loc, arr = slices[s]
                    pm = rng.permutation(arr)
                    upos = fill_p[loc]
                    pb7[loc] = pm[upos]
                fm = np.array([1.5 if pb7[j] == 1.5 and int(fill_c[j]) in mask else 1.0
                               for j in range(my.sum())], dtype=float)
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom_y
                if time.time() - last_hb > HB_S:
                    print(f"[hb] timing {variant} y={y} perm {k}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": ANCH[y].date().isoformat(),
                           "actual_norm": round(actual, 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} y={y} pct={pct:.2f}", flush=True)

        block = []
        for y in range(5):
            rng = np.random.default_rng(SEED_BLOCK + y)
            my = (yr == y)
            fm_actual = mult[my]
            actual = float(boost_y[y]) / float(fm_actual.mean())
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            fill_p = fill_pos[my]
            fill_c = co[my]
            denom_y = float(fm_actual.mean())
            blk_of = {}
            for s in SHIFTS:
                arr = uni[(y, s)]
                blks = [arr[b:b + BLOCK] for b in range(0, len(arr), BLOCK)]
                blk_of[s] = blks
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                pb7 = np.empty(my.sum())
                for s in SHIFTS:
                    loc = np.where(fill_ph == s)[0]
                    blks = blk_of[s]
                    order = rng.permutation(len(blks))
                    seq = np.concatenate([blks[b] for b in order]) if blks else np.array([])
                    upos = fill_p[loc]
                    pb7[loc] = seq[upos]
                fm = np.array([1.5 if pb7[j] == 1.5 and int(fill_c[j]) in mask else 1.0
                               for j in range(my.sum())], dtype=float)
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom_y
                if time.time() - last_hb > HB_S:
                    print(f"[hb] block {variant} y={y} perm {k}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": ANCH[y].date().isoformat(),
                          "actual_norm": round(actual, 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} y={y} pct={pct:.2f}", flush=True)

        dev4_v = float(sum(r["norm"] for r in years[:4]))
        dev4_b7 = float(sum(float(v) for v in norm_b7[:4]))
        res[variant] = {"per_year": years, "per_coin": per_coin,
                        "timing_placebo": timing, "block_placebo": block,
                        "dSum5y_vs_base": round(dsum_base, 6),
                        "dSum5y_vs_B7": round(dsum_b7, 6),
                        "sum_half_vs_base": int(sum_ge_base),
                        "dev4_sum_V": round(dev4_v, 6),
                        "dev4_sum_B7": round(dev4_b7, 6),
                        "dev4_gain_vs_B7": round(dev4_v - dev4_b7, 6)}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/replica_btceth.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/replica_btceth.json", flush=True)


if __name__ == "__main__":
    main()
