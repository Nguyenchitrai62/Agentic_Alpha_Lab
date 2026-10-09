"""oc_cboostbybit scoring (CPU-only): dev4 / Y4-diagnostic / 5y + full-path DD + worst episode.

Reads tmp/runs_<fric>.pkl (REF/B7 full-window runs per friction), scores with
reset_metric.year_reset + v388.mix, checks the reproduction gate (base REF ==
v421 G2 to the digit; base B7 == oc_cascadeboost B7 to the digit; REF_S1..S5 ==
v421_audit ROBUST.md G2 as a harness check), writes tmp/cboostbybit_table.json.
REPORT.md + results.json are written from that table only.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TMP = HERE / "tmp"
CB = ROOT / "research/tournament/oc_cascadeboost"
FRICS = ("base", "S1", "S2", "S3", "S4", "S5")
VARIANTS = ("REF", "B7")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs, nd=3):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), nd)


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


def main():
    v388 = _load("v388_cboostbybit", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_cboostbybit", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    cb_res = json.loads((CB / "results.json").read_text())

    runs = {}
    for fric in FRICS:
        p = TMP / f"runs_{fric}.pkl"
        assert p.exists(), f"missing cache {p} — run compute_cboostbybit_engine.py first"
        runs[fric] = pickle.loads(p.read_bytes())
        assert set(runs[fric]) == {0, 1, 2, 3}, (fric, sorted(runs[fric]))
        for s in range(4):
            assert set(runs[fric][s]) == set(VARIANTS), (fric, s, sorted(runs[fric][s]))

    table = {}
    for fric in FRICS:
        for v in VARIANTS:
            key = f"{v}_{fric}"
            rr = {s: {key: runs[fric][s][v]["run"]} for s in range(4)}
            yrs = [rm.year_reset(rr, key, y) for y in range(5)]
            Rs = [y["R"] for y in yrs]
            DDs = [y["DD"] for y in yrs]
            dev = Rs[:4]
            e, mn = v388.mix(rr, key, g1)
            seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
            es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
            fulldd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
            _, ep = full_dd_episode(v388, rr, key)
            wins = []
            for y in range(5):
                nb = sum(runs[fric][s][v]["wins"][y]["nb"] for s in range(4))
                wb = sum(runs[fric][s][v]["wins"][y]["wb"] for s in range(4))
                nr = sum(runs[fric][s][v]["wins"][y]["nr"] for s in range(4))
                wr = sum(runs[fric][s][v]["wins"][y]["wr"] for s in range(4))
                wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                                 book_win=round(wb / nb, 4) if nb else None,
                                 rung_win=round(wr / nr, 4) if nr else None,
                                 all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
            sms = [runs[fric][s][v]["mult"] for s in range(4)]
            n_sz = sum(m[str(y)]["n_sized"] for m in sms for y in range(5))
            sm = (sum(m[str(y)]["sized_mean"] * m[str(y)]["n_sized"]
                        for m in sms for y in range(5)) / n_sz) if n_sz else None
            table[key] = dict(years_R=Rs, years_DD=DDs,
                              Rdev4=geo(dev), Wdev4=round(min(dev), 3),
                              DDdev4=round(max(DDs[:4]), 2),
                              losing_dev4=sum(r < 0 for r in dev),
                              R5y=geo(Rs), W5y=round(min(Rs), 3),
                              DD5y=round(max(DDs), 2),
                              losing_5y=sum(r < 0 for r in Rs),
                              full_path_dd=fulldd,
                              DDmax_full=round(max(max(DDs), fulldd), 2),
                              worst_marked_episode=ep["worst_marked_episode"],
                              dd_marked=ep["dd_marked"], dd_close=ep["dd_close"],
                              sized_mean=round(sm, 6) if sm is not None else None,
                              wins=wins)

    # ---- reproduction gate: base REF == v421 G2 to the digit ----
    for y in range(5):
        er, ed = exp["years"][y]
        assert table["REF_base"]["years_R"][y] == er, (y, table["REF_base"]["years_R"][y], er)
        assert table["REF_base"]["years_DD"][y] == ed, (y, table["REF_base"]["years_DD"][y], ed)
    assert table["REF_base"]["R5y"] == exp["R"], (table["REF_base"]["R5y"], exp["R"])
    assert table["REF_base"]["DD5y"] == exp["DD"], table["REF_base"]["DD5y"]
    assert table["REF_base"]["full_path_dd"] == exp["full_path_dd"], table["REF_base"]
    print("REF_base reproduces v421 G2 EXACTLY:", table["REF_base"]["years_R"],
          "full", table["REF_base"]["full_path_dd"], flush=True)

    # ---- reproduction gate: base B7 == oc_cascadeboost B7 to the digit ----
    cb_dev_R = cb_res["dev4_engine"]["B7"]["years_R"]
    cb_dev_DD = cb_res["dev4_engine"]["B7"]["years_DD"]
    cb_last = cb_res["engine_last_once_REF_pick"]["B7"]
    for y in range(4):
        assert table["B7_base"]["years_R"][y] == cb_dev_R[y], (y, table["B7_base"]["years_R"][y], cb_dev_R[y])
        assert table["B7_base"]["years_DD"][y] == cb_dev_DD[y], (y, table["B7_base"]["years_DD"][y], cb_dev_DD[y])
    assert table["B7_base"]["years_R"][4] == cb_last["Rlast_diag"], (table["B7_base"]["years_R"][4], cb_last["Rlast_diag"])
    assert table["B7_base"]["years_DD"][4] == cb_last["DDlast_diag"], (table["B7_base"]["years_DD"][4], cb_last["DDlast_diag"])
    assert table["B7_base"]["R5y"] == cb_last["R5y"], table["B7_base"]
    assert table["B7_base"]["full_path_dd"] == cb_last["full_path_dd"], table["B7_base"]
    assert table["B7_base"]["Rdev4"] == cb_res["dev4_engine"]["B7"]["Rdev4"], table["B7_base"]
    print("B7_base reproduces oc_cascadeboost B7 EXACTLY:", table["B7_base"]["years_R"],
          "full", table["B7_base"]["full_path_dd"], flush=True)

    gaps = {}
    for fric in FRICS:
        gaps[fric] = dict(dev4=round(table[f"B7_{fric}"]["Rdev4"] - table[f"REF_{fric}"]["Rdev4"], 3),
                          y4_diag=round(table[f"B7_{fric}"]["years_R"][4] - table[f"REF_{fric}"]["years_R"][4], 3),
                          y5=round(table[f"B7_{fric}"]["R5y"] - table[f"REF_{fric}"]["R5y"], 3))
    (TMP / "cboostbybit_table.json").write_text(json.dumps(
        {"table": table, "gaps": gaps,
         "ref_gate": {"years": exp["years"], "R": exp["R"], "DD": exp["DD"],
                      "full_path_dd": exp["full_path_dd"]}}, indent=1))
    print("gaps B7-REF:", gaps, flush=True)
    print("saved tmp/cboostbybit_table.json", flush=True)


if __name__ == "__main__":
    main()
