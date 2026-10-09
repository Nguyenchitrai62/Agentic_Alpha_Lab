"""oc_timesfm scoring: dev validation + dev4 table + last-year ONCE (all four rows).

Stage dev (tmp/runs_dev.pkl): REF must reproduce v421_result G2 years 0..3
(R and DD) EXACTLY, else STOP; K2 must reproduce oc_kronoshidden REPORT dev
R/DD EXACTLY, else STOP. Then dev4 table + robust pick (T3 vs K2 vs T3K2,
informational) on dev4 only.
Stage last (tmp/runs_last.pkl, full window [DEV0, Y1)): determinism check
(dev segments equal stage-1); all four rows scored ONCE; REF Y4 must equal
v421 G2 Y4 to the digit; full-path DD via v388.mix.
Correlation (CPU-only, no engine): Spearman(risk_T3, Kronos -low1) pooled +
per-year on the shift-0 harness overlap AND the full decision-bar universe;
Pearson as a side row -> tmp/corr_t3.json.
CPU-only.
"""
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
KH = ROOT / "research/tournament/oc_kronoshidden"

ROWS = ["REF", "T3", "K2", "T3K2"]
EXP_REF_DEV = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27)]
EXP_K2_DEV = [(2.469, 11.78), (3.478, 16.20), (6.679, 15.69), (10.653, 8.54)]
EXP_REF_Y4 = (4.648, 12.90)
EXP_K2_Y4 = (4.801, 12.10)
EXP_REF_FULLDD = 16.82
EXP_K2_FULLDD = 16.09
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def full_dd(v388, runs, v):
    g1 = pd.Timestamp("2025-09-24 12:00", tz="UTC")
    e, mn = v388.mix(runs, v, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    return round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)


