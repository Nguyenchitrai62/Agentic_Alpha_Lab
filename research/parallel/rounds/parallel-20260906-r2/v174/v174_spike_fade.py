"""v174: intrabar spike-fade sleeve (mirror of the v172 dip sleeve) added to v172 (registry v174).

Why: v172 (books + dip sleeve) reached 4.597%/month but full-path DD 22.42%, because the dip sleeve is long exactly in
sell-offs when the books lose. A short sleeve that fades intrabar spikes earns in rallies; if spikes mean-revert like
dips, it adds return whose losses are not aligned with the books' sell-off drawdowns.
Fixed before running (mirror of v172, nothing tuned on the result):
- Trigger: first minute m in 16..238 of holding bar T with 1m close / 4h open - 1 >= +k sigma. Short entry at the minute
  m+1 open * (1 - s_in); cover at the next 4h open * (1 + s_out); s = max(0.0002, 0.25 * minute range / open); taker
  0.0005 per side; the short RECEIVES the funding settled at the exit open (pays it if negative).
  r = entry/exit - 1 - 0.001 + funding (short return).
- k per anchor from (2, 2.5, 3, 3.5, 4) by pre-anchor Sharpe, size 0.25, scaled by the governor.
- Rows: spike sleeve alone per anchor; primary = v172 primary (books v170 execution + dip sleeve 0.25) + spike sleeve
  0.25; secondary = books + spike sleeve only. Reference v172 4.597 / 22.42.

  python research/parallel/rounds/parallel-20260906-r2/v174/v174_spike_fade.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v172 = _load("v172", HERE.parent / "v172/v172_sleeve_realistic.py")
v171, v170, er = v172.v171, v172.v170, v172.er
PD = er.PD


def spike_returns(G, cols, A):
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1, o2 = opens.shift(-1).to_numpy(), opens.shift(-2).to_numpy()
    sig = opens.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    fund = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    O, H, L, C = A["open"], A["high"], A["low"], A["close"]
    path = C[:, 16:239, :] / o1[:, None, :] - 1
    xr = np.full(o1.shape, np.nan)
    xr[:-1] = (H[1:, 0, :] - L[1:, 0, :]) / O[1:, 0, :]
    out = {}
    for k in v171.KGRID:
        thr = k * sig
        hit = path >= thr[:, None, :]
        first = np.argmax(hit, axis=1) + 16
        ii, jj = np.nonzero(hit.any(axis=1) & np.isfinite(o2) & np.isfinite(thr))
        mm = first[ii, jj] + 1
        po = O[ii, mm, jj].astype(float)
        s_in = np.maximum(0.0002, 0.25 * np.nan_to_num((H[ii, mm, jj] - L[ii, mm, jj]).astype(float) / po))
        s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr[ii, jj]))
        val = (po * (1 - s_in)) / (o2[ii, jj] * (1 + s_out)) - 1 - 2 * v171.TAKER + fund[ii, jj]
        r = np.zeros(o1.shape)
        ev = np.zeros(o1.shape, dtype=bool)
        ok = np.isfinite(val)
        r[ii[ok], jj[ok]] = val[ok]
        ev[ii[ok], jj[ok]] = True
        out[k] = (r, ev)
    return out


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    dip = v172.event_returns_real(G, cols, A)
    spk = spike_returns(G, cols, A)
    del A
    dip_sleeve, _, dip_k = v171.sleeve_walk_forward(G, dip)
    spk_sleeve, spk_events, spk_k = v171.sleeve_walk_forward(G, spk)
    print("dip k", dip_k, "spike k", spk_k, flush=True)
    ctx = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    ctx = dict(ctx, exec=ex60)
    out = {"version": "v174", "dip_k": dip_k, "spike_k": spk_k, "reference_v172": (4.597, 22.42)}
    for key, sl in (("primary_books_dip_spike", dip_sleeve + spk_sleeve), ("secondary_books_spike", spk_sleeve),
                    ("check_v172_books_dip", dip_sleeve)):
        r, _ = v171.run_combined(books, ctx, sl)
        out[key] = r
        print(key, r["monthly_pct"], "fullDD", r["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    alone = []
    for a in v171.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (spk_sleeve.index >= a0) & (spk_sleeve.index < a0 + pd.Timedelta(days=365))
        eqs = (1 + spk_sleeve[mk]).cumprod()
        alone.append(dict(anchor=a, k=spk_k[a]["k"], net_pct=round(100 * float(eqs.iloc[-1] - 1), 2),
                          dd_pct=round(100 * float((1 - eqs / eqs.cummax()).max()), 2), events=int(spk_events[mk].sum())))
    out["spike_sleeve_alone"] = alone
    live = (G >= er.v110.START) & (G < er.v110.END)
    ds, dd_ = dip_sleeve[live], spk_sleeve[live]
    out["corr_daily_dip_vs_spike"] = round(float(ds.groupby(ds.index.floor("D")).sum().corr(dd_.groupby(dd_.index.floor("D")).sum())), 3)
    print("spike alone", alone, "corr dip/spike", out["corr_daily_dip_vs_spike"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v174_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
