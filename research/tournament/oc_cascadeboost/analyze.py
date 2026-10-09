"""oc_cascadeboost scoring: dev validation + dev4 table + last-year ONCE (REF + pick).

Stage dev (tmp/runs_dev.pkl with REF/B7/B3): REF must reproduce v421_result G2
years 0..3 (R and DD) EXACTLY, else STOP. Then dev4 table + robust pick on
dev4 ONLY. Stage last (tmp/runs_last.pkl with REF + pick): determinism check
(dev segments equal stage-dev); both rows scored ONCE; REF Y4 must equal v421
G2 Y4 to the digit; full-path DD via v388.mix + worst 1m-marked DD episode per
row. CPU-only. Post-release Y4 numbers are LABELLED DIAGNOSTIC (contaminated:
idea formed after seeing oc_cascadedelay replica covering all five years).
"""
import argparse
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

DEV_ROWS = ["REF", "B7", "B3"]
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
    """Full-path marked/close DD + worst 1m-marked DD episode (peak/trough/depth).

    dd(t) = 1 - ms(t)/peak(es)(t); trough = argmax dd; peak = argmax es[:t+1].
    """
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
        print(f"{v}: Rdev4={geo} W={t['Wdev4']} DDmax_year={t['DDdev4']} fullDD={fdd} "
              f"losing={t['losing']} sized_mean={t['sized_mean']} "
              f"boosted_share={t['boosted_share_sized']}", flush=True)
        print(f"   years R={Rs} DD={DDs}", flush=True)
        print(f"   all_win={[w['all_win'] for w in wins]} fills_rung={[w['nr'] for w in wins]} "
              f"book={[w['nb'] for w in wins]}", flush=True)
    return table


def robust_pick(table, rows):
    cands = {k: table[k] for k in rows
             if table[k]["DDmax"] <= 20 and table[k]["losing"] == 0}
    if cands:
        hot = {k: v for k, v in cands.items() if v["Rdev4"] >= 5}
        pool = hot or cands
        return max(pool, key=lambda k: (pool[k]["Wdev4"], pool[k]["Rdev4"]))
    return "none-eligible"


def stage_dev():
    v388 = _load("v388_analyze_cb", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_analyze_cb", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    dev = pickle.loads((HERE / "tmp/runs_dev.pkl").read_bytes())
    assert all(set(dev[s].keys()) == set(DEV_ROWS) for s in range(4)), \
        {s: sorted(dev[s]) for s in range(4)}

    # ---- reproduction gate: REF vs v421 G2 ----
    runs = {s: {"REF": dev[s]["REF"]["run"]} for s in range(4)}
    got = [rm.year_reset(runs, "REF", y) for y in range(4)]
    for y in range(4):
        assert (got[y]["R"], got[y]["DD"]) == (EXP_REF_DEV[y][0], EXP_REF_DEV[y][1]), \
            ("REF", y, (got[y]["R"], got[y]["DD"]), EXP_REF_DEV[y])
    print(f"REF reproduces v421 G2 dev years 0..3 EXACTLY: "
          f"{[(g['R'], g['DD']) for g in got]}", flush=True)

    table = dev_table(dev, v388, rm, DEV_ROWS)
    pick = robust_pick(table, DEV_ROWS)
    print("PICK on dev4 only:", pick, flush=True)
    (HERE / "tmp/dev_table.json").write_text(json.dumps(
        {"table": table, "pick": pick}, indent=1))
    print("saved tmp/dev_table.json", flush=True)
    return pick


def stage_last():
    v388 = _load("v388_analyze_cb2", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_analyze_cb2", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    pick = json.loads((HERE / "tmp/dev_table.json").read_text())["pick"]
    rows = ["REF", pick] if pick != "none-eligible" else ["REF"]
    dev = pickle.loads((HERE / "tmp/runs_dev.pkl").read_bytes())
    last = pickle.loads((HERE / "tmp/runs_last.pkl").read_bytes())
    assert all(set(last[s].keys()) == set(rows) for s in range(4)), \
        {s: sorted(last[s]) for s in range(4)}
    # determinism: stage-last dev segments equal stage-dev
    devt = json.loads((HERE / "tmp/dev_table.json").read_text())["table"]
    for v in rows:
        runs2 = {s: {v: last[s][v]["run"]} for s in range(4)}
        for y in range(4):
            a = rm.year_reset(runs2, v, y)
            assert (a["R"], a["DD"]) == (devt[v]["years_R"][y], devt[v]["years_DD"][y]), \
                (v, y, (a["R"], a["DD"]))
    print("determinism OK: stage-last dev segments equal stage-dev", flush=True)

    out = {}
    for v in rows:
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
        nb4 = sum(last[s][v]["wins"][y]["nb"] for s in range(4) for y in range(5))
        wb4 = sum(last[s][v]["wins"][y]["wb"] for s in range(4) for y in range(5))
        nr4 = sum(last[s][v]["wins"][y]["nr"] for s in range(4) for y in range(5))
        wr4 = sum(last[s][v]["wins"][y]["wr"] for s in range(4) for y in range(5))
        out[v] = dict(years_R5=Rs5, years_DD5=DDs5, R5y=r5, W5y=round(min(Rs5), 3),
                      DDmax5y=round(max(max(DDs5), ep["full"]), 2),
                      Rlast=yrs5[4]["R"], DDlast=yrs5[4]["DD"],
                      full_path_dd=ep["full"], dd_marked=ep["dd_marked"],
                      dd_close=ep["dd_close"],
                      worst_marked_episode=ep["worst_marked_episode"],
                      losing5y=sum(r < 0 for r in Rs5),
                      book_trades=nb, book_win=round(wb / nb, 4) if nb else None,
                      rung_trades=nr, rung_win=round(wr / nr, 4) if nr else None,
                      all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None,
                      book_trades_5y=nb4,
                      book_win_5y=round(wb4 / nb4, 4) if nb4 else None,
                      rung_trades_5y=nr4,
                      rung_win_5y=round(wr4 / nr4, 4) if nr4 else None,
                      all_win_5y=round((wb4 + wr4) / (nb4 + nr4), 4) if (nb4 + nr4) else None,
                      label_Y4="scored-once DIAGNOSTIC (contaminated: idea formed after "
                               "seeing oc_cascadedelay replica incl. post-release year)")
        print(v, json.dumps(out[v]), flush=True)

    assert (out["REF"]["Rlast"], out["REF"]["DDlast"]) == EXP_REF_Y4, out["REF"]
    assert out["REF"]["full_path_dd"] == EXP_REF_FULLDD, out["REF"]
    assert out["REF"]["R5y"] == EXP_REF_5Y, out["REF"]
    print("REF last-year + 5y reproduces v421 G2 (4.648/12.90, 5.41, 16.82) EXACTLY",
          flush=True)
    (HERE / "tmp/last_table.json").write_text(json.dumps(out, indent=1))
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