def spear(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return float("nan")
    return float(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman"))


def pear(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return float("nan")
    return float(pd.Series(x[m]).corr(pd.Series(y[m]), method="pearson"))


def compute_corr():
    """Spearman(risk_T3=-f_q10, Kronos -low1): harness shift-0 overlap + full universe."""
    t = pd.read_parquet(HERE / "timesfm_features_4shift.parquet")
    k = pd.read_parquet(KH / "kronos_features_4shift.parquet",
                        columns=["sym", "shift", "T", "low1"])
    t["T"] = pd.to_datetime(t["T"], utc=True)
    k["T"] = pd.to_datetime(k["T"], utc=True)
    out = {}
    # (a) shift-0 harness overlap (majors rows both present)
    sys.path.insert(0, str(ROOT / "research/tournament"))
    import harness  # noqa: E402
    d = harness.load()
    f0 = t[t["shift"] == 0][["sym", "T", "f_q10"]]
    k0 = k[k["shift"] == 0][["sym", "T", "low1"]]
    m = d[d["sym"].isin(harness.MAJORS)].merge(f0, on=["sym", "T"], how="inner")
    m = m.merge(k0, on=["sym", "T"], how="inner")
    rt = -m["f_q10"].to_numpy(dtype=float)
    rk = -m["low1"].to_numpy(dtype=float)
    per_y = {}
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC")
        a1 = a0 + pd.Timedelta(days=365)
        mm = (m["T"] >= a0) & (m["T"] < a1)
        per_y[a] = dict(n=int(mm.sum()), spearman=round(spear(rt[mm], rk[mm]), 4),
                        pearson=round(pear(rt[mm], rk[mm]), 4))
    out["harness_shift0_overlap"] = dict(
        n=int(len(m)), pooled_spearman=round(spear(rt, rk), 4),
        pooled_pearson=round(pear(rt, rk), 4), per_year=per_y)
    # (b) full decision-bar universe (all shifts, all syms)
    j = t.merge(k, on=["sym", "shift", "T"], how="inner")
    rt = -j["f_q10"].to_numpy(dtype=float)
    rk = -j["low1"].to_numpy(dtype=float)
    per_y = {}
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC")
        a1 = a0 + pd.Timedelta(days=365) if y < 4 else pd.Timestamp("2026-09-24", tz="UTC")
        mm = ((j["T"] >= a0) & (j["T"] < a1)).to_numpy()
        per_y[a] = dict(n=int(mm.sum()), spearman=round(spear(rt[mm], rk[mm]), 4),
                        pearson=round(pear(rt[mm], rk[mm]), 4))
    out["full_universe"] = dict(
        n=int(len(j)), pooled_spearman=round(spear(rt, rk), 4),
        pooled_pearson=round(pear(rt, rk), 4), per_year=per_y)
    (HERE / "tmp/corr_t3.json").write_text(json.dumps(out, indent=1))
    print("corr pooled harness_shift0 spearman:",
          out["harness_shift0_overlap"]["pooled_spearman"], flush=True)
    print("corr pooled full_universe spearman:",
          out["full_universe"]["pooled_spearman"], flush=True)
    print("saved tmp/corr_t3.json", flush=True)
    return out


def main():
    v388 = _load("v388_analyze_t3", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_analyze_t3", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    dev = pickle.loads((HERE / "tmp/runs_dev.pkl").read_bytes())
    assert all(set(dev[s].keys()) == set(ROWS) for s in range(4)), \
        {s: sorted(dev[s]) for s in range(4)}

    # ---- reproduction gates: REF vs v421 G2, K2 vs oc_kronoshidden ----
    for v, exp in (("REF", EXP_REF_DEV), ("K2", EXP_K2_DEV)):
        runs = {s: {v: dev[s][v]["run"]} for s in range(4)}
        got = [rm.year_reset(runs, v, y) for y in range(4)]
        for y in range(4):
            assert (got[y]["R"], got[y]["DD"]) == (exp[y][0], exp[y][1]), \
                (v, y, (got[y]["R"], got[y]["DD"]), exp[y])
        print(f"{v} reproduces expected dev years 0..3 EXACTLY: "
              f"{[(g['R'], g['DD']) for g in got]}", flush=True)

    table = {}
    for v in ROWS:
        runs = {s: {v: dev[s][v]["run"]} for s in range(4)}
        yrs = [rm.year_reset(runs, v, y) for y in range(4)]
        Rs = [y["R"] for y in yrs]
        DDs = [y["DD"] for y in yrs]
        geo = round(100 * (np.prod([1 + r / 100 for r in Rs]) ** (1 / 4) - 1), 3)
        fdd = full_dd(v388, runs, v)
        wins = []
        for y in range(4):
            nb = sum(dev[s][v]["wins"][y]["nb"] for s in range(4))
            wb = sum(dev[s][v]["wins"][y]["wb"] for s in range(4))
            nr = sum(dev[s][v]["wins"][y]["nr"] for s in range(4))
            wr = sum(dev[s][v]["wins"][y]["wr"] for s in range(4))
            wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                             book_win=round(wb / nb, 4) if nb else None,
                             rung_win=round(wr / nr, 4) if nr else None,
                             all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
        t = dict(years_R=Rs, years_DD=DDs, Rdev4=geo, Wdev4=round(min(Rs), 3),
                 DDdev4=round(max(DDs), 2), fullDDdev=fdd,
                 DDmax=round(max(max(DDs), fdd), 2),
                 losing=sum(r < 0 for r in Rs), wins=wins)
        table[v] = t
        print(f"{v}: Rdev4={geo} W={t['Wdev4']} DDmax_year={t['DDdev4']} fullDD={fdd} "
              f"losing={t['losing']}", flush=True)
        print(f"   years R={Rs} DD={DDs}", flush=True)
        print(f"   all_win={[w['all_win'] for w in wins]} fills_rung={[w['nr'] for w in wins]} "
              f"book={[w['nb'] for w in wins]}", flush=True)

    cands = {k: table[k] for k in ("T3", "K2", "T3K2")
             if table[k]["DDmax"] <= 20 and table[k]["losing"] == 0}
    if cands:
        hot = {k: v for k, v in cands.items() if v["Rdev4"] >= 5}
        pool = hot or cands
        pick = max(pool, key=lambda k: (pool[k]["Wdev4"], pool[k]["Rdev4"]))
    else:
        pick = "none-eligible"
    print("PICK on dev4 only (informational):", pick, flush=True)
    (HERE / "tmp/dev_table.json").write_text(json.dumps(
        {"table": table, "pick": pick}, indent=1))
    print("saved tmp/dev_table.json", flush=True)

    # ---- stage last: all four rows scored ONCE ----
    last = pickle.loads((HERE / "tmp/runs_last.pkl").read_bytes())
    assert all(set(last[s].keys()) == set(ROWS) for s in range(4)), \
        {s: sorted(last[s]) for s in range(4)}
    for v in ROWS:
        runs2 = {s: {v: last[s][v]["run"]} for s in range(4)}
        for y in range(4):
            a = rm.year_reset(runs2, v, y)
            assert (a["R"], a["DD"]) == (table[v]["years_R"][y], table[v]["years_DD"][y]), \
                (v, y, (a["R"], a["DD"]))
    print("determinism OK: stage-last dev segments equal stage-dev", flush=True)

    out = {}
    for v in ROWS:
        src = {s: {v: last[s][v]["run"]} for s in range(4)}
        y4 = rm.year_reset(src, v, 4)
        e, mn = v388.mix(src, v, v388.Y1 + pd.Timedelta(hours=12))
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fdd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        nb = sum(last[s][v]["wins"][4]["nb"] for s in range(4))
        wb = sum(last[s][v]["wins"][4]["wb"] for s in range(4))
        nr = sum(last[s][v]["wins"][4]["nr"] for s in range(4))
        wr = sum(last[s][v]["wins"][4]["wr"] for s in range(4))
        out[v] = dict(Rlast=y4["R"], DDlast=y4["DD"], full_path_dd=fdd,
                      book_trades=nb, book_win=round(wb / nb, 4) if nb else None,
                      rung_trades=nr, rung_win=round(wr / nr, 4) if nr else None,
                      all_win=round((wb + wr) / (nb + nr), 4) if (nb and nr) else None)
        print(v, out[v], flush=True)

    assert (out["REF"]["Rlast"], out["REF"]["DDlast"]) == EXP_REF_Y4, out["REF"]
    assert out["REF"]["full_path_dd"] == EXP_REF_FULLDD, out["REF"]
    assert (out["K2"]["Rlast"], out["K2"]["DDlast"]) == EXP_K2_Y4, out["K2"]
    assert out["K2"]["full_path_dd"] == EXP_K2_FULLDD, out["K2"]
    print("REF + K2 last-year reproduce expected numbers EXACTLY", flush=True)
    (HERE / "tmp/last_table.json").write_text(json.dumps(out, indent=1))
    print("saved tmp/last_table.json", flush=True)

    compute_corr()


if __name__ == "__main__":
    main()
