"""Dev-only diagnostic (not a registered version): PHASE-AUGMENTED R2 dip-agent decision tables (size S1 + take-profit X4, rungs
2.5/3.0/3.5/4.0/5.0) on the four 4h phases s = 0..3. Tables only - no simulation, no return is computed here.

Models: per anchor 2021-09-24 .. 2025-09-24 the same HGB specs as research/diagnostics/phase_agents/build_tables.py (v296.hgb seeds 10 jj + h
for size, 10 jj + h + 3 c for the TP actions, targets clipped to [-0.10, 0.08], mu = mean clipped y1.0 of the kept rows), but fitted on the
pooled 35-coin dip fills of ALL FOUR phases (fills_s{0..3}.parquet from fills_phase.py, concatenated in phase order, minute data only up to
2025-09-25) that exited before anchor - 7 days; cross-fit halves = j % 2 of each fill's own phase grid.
The non-augmented models (fills_U.parquet only, = build_tables / v376) are refitted too, only to check that this pipeline reproduces
v376/tables_hidden exactly (so the "changed vs non-augmented" shares compare like with like).
Decision tables per phase: state at the shifted holding bar open (build_tables logic: minute-0 close, shifted grid's own 4h opens, hour = T.hour),
model = latest anchor <= T, rules() of R2. Bars: 2021-09-24 + s .. 2026-09-23 12:00 + s (= v376/tables_hidden coverage; the 1m arrays are
loaded up to 2026-09-25 as in v376, but every state feature is a past-only rolling value, so dev bars are unaffected - checked by reproducing
v376/tables_hidden with the non-augmented models; the most recent year uses the anchor-2025 model and minute data only for the state), plus bars up to 2026-09-24 08:00 + s whose minute-0 close exists (minute data ends
2026-09-23 23:59, so bars from 2026-09-24 00:00 have no state and are not written).
Output: tables_aug/r2_table_s{s}.parquet (T, sym, rung, size, tp), tables_aug/raw_aug_s{s}.parquet, build_aug_report.json
  python research/diagnostics/phase_agents_aug/build_aug.py
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


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def fit(allf, v293, v296, anchors, label):
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    t_exit = pd.to_datetime(allf["t_exit"], utc=True)
    ph = allf["phase"].to_numpy() if "phase" in allf else np.zeros(len(allf), int)
    models, info = [], []
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(t_exit < a0 - v293.EMBARGO)
        assert t_exit[keep].max() < a0 - v293.EMBARGO
        sm = [v296.hgb(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tm = [[v296.hgb(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(3)] for h in (0, 1)]
        mu = float(y1[keep].mean())
        models.append((mu, sm, tm))
        info.append(dict(anchor=str(a0.date()), rows=int(keep.sum()), half0=int((keep & (half == 0)).sum()), half1=int((keep & (half == 1)).sum()),
                         rows_by_phase={str(p): int((keep & (ph == p)).sum()) for p in np.unique(ph)}, mu=round(mu, 6),
                         max_t_exit=str(t_exit[keep].max())))
        print("fit", label, info[-1], flush=True)
    return models, info


def predict(models, F, J, QC):
    res = {c: np.full(len(F), np.nan) for c in QC}
    for jj, (mu, sm, tm) in enumerate(models):
        sel = J == jj
        if not sel.any():
            continue
        x = F[sel]
        res["pa"][sel], res["pb"][sel] = sm[0].predict(x), sm[1].predict(x)
        res["mu"][sel] = mu
        for c in range(3):
            res[f"qa{c}"][sel] = tm[0][c].predict(x)
            res[f"qb{c}"][sel] = tm[1][c].predict(x)
    return res


def to_table(bt, meta, res):
    raw = pd.DataFrame({"T": [m_[0] for m_ in meta], "sym": [m_[1] for m_ in meta], "k": [m_[2] for m_ in meta], **res})
    g = raw[raw.k.isin(bt.R2)].copy()
    g["rung"] = g.k.map({k: r for r, k in enumerate(bt.R2)}).astype(int)
    g["size"], g["tp"] = bt.rules(g)
    return raw, g[["T", "sym", "rung", "size", "tp"]].reset_index(drop=True)


def changes(d):
    return dict(rows=len(d), size_changed=round(float((d["size"] != d["size_ref"]).mean()), 4),
                tp_changed=round(float((d["tp"] != d["tp_ref"]).mean()), 4),
                either_changed=round(float(((d["size"] != d["size_ref"]) | (d["tp"] != d["tp_ref"])).mean()), 4),
                size_counts_ref={str(k): int(v) for k, v in d["size_ref"].value_counts().sort_index().items()},
                size_counts_aug={str(k): int(v) for k, v in d["size"].value_counts().sort_index().items()},
                tp_counts_ref={str(k): int(v) for k, v in d["tp_ref"].value_counts().sort_index().items()},
                tp_counts_aug={str(k): int(v) for k, v in d["tp"].value_counts().sort_index().items()})


def main():
    bt = L("bt_aug", PA / "build_tables.py")
    v294 = L("v294_aug", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    v296 = L("v296_aug", RD / "v296/v296_joint_dip_agent.py")
    v293.RUNGS = bt.U
    START0 = v293.START
    rep = dict(note="tables only; no simulation / returns", fills={})
    fu = pd.read_parquet(PA / "fills_U.parquet")
    parts = []
    for s in range(4):
        f = pd.read_parquet(HERE / f"fills_s{s}.parquet")
        c = json.loads((HERE / f"fills_check_s{s}.json").read_text())
        assert pd.to_datetime(f.t_exit, utc=True).max() <= bt.END and pd.to_datetime(f.t_fill, utc=True).max() < bt.END
        rep["fills"][f"s{s}"] = dict(rows=len(f), t_fill_min=str(f.t_fill.min()), t_exit_max=str(f.t_exit.max()),
                                     usable_by_anchor_2025=int((pd.to_datetime(f.t_exit, utc=True) < bt.ANCHORS[4] - v293.EMBARGO).sum()),
                                     majors=int(f.sym.isin(v293.MAJORS).sum()), equals_fills_U=c.get("equals_fills_U"))
        parts.append(f)
    assert rep["fills"]["s0"]["equals_fills_U"] is True
    aug = pd.concat(parts, ignore_index=True)
    m_orig, info_orig = fit(fu, v293, v296, bt.ANCHORS, "orig")
    m_aug, info_aug = fit(aug, v293, v296, bt.ANCHORS, "aug")
    rep["train_orig"], rep["train_aug"] = info_orig, info_aug
    (HERE / "tables_aug").mkdir(exist_ok=True)
    v293.END = pd.Timestamp("2026-09-25", tz="UTC")   # most recent year: minute data only for the state at each bar open
    rep["phases"] = {}
    for sft in range(4):
        sh = pd.Timedelta(hours=sft)
        v293.START = START0 + sh
        assets = {s: v293.Asset(s) for s in v293.MAJORS}
        btc = assets["BTCUSDT"]
        meta, feats, J = [], [], []
        n_ext, n_ext_drop = 0, 0
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
                for k in bt.U:
                    meta.append((T, s, k))
                    feats.append(base[:1] + [k] + base[2:])
                    J.append(jj)
        del assets, btc
        F, J = np.array(feats, float), np.array(J)
        _, tab_o = to_table(bt, meta, predict(m_orig, F, J, bt.QC))
        raw_a, tab_a = to_table(bt, meta, predict(m_aug, F, J, bt.QC))
        tab_a.to_parquet(HERE / "tables_aug" / f"r2_table_s{sft}.parquet")
        raw_a.to_parquet(HERE / "tables_aug" / f"raw_aug_s{sft}.parquet")
        ref = pd.read_parquet(V376 / f"r2_table_s{sft}.parquet")
        key = ["T", "sym", "rung"]
        mo = ref.merge(tab_o, on=key, how="outer", suffixes=("_ref", ""), indicator=True)
        both = mo[mo._merge == "both"]
        mine_only = mo[mo._merge == "right_only"]
        repro = dict(ref_rows=len(ref), mine_rows=len(tab_o), common=len(both), ref_only=int((mo._merge == "left_only").sum()),
                     mine_only=len(mine_only), mine_only_T_min=str(mine_only["T"].min()) if len(mine_only) else None,
                     size_eq=float((both["size"] == both["size_ref"]).mean()), tp_eq=float((both["tp"] == both["tp_ref"]).mean()))
        ma = ref.merge(tab_a, on=key, how="inner", suffixes=("_ref", ""))
        recent = (ma["T"] > bt.TMAX + sh).to_numpy()
        anc = np.array([max(q for q, a0 in enumerate(bt.ANCHORS) if t >= a0) for t in ma["T"]])
        st = dict(rows=len(tab_a), T_min=str(tab_a["T"].min()), T_max=str(tab_a["T"].max()), hours=sorted(set(int(h) for h in tab_a["T"].dt.hour)),
                  extension_bars_written=n_ext, extension_bars_dropped_no_data=n_ext_drop,
                  repro_nonaug_vs_v376=repro, changed_all=changes(ma), changed_dev=changes(ma[~recent]), changed_recent_year=changes(ma[recent]),
                  changed_by_anchor={str(q): {k: v for k, v in changes(ma[anc == q]).items() if k in ("rows", "size_changed", "tp_changed")}
                                     for q in range(5)})
        rep["phases"][f"s{sft}"] = st
        print("shift", sft, json.dumps({k: st[k] for k in ("rows", "T_min", "T_max", "extension_bars_written", "repro_nonaug_vs_v376")}), flush=True)
        print("   changed dev", st["changed_dev"]["size_changed"], st["changed_dev"]["tp_changed"],
              "recent", st["changed_recent_year"]["size_changed"], st["changed_recent_year"]["tp_changed"], flush=True)
    (HERE / "build_aug_report.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
