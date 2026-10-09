"""oc_cboostctrl scoring: dev validation + controls + last-year ONCE (all rows).

Stage dev (tmp/runs_dev.pkl): REF must reproduce v421_result G2 years 0..3
(R and DD) EXACTLY, else STOP. Then dev4 table for ALL rows + CTRL_R
distributions + timing/exposure shares on dev4.
Stage last (tmp/runs_last.pkl): determinism check (dev segments equal
stage-dev); REF Y4/5y/full-path must equal v421 G2 to the digit, else STOP.
5y + full-path DD + worst 1m-marked episode per row; CTRL_R mean/p5/p95 of each
metric; per-year B7-vs-p95; share split (dev4 primary, per-year + Y4 diagnostic).
CPU-only. Last-year control numbers are scored-once DIAGNOSTICS (no selection;
there is no selection in this study — B7 is the frozen copy).
"""

import argparse
import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"

import sys

sys.path.insert(0, str(HERE))
from ctrl_rule import N_SEEDS  # noqa: E402

R_ROWS = [f"R{j:02d}" for j in range(N_SEEDS)]
MAIN_ROWS = ["REF", "B7", "CTRL_C"]
ALL_ROWS = MAIN_ROWS + R_ROWS
EXP_REF_DEV = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27)]
EXP_REF_Y4 = (4.648, 12.90)
EXP_REF_5Y = 5.41
EXP_REF_MAXDD = 16.91
EXP_REF_FULLDD = 16.82


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def full_dd_episode(v388, runs, v):
    """Full-path marked/close DD + worst 1m-marked DD episode (verbatim cascadeboost)."""
    g1 = pd.Timestamp("2025-09-24 12:00", tz="UTC")
    e, mn = v388.mix(runs, v, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(float), mn[seg].to_numpy(float)
    idx = e.index[seg]
    pk = np.maximum.accumulate(es)
    dd = 1 - ms / pk
    dd_m = round(100 * float(np.max(dd)), 2)
    dd_c = round(100 * float(np.max(1 - es / pk)), 2)
    i_dd = int(np.argmax(dd))
    i_pk = int(np.argmax(es[:i_dd + 1])) if i_dd > 0 else 0
    return (round(100 * float(np.max(1 - ms / pk)), 2),
            {"dd_marked": dd_m, "dd_close": dd_c,
             "full": max(dd_m, dd_c),
             "worst_marked_episode": {
                 "peak": str(idx[i_pk]), "trough": str(idx[i_dd]),
                 "depth_pct": round(100 * float(dd[i_dd]), 2)}})


def dev_table(dev, v388, rm, rows):
    table = {}
    for v in rows:
        runs = {s: {v: dev[s][v]["run"]} for s in range(4)}
        yrs = [rm.year_reset(runs, v, y) for y in range(4)]
        Rs = [y["R"] for y in yrs]
        DDs = [y["DD"] for y in yrs]
        geo = round(100 * (np.prod([1 + r / 100 for r in Rs]) ** (1 / 4) - 1), 3)
        fdd, _ep = full_dd_episode(v388, runs, v)
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
        sms = [dev[s][v]["mult"] for s in range(4)]
        n_sz = sum(m[str(y)]["n_sized"] for m in sms for y in range(4))
        sm = sum(m[str(y)]["sized_mean"] * m[str(y)]["n_sized"]
                 for m in sms for y in range(4)) / n_sz if n_sz else None
        t = dict(years_R=Rs, years_DD=DDs, Rdev4=geo, Wdev4=round(min(Rs), 3),
                 DDdev4=round(max(DDs), 2), fullDDdev=fdd,
                 DDmax=round(max(max(DDs), fdd), 2),
                 losing=sum(r < 0 for r in Rs), wins=wins,
                 sized_mean=round(sm, 6) if sm is not None else None,
                 n_sized=int(n_sz),
                 boosted_share_sized=round((sm - 1.0) / 0.5, 4) if sm is not None else None)
        table[v] = t
    for v in rows:
        t = table[v]
        print(f"{v}: Rdev4={t['Rdev4']} W={t['Wdev4']} DDmax={t['DDmax']} "
              f"losing={t['losing']} sized_mean={t['sized_mean']} "
              f"boosted_share={t['boosted_share_sized']}", flush=True)
        print(f"   years R={t['years_R']} DD={t['years_DD']}", flush=True)
    return table


def dist_of(vals):
    a = np.asarray(vals, dtype=float)
    return dict(n=int(len(a)), mean=round(float(a.mean()), 3),
                p5=round(float(np.quantile(a, 0.05)), 3),
                p50=round(float(np.quantile(a, 0.50)), 3),
                p95=round(float(np.quantile(a, 0.95)), 3),
                min=round(float(a.min()), 3), max=round(float(a.max()), 3))


def ctrlR_dist(table):
    """Distribution (mean/p5/p95/...) of each metric over the 20 seeds (dev4)."""
    d = {}
    for k in ["Rdev4", "Wdev4", "DDmax", "DDdev4", "fullDDdev"]:
        d[k] = dist_of([table[r][k] for r in R_ROWS])
    for y in range(4):
        d[f"R_y{y}"] = dist_of([table[r]["years_R"][y] for r in R_ROWS])
        d[f"DD_y{y}"] = dist_of([table[r]["years_DD"][y] for r in R_ROWS])
    return d


def shares(b7, ref, ctrl, label):
    """Timing/exposure split of (b7-ref) gain; None when degenerate."""
    denom = b7 - ref
    if not np.isfinite(denom) or abs(denom) < 1e-9 or denom <= 0:
        return dict(label=label, degenerate=True, b7=b7, ref=ref, ctrl=ctrl)
    return dict(label=label, degenerate=False, b7=b7, ref=ref, ctrl=ctrl,
                exposure=round((ctrl - ref) / denom, 3),
                timing=round((b7 - ctrl) / denom, 3))


def stage_dev():
    v388 = _load("v388_analyze_cc", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_analyze_cc", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    dev = pickle.loads((HERE / "tmp/runs_dev.pkl").read_bytes())
    assert all(set(dev[s].keys()) == set(ALL_ROWS) for s in range(4)), \
        {s: sorted(dev[s]) for s in range(4)}

    runs = {s: {"REF": dev[s]["REF"]["run"]} for s in range(4)}
    got = [rm.year_reset(runs, "REF", y) for y in range(4)]
    for y in range(4):
        assert (got[y]["R"], got[y]["DD"]) == (EXP_REF_DEV[y][0], EXP_REF_DEV[y][1]), \
            ("REF", y, (got[y]["R"], got[y]["DD"]), EXP_REF_DEV[y])
    print(f"REF reproduces v421 G2 dev years 0..3 EXACTLY: "
          f"{[(g['R'], g['DD']) for g in got]}", flush=True)

    table = dev_table(dev, v388, rm, ALL_ROWS)
    cdist = ctrlR_dist(table)
    rmean = {k: cdist[k]["mean"] for k in ["Rdev4", "Wdev4", "DDmax"]}
    out = {"table": table, "ctrlR_dist": cdist,
           "share_CTRL_C_dev4": shares(table["B7"]["Rdev4"], table["REF"]["Rdev4"],
                                       table["CTRL_C"]["Rdev4"], "CTRL_C/dev4mean"),
           "share_CTRL_Rmean_dev4": shares(table["B7"]["Rdev4"], table["REF"]["Rdev4"],
                                           rmean["Rdev4"], "CTRL_Rmean/dev4mean"),
           "share_CTRL_C_per_year": {
               str(y): shares(table["B7"]["years_R"][y], table["REF"]["years_R"][y],
                              table["CTRL_C"]["years_R"][y], f"CTRL_C/y{y}")
               for y in range(4)},
           "b7_vs_p95_per_year": {
               str(y): {"b7": table["B7"]["years_R"][y],
                        "p95": cdist[f"R_y{y}"]["p95"],
                        "above": bool(table["B7"]["years_R"][y] > cdist[f"R_y{y}"]["p95"])}
               for y in range(4)}}
    (HERE / "tmp/dev_table.json").write_text(json.dumps(out, indent=1))
    print("share_CTRL_C_dev4:", out["share_CTRL_C_dev4"], flush=True)
    print("share_CTRL_Rmean_dev4:", out["share_CTRL_Rmean_dev4"], flush=True)
    print("b7_vs_p95:", out["b7_vs_p95_per_year"], flush=True)
    print("saved tmp/dev_table.json", flush=True)


def stage_last():
    v388 = _load("v388_analyze_cc2", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_analyze_cc2", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    devt = json.loads((HERE / "tmp/dev_table.json").read_text())["table"]
    last = pickle.loads((HERE / "tmp/runs_last.pkl").read_bytes())
    assert all(set(last[s].keys()) == set(ALL_ROWS) for s in range(4)), \
        {s: sorted(last[s]) for s in range(4)}
    for v in ALL_ROWS:
        runs2 = {s: {v: last[s][v]["run"]} for s in range(4)}
        for y in range(4):
            a = rm.year_reset(runs2, v, y)
            assert (a["R"], a["DD"]) == (devt[v]["years_R"][y], devt[v]["years_DD"][y]), \
                (v, y, (a["R"], a["DD"]))
    print("determinism OK: stage-last dev segments equal stage-dev (all rows)",
          flush=True)

    out = {}
    for v in ALL_ROWS:
        src = {s: {v: last[s][v]["run"]} for s in range(4)}
        yrs5 = [rm.year_reset(src, v, y) for y in range(5)]
        Rs5 = [y["R"] for y in yrs5]
        DDs5 = [y["DD"] for y in yrs5]
        r5 = round(100 * (np.prod([1 + r / 100 for r in Rs5]) ** (1 / 5) - 1), 3)
        _m, ep = full_dd_episode(v388, src, v)
        nb = sum(last[s][v]["wins"][4]["nb"] for s in range(4))
        wb = sum(last[s][v]["wins"][4]["wb"] for s in range(4))
        nr = sum(last[s][v]["wins"][4]["nr"] for s in range(4))
        wr = sum(last[s][v]["wins"][4]["wr"] for s in range(4))
        nb5 = sum(last[s][v]["wins"][y]["nb"] for s in range(4) for y in range(5))
        wb5 = sum(last[s][v]["wins"][y]["wb"] for s in range(4) for y in range(5))
        nr5 = sum(last[s][v]["wins"][y]["nr"] for s in range(4) for y in range(5))
        wr5 = sum(last[s][v]["wins"][y]["wr"] for s in range(4) for y in range(5))
        sms = [last[s][v]["mult"] for s in range(4)]
        n_sz = sum(m[str(y)]["n_sized"] for m in sms for y in range(5))
        sm = (sum(m[str(y)]["sized_mean"] * m[str(y)]["n_sized"]
                    for m in sms for y in range(5)) / n_sz) if n_sz else None
        out[v] = dict(years_R5=Rs5, years_DD5=DDs5, R5y=r5, W5y=round(min(Rs5), 3),
                      DDmax5y=round(max(max(DDs5), ep["full"]), 2),
                      Rlast=yrs5[4]["R"], DDlast=yrs5[4]["DD"],
                      full_path_dd=ep["full"], dd_marked=ep["dd_marked"],
                      dd_close=ep["dd_close"],
                      worst_marked_episode=ep["worst_marked_episode"],
                      losing5y=sum(r < 0 for r in Rs5),
                      sized_mean_5y=round(sm, 6) if sm is not None else None,
                      book_win_Y4=round(wb / nb, 4) if nb else None,
                      rung_win_Y4=round(wr / nr, 4) if nr else None,
                      all_win_Y4=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None,
                      book_win_5y=round(wb5 / nb5, 4) if nb5 else None,
                      rung_win_5y=round(wr5 / nr5, 4) if nr5 else None,
                      all_win_5y=round((wb5 + wr5) / (nb5 + nr5), 4) if (nb5 + nr5) else None,
                      label_Y4="scored-once DIAGNOSTIC (controls: never used for selection; B7 idea post-dates 5y)")
        print(v, json.dumps(out[v]), flush=True)

    assert (out["REF"]["Rlast"], out["REF"]["DDlast"]) == EXP_REF_Y4, out["REF"]
    assert out["REF"]["full_path_dd"] == EXP_REF_FULLDD, out["REF"]
    assert out["REF"]["R5y"] == EXP_REF_5Y, out["REF"]
    print("REF last-year + 5y reproduces v421 G2 (4.648/12.90, 5.41, 16.82) EXACTLY",
          flush=True)

    cdist5: dict[str, dict] = {}
    for k in ["R5y", "W5y", "DDmax5y", "full_path_dd", "Rlast", "DDlast"]:
        cdist5[k] = dist_of([out[r][k] for r in R_ROWS])
    for y in range(5):
        cdist5[f"R_y{y}"] = dist_of([out[r]["years_R5"][y] for r in R_ROWS])
        cdist5[f"DD_y{y}"] = dist_of([out[r]["years_DD5"][y] for r in R_ROWS])
    final = {"rows": out, "ctrlR_dist_5y": cdist5,
             "b7_vs_p95_per_year_5y": {
                 str(y): {"b7": out["B7"]["years_R5"][y],
                          "p95": cdist5[f"R_y{y}"]["p95"],
                          "above": bool(out["B7"]["years_R5"][y] > cdist5[f"R_y{y}"]["p95"])}
                 for y in range(5)},
             "share_CTRL_C_5y": shares(out["B7"]["R5y"], out["REF"]["R5y"],
                                       out["CTRL_C"]["R5y"], "CTRL_C/5y"),
             "share_CTRL_Rmean_5y": shares(out["B7"]["R5y"], out["REF"]["R5y"],
                                          cdist5["R5y"]["mean"], "CTRL_Rmean/5y")}
    (HERE / "tmp/last_table.json").write_text(json.dumps(final, indent=1))
    print("b7_vs_p95_5y:", final["b7_vs_p95_per_year_5y"], flush=True)
    print("share_5y:", final["share_CTRL_C_5y"], final["share_CTRL_Rmean_5y"], flush=True)
    print("saved tmp/last_table.json", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "last"], required=True)
    args = ap.parse_args()
    if args.stage == "dev":
        stage_dev()
    else:
        stage_last()


if __name__ == "__main__":
    main()
