"""v168: uncertainty-aware confidence sizing of the short-horizon (v103) book via quantile HGBs (registry v168).

In all three v154 members (A = v144, B = options, D = Coinbase premium) the v103 model is replaced, per anchor and horizon
h in (6, 18), by three HistGradientBoostingRegressor(loss="quantile", quantile=q) models, q in (0.25, 0.5, 0.75), with
the v92 hyperparameters and the audited v103 cutoffs/embargo/row filters. Median prediction m = mean over h of the q=0.5
predictions; spread s = mean over h of (q75 - q25) (floored at 1e-3); confidence c = |m| / s; reference c_ref = median of c
on the anchor's training rows (in-sample, known at training time); multiplier k = clip(c / c_ref, 0.5, 1.5). The v103 book
uses pred = m * k in the audited weight formula (so relative sizes shift toward confident, low-uncertainty predictions).
v92/v94 books unchanged. Books (A + B + D)/3, v144 realistic engine rows. Reference v154: 3.515/19.15. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v168/v168_quantile_confidence.py
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
QS = (0.25, 0.5, 0.75)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_train_predict(v103):
    def train_predict(panel, anchor, feats):
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * v103.EMBARGO)
        te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
        med_te, spr_te, med_tr, spr_tr = [], [], [], []
        rows = {}
        for h in v103.HS:
            tr = panel[(panel.t < cutoff) & panel[f"y{h}"].notna()]
            tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
            P_te, P_tr = {}, {}
            for q in QS:
                m = HistGradientBoostingRegressor(loss="quantile", quantile=q, max_depth=4, learning_rate=0.03, max_iter=400,
                                                  min_samples_leaf=300, l2_regularization=1.0, random_state=0).fit(tr[feats], tr[f"y{h}"])
                P_te[q], P_tr[q] = m.predict(te[feats]), m.predict(tr[feats])
            med_te.append(P_te[0.5]); spr_te.append(np.maximum(P_te[0.75] - P_te[0.25], 1e-3))
            med_tr.append(pd.Series(P_tr[0.5], index=tr.index)); spr_tr.append(pd.Series(np.maximum(P_tr[0.75] - P_tr[0.25], 1e-3), index=tr.index))
            rows[h] = len(tr)
        m_te, s_te = np.mean(med_te, 0), np.mean(spr_te, 0)
        common = med_tr[0].index.intersection(med_tr[1].index)
        c_tr = (np.abs((med_tr[0][common] + med_tr[1][common]) / 2) / ((spr_tr[0][common] + spr_tr[1][common]) / 2))
        c_ref = float(np.median(c_tr))
        k = np.clip((np.abs(m_te) / s_te) / c_ref, 0.5, 1.5)
        te["pred"] = m_te * k
        return te, rows
    return train_predict


def fresh_v144(tag):
    v144 = _load(f"v144_{tag}", "v144/v144_deploy_v3.py")
    v144.v103.train_predict = make_train_predict(v144.v103)
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.v92.load_asset = v144.v115.v114.v113.load_asset_ext
    return v144


def with_extra(v144, feats, excl):
    ext, v103 = v144.v115.v114.v113, v144.v103
    b92, b103 = ext.v92.build, v103.build
    orig_vp = v144.v129.vol_predict
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in excl], anchors, emb)
    ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
    v103.build = lambda: b103().merge(feats, on="t", how="left")
    return v144.books_v142()


def main():
    A_mod = fresh_v144("A")
    p103, A = A_mod.books_v142()
    v150 = _load("v150_q", "v150/v150_options_flow.py")
    _, B = with_extra(fresh_v144("B"), v150.opt_features(), v150.OPT)
    v111 = _load("v111_q", "v111/v111_coinbase_premium.py")
    cbf = v111.add_cb(A_mod.v103.build()[["t", "sym"]]).drop(columns="sym").drop_duplicates("t")
    _, D = with_extra(fresh_v144("D"), cbf, v111.CB)
    idx = A.index.union(B.index).union(D.index)
    books = sum(X.reindex(idx).fillna(0.0) for X in (A, B, D)) / 3
    out = {"version": "v168", **A_mod.simulate(p103, books)}
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v168_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
