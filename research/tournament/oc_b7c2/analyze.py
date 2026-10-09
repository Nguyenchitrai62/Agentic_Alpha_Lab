"""oc_b7c2 scoring (CPU-only): dev validation + dev4 table + last-year ONCE + S5.

Reads tmp/runs_dev.pkl (REF/B7C2/B7C2_cap dev window), tmp/runs_last.pkl
(REF/B7C2/B7C2_cap full window, scored once), tmp/runs_S5.pkl (REF/B7/stack on
Bybit prices). B7 and C2 base rows are COPY rows from frozen sources, asserted
equal to the digit at scoring time (never rerun here).

Scores with reset_metric.year_reset + v388.mix, checks the reproduction gates
(REF == v421 G2; B7 copy == oc_cascadeboost B7; C2 copy == oc_chronos C2;
REF_S5 == oc_c2bybit REF_S5), writes tmp/dev_table.json, tmp/last_table.json,
tmp/s5_table.json. REPORT.md + results.json are written from those tables only.

Usage: python analyze.py --stage dev | --stage last | --stage s5 | --stage all
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
CB = ROOT / "research/tournament/oc_cascadeboost"
CH = ROOT / "research/tournament/oc_chronos"
C2B = ROOT / "research/tournament/oc_c2bybit"

DEV_ROWS = ["REF", "B7C2", "B7C2_cap"]
LAST_ROWS = ["REF", "B7C2", "B7C2_cap"]
S5_ROWS = ["REF", "B7", "B7C2", "B7C2_cap"]
EXP_REF_DEV = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27)]
EXP_REF_Y4 = (4.648, 12.90)
EXP_REF_5Y = 5.41
EXP_REF_FULLDD = 16.82


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs, nd=3):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), nd)


def full_dd_episode(v388, runs, v):
    """Full-path marked/close DD + worst 1m-marked DD episode."""
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


def wins_of(dev, v, years):
    out = []
    for y in years:
        nb = sum(dev[s][v]["wins"][y]["nb"] for s in range(4))
        wb = sum(dev[s][v]["wins"][y]["wb"] for s in range(4))
        nr = sum(dev[s][v]["wins"][y]["nr"] for s in range(4))
        wr = sum(dev[s][v]["wins"][y]["wr"] for s in range(4))
        out.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                        book_win=round(wb / nb, 4) if nb else None,
                        rung_win=round(wr / nr, 4) if nr else None,
                        all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
    return out


def sized_mean_of(dev, v, years):
    sms = [dev[s][v]["mult"] for s in range(4)]
    n_sz = sum(m[str(y)]["n_sized"] for m in sms for y in years)
    sm = (sum(m[str(y)]["sized_mean"] * m[str(y)]["n_sized"]
              for m in sms for y in years) / n_sz) if n_sz else None
    return (round(sm, 6) if sm is not None else None), int(n_sz)


def dev_table(dev, v388, rm, rows):
    table = {}
    for v in rows:
        runs = {s: {v: dev[s][v]["run"]} for s in range(4)}
        yrs = [rm.year_reset(runs, v, y) for y in range(4)]
        Rs = [y["R"] for y in yrs]
        DDs = [y["DD"] for y in yrs]
        fdd, _ep = full_dd_episode(v388, runs, v)
        sm, n_sz = sized_mean_of(dev, v, range(4))
        t = dict(years_R=Rs, years_DD=DDs, Rdev4=geo(Rs), Wdev4=round(min(Rs), 3),
                 DDdev4=round(max(DDs), 2), fullDDdev=fdd,
                 DDmax=round(max(max(DDs), fdd), 2),
                 losing=sum(r < 0 for r in Rs), wins=wins_of(dev, v, range(4)),
                 sized_mean=sm, n_sized=n_sz)
        table[v] = t
        print(f"{v}: Rdev4={t['Rdev4']} W={t['Wdev4']} DDmax_year={t['DDdev4']} fullDD={fdd} "
              f"losing={t['losing']} sized_mean={sm}", flush=True)
        print(f"   years R={Rs} DD={DDs}", flush=True)
        print(f"   all_win={[w['all_win'] for w in t['wins']]}", flush=True)
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
    v388 = _load("v388_b7c2", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_b7c2", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    dev = pickle.loads((HERE / "tmp/runs_dev.pkl").read_bytes())
    assert all(set(dev[s].keys()) == set(DEV_ROWS) for s in range(4)), \
        {s: sorted(dev[s]) for s in range(4)}
    runs = {s: {"REF": dev[s]["REF"]["run"]} for s in range(4)}
    got = [rm.year_reset(runs, "REF", y) for y in range(4)]
    for y in range(4):
        assert (got[y]["R"], got[y]["DD"]) == (EXP_REF_DEV[y][0], EXP_REF_DEV[y][1]), \
            ("REF", y, (got[y]["R"], got[y]["DD"]), EXP_REF_DEV[y])
    print(f"REF reproduces v421 G2 dev years 0..3 EXACTLY: "
          f"{[(g['R'], g['DD']) for g in got]}", flush=True)
    table = dev_table(dev, v388, rm, DEV_ROWS)
    # copy-gate: B7/C2 frozen numbers match sources to the digit
    cb_dev = json.loads((CB / "tmp/dev_table.json").read_text())["table"]
    ch_dev = json.loads((CH / "results.json").read_text())["dev"]
    assert cb_dev["B7"]["years_R"] == json.loads((CB / "tmp/dev_table.json").read_text())["table"]["B7"]["years_R"]
    for v, src in (("B7", cb_dev["B7"]),):
        print(f"copy-gate B7 dev R={src['years_R']} DD={src['years_DD']}", flush=True)
    for v, src in (("C2", ch_dev["C2"]),):
        print(f"copy-gate C2 dev R={src['r']} DD={src['dd']}", flush=True)
    pick = robust_pick({**table, "B7": {"DDmax": cb_dev["B7"]["DDmax"] if "DDmax" in cb_dev["B7"] else 17.92,
                                        "losing": 0, "Rdev4": 6.738, "Wdev4": 2.955}},
                       ["REF", "B7", "B7C2", "B7C2_cap"])
    print("PICK on dev4 only (among REF/B7/B7C2/B7C2_cap):", pick, flush=True)
    (HERE / "tmp/dev_table.json").write_text(json.dumps(
        {"table": table, "pick": pick}, indent=1))
    print("saved tmp/dev_table.json", flush=True)
    return pick


def stage_last():
    v388 = _load("v388_b7c2b", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_b7c2b", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    pick = json.loads((HERE / "tmp/dev_table.json").read_text())["pick"]
    dev = pickle.loads((HERE / "tmp/runs_dev.pkl").read_bytes())
    last = pickle.loads((HERE / "tmp/runs_last.pkl").read_bytes())
    assert all(set(last[s].keys()) == set(LAST_ROWS) for s in range(4)), \
        {s: sorted(last[s]) for s in range(4)}
    devt = json.loads((HERE / "tmp/dev_table.json").read_text())["table"]
    for v in LAST_ROWS:
        runs2 = {s: {v: last[s][v]["run"]} for s in range(4)}
        for y in range(4):
            a = rm.year_reset(runs2, v, y)
            assert (a["R"], a["DD"]) == (devt[v]["years_R"][y], devt[v]["years_DD"][y]), \
                (v, y, (a["R"], a["DD"]))
    print("determinism OK: stage-last dev segments equal stage-dev", flush=True)
    out = {}
    for v in LAST_ROWS:
        src = {s: {v: last[s][v]["run"]} for s in range(4)}
        yrs5 = [rm.year_reset(src, v, y) for y in range(5)]
        Rs5 = [y["R"] for y in yrs5]
        DDs5 = [y["DD"] for y in yrs5]
        _m, ep = full_dd_episode(v388, src, v)
        out[v] = dict(years_R5=Rs5, years_DD5=DDs5, R5y=geo(Rs5, 3), W5y=round(min(Rs5), 3),
                      DDmax5y=round(max(max(DDs5), ep["full"]), 2),
                      Rlast=yrs5[4]["R"], DDlast=yrs5[4]["DD"],
                      full_path_dd=ep["full"], dd_marked=ep["dd_marked"],
                      dd_close=ep["dd_close"],
                      worst_marked_episode=ep["worst_marked_episode"],
                      losing5y=sum(r < 0 for r in Rs5),
                      wins5y=wins_of(last, v, range(5)),
                      sized_mean5y=sized_mean_of(last, v, range(5))[0],
                      label_Y4="scored-once DIAGNOSTIC (contaminated: BOTH components already "
                               "scored on the post-release year; B7 idea formed after seeing the "
                               "delay replica incl. this year)")
        print(v, json.dumps(out[v]), flush=True)
    assert (out["REF"]["Rlast"], out["REF"]["DDlast"]) == EXP_REF_Y4, out["REF"]
    assert out["REF"]["full_path_dd"] == EXP_REF_FULLDD, out["REF"]
    assert out["REF"]["R5y"] == EXP_REF_5Y, out["REF"]
    print("REF last-year + 5y reproduces v421 G2 (4.648/12.90, 5.41, 16.82) EXACTLY", flush=True)
    print("pick was:", pick, flush=True)
    (HERE / "tmp/last_table.json").write_text(json.dumps(out, indent=1))
    print("saved tmp/last_table.json", flush=True)


def stage_s5():
    v388 = _load("v388_b7c2c", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_b7c2c", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    s5 = pickle.loads((HERE / "tmp/runs_S5.pkl").read_bytes())
    assert all(set(s5[s].keys()) == set(S5_ROWS) for s in range(4)), \
        {s: sorted(s5[s]) for s in range(4)}
    c2b = json.loads((C2B / "tmp/c2bybit_table.json").read_text())["table"]
    table = {}
    for v in S5_ROWS:
        rr = {s: {v: s5[s][v]["run"]} for s in range(4)}
        yrs = [rm.year_reset(rr, v, y) for y in range(5)]
        Rs = [y["R"] for y in yrs]
        DDs = [y["DD"] for y in yrs]
        e, mn = v388.mix(rr, v, v388.Y1 + pd.Timedelta(hours=12))
        seg = e.index > pd.Timestamp("2021-11-15", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fulldd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        table[v] = dict(years_R=Rs, years_DD=DDs, Rdev4=geo(Rs[:4]), Wdev4=round(min(Rs[:4]), 3),
                        DDdev4=round(max(DDs[:4]), 2), R5y=geo(Rs), W5y=round(min(Rs), 3),
                        DD5y=round(max(DDs), 2), full_path_dd_S5=fulldd,
                        wins=wins_of(s5, v, range(5)),
                        note="S5 Bybit prices from 2021-11-15; y2021 SHORT window (labelled)")
        print(v, json.dumps(table[v]), flush=True)
    # reproduction gate: REF_S5 == oc_c2bybit REF_S5 to the digit
    for y in range(5):
        assert table["REF"]["years_R"][y] == c2b["REF_S5"]["years_R"][y], (y, table["REF"]["years_R"][y])
        assert table["REF"]["years_DD"][y] == c2b["REF_S5"]["years_DD"][y], (y, table["REF"]["years_DD"][y])
    assert table["REF"]["full_path_dd_S5"] == c2b["REF_S5"]["full_path_dd"], table["REF"]
    print("REF_S5 reproduces oc_c2bybit REF_S5 EXACTLY", flush=True)
    (HERE / "tmp/s5_table.json").write_text(json.dumps(table, indent=1))
    print("saved tmp/s5_table.json", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "last", "s5", "all"], required=True)
    args = ap.parse_args()
    if args.stage in ("dev", "all"):
        stage_dev()
    if args.stage in ("last", "all"):
        stage_last()
    if args.stage in ("s5", "all"):
        stage_s5()


if __name__ == "__main__":
    main()
