"""v202 blind audit Part A replication.

Blind rule: does NOT read research v202 files, the v202 result json, nor
the v202 quarterly-retrain source, until replication.json is saved.
Independent implementation from OPENCODE_V202_AUDIT.md, using
research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
as the gate engine base (AGENTS.md 2026-09-27 user goal, gate cost model
and current execution assumptions). Base: the v199 replication in
v199_audit (v151 books, sleeve rung size x1.5, stop-risk budget 0.12,
rung stop 5 sigma_4h, TP 1 sigma_4h, v197 selected rules).

A: quarterly walk-forward of the book members. Quarterly anchors =
2021-09-24 + k * 3 calendar months, k = 0..19; each anchor's models
predict only [anchor, next anchor) (last: until 2026-09-24); per-target
cutoffs = anchor - embargo as in the audited v92/v94/v103/v129 code.
Re-build member A (v144 books_v142) and member B (v151
books_with_options) with this schedule IN FULL for the first two
quarterly anchors (2021-09-24 and 2021-12-24) and compare those rows
with artifacts/research/engine_real/members_quarterly.parquet (columns
(member, symbol)); then use the cache for the full evaluation:
pipelines (A+B)/2 annual (members_v154.parquet) and (Aq+Bq)/2 quarterly
under engine_user with the v197 rules. Report dev4, 5y, last year, gate
DD, first-four yearly nets. Save replication.json.

Quarterly train/predict logic below copies the audited cutoffs exactly:
  v92  (7d): EMBARGO_BARS = 42 + 10*6 = 102; tr.t + 4*(42+1) < cutoff.
  v94  (3/7/14d): EMBARGO_BARS = 84 + 10*6 = 144; per-h tr.t + 4*(h+1) < cutoff.
  v103 (1/3d): EMBARGO = 18 + 10*6 = 78; per-h tr.t + 4*(h+1) < cutoff.
  vol  (42-bar forward std): embargo 102 bars; tr.t + 4*(42+2) < cutoff.
Test window for a quarterly anchor a is [a, next_a) with next_a the
following quarterly anchor (last: 2026-09-24). HGB hyperparameters are
the audited v92 ones on every model. Member B merges the v150 Deribit
options features on t before the v142 cross-sectional step; vol models
exclude the OPT columns. Books use the v144 construction (tranched over
all 6 phases, 0.25/0.25/0.5 with own causal vol targets, trim at
p103.t.min()).

v197 rules (selected mult 1.5): engine_user simulate with m_sl = 4.0,
m_sleeve_sl = 5.0, sleeve True, d_limit = 0.001, win_end = 239,
sleeve_risk_budget = 0.12, size_mult = 1.5, target 0.25, cap 2.0,
gap 0.02, m_sleeve_tp 1.0, rungs (2.5, 3.0, 3.5, 4.0).

Updated conventions from the v188 audit (asserted so self-contained):
  C1 1m-marked DD peaks over the minute path (maximum(e, ex) peaks).
  C2 held-position stop wins a same-minute tie with a new book fill
     (seg_end = fill_min + 1, pending order cancelled).

Run from the repository root so every data path below stays relative.

Leakage notes (checked in code, reported in COMPARISON.md Part B):
  L1 Feature timing: books at t, opens at t/t-1, sigma windows ending at
     t, s/g known at the decision; cubes row i = holding bar T.
  L2 No label window: no forward return read except fills and T/T+4h exits.
  L3 Fit windows: quarterly cutoffs anchor - embargo per target above;
     no statistic fit on any test quarter here; selection on first four
     anchor years only.
  L4 Fill timing: book limit minutes 2..238 strict trade-through, held
     SL/TP from minute 0 with stop-wins-tie and stop-first, sleeve
     trigger 16..238 with exits strictly after the fill minute.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

AUD = Path("research/parallel/rounds/parallel-20260906-r2") / "v202_audit"
OUT = AUD / "replication.json"
CACHE = Path("artifacts/research/engine_real")
MEMBERS_ANNUAL_FILE = CACHE / "members_v154.parquet"
MEMBERS_Q_FILE = CACHE / "members_quarterly.parquet"
BOOKS_FILE = CACHE / "books_v154.parquet"
OPENS_FILE = CACHE / "opens_v154.parquet"

M_SL = 4.0
M_SLEEVE_SL = 5.0
M_SLEEVE_TP = 1.0
D_LIMIT = 0.001
WIN_END = 239
GAP = 0.02
TARGET = 0.25
CAP = 2.0
SIZE_MULT = 1.5
SLEEVE_X = 0.12

PD = 6
H92 = 42
EMB92 = H92 + 10 * PD
H94 = (18, 42, 84)
EMB94 = max(H94) + 10 * PD
HS103 = (6, 18)
EMB103 = max(HS103) + 10 * PD
HV = 42
EMBV = H92 + 10 * PD


def quarterly_anchors():
    out = []
    y, m = 2021, 9
    for _ in range(20):
        out.append(f"{y:04d}-{m:02d}-24")
        m += 3
        if m > 12:
            m -= 12
            y += 1
    return out


QANCHORS = quarterly_anchors()
QNEXT = {a: (QANCHORS[i + 1] if i + 1 < len(QANCHORS) else "2026-09-24") for i, a in enumerate(QANCHORS)}


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, Path("research/parallel/rounds/parallel-20260906-r2") / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hgb():
    return HistGradientBoostingRegressor(
        max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
        l2_regularization=1.0, random_state=0)


def q_v92_predict(panel, feats, anchor, end):
    a = pd.Timestamp(anchor, tz="UTC")
    e = pd.Timestamp(end, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * EMB92)
    tr = panel[(panel.t < cutoff) & panel.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H92 + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < e)].copy()
    m = hgb()
    m.fit(tr[feats], tr["y"])
    te["pred"] = m.predict(te[feats])
    return te, len(tr)


def q_v94_predict(panel, feats, anchor, end):
    a = pd.Timestamp(anchor, tz="UTC")
    e = pd.Timestamp(end, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * EMB94)
    te = panel[(panel.t >= a) & (panel.t < e)].copy()
    preds, rows = [], {}
    for hh in H94:
        tr = panel[(panel.t < cutoff) & panel[f"y{hh}"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (hh + 1)) < cutoff]
        m = hgb()
        m.fit(tr[feats], tr[f"y{hh}"])
        preds.append(m.predict(te[feats]))
        rows[hh] = len(tr)
    te["pred"] = np.mean(preds, axis=0)
    te["y"] = te["y42"]
    return te, rows


def q_v103_predict(panel, feats, anchor, end):
    a = pd.Timestamp(anchor, tz="UTC")
    e = pd.Timestamp(end, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * EMB103)
    te = panel[(panel.t >= a) & (panel.t < e)].copy()
    preds, rows = [], {}
    for hh in HS103:
        tr = panel[(panel.t < cutoff) & panel[f"y{hh}"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (hh + 1)) < cutoff]
        m = hgb()
        m.fit(tr[feats], tr[f"y{hh}"])
        preds.append(m.predict(te[feats]))
        rows[hh] = len(tr)
    te["pred"] = np.mean(preds, axis=0)
    return te, rows


def add_fv(panel):
    out = []
    for _s, g in panel.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        r = np.log(g["open"]).diff()
        g["fv"] = np.log(r.rolling(HV).std().shift(-(HV + 1)))
        out.append(g)
    return pd.concat(out, ignore_index=True)


def q_vol_predict(panel, feats, anchor, end):
    p = add_fv(panel)
    a = pd.Timestamp(anchor, tz="UTC")
    e = pd.Timestamp(end, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * EMBV)
    tr = p[(p.t < cutoff) & p.fv.notna() & np.isfinite(p.fv)]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (HV + 2)) < cutoff]
    te = p[(p.t >= a) & (p.t < e)].copy()
    m = hgb()
    te["pvol"] = np.exp(m.fit(tr[feats], tr["fv"]).predict(te[feats]))
    return te[["t", "sym", "pvol"]], len(tr)


def main():
    eu = _load("v202_audit_engine_user", "engine_user/engine_user.py")
    print(f"engine_user maker={eu.MAKER} taker={eu.TAKER} fund_long={eu.FUND_LONG}", flush=True)
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    assert eu.D_LIMIT == 0.001 and eu.SIZE == 0.25 and eu.S_REF == 1.657
    assert tuple(eu.RUNGS) == (2.5, 3.0, 3.5, 4.0)
    sim_src = inspect.getsource(eu.simulate)
    sum_src = inspect.getsource(eu.summarize)
    assert "fill_min + 1" in sim_src, "C2 missing"
    assert "eq_max" in sim_src, "C1 eq_max missing"
    assert "peak1" in sum_src, "C1 peak1 missing"
    assert "np.maximum(e, ex)" in sum_src, "C1 peak missing"
    print("conventions C1/C2 verified", flush=True)
    assert QANCHORS[0] == "2021-09-24" and QANCHORS[1] == "2021-12-24"
    assert QANCHORS[19] == "2026-06-24" and QNEXT[QANCHORS[19]] == "2026-09-24"
    assert len(QANCHORS) == 20
    print(f"quarterly anchors {QANCHORS[0]} .. {QANCHORS[-1]} n=20", flush=True)

    v142 = _load("v142mod", "v142/v142_cross_sectional_features.py")
    v150 = _load("v150mod", "v150/v150_options_flow.py")
    v144 = v142.v129.v125.v115.v114.v113
    ext = v142.v125.v115.v114.v113
    v103 = v142.v103
    v125 = v142.v125
    v129mod = v142.v129
    BASE, FLOWX, OPT = v142.BASE, v142.FLOWX, v150.OPT
    v115mod = v142.v125.v115
    v115mod.v114.v113.cb_bars = v115mod.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    print(f"BASE={BASE} FLOWX={FLOWX} OPT={OPT}", flush=True)

    print("building base panels (extended history) ...", flush=True)
    p92 = ext.v92.build()
    f92_base = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    p103 = v103.build()
    f103_base = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    print(f"p92 {p92.shape} p103 {p103.shape}", flush=True)
    feats_opt = v150.opt_features()
    print(f"options features {feats_opt.shape}", flush=True)

    members_q = pd.read_parquet(MEMBERS_Q_FILE)
    print(f"members_quarterly {members_q.shape} {members_q.index.min()} .. {members_q.index.max()}", flush=True)
    assert list(members_q.columns.get_level_values(0).unique()) >= ["A", "B"]

    rebuild_anchors = [QANCHORS[0], QANCHORS[1]]
    print(f"rebuilding IN FULL for quarterly anchors {rebuild_anchors}", flush=True)

    results = {}
    for member in ("A", "B"):
        if member == "A":
            p92m = p92
            p103m = p103
        else:
            p92m = p92.merge(feats_opt, on="t", how="left")
            p103m = p103.merge(feats_opt, on="t", how="left")
        p92x = v142.add_xs(p92m, BASE)
        f92x = [c for c in p92x.columns if c not in ("y", "t", "open", "sym", "bar")]
        p94m = ext.v94.add_targets(p92x)
        f94 = [c for c in p94m.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
        p103x = v142.add_xs(p103m, BASE + FLOWX)
        f103 = [c for c in p103x.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
        f92v = [c for c in f92_base if c not in OPT]
        f103v = [c for c in f103_base if c not in OPT]
        lo_parts, ls_parts, fl_parts, pv92_parts, pv103_parts = [], [], [], [], []
        train_rows = {}
        for qa in rebuild_anchors:
            qe = QNEXT[qa]
            te92, n92 = q_v92_predict(p92x, f92x, qa, qe)
            lo_parts.append(te92)
            te94, n94 = q_v94_predict(p94m, f94, qa, qe)
            ls_parts.append(te94)
            te103, n103 = q_v103_predict(p103x, f103, qa, qe)
            fl_parts.append(te103)
            pv92, nv92 = q_vol_predict(p92m, f92v, qa, qe)
            pv92_parts.append(pv92)
            pv103, nv103 = q_vol_predict(p103m, f103v, qa, qe)
            pv103_parts.append(pv103)
            train_rows[qa] = {"v92": n92, "v94": n94, "v103": n103, "vol92": nv92, "vol103": nv103}
            print(f"member {member} quarter {qa}..{qe} rows v92={n92} v94={n94} v103={n103} vol=({nv92},{nv103}) "
                  f"pred={len(te92)},{len(te94)},{len(te103)}", flush=True)
        lo = pd.concat(lo_parts, ignore_index=True)
        ls = pd.concat(ls_parts, ignore_index=True)
        fl = pd.concat(fl_parts, ignore_index=True)
        pv92c = pd.concat(pv92_parts, ignore_index=True)
        pv103c = pd.concat(pv103_parts, ignore_index=True)

        def swap(df, pv):
            d = df.merge(pv, on=["t", "sym"], how="left")
            d["vol42"] = d["pvol"].fillna(d["vol42"])
            return d.drop(columns="pvol")

        ph = list(range(PD))
        W_lo = v125.phased(v125.raw_lo(swap(lo, pv92c)), ph)
        W94 = v125.phased(v125.raw_ls(swap(ls, pv92c)), ph)
        W103 = v125.phased(v125.raw_ls(swap(fl, pv103c)), ph)
        idx = W_lo.index.union(W94.index).union(W103.index)
        idx = idx[idx >= p103m.t.min()]
        books = (0.25 * W_lo.reindex(idx).fillna(0.0).mul(
            ext.v92.vol_target_scale(p92m, W_lo).reindex(idx).fillna(1.0), axis=0)
            + 0.25 * W94.reindex(idx).fillna(0.0).mul(
            ext.v94.vol_target_scale(p92m, W94).reindex(idx).fillna(1.0), axis=0)
            + 0.5 * W103.reindex(idx).fillna(0.0).mul(
            ext.v94.vol_target_scale(p103m, W103).reindex(idx).fillna(1.0), axis=0))
        cached = members_q[member].reindex(idx)
        common = books.index.intersection(cached.index)
        diff = (books.reindex(common).fillna(0.0) - cached.reindex(common).fillna(0.0)).abs()
        maxd = float(diff.max().max())
        meand = float(diff.mean().mean())
        print(f"member {member}: rebuilt {books.shape} cached-slice {cached.shape} common {len(common)} "
              f"max_abs_diff={maxd:.6f} mean_abs_diff={meand:.8f}", flush=True)
        results[member] = {
            "rebuild_anchors": rebuild_anchors,
            "train_rows": train_rows,
            "rebuilt_shape": list(books.shape),
            "common_bars": int(len(common)),
            "max_abs_diff_vs_cache": maxd,
            "mean_abs_diff_vs_cache": meand,
            "match": bool(maxd == 0.0),
        }

    mem_ann = pd.read_parquet(MEMBERS_ANNUAL_FILE)
    books_cache = pd.read_parquet(BOOKS_FILE)
    opens = pd.read_parquet(OPENS_FILE).sort_index()
    assert set(mem_ann.columns.get_level_values(0).unique()) >= {"A", "B", "D"}
    cols = list(books_cache.columns)
    A_ann = mem_ann["A"].reindex(books_cache.index)[cols].fillna(0.0)
    B_ann = mem_ann["B"].reindex(books_cache.index)[cols].fillna(0.0)
    P_ann = ((A_ann + B_ann) / 2).sort_index()
    assert list(P_ann.index) == list(books_cache.index)
    Aq = members_q["A"]
    Bq = members_q["B"]
    qcols = list(Aq.columns)
    P_q = ((Aq.fillna(0.0) + Bq.fillna(0.0)) / 2).sort_index()
    print(f"annual P {P_ann.shape} quarterly P {P_q.shape} opens {opens.shape}", flush=True)

    rows = {}
    for key, P in (("annual_(A+B)/2", P_ann), ("quarterly_(Aq+Bq)/2", P_q)):
        prep = eu.prepare(P, opens)
        print(f"simulate {key} with v197 selected (mult 1.5, X 0.12) ...", flush=True)
        out = eu.simulate(
            P, opens, prep, m_sl=float(M_SL), m_sleeve_sl=float(M_SLEEVE_SL),
            sleeve=True, target=float(TARGET), cap=float(CAP),
            d_limit=float(D_LIMIT), win_end=int(WIN_END),
            sleeve_risk_budget=float(SLEEVE_X), gap=float(GAP),
            m_sleeve_tp=float(M_SLEEVE_TP), size_mult=float(SIZE_MULT))
        yearly = out["yearly"]
        assert [y["anchor"] for y in yearly] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
        first4 = yearly[:4]
        losing_first4 = sum(1 for y in first4 if y["net_pct"] < 0)
        geo4 = float(np.prod([1 + y["net_pct"] / 100 for y in first4]) ** (1 / 4) - 1)
        dev4_check = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4_check - out["monthly_dev4"]) < 0.002, (key, dev4_check, out["monthly_dev4"])
        assert abs(out["gate_dd"] - max(out["dd_4h"], out["dd_1m"])) < 1e-9, key
        rows[key] = {
            "pipeline": key,
            "books": "v151=(A+B)/2" if key.startswith("annual") else "quarterly (Aq+Bq)/2",
            "sleeve": True,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "m_sleeve_tp_mult": float(M_SLEEVE_TP),
            "d_limit": float(D_LIMIT),
            "win_end": int(WIN_END),
            "target": float(TARGET),
            "cap": float(CAP),
            "size_mult": float(SIZE_MULT),
            "sleeve_risk_budget": float(SLEEVE_X),
            "gap": float(GAP),
            "rungs": list(eu.RUNGS),
            "monthly_dev4": out["monthly_dev4"],
            "monthly_5y": out["monthly_5y"],
            "monthly_last_year": out["monthly_last_year"],
            "yearly": yearly,
            "yearly_net_pct": [y["net_pct"] for y in yearly],
            "yearly_monthly_pct": [y["monthly_pct"] for y in yearly],
            "yearly_dd_1m_pct": [y["dd_1m_pct"] for y in yearly],
            "losing_years": out["losing_years"],
            "losing_years_first4": losing_first4,
            "dd_4h": out["dd_4h"],
            "dd_1m": out["dd_1m"],
            "gate_dd": out["gate_dd"],
            "gate_pass": out["gate_pass"],
            "stats": out["stats"],
        }
        print(f"{key}: dev4={out['monthly_dev4']} 5y={out['monthly_5y']} last={out['monthly_last_year']} "
              f"gateDD={out['gate_dd']} lose={out['losing_years']} lose4={losing_first4} "
              f"nets={[y['net_pct'] for y in yearly]}", flush=True)

    eligible = {k: v for k, v in rows.items() if v["gate_dd"] <= 20 and v["losing_years_first4"] == 0}
    selection = max(eligible, key=lambda k: eligible[k]["monthly_dev4"]) if eligible else None
    print(f"eligible {sorted(eligible)} selection {selection}", flush=True)

    replication = {
        "version": "v202_audit_replication",
        "blind": "did_not_open_research_v202_until_this_file_saved",
        "quarterly_anchors": QANCHORS,
        "quarterly_next": QNEXT,
        "cutoffs": {
            "v92_embargo_bars": EMB92,
            "v94_embargo_bars": EMB94,
            "v103_embargo_bars": EMB103,
            "vol_embargo_bars": EMBV,
            "rule": "cutoff = anchor - embargo as in audited v92/v94/v103/v129 code; "
                    "per-horizon label-realized condition tr.t + (h+1)*4h < cutoff; "
                    "test window [anchor, next_anchor), last until 2026-09-24",
        },
        "rebuild": results,
        "members_check": {
            "annual_file": "artifacts/research/engine_real/members_v154.parquet",
            "quarterly_file": "artifacts/research/engine_real/members_quarterly.parquet",
            "books_file": "artifacts/research/engine_real/books_v154.parquet",
            "opens_file": "artifacts/research/engine_real/opens_v154.parquet",
            "annual_shape": list(mem_ann.shape),
            "quarterly_shape": list(members_q.shape),
        },
        "engine": {
            "file": "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py",
            "maker": eu.MAKER,
            "taker": eu.TAKER,
            "d_limit": float(D_LIMIT),
            "win_end": int(WIN_END),
            "fund_long": eu.FUND_LONG,
            "default_rungs": list(eu.RUNGS),
            "size": eu.SIZE,
            "s_ref": eu.S_REF,
            "m_sl": M_SL,
            "m_sleeve_sl": float(M_SLEEVE_SL),
            "m_sleeve_tp_mult": float(M_SLEEVE_TP),
            "target": float(TARGET),
            "cap": float(CAP),
            "gap": float(GAP),
            "size_mult": float(SIZE_MULT),
            "sleeve_risk_budget": float(SLEEVE_X),
            "v197_rules": "selected mult 1.5: size_mult 1.5, budget 0.12, m 4, rung SL 5, TP 1, limit 0.001/239",
            "conventions": [
                "C1 1m-marked DD peaks over the minute path (intrabar highs count)",
                "C2 held-position stop wins a same-minute tie with a new book fill (pending order cancelled)",
            ],
        },
        "rows": rows,
        "selection_rule": "best monthly_dev4 among rows with gate_dd <= 20 and no losing year in the first four anchor years",
        "eligible": sorted(eligible),
        "selection": selection,
    }
    AUD.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
