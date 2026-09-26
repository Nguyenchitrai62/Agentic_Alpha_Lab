"""v190 blind audit Part A replication.

Blind rule: does NOT read research v190 files, v190_result.json, nor the
v190 pipeline source, until replication.json is saved. Independent
implementation from OPENCODE_V190_AUDIT.md plus AGENTS.md (2026-09-27)
and engine_user.py as the gate engine base.

A: v103 panel p103 (from v144 books_v142()), features f103 = columns
except y*, t, open, sym, bar. Labels per (t, sym) from the asset 4h bars
(v92.load_asset as used by the panel): entry = open(t+1); sigma_d =
std(360 4h open pct changes ending at t, min 120) * sqrt(6); long:
SL = e(1 - 4 sd), TP = e(1 + 8 sd), scan bars t+1..t+42 (low <= SL
first, else high >= TP; SL first if both in one bar), else exit
open(t+43); ret - 0.00075 - 0.0001 * bars_held/2; short mirrored (no
funding); target = ret / sd clipped [-4, 8]. HGB(max_depth 4, lr 0.03,
400 iters, min_samples_leaf 300, l2 1, random_state 0) per anchor and
side on rows with t + 43 bars < anchor - 78 bars; pred = p_long -
p_short on the anchor year. Book E = v125.phased(v125.raw_ls(frame),
6 phases) with the v129 vol forecast replacing vol42, times
ext.v94.vol_target_scale. Rows under engine_user (SL/TP m = 4, sleeve):
v151 = (A+B)/2 members, E alone, 0.5 v151 + 0.5 E. Report IC per
anchor, monthly_dev4, 5y, DD. Save replication.json.

Frozen engine_user spec (from OPENCODE_V188_AUDIT.md, implemented in
engine_user.py and re-stated here so the audit is self-contained):
  E1 Inputs: books (pipeline weights), opens (4h opens), 1m klines of
     the majors. Decision bar t is the books index; holding bar T = t + 4h.
  E2 Vol target: realized[t] = 0.8 * sum_j books[t-2,j] *
     (open[t,j]/open[t-1,j] - 1); vol = rolling std 360 (min 120) *
     sqrt(2190); s = min(0.25/vol, 2) (1 if NaN); governor g[t] =
     clip((0.20 - (1 - eq[t-2]/max eq over the 540 bars ending t-2))/0.10,
     0, 1). Live span 2021-09-24 .. +1825 d. Target weight =
     0.8 * s * books[t] * g.
  E3 Quantities q = w / open(T) at bar start (w drifted from previous bar
     end). Order dw = target - w (skip if |dw|*equity*10000 < min notional:
     BTC 100, ETH 20, others 5, unless target is 0 and position is not).
     Limit at open_1m(T, minute 0) * (1 -/+ 0.001), filled at the limit if
     a 1m low (buy) / high (sell) in minutes 2..59 trades through it
     (strict), maker 0.0002; otherwise expires. Average entry: new -> fill;
     adding same side -> weighted; reducing -> unchanged; flip -> fill.
  E4 Book SL/TP with m = 4 (this audit): sigma_d = std of 360 4h
     open-to-open returns ending at t * sqrt(6); long SL = entry *
     (1 - m sigma_d), TP = entry * (1 + 2 m sigma_d) (short mirrored);
     levels reset at each decision; checked from minute 0 on the position
     held (before the fill) and from the fill minute on the new position;
     SL if low <= SL (long), filled at min(SL, minute open), taker
     0.00055; TP on high > TP (strict), maker 0.0002; both in one minute ->
     SL first; after SL/TP the asset is flat for the rest of the bar and
     the pending order is cancelled if not yet filled.
  E5 Funding (gate): a long held at the end of the bar pays 0.0001 of its
     notional if T + 4h is 00/08/16 UTC; shorts 0. No carry sleeve.
  E6 Dip sleeve: rungs k = 2.5/3/3.5/4 with sigma_4h (not daily), bid
     L = open(T) (1 - k sigma_4h) live minutes 16..238, maker fill on
     low < L (strict); exits after the fill minute: SL at L (1 - 2
     sigma_4h) (low <= SL, fill min(SL, open), taker 0.00055), TP at
     L (1 + sigma_4h) (high > TP strict, maker 0.0002), else at open(T+4h)
     taker paying 0.0001 if that is a settlement; rung notional
     rn = s g 0.25/4/1.657; fills taken in (minute, rung, asset) order iff
     (open rungs at that minute + 1) rn <= 1/6.
  E7 1m-marked equity per minute = start equity * (1 + position MTM +
     sleeve MTM); gate DD = max(4h-close DD, 1m-marked DD); per anchor year
     net/monthly; monthly_dev4 = geometric mean of the first four anchor
     years (monthly % = 100 * ((1+geo) ** (1/12) - 1)).
  E8 Rows: v151 ((A+B)/2 members), E alone, 0.5 v151 + 0.5 E, all with
     m = 4 and the sleeve on.

Leakage notes (checked in code, reported in COMPARISON.md Part B):
  L1 Feature timing: p103/features at t use only bars closed at t
     (v103.build from bars <= t; no forward join except the blind
     opt-free path used here).
  L2 Label window: labels use future bars t+1..t+43 ONLY as targets;
     sigma_d uses open pct changes ending at t (bars <= t).
  L3 Fit windows: per-anchor training requires exit open(t+43) before
     anchor - 78 bars (t + 43 bars < anchor - 78 bars); vol forecast uses
     the audited v129 cutoff/embargo; no statistic is fit on any test
     year inside this script (vol/governor are running causal filters;
     selection, if any, uses first-four-years metrics only).
  L4 Fill timing: engine_user book limit minutes 2..59 strict
     trade-through, SL/TP from minute 0 (held) / fill minute (new),
     sleeve trigger 16..238 and exits strictly after the fill minute,
     stop-first within a minute.

Run from the repository root so every data path below stays relative.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

AUD = Path("research/parallel/rounds/parallel-20260906-r2") / "v190_audit"
OUT = AUD / "replication.json"

ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
HOR_BARS = 42
HOLD_EXIT_BAR = 43
EMBARGO_BARS = 78
M_SL_LABEL = 4.0
TP_MULT = 2.0
FEE_LABEL = 0.00075
FUND_PER_BAR = 0.0001 / 2.0
SIG_WIN = 360
SIG_MIN = 120

M_SL = 4.0
M_SLEEVE_SL = 2.0
TARGET = 0.25
CAP = 2.0

HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400,
           min_samples_leaf=300, l2_regularization=1.0, random_state=0)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(
        name, Path("research/parallel/rounds/parallel-20260906-r2") / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _spearman(a, b):
    m = pd.DataFrame({"a": np.asarray(a, dtype=float),
                      "b": np.asarray(b, dtype=float)}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(m["a"].corr(m["b"], method="spearman"))


def compute_asset_labels(bars):
    """Labels per bar position using only past sigma and future exits.

    bars: 4h bars sorted by open_time with open/high/low.
    Returns arrays aligned with bars: sigma_d, long_target, short_target,
    bars_held_long, bars_held_short, entry.
    """
    o = bars["open"].to_numpy(dtype=float)
    h = bars["high"].to_numpy(dtype=float)
    l = bars["low"].to_numpy(dtype=float)
    n = len(bars)
    pct = np.full(n, np.nan)
    pct[1:] = o[1:] / o[:-1] - 1.0
    sigma = np.full(n, np.nan)
    # rolling std ending at t, window 360, min 120
    s = pd.Series(pct)
    roll = s.rolling(SIG_WIN, min_periods=SIG_MIN).std(ddof=1).to_numpy()
    sigma = roll * np.sqrt(6.0)
    entry = np.full(n, np.nan)
    entry[: n - 1] = o[1:]
    lt = np.full(n, np.nan)
    st = np.full(n, np.nan)
    hlt = np.full(n, np.nan)
    hst = np.full(n, np.nan)
    for pos in range(n):
        sd = sigma[pos]
        e = entry[pos]
        if not np.isfinite(sd) or not np.isfinite(e) or sd <= 0:
            continue
        if pos + 1 >= n:
            continue
        # need exit open(t+43) for the timeout path; if beyond end, timeout impossible
        # but SL/TP path may still be possible if bars exist; require at least pos+1
        sl_l = e * (1.0 - M_SL_LABEL * sd)
        tp_l = e * (1.0 + TP_MULT * M_SL_LABEL * sd)
        sl_s = e * (1.0 + M_SL_LABEL * sd)
        tp_s = e * (1.0 - TP_MULT * M_SL_LABEL * sd)
        # long scan
        found = False
        for k in range(1, HOR_BARS + 1):
            j = pos + k
            if j >= n:
                break
            lo, hi = l[j], h[j]
            if not np.isfinite(lo) or not np.isfinite(hi):
                continue
            if lo <= sl_l:
                # stop first if both in one bar
                gross = sl_l / e - 1.0
                net = gross - FEE_LABEL - FUND_PER_BAR * k
                lt[pos] = np.clip(net / sd, -4.0, 8.0)
                hlt[pos] = k
                found = True
                break
            if hi >= tp_l:
                gross = tp_l / e - 1.0
                net = gross - FEE_LABEL - FUND_PER_BAR * k
                lt[pos] = np.clip(net / sd, -4.0, 8.0)
                hlt[pos] = k
                found = True
                break
        if not found:
            j = pos + HOLD_EXIT_BAR
            if j < n and np.isfinite(o[j]):
                gross = o[j] / e - 1.0
                net = gross - FEE_LABEL - FUND_PER_BAR * HOR_BARS
                lt[pos] = np.clip(net / sd, -4.0, 8.0)
                hlt[pos] = HOR_BARS
        # short scan (mirrored, no funding)
        found = False
        for k in range(1, HOR_BARS + 1):
            j = pos + k
            if j >= n:
                break
            lo, hi = l[j], h[j]
            if not np.isfinite(lo) or not np.isfinite(hi):
                continue
            if hi >= sl_s:
                gross = e / sl_s - 1.0
                net = gross - FEE_LABEL
                st[pos] = np.clip(net / sd, -4.0, 8.0)
                hst[pos] = k
                found = True
                break
            if lo <= tp_s:
                gross = e / tp_s - 1.0
                net = gross - FEE_LABEL
                st[pos] = np.clip(net / sd, -4.0, 8.0)
                hst[pos] = k
                found = True
                break
        if not found:
            j = pos + HOLD_EXIT_BAR
            if j < n and np.isfinite(o[j]) and o[j] > 0:
                gross = e / o[j] - 1.0
                net = gross - FEE_LABEL
                st[pos] = np.clip(net / sd, -4.0, 8.0)
                hst[pos] = HOR_BARS
    return dict(sigma=sigma, entry=entry, long_target=lt,
                short_target=st, held_long=hlt, held_short=hst)


def main():
    eu = _load("v190_audit_engine_user",
               Path("engine_user/engine_user.py").as_posix())
    print(f"engine_user maker={eu.MAKER} taker={eu.TAKER} fund_long={eu.FUND_LONG}", flush=True)
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    assert eu.D_LIMIT == 0.001 and eu.SIZE == 0.25 and eu.S_REF == 1.657
    assert tuple(eu.RUNGS) == (2.5, 3.0, 3.5, 4.0)

    v144 = _load("v190_audit_v144", Path("v144/v144_deploy_v3.py").as_posix())
    print("building v144 books for p103 panel ...", flush=True)
    p103, books_v144 = v144.books_v142()
    print(f"p103 {p103.shape} books_v144 {books_v144.shape} index {books_v144.index.min()} -> {books_v144.index.max()}", flush=True)
    f103 = [c for c in p103.columns
            if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    print(f"f103 n={len(f103)}", flush=True)
    assert len(f103) > 0 and "vol42" in f103 and "rib" in f103 and "pred" not in f103

    # labels from the same 4h bars the panel used
    v92_panel = v144.v103.v92
    bars_by_sym = {}
    label_frames = []
    for sym in sorted(p103["sym"].unique().tolist()):
        b, _, _ = v92_panel.load_asset(sym)
        b = b.sort_values("open_time").reset_index(drop=True)
        bars_by_sym[sym] = b
        lab = compute_asset_labels(b)
        df = pd.DataFrame({
            "t": pd.to_datetime(b["open_time"], utc=True),
            "sym": sym,
            "sigma_d": lab["sigma"],
            "entry": lab["entry"],
            "y_long": lab["long_target"],
            "y_short": lab["short_target"],
            "held_long": lab["held_long"],
            "held_short": lab["held_short"],
        })
        # sanity: panel opens at t must match bars opens used for entry/sigma
        pm = p103[p103.sym == sym].sort_values("t")
        chk = pm.merge(df[["t", "entry", "sigma_d"]], on="t", how="left")
        # entry in labels = open(t+1); panel open at t+1 should equal entry where both exist
        label_frames.append(df)
        print(f"{sym} bars={len(b)} labels valid long={int(df['y_long'].notna().sum())} short={int(df['y_short'].notna().sum())}", flush=True)
    labels = pd.concat(label_frames, ignore_index=True)
    panel = p103.merge(labels, on=["t", "sym"], how="left")
    panel["y_comb"] = panel["y_long"] - panel["y_short"]

    # per-anchor long/short HGBs, training filter t+43 bars < anchor-78 bars
    oos_parts = []
    ic_rows = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
        exit_deadline = cutoff
        # t + 43 bars < anchor - 78 bars  <=>  t + 43*4h < cutoff
        tr = panel[(panel.t + pd.Timedelta(hours=4 * HOLD_EXIT_BAR) < exit_deadline)
                   & panel["y_long"].notna() & panel["y_short"].notna()].copy()
        # strictly before the anchor year too (training is past only)
        tr = tr[tr.t < cutoff]
        te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
        assert len(te) > 0
        m_long = HistGradientBoostingRegressor(**HGB)
        m_short = HistGradientBoostingRegressor(**HGB)
        m_long.fit(tr[f103], tr["y_long"])
        m_short.fit(tr[f103], tr["y_short"])
        te["p_long"] = m_long.predict(te[f103])
        te["p_short"] = m_short.predict(te[f103])
        te["pred"] = te["p_long"] - te["p_short"]
        oos_parts.append(te)
        ev = te.dropna(subset=["y_comb"])
        ic = _spearman(te["pred"], te["y_comb"]) if len(ev) >= 3 else float("nan")
        ic_l = _spearman(te["p_long"], te["y_long"]) if len(te.dropna(subset=["y_long"])) >= 3 else float("nan")
        ic_s = _spearman(te["p_short"], te["y_short"]) if len(te.dropna(subset=["y_short"])) >= 3 else float("nan")
        ic_rows.append(dict(anchor=anchor, train_rows=int(len(tr)),
                            train_rows_long=int(tr["y_long"].notna().sum()),
                            train_rows_short=int(tr["y_short"].notna().sum()),
                            n_pred_rows=int(len(te)),
                            n_eval_rows=int(len(ev)),
                            ic_combined=round(float(ic), 4) if np.isfinite(ic) else None,
                            ic_long=round(float(ic_l), 4) if np.isfinite(ic_l) else None,
                            ic_short=round(float(ic_s), 4) if np.isfinite(ic_s) else None))
        print(f"{anchor} tr={len(tr)} te={len(te)} eval={len(ev)} ic={ic_rows[-1]['ic_combined']}", flush=True)
    frame = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)

    # Book E: v129 vol forecast replacing vol42, then raw_ls + phased(6) + vol_target_scale
    v125 = v144.v125
    v129 = v144.v129
    ext = v144.v115.v114.v113
    emb = ext.v92.EMBARGO_BARS
    print(f"vol forecast embargo={emb} ...", flush=True)
    pv, q = v129.vol_predict(p103, f103, list(ANCHORS), emb)
    print(f"vol quality {q}", flush=True)
    merged = frame.merge(pv, on=["t", "sym"], how="left")
    n_replace = int(merged["pvol"].notna().sum())
    merged["vol42"] = merged["pvol"].where(merged["pvol"].notna(), merged["vol42"])
    merged = merged.drop(columns=["pvol"])
    print(f"vol replaced {n_replace}/{len(merged)}", flush=True)
    W_raw = v125.raw_ls(merged)
    W_E = v125.phased(W_raw, list(range(6)))
    scale_E = ext.v94.vol_target_scale(p103, W_E)
    E_scaled = W_E.mul(scale_E, axis=0)
    print(f"E book {E_scaled.shape}", flush=True)

    # v151 = (A+B)/2 members
    v151mod = _load("v190_audit_v151", Path("v151/v151_info_ensemble.py").as_posix())
    print("building v151 B leg (options-flow books) ...", flush=True)
    _, B_books = v151mod.books_with_options()
    print(f"B books {B_books.shape}", flush=True)
    idx_union_v = books_v144.index.union(B_books.index).sort_values()
    v151_books = 0.5 * books_v144.reindex(idx_union_v).fillna(0.0) + 0.5 * B_books.reindex(idx_union_v).fillna(0.0)
    print(f"v151 books {v151_books.shape} union={len(idx_union_v)}", flush=True)

    # rows under engine_user
    idx_all = v151_books.index.union(E_scaled.index).sort_values()
    V = v151_books.reindex(idx_all).fillna(0.0)
    E = E_scaled.reindex(idx_all).fillna(0.0)
    blend = 0.5 * V + 0.5 * E
    opens = p103.pivot_table(index="t", columns="sym", values="open").sort_index()
    # ensure opens covers the union (ffill gaps, then 0 not needed; engine_user skips non-finite)
    opens = opens.reindex(idx_all)
    print(f"opens {opens.shape} union {len(idx_all)}", flush=True)
    prep = eu.prepare(blend, opens)
    print(f"prepared cubes O {prep['O'].shape}", flush=True)

    rows = {}
    for key, books in (("v151", V), ("E", E), ("blend_50_50", blend)):
        print(f"simulate {key} m_sl={M_SL} sleeve=True ...", flush=True)
        out = eu.simulate(books, opens, prep, m_sl=M_SL,
                          m_sleeve_sl=M_SLEEVE_SL, sleeve=True,
                          target=TARGET, cap=CAP)
        yearly = out["yearly"]
        assert [y["anchor"] for y in yearly] == list(ANCHORS)
        first4 = yearly[:4]
        losing_first4 = sum(1 for y in first4 if y["net_pct"] < 0)
        geo4 = float(np.prod([1 + y["net_pct"] / 100 for y in first4]) ** (1 / 4) - 1)
        dev4_check = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4_check - out["monthly_dev4"]) < 0.002, (key, dev4_check, out["monthly_dev4"])
        rows[key] = {
            "books": key,
            "m_sl": M_SL,
            "m_sleeve_sl": M_SLEEVE_SL,
            "sleeve": True,
            "target": TARGET,
            "cap": CAP,
            "monthly_dev4": out["monthly_dev4"],
            "monthly_5y": out["monthly_5y"],
            "monthly_last_year": out["monthly_last_year"],
            "yearly": yearly,
            "yearly_net_pct": [y["net_pct"] for y in yearly],
            "yearly_monthly_pct": [y["monthly_pct"] for y in yearly],
            "losing_years": out["losing_years"],
            "losing_years_first4": losing_first4,
            "dd_4h": out["dd_4h"],
            "dd_1m": out["dd_1m"],
            "gate_dd": out["gate_dd"],
            "gate_pass": out["gate_pass"],
            "stats": out["stats"],
        }
        print(f"{key}: dev4={out['monthly_dev4']} 5y={out['monthly_5y']} "
              f"last={out['monthly_last_year']} gateDD={out['gate_dd']} "
              f"lose={out['losing_years']} nets={[y['net_pct'] for y in yearly]}", flush=True)

    replication = {
        "version": "v190_audit_replication",
        "blind": "did_not_open_research_v190_until_this_file_saved",
        "spec": {
            "panel": "v103 p103 from v144 books_v142()",
            "features": "columns except y*, t, open, sym, bar",
            "label": "entry=open(t+1); sigma_d=std(360 open pct ending at t,min120)*sqrt(6); "
                     "long SL=e(1-4sd) TP=e(1+8sd) scan t+1..t+42 SL-first else open(t+43); "
                     "ret-0.00075-0.0001*bars_held/2; short mirrored no funding; target=ret/sd [-4,8]",
            "model": HGB,
            "train_filter": "t + 43 bars < anchor - 78 bars",
            "pred": "p_long - p_short",
            "book_E": "v125.phased(v125.raw_ls(frame),6 phases) with v129 pvol replacing vol42 times ext.v94.vol_target_scale",
            "rows": "v151=(A+B)/2 members, E alone, 0.5 v151+0.5 E under engine_user m=4 sleeve",
        },
        "anchors": list(ANCHORS),
        "features": {"f103_n": len(f103), "f103": f103},
        "labels": {"m_sl": M_SL_LABEL, "tp_mult": TP_MULT, "fee": FEE_LABEL,
                   "fund_per_bar": FUND_PER_BAR, "horizon_bars": HOR_BARS,
                   "exit_bar": HOLD_EXIT_BAR, "embargo_bars": EMBARGO_BARS,
                   "sigma_win": SIG_WIN, "sigma_min": SIG_MIN},
        "ic_per_anchor": ic_rows,
        "vol_forecast": {"embargo_bars": int(emb), "quality": q,
                         "n_replaced": n_replace, "n_frame": int(len(merged))},
        "v151_union_bars": int(len(idx_union_v)),
        "union_bars": int(len(idx_all)),
        "columns": sorted(list(blend.columns)),
        "engine": {
            "file": "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py",
            "maker": eu.MAKER,
            "taker": eu.TAKER,
            "d_limit": eu.D_LIMIT,
            "fund_long": eu.FUND_LONG,
            "rungs": list(eu.RUNGS),
            "size": eu.SIZE,
            "s_ref": eu.S_REF,
            "m_sl": M_SL,
            "m_sleeve_sl": M_SLEEVE_SL,
            "target": TARGET,
            "cap": CAP,
        },
        "rows": rows,
    }
    AUD.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
