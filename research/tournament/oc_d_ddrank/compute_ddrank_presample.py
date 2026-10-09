"""DD-rank pre-sample replica + placebos (CPU-only).

Reuses oc_presampletilt ledger read-only (reproduction gate n==9731,
per-leg 909/2986/3115/2721, base sums == 2.313362/2.678870/0.577643/0.297538).
Joins per-fill (sym, shift=phase, T) DD-rank mults (V1/V2) with causal ffill
fallback; missing -> 1.0. Per-year 4-phase-mean base/tilted/realised/norm/gain.
Placebos (1000 perms): rank-shuffle within (year,shift,T) bars (primary null,
seed 20261007+y), timing uniform across fills within year (seed 20261009+y),
block-42 per (sym,shift) within year (seed 20261008+y). Percentile =
100*(1+#{perm<=actual})/1001, signif iff >=95. Heartbeat every 600 s.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PST = ROOT / "research/tournament/oc_presampletilt"

LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
LEG_BOUNDS = {
    "Y2017": (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
    "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
    "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
    "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC")),
}
SYMS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")  # ledger coin 0..3
SEED_RANK = 20261007
SEED_BLOCK = 20261008
SEED_TIMING = 20261009
N_PERM = 1000
BLOCK = 42
N_GATE = 9731
PER_LEG_GATE = (909, 2986, 3115, 2721)
BASE_GATE = (2.313362, 2.678870, 0.577643, 0.297538)
PHASES = (0, 1, 2, 3)
VARIANTS = ("V1", "V2")
HB_S = 600


def phase_mean_sums(ph, yr, wv, yv, n_years=4):
    out = []
    for y in range(n_years):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


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
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"
    for y, g in enumerate(PER_LEG_GATE):
        got = int((led["year"] == y).sum())
        assert got == g, f"leg {LEG_ORDER[y]} n {got} != {g}"

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    base_y = phase_mean_sums(ph, yr, w, yv)
    print(f"base 4-phase-mean sums={[round(v,6) for v in base_y]}", flush=True)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6, f"base {LEG_ORDER[y]} fail"

    # mult panel LUT
    panel = pd.read_parquet(HERE / "ddrank_mult_presample.parquet")
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    exact = {}
    per_sym_shift = {}
    for (sym, s), sub in panel.groupby(["sym", "shift"]):
        sub = sub.sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_sym_shift[(str(sym), int(s))] = (
            t_ns, sub["mult_V1"].to_numpy(float), sub["mult_V2"].to_numpy(float))
        for t, a, e in zip(sub["T"], sub["mult_V1"], sub["mult_V2"]):
            exact[(str(sym), int(s), pd.Timestamp(t))] = (float(a), float(e))

    def mult_at(sym, shift, t, variant):
        hit = exact.get((sym, int(shift), pd.Timestamp(t)))
        if hit is not None:
            return hit[0] if variant == "V1" else hit[1]
        key = (sym, int(shift))
        if key not in per_sym_shift:
            return 1.0
        t_ns, a, e = per_sym_shift[key]
        q = pd.Timestamp(t)
        if q.tzinfo is None:
            q = q.tz_localize("UTC")
        pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
        if pos < 0:
            return 1.0
        arr = a if variant == "V1" else e
        return float(arr[pos])

    res = {
        "config": {
            "ledger": "oc_presampletilt/tmp/ledger_presample.npz read-only (D0+B1, SPOT)",
            "mult": "ddrank_mult_presample.parquet (frozen 180/60 DD rank; V1 1.25/0.75/1.0, V2 top-2 1.25)",
            "seed_rank": SEED_RANK, "seed_block": SEED_BLOCK,
            "seed_timing": SEED_TIMING, "n_perm": N_PERM, "block": BLOCK,
            "rule": "norm(y)=tilted(y)/realised_mean(y); gain=norm-base; perm norms use ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; signif iff >=95",
            "nulls": "rank-shuffle within (year,shift,T) bars (primary); timing uniform across fills (diagnostic); block-42 per (sym,shift) (diagnostic)",
        },
        "reproduction": {"per_leg_gate": list(PER_LEG_GATE),
                         "base_sums": [round(v, 6) for v in base_y],
                         "n_fills": int(n)},
    }
    # fill sym names
    fill_sym = np.array([SYMS4[int(c)] for c in co])

    for variant in VARIANTS:
        mult = np.array([mult_at(fill_sym[i], int(ph[i]), bt_all[i], variant)
                         for i in range(n)], dtype=float)
        nmiss = 0
        print(f"{variant}: boosted={(mult==1.25).mean():.4f} "
              f"deweighted={(mult==0.75).mean():.4f} "
              f"mid={(mult==1.0).mean():.4f}", flush=True)
        tilt_y = phase_mean_sums(ph, yr, w * mult, yv)
        years = []
        for y in range(4):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            norm = float(tilt_y[y]) / rm if rm else 0.0
            years.append({"year": LEG_ORDER[y], "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "tilted": round(float(tilt_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(norm, 6),
                          "gain": round(norm - float(base_y[y]), 6),
                          "boosted_share": round(float((mult[m] == 1.25).mean()), 4),
                          "deweighted_share": round(float((mult[m] == 0.75).mean()), 4)})
            print(f"  {LEG_ORDER[y]} base={base_y[y]:.6f} tilt={tilt_y[y]:.6f} "
                  f"rm={rm:.6f} norm={norm:.6f} gain={norm-base_y[y]:+.6f}", flush=True)

        # ---- rank-shuffle null: permute mults within each (y, s, T) bar ----
        rank = []
        for y in range(4):
            rng = np.random.default_rng(SEED_RANK + y)
            my = np.where(yr == y)[0]
            denom = float(mult[my].mean())
            actual = float(tilt_y[y]) / denom
            # group fill positions by (phase, T)
            groups: dict = {}
            for j in my:
                key = (int(ph[j]), pd.Timestamp(bt_all[j]).value)
                groups.setdefault(key, []).append(j)
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            idx_of = {j: k for k, j in enumerate(my)}
            perms = np.empty(N_PERM)
            m0 = mult[my]
            for k in range(N_PERM):
                fm = np.empty(len(my))
                for members in groups.values():
                    vals = mult[members]
                    fm[[idx_of[j] for j in members]] = rng.permutation(vals)
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom
                if time.time() - last_hb > HB_S:
                    print(f"[hb] rank {variant} y={y} perm {k}/{N_PERM}", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            rank.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                         "p5": round(float(np.quantile(perms, 0.05)), 6),
                         "p50": round(float(np.quantile(perms, 0.50)), 6),
                         "p95": round(float(np.quantile(perms, 0.95)), 6),
                         "percentile": round(float(pct), 2)})
            print(f"rank {variant} y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

        # ---- timing null: uniform permutation of fill mults within year ----
        timing = []
        for y in range(4):
            rng = np.random.default_rng(SEED_TIMING + y)
            my = yr == y
            denom = float(mult[my].mean())
            actual = float(tilt_y[y]) / denom
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            m0 = mult[my]
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = rng.permutation(m0)
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

        # ---- block null: 42-bar blocks per (sym, shift) within year ----
        block = []
        for y in range(4):
            rng = np.random.default_rng(SEED_BLOCK + y)
            lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
            lo_ns, hi_ns = np.int64(lo.value), np.int64(hi.value)
            blk_of = {}
            for (sym, s), (t_ns, a, e) in per_sym_shift.items():
                arr = (a if variant == "V1" else e)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                seq = arr[m].astype(float)
                blk_of[(sym, s)] = [seq[b:b + BLOCK]
                                    for b in range(0, len(seq), BLOCK)]
            my = np.where(yr == y)[0]
            denom = float(mult[my].mean())
            actual = float(tilt_y[y]) / denom
            # map each fill to position in its (sym,shift) year-sequence
            pos = np.empty(len(my), dtype=np.int64)
            seq_len = {}
            for (sym, s), blks in blk_of.items():
                seq_len[(sym, s)] = sum(len(b) for b in blks)
            # position = index of T in year sequence
            for k, j in enumerate(my):
                key = (fill_sym[j], int(ph[j]))
                t_ns, _, _ = per_sym_shift[key]
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                grid = t_ns[m]
                q = pd.Timestamp(bt_all[j])
                if q.tzinfo is None:
                    q = q.tz_localize("UTC")
                pos[k] = int(np.searchsorted(grid, np.int64(q.value), side="right")) - 1
            assert (pos >= 0).all(), f"block map miss y={y}"
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = np.empty(len(my))
                perm_seq = {}
                for key, blks in blk_of.items():
                    order = rng.permutation(len(blks)) if blks else np.array([], dtype=int)
                    perm_seq[key] = np.concatenate([blks[b] for b in order]) if blks else np.array([])
                for t, j in enumerate(my):
                    fm[t] = perm_seq[(fill_sym[j], int(ph[j]))][pos[t]]
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom
                if time.time() - last_hb > HB_S:
                    print(f"[hb] block {variant} y={y} perm {k}/{N_PERM}", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

        res[variant] = {"per_year": years, "rank_placebo": rank,
                        "timing_placebo": timing, "block_placebo": block}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/ddrank_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/ddrank_presample.json", flush=True)


if __name__ == "__main__":
    main()
