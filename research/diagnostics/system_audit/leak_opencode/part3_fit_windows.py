"""Part 3: walk-forward fit-window code review (static evidence + numeric embargo check)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = Path("research/parallel/rounds/parallel-20260906-r2")


def main():
    ev = {"v92": {"train_select": "v92/v92_pooled_hgb_vt.py:111-113",
                  "quote": ["cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)",
                             "tr = panel[(panel.t < cutoff) & panel.y.notna()]",
                             "tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]"],
                  "label": "v92_pooled_hgb_vt.py:81-83 fwd[:n-1-H]=log(o[1+H:]/o[1:n-H]); horizon H=42 bars (7d); label end = t+(H+1)*4h",
                  "embargo": "EMBARGO_BARS = H + 10*PD = 102 bars (17d) >= horizon 42",
                  "norm": "no scaler/calibration/threshold: HGB fit on tr[FEATS] only (line 116); weights_from uses fixed 0.5 + vol42 of OOS rows (trailing, causal); vol_target_scale trailing realized vol with W.shift(2) (line 142)"},
          "v94": {"train_select": "v94/v94_long_short_ensemble.py:46-51",
                  "quote": ["cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)",
                             "tr = panel[(panel.t < cutoff) & panel[f'y{h}'].notna()]",
                             "tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]"],
                  "label": "v94_long_short_ensemble.py:36-39 horizons (18,42,84); label end = t+(h+1)*4h",
                  "embargo": "EMBARGO_BARS = max(HORIZONS)+10*PD = 144 bars (24d) >= max horizon 84",
                  "norm": "no scaler: one HGB per horizon fit on tr only (line 52-53); weights_ls fixed 0.5/ribbon gating (lines 65-66)"},
          "v103": {"train_select": "v103/v103_flow_short_horizon.py:89-94",
                   "quote": ["cutoff = a - pd.Timedelta(hours=4 * EMBARGO)",
                              "tr = panel[(panel.t < cutoff) & panel[f'y{h}'].notna()]",
                              "tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]"],
                   "label": "v103_flow_short_horizon.py:77-80 horizons HS=(6,18); label end = t+(h+1)*4h",
                   "embargo": "EMBARGO = max(HS)+10*PD = 78 bars (13d) >= max horizon 18",
                   "norm": "no scaler: HGBs fit on tr only (line 95-96)"},
          "v129-vol": {"train_select": "v129/v129_vol_forecast_sizing.py:49-51",
                       "quote": ["cutoff = A - pd.Timedelta(hours=4 * embargo_bars)",
                                  "tr = p[(p.t < cutoff) & p.fv.notna() & np.isfinite(p.fv)]",
                                  "tr = tr[tr.t + pd.Timedelta(hours=4 * (HV + 2)) < cutoff]"],
                       "label": "v129_vol_forecast_sizing.py:39 fv=log(std(r[t+2..t+43])); end = t+(HV+2)*4h = t+44 bars",
                       "embargo": "called with v92.EMBARGO_BARS=102 >= 44 (v129 main lines 92-93; v240 build_member line 77 excludes new feats from vol models)",
                       "norm": "HGB fit on tr only (line 53-54); pvol fills vol42 in OOS rows only"},
          "v144": {"train_select": "v144/v144_deploy_v3.py:47,50,55 (per-anchor train_predict calls)",
                   "quote": ["lo = concat([ext.v92.train_predict(p92x, a)[0] for a in ext.v92.ANCHORS])",
                              "ls = concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS])",
                              "fl = concat([v103.train_predict(p103x, a, f103)[0] for a in ext.v92.ANCHORS])"],
                   "label": "inherits v92/v94/v103 labels above; anchors v92.ANCHORS 2021-09-24..2025-09-24 (v92 line 25)",
                   "embargo": "inherits cutoffs above; te = panel in [anchor, anchor+365d) only (v92:110, v94:47, v103:90)",
                   "norm": "vol_predict excludes new features (v144 books_v142 lines 56-57 via v129); vol_target_scale trailing only"},
          "v202": {"train_select": "v202/v202_quarterly_retrain.py:31-32,51-64 (20 quarterly anchors, _cut to [anchor, next))",
                   "quote": ["Q = date_range 2021-09-24 periods=20 freq=3M; END[next anchor]",
                              "def _cut(df, a): rows with t in [A, E)",
                              "tp92/tp94/tp103 wrap audited train_predict then _cut; vp concats per-anchor vol"],
                   "label": "unchanged per-target cutoffs/embargoes relative to each quarterly anchor (docstring lines 7-9)",
                   "embargo": "same EMBARGO_BARS per model, now relative to each quarterly anchor; te never crosses next anchor",
                   "norm": "no new fitting; wraps audited functions"},
          "v285": {"train_select": "v285/v285_coinbase_member_c4.py:45-51 (no training; reads cached members)",
                   "quote": ["m[k] = read_parquet(member_*) reindexed; c4 = 0.5*(A+B)/2+0.5*(Aq+Bq)/2; D2 = 0.8*c4+0.2*(D+Dq)/2"],
                   "label": "n/a (mixing only); D built by v154.books_coinbase via v144 builder + v111 Coinbase features",
                   "embargo": "inherits v144/v202 fit windows of cached members",
                   "norm": "no fitting in v285 (simulate only)"},
          "coinbase-D-features": {"train_select": "v111/v111_coinbase_premium.py:54-59 (causal rolls); v154/v154_ensemble_coinbase.py:32-40",
                                  "quote": ["premium uses merge_asof backward (line 54-55); rolls use rows <= t only (lines 57-58)",
                                             "cbf merged on t (v154 line 39-40); vol models exclude CB feats (line 36)"],
                                  "label": "features at t use Coinbase 1h candle opening at T+3h vs Binance spot 4h close (docstring lines 3-5); 1h candle closes at T+4h = bar close",
                                  "embargo": "n/a (features, not labels); z-scores use trailing 540-bar windows",
                                  "norm": "no scaler; raw premium levels excluded (docstring lines 8-9)"}}
    # numeric check: max label end of training rows < anchor - embargo already enforced by construction;
    # verify embargo >= horizon for each model
    checks = {"v92": (42, 102), "v94": (84, 144), "v103": (18, 78), "v129-vol": (44, 102)}
    ev["numeric_embargo_check"] = {k: {"horizon_bars": h, "embargo_bars": e, "ok": e >= h} for k, (h, e) in checks.items()}
    ev["verdict"] = "PASS: all training-row selections require label end < cutoff = anchor - embargo, embargo >= horizon; no scaler/calibration/threshold fit on test rows found in v92/v94/v103/v129/v144/v202/v285."
    (HERE / "part3_fit_windows.json").write_text(json.dumps(ev, indent=1))
    print("part3 done:", ev["verdict"])


if __name__ == "__main__":
    main()
