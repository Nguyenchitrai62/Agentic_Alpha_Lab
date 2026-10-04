"""Dev-only diagnostic (not a registered version): BITFINEX-AUGMENTED R2 dip-agent decision tables (size S1 + take-profit X4, rungs
2.5/3.0/3.5/4.0/5.0) on the four 4h phases s = 0..3. Tables only - no simulation, no return is computed here.

Features: x0..x6 exactly as the deployed R2 agents (v293.fills_of state at fill time / build_tables state at the shifted bar open) plus
  x7  = own-coin bfx_logls          x8 = own-coin bfx_dlog_ls_24h      x9 = own-coin bfx_dlog_short_4h
  x10 = BTC-wide bfx_btc_dlog_ls_24h
with the definitions of research/diagnostics/newdata_bitfinex/features_bitfinex.py (hourly panel data/raw/bitfinex_20261004; a value stamped h is
usable from h + 1h). Own-coin columns are NaN for coins without a Bitfinex margin series (BNB and the 30 alts) and before a series starts;
x10 applies to every coin.
Timing: training rows join AS OF availability strictly before t_fill (fills_of's state is the close of the minute before the fill, i.e. time
t_fill); decision rows join AS OF availability strictly before T + 1 min (state at the close of minute 0 of the shifted bar). Both asserted
row by row; the training join is also cross-checked against features_bitfinex.asof_for_fills.
Models: per anchor 2021-09-24 .. 2025-09-24 the same HGB specs / seeds as build_tables (v296.hgb 10 jj + h for size, 10 jj + h + 3 c for TP
actions, targets clipped [-0.10, 0.08], mu = mean clipped y1.0 of kept rows), trained on the STANDARD-grid fills only
(phase_agents/fills_U.parquet), t_exit < anchor - 7 days, cross-fit halves j % 2. HGB handles NaN natively.
The non-augmented models (x0..x6 only) are refitted in the same run to check that this pipeline reproduces v376/tables_hidden exactly.
Decision tables: build_aug.py bar loop (state at the shifted bar open, model = latest anchor <= T, R2 rules), bars 2021-09-24 + s ..
2026-09-23 12:00 + s (= v376/tables_hidden) plus the bars up to 2026-09-24 08:00 + s whose minute-0 close exists (as tables_aug).
Output: tables_bfx/r2_table_s{s}.parquet (T, sym, rung, size, tp), tables_bfx/raw_bfx_s{s}.parquet, build_bfx_report.json
  python research/diagnostics/phase_agents_bfx/build_bfx.py
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
AUG = ROOT / "research/diagnostics/phase_agents_aug"
V376 = RD / "v376/tables_hidden"
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
TEND = pd.Timestamp("2026-09-24 08:00", tz="UTC")
XB = ["x7", "x8", "x9", "x10"]
OWN = ["bfx_logls", "bfx_dlog_ls_24h", "bfx_dlog_short_4h"]
WIDE = "bfx_btc_dlog_ls_24h"


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def asof(times, frame, cols):
    """Values of `cols` at the latest stamp whose availability (stamp + 1h) is strictly before `times` (asserted)."""
    right = frame[cols].copy()
    right["_avail"] = right.index + pd.Timedelta("1h")
    right = right.sort_values("_avail")
    left = pd.DataFrame({"_t": pd.to_datetime(pd.Series(times), utc=True).to_numpy()})
    left["_t"] = pd.to_datetime(left["_t"], utc=True)
    left["_i"] = np.arange(len(left))
    left = left.sort_values("_t")
    m = pd.merge_asof(left, right, left_on="_t", right_on="_avail", direction="backward", allow_exact_matches=False)
    m = m.sort_values("_i").reset_index(drop=True)
    ok = m["_avail"].notna()
    assert (m.loc[ok, "_avail"] < m.loc[ok, "_t"]).all()
    return m[cols].to_numpy(float)


def bfx_cols(syms, times, feats, fb):
    """x7..x10 for rows (sym, join time); join time = t_fill (training) or T + 1 min (decision)."""
    syms = np.asarray(syms)
    times = pd.to_datetime(pd.Series(times), utc=True).reset_index(drop=True)
    out = np.full((len(syms), 4), np.nan)
    for s in np.unique(syms):
        sel = np.flatnonzero(syms == s)
        coin = fb.SYM_TO_COIN.get(s)
        if coin is not None:
            out[sel, :3] = asof(times.iloc[sel], feats[coin], OWN)
        out[sel, 3] = asof(times.iloc[sel], feats["BTC"], ["bfx_dlog_ls_24h"])[:, 0]
    return out


def fit(X, allf, v293, v296, anchors, label):
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    t_exit = pd.to_datetime(allf["t_exit"], utc=True)
    models, info = [], []
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(t_exit < a0 - v293.EMBARGO)
        assert t_exit[keep].max() < a0 - v293.EMBARGO
        sm = [v296.hgb(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tm = [[v296.hgb(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(3)] for h in (0, 1)]
        mu = float(y1[keep].mean())
        models.append((mu, sm, tm))
        d = dict(anchor=str(a0.date()), rows=int(keep.sum()), half0=int((keep & (half == 0)).sum()), half1=int((keep & (half == 1)).sum()),
                 mu=round(mu, 6), max_t_exit=str(t_exit[keep].max()), cutoff=str(a0 - v293.EMBARGO))
        if X.shape[1] > 7:
            maj = keep & allf.sym.isin(v293.MAJORS).to_numpy()
            d["nan_share_kept"] = {c: round(float(np.isnan(X[keep, 7 + i]).mean()), 4) for i, c in enumerate(XB)}
            d["nan_share_kept_majors"] = {c: round(float(np.isnan(X[maj, 7 + i]).mean()), 4) for i, c in enumerate(XB)}
        info.append(d)
        print("fit", label, d, flush=True)
    return models, info


def nan_by_year(years, Xb, mask=None):
    mask = np.ones(len(years), bool) if mask is None else mask
    return {str(y): dict(rows=int((mask & (years == y)).sum()),
                         **{c: round(float(np.isnan(Xb[mask & (years == y), i]).mean()), 4) for i, c in enumerate(XB)})
            for y in np.unique(years[mask])}


def main():
    bt = L("bt_bfx", PA / "build_tables.py")
    ba = L("ba_bfx", AUG / "build_aug.py")
    fb = L("fb_bfx", ROOT / "research/diagnostics/newdata_bitfinex/features_bitfinex.py")
    v294 = L("v294_bfx", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    v296 = L("v296_bfx", RD / "v296/v296_joint_dip_agent.py")
    v293.RUNGS = bt.U
    START0 = v293.START
    panel = fb.load_panel()
    feats = fb.compute_all_features(panel)
    rep = dict(note="tables only; no simulation / returns",
               features=dict(x7="own bfx_logls", x8="own bfx_dlog_ls_24h", x9="own bfx_dlog_short_4h", x10="BTC-wide bfx_btc_dlog_ls_24h"),
               panel=dict(first=str(panel.index.min()), last=str(panel.index.max()), rows=len(panel)))
    mk = fb._market_frame(feats)   # x10 definition = the module's BTC-wide column
    assert np.allclose(mk[WIDE].to_numpy(), feats["BTC"]["bfx_dlog_ls_24h"].reindex(mk.index).to_numpy(), equal_nan=True)

    fu = pd.read_parquet(PA / "fills_U.parquet")
    assert pd.to_datetime(fu.t_exit, utc=True).max() <= bt.END
    Xb = bfx_cols(fu["sym"].to_numpy(), fu["t_fill"], feats, fb)
    ref = fb.asof_for_fills(fu.assign(t_fill=pd.to_datetime(fu.t_fill, utc=True)), feats=feats)
    refm = np.column_stack([ref[c].to_numpy(float) for c in OWN + [WIDE]])
    assert np.array_equal(np.isnan(refm), np.isnan(Xb)) and np.allclose(np.nan_to_num(refm), np.nan_to_num(Xb))
    X0 = fu[[f"x{q}" for q in range(7)]].to_numpy(float)
    X1 = np.column_stack([X0, Xb])
    yrs = pd.to_datetime(fu.t_fill, utc=True).dt.year.to_numpy()
    rep["train"] = dict(rows=len(fu), join="availability (stamp + 1h) < t_fill, asserted; equals features_bitfinex.asof_for_fills",
                        nan_by_year_all=nan_by_year(yrs, Xb), nan_by_year_majors=nan_by_year(yrs, Xb, fu.sym.isin(v293.MAJORS).to_numpy()))
    print("train nan by year", json.dumps(rep["train"]["nan_by_year_all"]), flush=True)
    m_orig, info_orig = fit(X0, fu, v293, v296, bt.ANCHORS, "orig")
    m_bfx, info_bfx = fit(X1, fu, v293, v296, bt.ANCHORS, "bfx")
    rep["train_orig"], rep["train_bfx"] = info_orig, info_bfx
    (HERE / "tables_bfx").mkdir(exist_ok=True)
    v293.END = pd.Timestamp("2026-09-25", tz="UTC")   # most recent year: minute data only for the state at each bar open
    rep["phases"] = {}
    key = ["T", "sym", "rung"]
    for sft in range(4):
        sh = pd.Timedelta(hours=sft)
        v293.START = START0 + sh
        assets = {s: v293.Asset(s) for s in v293.MAJORS}
        btc = assets["BTCUSDT"]
        meta, F, J = [], [], []
        n_ext, n_ext_drop = 0, 0
        for s, A in assets.items():
            for j, T in enumerate(A.t0):
                if T < bt.ANCHORS[0] or T > TEND + sh or not np.isfinite(A.sig[j]):
                    continue
                kk = j * 240
                if T > Y1 + pd.Timedelta(hours=12) + sh:
                    if not (np.isfinite(A.C[kk]) and np.isfinite(btc.C[kk])):
                        n_ext_drop += 1
                        continue
                    n_ext += 1
                jj = max(q for q, a0 in enumerate(bt.ANCHORS) if T >= a0)
                base = [A.sp30(kk), 0.0, A.volreg[j], A.trend[j], btc.sp30(kk),
                        np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan, T.hour]
                for k in bt.U:
                    meta.append((T, s, k))
                    F.append(base[:1] + [k] + base[2:])
                    J.append(jj)
        del assets, btc
        F, J = np.array(F, float), np.array(J)
        Tm = pd.to_datetime(pd.Series([m_[0] for m_ in meta]), utc=True)
        sy = np.array([m_[1] for m_ in meta])
        Fb = bfx_cols(sy, Tm + pd.Timedelta(minutes=1), feats, fb)
        _, tab_o = ba.to_table(bt, meta, ba.predict(m_orig, F, J, bt.QC))
        raw_b, tab_b = ba.to_table(bt, meta, ba.predict(m_bfx, np.column_stack([F, Fb]), J, bt.QC))
        for i, c in enumerate(XB):
            raw_b[c] = Fb[:, i]
        tab_b.to_parquet(HERE / "tables_bfx" / f"r2_table_s{sft}.parquet")
        raw_b.to_parquet(HERE / "tables_bfx" / f"raw_bfx_s{sft}.parquet")
        ref = pd.read_parquet(V376 / f"r2_table_s{sft}.parquet")
        mo = ref.merge(tab_o, on=key, how="outer", suffixes=("_ref", ""), indicator=True)
        both = mo[mo._merge == "both"]
        mine_only = mo[mo._merge == "right_only"]
        repro = dict(ref_rows=len(ref), mine_rows=len(tab_o), common=len(both), ref_only=int((mo._merge == "left_only").sum()),
                     mine_only=len(mine_only), mine_only_T_min=str(mine_only["T"].min()) if len(mine_only) else None,
                     size_eq=float((both["size"] == both["size_ref"]).mean()), tp_eq=float((both["tp"] == both["tp_ref"]).mean()))
        assert repro["ref_only"] == 0 and repro["size_eq"] == 1.0 and repro["tp_eq"] == 1.0, repro
        mb = ref.merge(tab_b, on=key, how="inner", suffixes=("_ref", ""))
        recent = (mb["T"] > bt.TMAX + sh).to_numpy()
        anc = np.array([max(q for q, a0 in enumerate(bt.ANCHORS) if t >= a0) for t in mb["T"]])
        is_r2 = np.isin(np.array([m_[2] for m_ in meta]), bt.R2)
        st = dict(rows=len(tab_b), T_min=str(tab_b["T"].min()), T_max=str(tab_b["T"].max()),
                  hours=sorted(set(int(h) for h in tab_b["T"].dt.hour)),
                  extension_bars_written=n_ext, extension_bars_dropped_no_data=n_ext_drop,
                  decision_join="availability (stamp + 1h) < T + 1 min, asserted",
                  decision_nan_by_year=nan_by_year(Tm.dt.year.to_numpy(), Fb, is_r2),
                  decision_nan_by_sym={s: {c: round(float(np.isnan(Fb[is_r2 & (sy == s), i]).mean()), 4) for i, c in enumerate(XB)}
                                       for s in v293.MAJORS},
                  repro_nonaug_vs_v376=repro, changed_all=ba.changes(mb), changed_dev=ba.changes(mb[~recent]),
                  changed_recent_year=ba.changes(mb[recent]),
                  changed_by_anchor={str(q): {k: v for k, v in ba.changes(mb[anc == q]).items() if k in ("rows", "size_changed", "tp_changed")}
                                     for q in range(5)})
        rep["phases"][f"s{sft}"] = st
        print("shift", sft, json.dumps({k: st[k] for k in ("rows", "T_min", "T_max", "extension_bars_written", "repro_nonaug_vs_v376")}), flush=True)
        print("   changed dev", st["changed_dev"]["size_changed"], st["changed_dev"]["tp_changed"],
              "recent", st["changed_recent_year"]["size_changed"], st["changed_recent_year"]["tp_changed"], flush=True)
    (HERE / "build_bfx_report.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
