"""oc_oishort last-year scoring: determinism + pick/REF scored ONCE (CPU-only)."""
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

EXP_REF_Y4 = (4.648, 12.90)
EXP_REF_FULLDD = 16.82


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v388 = _load("v388_last_os", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_last_os", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    dev = json.loads((HERE / "tmp/dev_table.json").read_text())
    pick = dev["pick"]
    rows = ["REF", pick] if pick not in ("REF", "none-eligible") else ["REF"]
    if pick == "none-eligible":
        rows = ["REF"]
    print("rows to score ONCE:", rows, "pick:", pick, flush=True)
    last = pickle.loads((HERE / "tmp/runs_last.pkl").read_bytes())
    assert all(set(last[s].keys()) == set(rows) for s in range(4)), \
        {s: sorted(last[s]) for s in range(4)}
    # determinism: dev segments equal stage-dev
    for v in rows:
        for y in range(4):
            a = rm.year_reset({s: {v: last[s][v]["run"]} for s in range(4)}, v, y)
            expR = dev["table"][v]["years_R"][y]
            expD = dev["table"][v]["years_DD"][y]
            assert (a["R"], a["DD"]) == (expR, expD), (v, y, (a["R"], a["DD"]), (expR, expD))
    print("determinism OK: stage-last dev segments equal stage-dev", flush=True)
    out, five = {}, {}
    for v in rows:
        src = {s: {v: last[s][v]["run"]} for s in range(4)}
        y4 = rm.year_reset(src, v, 4)
        yrs5 = [rm.year_reset(src, v, y) for y in range(5)]
        r5 = [y["R"] for y in yrs5]
        d5 = [y["DD"] for y in yrs5]
        geo5 = round(100 * (np.prod([1 + r / 100 for r in r5]) ** (1 / 5) - 1), 3)
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
                      all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None)
        five[v] = dict(R5=r5, D5=d5, R5geo=geo5, W5=round(min(r5), 3),
                       losing5=sum(r < 0 for r in r5))
        print(v, out[v], five[v], flush=True)
    assert (out["REF"]["Rlast"], out["REF"]["DDlast"]) == EXP_REF_Y4, out["REF"]
    assert out["REF"]["full_path_dd"] == EXP_REF_FULLDD, out["REF"]
    print("REF last-year reproduces v421 G2 Y4 EXACTLY", flush=True)
    (HERE / "tmp/last_table.json").write_text(json.dumps(
        {"last": out, "five": five, "pick": pick}, indent=1))
    print("saved tmp/last_table.json", flush=True)


if __name__ == "__main__":
    main()
