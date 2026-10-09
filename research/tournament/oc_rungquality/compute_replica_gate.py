"""oc_rungquality step 2: filtered replica sums + dSum gate + fill-level placebos.

Reuses the D0+B1 ledger read-only from oc_k2placebo/tmp (ledger.npz + bt_all.npy;
reproduction gate n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002).
Skip sets per anchor come from tmp/quality_stats.json (step 1); a fill is skipped
iff its (coin_ix, rung_ix) cell is in the anchor year's skip set (F1 / F2).

Per year y: base(y), filt(y) (4-phase means, w*y10 units). Gate: sum-half
(filt >= base in >= 4/5 years) PLUS dSum5y >= +0.273. Supporting (not binding)
placebos per variant/year: 1000 uniform + 1000 block-42 fill-level permutations
of the skip indicators at the fixed skipped-fill count (seeds 20261007+y /
20261008+y); percentile = 100*(1+#{perm_sum >= actual})/1001, >= 95 significant.

CPU-only numpy. Writes tmp/replica_rungquality.json + results.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2P = ROOT / "research/tournament/oc_k2placebo"

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
DEPTHS = (2.5, 3.0, 3.5, 4.0, 5.0)
PHASES = (0, 1, 2, 3)
VARIANTS = ("F1", "F2")
SEED_UNIFORM = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
BASE_GATE = 7.718304
N_GATE = 22312
DSUM_GATE = 0.273

COIN_IX = {s: i for i, s in enumerate(MAJORS)}
RUNG_IX = {k: i for i, k in enumerate(DEPTHS)}


def phase_mean_sums(ph, yr, wv, yv):
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def run_variant(variant, skip_cells, ph, yr, co, ru, w, yv, bt_all, n):
    """skip_cells[y] = set of (coin_ix, rung_ix) skipped in year y."""
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if (int(co[i]), int(ru[i])) in skip_cells[int(yr[i])]:
            keep[i] = False
    skip_ind = (~keep).astype(np.int64)

    base_y = phase_mean_sums(ph, yr, w, yv)
    filt_y = phase_mean_sums(ph, yr, w * keep, yv)
    got5 = float(sum(base_y))
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]} sum5y={got5:.6f}",
          flush=True)
    assert abs(got5 - BASE_GATE) <= 0.002, f"base {got5} != {BASE_GATE}"

    years = []
    for y in range(5):
        m = yr == y
        years.append({"year": ANCH5[y], "n_fills": int(m.sum()),
                      "n_skipped": int(skip_ind[m].sum()),
                      "base": round(float(base_y[y]), 6),
                      variant.lower(): round(float(filt_y[y]), 6)})
        r = years[-1]
        print(f"  {r['year']} n={r['n_fills']} skipped={r['n_skipped']} "
              f"base={r['base']} {variant.lower()}={r[variant.lower()]}", flush=True)

    placebo = []
    for y in range(5):
        m = np.where(yr == y)[0]
        wy = w[m]
        yy = yv[m]
        ind = skip_ind[m]
        k = int(ind.sum())
        actual = float((wy[ind == 0] * yy[ind == 0]).sum())
        # 4-phase-mean actual for percentile comparability (same construction as base_y)
        act_pm = 0.0
        phy = ph[m]
        for p in PHASES:
            mp = phy == p
            act_pm += float((wy[mp & (ind == 0)] * yy[mp & (ind == 0)]).sum())
        act_pm /= 4.0
        uni, blo = np.empty(N_PERM), np.empty(N_PERM)
        rng_u = np.random.default_rng(SEED_UNIFORM + y)
        for t in range(N_PERM):
            pi = rng_u.permutation(len(m))[:k] if k else np.empty(0, dtype=int)
            sel = np.ones(len(m), dtype=bool)
            sel[pi] = False
            s = 0.0
            for p in PHASES:
                mp = phy == p
                s += float((wy[mp & sel] * yy[mp & sel]).sum())
            uni[t] = s / 4.0
        # block: fills of year y sorted by (coin, phase, bar_time); skip indicators
        # chunked into consecutive 42-fill blocks per (coin, phase) group and the
        # block order permuted within each group (seed SEED_BLOCK + y).
        tns = pd.to_datetime(pd.Series(list(bt_all[m]))).values.astype(
            "datetime64[ns]").astype(np.int64)
        order = np.lexsort((tns, phy, co[m]))
        L = len(m)
        groups: dict[tuple[int, int], list[int]] = {}
        for j in range(L):
            idx = int(order[j])
            groups.setdefault((int(co[m][idx]), int(phy[idx])), []).append(j)
        group_blocks: dict[tuple[int, int], list[list[int]]] = {}
        for g, poslist in groups.items():
            group_blocks[g] = [poslist[b:b + BLOCK] for b in range(0, len(poslist), BLOCK)]
        sind = ind[order]  # skip indicators in sorted order
        rng_b = np.random.default_rng(SEED_BLOCK + y)
        for t in range(N_PERM):
            new_sind = np.empty(L, dtype=np.int64)
            for g, blks in group_blocks.items():
                vecs = [sind[b] for b in blks]
                porder = rng_b.permutation(len(blks))
                flat = np.concatenate([vecs[b] for b in porder]) if vecs else np.empty(0)
                slots = np.concatenate([np.asarray(b) for b in blks]) \
                    if blks else np.empty(0, dtype=int)
                new_sind[slots] = flat
            new_ind = np.empty(L, dtype=np.int64)
            new_ind[order] = new_sind
            s = 0.0
            for p in PHASES:
                mp = phy == p
                kept = new_ind == 0
                s += float((wy[mp & kept] * yy[mp & kept]).sum())
            blo[t] = s / 4.0
        pct_u = 100.0 * (1 + int((uni >= act_pm).sum())) / (N_PERM + 1)
        pct_b = 100.0 * (1 + int((blo >= act_pm).sum())) / (N_PERM + 1)
        placebo.append({"year": ANCH5[y], "k_skipped": k,
                        "actual": round(float(act_pm), 6),
                        "uniform_p5": round(float(np.quantile(uni, 0.05)), 6),
                        "uniform_p95": round(float(np.quantile(uni, 0.95)), 6),
                        "uniform_pct": round(float(pct_u), 2),
                        "block_p5": round(float(np.quantile(blo, 0.05)), 6),
                        "block_p95": round(float(np.quantile(blo, 0.95)), 6),
                        "block_pct": round(float(pct_b), 2)})
        q = placebo[-1]
        print(f"  placebo {variant} {q['year']}: k={k} actual={q['actual']} "
              f"uni_p95={q['uniform_p95']} uni_pct={q['uniform_pct']} "
              f"blk_p95={q['block_p95']} blk_pct={q['block_pct']}", flush=True)

    dsum = float(sum(filt_y) - sum(base_y))
    sum_ge = sum(1 for y in range(5) if filt_y[y] >= base_y[y] - 1e-12)
    return years, placebo, dsum, sum_ge, base_y, filt_y


def main() -> None:
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"

    qstats = json.loads((HERE / "tmp/quality_stats.json").read_text())["anchors"]
    skip_cells: dict[str, list[set]] = {}
    for variant in VARIANTS:
        key = variant.lower()
        per_year = []
        for y, a in enumerate(ANCH5):
            cells = set()
            for sym, depth in qstats[a][key]:
                cells.add((COIN_IX[str(sym)], RUNG_IX[float(depth)]))
            per_year.append(cells)
            print(f"{variant} {a}: {len(cells)} cells skipped", flush=True)
        skip_cells[variant] = per_year

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    ru = led["rung"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    res: dict = {"config": {
        "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only (identical build_base)",
        "quality": "tmp/quality_stats.json (oc_kpi FIFO pairs, T in [A-97d,A-7d), exit<A-7d)",
        "rule": "skip fills whose (coin_ix,rung_ix) cell is in the anchor-year skip set; "
                "F1 stop_rate>p80, F2 F1 + fill_rate<p20 (strict; ties keep; min_n=10)",
        "seed_uniform": SEED_UNIFORM, "seed_block": SEED_BLOCK, "n_perm": N_PERM,
        "block": BLOCK,
        "percentile": "100*(1+#{perm_sum>=actual})/1001 on RAW 4-phase-mean sums; >=95 significant",
        "gate": "sum-half (filt>=base in >=4/5y) PLUS dSum5y>=+0.273; replica DD-half not scored "
                "from this ledger (no daily path) — binding DD check is the 4-phase engine",
    }, "reproduction": {"base_sum5y_gate": BASE_GATE, "n_fills": int(n)}}
    for variant in VARIANTS:
        years, placebo, dsum, sum_ge, base_y, filt_y = run_variant(
            variant, skip_cells[variant], ph, yr, co, ru, w, yv, bt_all, n)
        res[variant] = {"per_year": years, "placebo": placebo,
                        "dSum5y": round(dsum, 6),
                        "sum_half_years_ge": int(sum_ge),
                        "gate_sum_half": bool(sum_ge >= 4),
                        "gate_dsum": bool(dsum >= DSUM_GATE),
                        "gate_pass": bool(sum_ge >= 4 and dsum >= DSUM_GATE)}
        print(f"{variant}: dSum5y={dsum:.6f} sum_half={sum_ge}/5 "
              f"gate_pass={res[variant]['gate_pass']}", flush=True)
    (HERE / "tmp/replica_rungquality.json").write_text(json.dumps(res, indent=1))
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/replica_rungquality.json + results.json", flush=True)


if __name__ == "__main__":
    main()
