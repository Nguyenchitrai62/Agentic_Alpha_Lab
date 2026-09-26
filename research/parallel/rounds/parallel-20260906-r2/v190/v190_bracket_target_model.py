"""v190: triple-barrier ("bracket") targets aligned with the user's trade structure (registry v190).

Why: every live position is traded with a market stop at 4 daily sigma and a limit take-profit at 8 daily sigma
(v188 selection), but the books are trained on plain forward returns. A model trained on the realised return of exactly
that bracket trade learns what the user will actually earn (stops cap losses, take-profits cap gains).
Fixed before running:
- Panel: v103 panel (pooled majors, 4h, spot prefix before the perps; features f103 = all non-target columns).
- Labels per (t, asset): entry = open of bar t+1; sigma_d = std of 360 4h open-to-open returns ending at t * sqrt(6);
  long bracket: SL = entry (1 - 4 sigma_d), TP = entry (1 + 8 sigma_d), walk bars t+1 .. t+42 on 4h high/low (SL first
  if both in one bar), else exit at open of bar t+43; minus 0.00075 costs and minus 0.0001 per 8h held (adverse long
  funding); short mirrored without funding. Target = bracket return / sigma_d, clipped to [-4, 8].
- Model per anchor and side: HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400,
  min_samples_leaf=300, l2_regularization=1.0, random_state=0) (the v92/v103 settings) on rows with
  t + 43 bars < anchor - 78 bars (v103 embargo 78 >= horizon); test = the anchor year.
- Book E: pred = pred_long - pred_short; v125.raw_ls on the v129 vol-forecast frame, phased over 6 phases, scaled by
  the v94 book vol target (as v165's LS103 member).
- Variants (the only two): E alone; 0.5 * v151 books + 0.5 * E. Both with the dip sleeve under engine_user (book SL/TP
  m = 4). Reference: v151 + sleeve (v189 selection, dev4 3.896). SELECTION on the first four years (monthly_dev4,
  DD <= 20, no losing year among them); the selected row's most recent year is the one-time final score. IC report.

  python research/parallel/rounds/parallel-20260906-r2/v190/v190_bracket_target_model.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
H, M_SL, M_TP, EMB = 42, 4.0, 8.0, 78
COST, FUND_8H = 0.00075, 0.0001


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


eu = _load("engine_user", HERE.parent / "engine_user/engine_user.py")
v144 = eu.er.v144
v129, v125, v103 = v144.v129, v144.v125, v144.v103
ext = v144.v115.v114.v113


def bracket_labels(p103):
    out = []
    for s, g in p103.groupby("sym", sort=False):
        b, _, _ = ext.v92.load_asset(s)
        b = b.set_index("open_time")
        o, hi, lo = b["open"].astype(float), b["high"].astype(float), b["low"].astype(float)
        sig = o.pct_change().rolling(360, min_periods=120).std() * np.sqrt(6)
        O, Hh, Ll, S = o.to_numpy(), hi.to_numpy(), lo.to_numpy(), sig.to_numpy()
        pos = pd.Series(np.arange(len(b)), index=b.index)
        rows = pos.reindex(pd.to_datetime(g["t"], utc=True)).to_numpy()
        yl, ys = np.full(len(g), np.nan), np.full(len(g), np.nan)
        for n_, r in enumerate(rows):
            if np.isnan(r):
                continue
            r = int(r)
            if r + 1 + H >= len(O) or not np.isfinite(S[r]) or S[r] <= 0:
                continue
            e = O[r + 1]
            sd = S[r]
            hh, ll = Hh[r + 1: r + 1 + H], Ll[r + 1: r + 1 + H]
            # long
            sl, tp = e * (1 - M_SL * sd), e * (1 + M_TP * sd)
            hs, ht = ll <= sl, hh >= tp
            k_s = np.argmax(hs) if hs.any() else H
            k_t = np.argmax(ht) if ht.any() else H
            if k_s <= k_t and k_s < H:
                ret, held = sl / e - 1, k_s + 1
            elif k_t < H:
                ret, held = tp / e - 1, k_t + 1
            else:
                ret, held = O[r + 1 + H] / e - 1, H
            yl[n_] = (ret - COST - FUND_8H * held / 2) / sd
            # short
            sl, tp = e * (1 + M_SL * sd), e * (1 - M_TP * sd)
            hs, ht = hh >= sl, ll <= tp
            k_s = np.argmax(hs) if hs.any() else H
            k_t = np.argmax(ht) if ht.any() else H
            if k_s <= k_t and k_s < H:
                ret = 1 - sl / e
            elif k_t < H:
                ret = 1 - tp / e
            else:
                ret = 1 - O[r + 1 + H] / e
            ys[n_] = (ret - COST) / sd
        out.append(pd.DataFrame({"t": g["t"].to_numpy(), "sym": s, "yl": np.clip(yl, -4, 8), "ys": np.clip(ys, -4, 8)}))
    return pd.concat(out, ignore_index=True)


def main():
    p103, A = v144.books_v142()
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    Am, Bm = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (Am + Bm) / 2
    lab = bracket_labels(p103)
    p = p103.merge(lab, on=["t", "sym"], how="left")
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    preds, ic = [], {}
    for a in ext.v92.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        cutoff = a0 - pd.Timedelta(hours=4 * EMB)
        tr = p[(p.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff)]
        te = p[(p.t >= a0) & (p.t < a0 + pd.Timedelta(days=365))].copy()
        for side in ("yl", "ys"):
            t2 = tr[tr[side].notna()]
            mdl = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
                                                l2_regularization=1.0, random_state=0).fit(t2[f103], t2[side])
            te["p_" + side] = mdl.predict(te[f103])
        te["pred"] = te["p_yl"] - te["p_ys"]
        ok = te["yl"].notna()
        ic[a] = {"ic_long": round(float(te.loc[ok, "p_yl"].corr(te.loc[ok, "yl"], method="spearman")), 4),
                 "ic_short": round(float(te.loc[ok, "p_ys"].corr(te.loc[ok, "ys"], method="spearman")), 4),
                 "ic_pred_vs_y": round(float(te["pred"].corr(te["y"], method="spearman")), 4)}
        print(a, ic[a], flush=True)
        preds.append(te[["t", "sym", "pred"]])
    pr = pd.concat(preds, ignore_index=True)
    pv, _ = v129.vol_predict(p103, f103, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    base = p103.merge(pr, on=["t", "sym"], how="inner")
    d = base[["t", "sym", "rib", "vol42", "pred"]].merge(pv, on=["t", "sym"], how="left")
    d["vol42"] = d["pvol"].fillna(d["vol42"])
    W = v125.phased(v125.raw_ls(d.drop(columns="pvol")), list(range(6)))
    E = W.mul(ext.v94.vol_target_scale(p103, W).reindex(W.index).fillna(1.0), axis=0).reindex(books154.index).fillna(0.0)[cols]
    prep = eu.prepare(books154, opens)
    out = {"version": "v190", "ic": ic, "rows": {}}
    for key, bk in (("ref_v151", v151), ("E_alone", E), ("blend_v151_E", 0.5 * v151 + 0.5 * E)):
        r = eu.simulate(bk, opens, prep, m_sl=4.0, m_sleeve_sl=2.0, sleeve=True)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
    ok = {k: v for k, v in out["rows"].items() if k != "ref_v151" and v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    cand = {k: v for k, v in out["rows"].items() if k != "ref_v151"}
    pool = ok or cand
    sel = max(pool, key=lambda k: pool[k]["monthly_dev4"])
    beats_ref = out["rows"][sel]["monthly_dev4"] > out["rows"]["ref_v151"]["monthly_dev4"]
    s = out["rows"][sel]
    out["selected"], out["beats_reference_on_dev4"] = sel, bool(beats_ref)
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"]}
    print("SELECTED", sel, "beats ref on dev4:", beats_ref, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v190_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
