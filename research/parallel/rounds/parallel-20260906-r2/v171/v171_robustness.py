"""v171 robustness (DIAGNOSTIC, ex post, labelled): is the dip-reversal sleeve an artefact of optimistic fills?

Uses the walk-forward k chosen by v171 per anchor (no re-selection). Sleeve alone per anchor year under:
- slippage per side 2 (v171), 5, 10, 20 bps;
- entry latency: open of minute m+1 (v171), m+2, m+5 (a slower order);
- entry at the 1m CLOSE of minute m+1 instead of its open (another fill proxy);
- concentration: v171 without the best 5% of events in each year;
- per-asset contribution and the mean/median event return.

  python research/parallel/rounds/parallel-20260906-r2/v171/v171_robustness.py
"""

from __future__ import annotations

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


v171 = _load("v171", HERE / "v171_intrabar_reversal.py")
er, v169 = v171.er, v171.v169


def main():
    res = json.loads((HERE / "v171_result.json").read_text())
    chosen = {a: v["k"] for a, v in res["chosen"].items()}
    books, _ = er.v154_books()
    cols = list(books.columns)
    G = pd.date_range(v171.START, books.index.max(), freq="4h")
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1, o2 = opens.shift(-1).to_numpy(), opens.shift(-2).to_numpy()
    sig = opens.pct_change().rolling(360, min_periods=120).std().to_numpy()
    fund = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    C, O = v169.minute_cube(G, cols)
    path = C[:, 16:239, :] / o1[:, None, :] - 1

    def events(k, delay=1, slip=0.0002, use_close=False):
        thr = -k * sig
        hit = path <= thr[:, None, :]
        first = np.argmax(hit, axis=1) + 16
        ii, jj = np.nonzero(hit.any(axis=1) & np.isfinite(o2) & np.isfinite(thr))
        mm = np.minimum(first[ii, jj] + delay, 239)
        px = (C if use_close else O)[ii, mm, jj]
        r = np.full(C.shape[0:1] + (len(cols),), np.nan)
        val = o2[ii, jj] * (1 - slip) / (px * (1 + slip)) - 1 - 2 * v171.TAKER - fund[ii, jj]
        r[ii, jj] = val
        return r

    variants = {"v171": dict(), "slip5": dict(slip=0.0005), "slip10": dict(slip=0.0010), "slip20": dict(slip=0.0020),
                "delay2": dict(delay=2), "delay5": dict(delay=5), "close_m1": dict(use_close=True)}
    out = {"note": "DIAGNOSTIC ex post; k fixed to the v171 walk-forward choice", "rows": {}}
    for name, kw in variants.items():
        rows = []
        for a in v171.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            te = np.asarray((G >= a0) & (G < a0 + pd.Timedelta(days=365)))
            r = events(chosen[a], **kw)[te]
            bar = v171.SIZE * np.nansum(r, axis=1)
            eq = np.cumprod(1 + bar)
            ev = r[np.isfinite(r)]
            row = dict(anchor=a[:4], net_pct=round(100 * float(eq[-1] - 1), 2),
                       dd_pct=round(100 * float(np.max(1 - eq / np.maximum.accumulate(eq))), 2), events=int(ev.size),
                       mean_bps=round(1e4 * float(ev.mean()), 1), median_bps=round(1e4 * float(np.median(ev)), 1))
            if name == "v171":
                cut = np.quantile(ev, 0.95)
                r2 = np.where(r >= cut, 0.0, r)
                eq2 = np.cumprod(1 + v171.SIZE * np.nansum(r2, axis=1))
                row["net_pct_without_top5pct"] = round(100 * float(eq2[-1] - 1), 2)
                row["per_asset_mean_bps"] = {c: round(1e4 * float(np.nanmean(r[:, j])), 1) if np.isfinite(r[:, j]).any() else None
                                             for j, c in enumerate(cols)}
            rows.append(row)
        out["rows"][name] = rows
        print(name, rows, flush=True)
    (HERE / "v171_robustness.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
