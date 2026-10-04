"""Dev-only diagnostic (not a registered version): R2 dip-agent decision tables (size S1 + take-profit X4, rungs 2.5/3.0/3.5/4.0/5.0) on 4h grids
shifted by HALF hours, s = 0.5 / 1.5 / 2.5 / 3.5 h (bar opens 00:30, 04:30, .. / 01:30, .. / 02:30, .. / 03:30, .. UTC). Tables only - no simulation.

Deployed recipe, unchanged (= research/parallel/rounds/parallel-20260906-r2/v376/tables_hidden):
  - models: per anchor 2021-09-24 .. 2025-09-24, HGB v296.hgb (seeds 10 jj + h for size, 10 jj + h + 3 c for TP) fitted on
    research/diagnostics/phase_agents/fills_U.parquet rows with t_exit < anchor - 7 days, cross-fit halves j % 2, targets clipped [-0.10, 0.08]
    (phase_agents_aug/build_aug.fit with the non-augmented fills = identical data, order, seeds);
  - state at the open T of every shifted holding bar (START + s h + 4h j): sp30 / btc sp30 / dd24 at the close of minute 0 (kk = 240 j),
    volreg / trend / sigma_4h from that grid's own 4h opens, hour feature = T.hour (00:30 -> 0); model = latest anchor <= T; R2 rules().
v293.START + s h with a 30-minute offset: Asset builds the 1m index with pd.date_range(START, END - 1 min, freq 1min) and slices every 240th minute,
so any minute-aligned START works (nothing in Asset / sp30 assumes whole hours); bars simply open at hh:30.
Coverage: bars 2021-09-24 + s .. 2026-09-23 12:00 + s (= v376/tables_hidden coverage), plus bars up to 2026-09-24 08:00 + s whose minute-0 close
exists (minute data ends 2026-09-23 23:59; 1m arrays loaded to 2026-09-25 as in v376/build_aug - every state feature is past-only).
Row order as v376/tables_hidden: dev part (T <= 2025-09-24 08:00 + s) then the rest, each symbol-major.
Sanity: s = 0 and s = 1 restricted to v376 coverage must equal v376/tables_hidden/r2_table_s{0,1}.parquet exactly (DataFrame.equals).
Output: tables_half/r2_table_s{0.5,1.5,2.5,3.5}.parquet (T, sym, rung, size, tp), build_half_report.json
  python research/diagnostics/phase_agents_half/build_half.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
HERE = Path(__file__).parent
PA = ROOT / "research/diagnostics/phase_agents"
V376 = RD / "v376/tables_hidden"
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
TEND = pd.Timestamp("2026-09-24 08:00", tz="UTC")
SHIFTS = (0.0, 1.0, 0.5, 1.5, 2.5, 3.5)


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def counts(x):
    return {str(k): int(v) for k, v in x.value_counts().sort_index().items()}


def shares(x):
    return {str(k): round(float(v), 4) for k, v in x.value_counts(normalize=True).sort_index().items()}


def main():
    bt = L("bt_half", PA / "build_tables.py")
    ba = L("ba_half", ROOT / "research/diagnostics/phase_agents_aug/build_aug.py")
    v294 = L("v294_half", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    v296 = L("v296_half", RD / "v296/v296_joint_dip_agent.py")
    v293.RUNGS = bt.U
    START0 = v293.START
    assert START0 == pd.Timestamp("2020-08-01", tz="UTC")
    fu = pd.read_parquet(PA / "fills_U.parquet")
    models, info = ba.fit(fu, v293, v296, bt.ANCHORS, "U")
    rep = dict(note="tables only; no simulation / returns", train=info, phases={})
    v293.END = pd.Timestamp("2026-09-25", tz="UTC")
    (HERE / "tables_half").mkdir(exist_ok=True)
    for sft in SHIFTS:
        sh = pd.Timedelta(minutes=int(round(sft * 60)))
        v293.START = START0 + sh
        assets = {s: v293.Asset(s) for s in v293.MAJORS}
        btc = assets["BTCUSDT"]
        assert all(A.t0[0] == START0 + sh and (A.t0[1] - A.t0[0]) == pd.Timedelta(hours=4) for A in assets.values())
        meta, feats, J = [], [], []
        n_ext, n_ext_drop, n_nan_state = 0, 0, 0
        for s, A in assets.items():
            for j, T in enumerate(A.t0):
                if T < bt.ANCHORS[0] or T > TEND + sh or not np.isfinite(A.sig[j]):
                    continue
                kk = j * 240
                if T > Y1 + pd.Timedelta(hours=12) + sh:      # beyond v376 coverage: only bars whose minute-0 state exists
                    if not (np.isfinite(A.C[kk]) and np.isfinite(btc.C[kk])):
                        n_ext_drop += 1
                        continue
                    n_ext += 1
                jj = max(q for q, a0 in enumerate(bt.ANCHORS) if T >= a0)
                base = [A.sp30(kk), 0.0, A.volreg[j], A.trend[j], btc.sp30(kk),
                        np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan, T.hour]
                if not np.all(np.isfinite(base)):
                    n_nan_state += 1
                for k in bt.U:
                    meta.append((T, s, k))
                    feats.append(base[:1] + [k] + base[2:])
                    J.append(jj)
        del assets, btc
        F, J = np.array(feats, float), np.array(J)
        _, tab = ba.to_table(bt, meta, ba.predict(models, F, J, bt.QC))
        dev = (tab["T"] <= bt.TMAX + sh).to_numpy()
        tab = pd.concat([tab[dev], tab[~dev]], ignore_index=True)       # v376/tables_hidden row order
        Jt = np.array([max(q for q, a0 in enumerate(bt.ANCHORS) if t >= a0) for t in tab["T"]])
        recent = (tab["T"] > bt.TMAX + sh).to_numpy()
        st = dict(rows=len(tab), T_min=str(tab["T"].min()), T_max=str(tab["T"].max()),
                  hours=sorted(set(int(h) for h in tab["T"].dt.hour)), minutes=sorted(set(int(m) for m in tab["T"].dt.minute)),
                  n_bars=int(tab["T"].nunique()), rows_dev=int((~recent).sum()), rows_recent=int(recent.sum()),
                  extension_bars_written=n_ext, extension_bars_dropped_no_data=n_ext_drop, bars_with_nan_state=n_nan_state,
                  size_counts=counts(tab["size"]), size_share=shares(tab["size"]), tp_counts=counts(tab["tp"]), tp_share=shares(tab["tp"]),
                  size_share_dev=shares(tab["size"][~recent]), tp_share_dev=shares(tab["tp"][~recent]),
                  size_share_recent=shares(tab["size"][recent]), tp_share_recent=shares(tab["tp"][recent]),
                  size_share_by_anchor={str(q): shares(tab["size"][Jt == q]) for q in range(5)},
                  tp_share_by_anchor={str(q): shares(tab["tp"][Jt == q]) for q in range(5)},
                  dtypes={c: str(t) for c, t in tab.dtypes.items()})
        if sft in (0.0, 1.0):
            ref = pd.read_parquet(V376 / f"r2_table_s{int(sft)}.parquet")
            mine = tab[tab["T"] <= Y1 + pd.Timedelta(hours=12) + sh].reset_index(drop=True)
            st["repro_v376"] = dict(ref_rows=len(ref), mine_rows_in_coverage=len(mine), exact_equal=bool(mine.equals(ref)),
                                    dtypes_equal=bool((mine.dtypes == ref.dtypes).all()),
                                    extra_rows_beyond_v376=int(len(tab) - len(mine)))
            if not st["repro_v376"]["exact_equal"]:
                mg = ref.merge(mine, on=["T", "sym", "rung"], how="outer", suffixes=("_ref", ""), indicator=True)
                b = mg[mg._merge == "both"]
                st["repro_v376"].update(common=len(b), size_eq=float((b["size"] == b["size_ref"]).mean()),
                                        tp_eq=float((b["tp"] == b["tp_ref"]).mean()), unmatched=int((mg._merge != "both").sum()))
        else:
            tab.to_parquet(HERE / "tables_half" / f"r2_table_s{sft}.parquet")
        rep["phases"][f"s{sft}"] = st
        print("shift", sft, json.dumps({k: st[k] for k in st if k not in ("size_share_by_anchor", "tp_share_by_anchor")}), flush=True)
    (HERE / "build_half_report.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
