"""v170: longer resting window for the 10 bps limit orders under the realistic engine (registry v170).

Motivation: execution costs are ~9% of v154 gross (error analysis); v135 chose the 10 bps offset with a fixed 15-minute
window, the window itself was never tested. The signals have 1-7 day horizons, so a longer rest should raise the maker
share at little alpha cost. The drift cost of waiting is measured, not assumed: returns still start at the minute-0 price
p0 and a taker fallback fills at the minute-W open (+2 bps).
Fixed before running: books v154 (cached), engine_real with all realism on, target 0.25, 20% governor. Execution per
symbol and weight change in holding bar T: buy maker at p0 (1 - 0.001), fee 0.0002, if the 1m low over minutes 2..W-1 is
below that price; else taker at the minute-W open * (1 + 0.0002), fee 0.0005 (sell symmetric). Primary W = 60 minutes;
W = 15 (must equal engine_real 3.708 / 18.87) and W = 120 reported (W = 120 is a labelled sensitivity, not selectable).
Reported: monthly, yearly, full-path DD, maker share, execution cost sum.

  python research/parallel/rounds/parallel-20260906-r2/v170/v170_exec_window.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
WINDOWS = (("baseline_w15", 15), ("primary_w60", 60), ("sensitivity_w120", 120))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


er = _load("engine_real", HERE.parent / "engine_real/engine_real.py")
D = er.D


def bar_stats_w(sym, W):
    m = er.v135.load_1m(sym)
    T = m["open_time"].dt.floor("4h")
    off = ((m["open_time"] - T).dt.total_seconds() // 60).astype(int)
    p0 = m[off == 0].set_index(T[off == 0])["open"]
    mk = (off >= 2) & (off <= W - 1)
    lo = m[mk].groupby(T[mk])["low"].min()
    hi = m[mk].groupby(T[mk])["high"].max()
    pw = m[off == W].set_index(T[off == W])["open"]
    return pd.DataFrame({"p0": p0, "lo": lo, "hi": hi, "pw": pw})


def exec_costs_w(idx, cols, W):
    fee_b, rel_b, fee_s, rel_s = (np.zeros((len(idx), len(cols))) for _ in range(4))
    maker_b, maker_s = np.zeros((len(idx), len(cols)), bool), np.zeros((len(idx), len(cols)), bool)
    for j, s in enumerate(cols):
        st = bar_stats_w(s, W).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx)
        p0, lo_, hi_, pw = st["p0"].to_numpy(), st["lo"].to_numpy(), st["hi"].to_numpy(), st["pw"].to_numpy()
        have = ~np.isnan(p0)
        pw = np.where(np.isnan(pw), p0, pw)
        mv = np.where(have, pw / np.where(have, p0, 1.0) - 1, 0.0)
        fb, fs = have & (lo_ < p0 * (1 - D)), have & (hi_ > p0 * (1 + D))
        fee_b[:, j], rel_b[:, j] = np.where(fb, 0.0002, 0.0005), np.where(fb, -D, mv + 0.0002)
        fee_s[:, j], rel_s[:, j] = np.where(fs, 0.0002, 0.0005), np.where(fs, D, mv - 0.0002)
        maker_b[:, j], maker_s[:, j] = fb, fs
    return (fee_b, rel_b, fee_s, rel_s), (maker_b, maker_s)


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    ctx = er.context(books, opens)
    out = {"version": "v170", "reference_engine_real_v154": {"monthly_pct": 3.708, "full_path_dd": 18.87}}
    live = np.asarray((idx >= er.v110.START) & (idx < er.v110.END))
    for key, W in WINDOWS:
        ex, (mb, ms) = exec_costs_w(idx, cols, W)
        c = dict(ctx, exec=ex)
        r = er.run(books, c, 0.25, True, er.FULL)
        r["maker_share_buy"] = round(float(mb[live].mean()), 3)
        r["maker_share_sell"] = round(float(ms[live].mean()), 3)
        out[key] = r
        print(key, r["monthly_pct"], "fullDD", r["full_path_dd"], "maker b/s", r["maker_share_buy"], r["maker_share_sell"],
              r["components_pct_of_start_equity_sum"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v170_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
