"""oc_underwater: drawdown episodes on the continuous 4-phase mix (REPORTING ONLY).

Pre-registered in PLAN.md before any outcome was computed. Post-hoc informed,
REPORTING ONLY. Uses ONLY the cached 4-phase runs (t/eq/eq_min per shift);
hourly mix via v388_bot_stop_distance.hourly/mix (imported, not copied).

Usage: .venv/Scripts/python.exe research/tournament/oc_underwater/compute_underwater.py
Reads: research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl (R2B1D17BFG2),
  .../v424/v424_runs.pkl (R2B1D13BF), v421_result.json / v424_result.json (official DD check).
Writes: research/tournament/oc_underwater/results.json
One process, no 1m data, RAM < 1 GB.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"

SPECS = [
    ("R2B1D17BFG2", "v421", "v421_runs.pkl", "R2B1D17BFG2"),
    ("R2B1D13BF", "v424", "v424_runs.pkl", "R2B1D13BF"),
]
ANCHOR0 = pd.Timestamp("2021-09-24 00:00", tz="UTC")
THRESH = 0.05
THRESH10 = 0.10


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_excursions(e: pd.Series, mn: pd.Series) -> list[dict]:
    """Peak-to-recovery underwater excursions (PLAN.md definition).

    Returns list of dicts with integer positions (ipos_peak/trough/rec or None).
    Caller filters depth > 5% and formats dates. Pure function of (e, mn).
    """
    ev = e.to_numpy(float)
    mv = mn.to_numpy(float)
    n = len(ev)
    pk_val = ev[0]
    pk_pos = 0
    under = False
    out = []
    for i in range(1, n):
        if ev[i] >= pk_val:
            if under:
                seg = slice(pk_pos, i + 1)  # include recovery hour (conservative mn)
                dd = 1.0 - mv[seg] / pk_val
                k = int(np.argmax(dd))  # first max on ties
                out.append({
                    "ipos_peak": int(pk_pos),
                    "ipos_trough": int(pk_pos + k),
                    "ipos_rec": int(i),
                    "peak": float(pk_val),
                    "depth": float(np.max(dd)),
                    "censored": False,
                })
                pk_val = ev[i]
                pk_pos = i
                under = False
            else:
                pk_val = ev[i]
                pk_pos = i
        else:
            under = True
    if under:
        seg = slice(pk_pos, n)
        dd = 1.0 - mv[seg] / pk_val
        k = int(np.argmax(dd))
        out.append({
            "ipos_peak": int(pk_pos),
            "ipos_trough": int(pk_pos + k),
            "ipos_rec": None,
            "peak": float(pk_val),
            "depth": float(np.max(dd)),
            "censored": True,
        })
    return out


def main() -> None:
    v388 = _load("v388_uw", RD / "v388" / "v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")

    rows = []
    for label, vdir, pkl, row in SPECS:
        runs = pickle.loads((RD / vdir / pkl).read_bytes())
        assert set(runs) == {0, 1, 2, 3}, (label, sorted(runs))
        for s in runs:
            assert set(runs[s][row]) == {"t", "eq", "eq_min"}, (label, s)
        e_full, mn_full = v388.mix(runs, row, g1)
        assert (e_full.index == mn_full.index).all()
        assert e_full.index[0] == g0 and e_full.index[-1] == g1
        seg = e_full.index > ANCHOR0
        e = e_full[seg]
        mn = mn_full[seg]
        n = len(e)
        peak = np.maximum.accumulate(e.to_numpy(float))
        dd = 1.0 - mn.to_numpy(float) / peak
        viol = float(np.max(mn.to_numpy(float) - e.to_numpy(float)))
        full_dd = float(np.max(dd)) * 100.0

        official = json.loads((RD / vdir / f"{vdir}_result.json").read_text())["rows"][row]
        official_fp = float(official["full_path_dd"])

        exc = find_excursions(e, mn)
        episodes = []
        for x in exc:
            if x["depth"] <= THRESH:
                continue
            t_peak = e.index[x["ipos_peak"]]
            t_tr = e.index[x["ipos_trough"]]
            t_rec = e.index[x["ipos_rec"]] if x["ipos_rec"] is not None else None
            dtt = (t_tr - t_peak).total_seconds() / 86400.0
            duw = ((t_rec if t_rec is not None else e.index[-1]) - t_peak).total_seconds() / 86400.0
            episodes.append({
                "peak_date": t_peak.isoformat(),
                "trough_date": t_tr.isoformat(),
                "recovery_date": t_rec.isoformat() if t_rec is not None else None,
                "censored": bool(x["censored"]),
                "depth_pct": round(x["depth"] * 100.0, 2),
                "days_to_trough": round(float(dtt), 2),
                "days_underwater": round(float(duw), 2),
                "hours_to_trough": int(round((t_tr - t_peak).total_seconds() / 3600.0)),
                "hours_underwater": int(round(((t_rec if t_rec is not None else e.index[-1]) - t_peak).total_seconds() / 3600.0)),
            })
        episodes.sort(key=lambda d: -d["depth_pct"])
        durs = np.array([d["days_underwater"] for d in episodes], float)
        if len(durs):
            dist = {
                "n": int(len(durs)),
                "median_days": round(float(np.median(durs)), 2),
                "p90_days": round(float(np.percentile(durs, 90)), 2),
                "max_days": round(float(np.max(durs)), 2),
            }
        else:
            dist = {"n": 0, "median_days": 0.0, "p90_days": 0.0, "max_days": 0.0}
        sh5 = float(np.mean(dd > THRESH))
        sh10 = float(np.mean(dd > THRESH10))
        window_days = n / 24.0
        rows.append({
            "row": label,
            "src": f"{vdir}/{row}",
            "window": {"start": e.index[0].isoformat(), "end": e.index[-1].isoformat(),
                       "n_hours": int(n), "window_days": round(float(window_days), 2)},
            "final_eq": round(float(e.iloc[-1]), 4),
            "full_path_dd": round(full_dd, 2),
            "official_full_path_dd": official_fp,
            "full_path_match": bool(abs(full_dd - official_fp) < 0.011),
            "max_eqmin_above_eq": round(viol, 10),
            "episodes_gt5": episodes,
            "underwater_dist_gt5": dist,
            "share": {
                "gt5_frac": round(sh5, 6),
                "gt10_frac": round(sh10, 6),
                "gt5_pct_time": round(sh5 * 100.0, 2),
                "gt10_pct_time": round(sh10 * 100.0, 2),
                "gt5_days_equiv": round(sh5 * window_days, 1),
                "gt10_days_equiv": round(sh10 * window_days, 1),
            },
        })

    out = {
        "meta": {
            "convention": "continuous 4-phase mix 1/4 each, no reset: e,mn = v388.mix(runs,row,g1), window t > 2021-09-24T00:00Z; P=cummax(e), dd=1-mn/P; episode = peak-to-e-recovery excursion with max dd > 5% (nested 5% crossings do not split; recovery on eq; censored at grid end)",
            "grid": {"g0": "2021-09-24T04:00:00+00:00", "g1": "2026-09-23T12:00:00+00:00", "freq": "1h"},
            "rows": [s[0] for s in SPECS],
            "data_cap": "2026-09-24T00:00:00Z",
            "reporting_only": True,
            "post_hoc_informed": True,
        },
        "rows_data": rows,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for r in rows:
        print(f"{r['row']}: fullDD={r['full_path_dd']} (official {r['official_full_path_dd']}) "
              f"episodes>5%={len(r['episodes_gt5'])} uw_dist={r['underwater_dist_gt5']} "
              f"share>5%={r['share']['gt5_pct_time']}% (>10%={r['share']['gt10_pct_time']}%)", flush=True)
        for ep in r["episodes_gt5"][:12]:
            print(f"  {ep['depth_pct']}% peak {ep['peak_date'][:10]} trough {ep['trough_date'][:10]} "
                  f"rec {str(ep['recovery_date'])[:10]} uw {ep['days_underwater']}d", flush=True)


if __name__ == "__main__":
    main()
