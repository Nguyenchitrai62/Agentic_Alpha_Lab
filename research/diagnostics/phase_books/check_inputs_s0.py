"""s = 0 input check: every shifted-grid data entry point at s = 0 vs the original 4h inputs of the builders."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase_books as pb  # noqa: E402

END = pd.Timestamp("2026-09-24", tz="UTC")


def cmp(a: pd.DataFrame, b: pd.DataFrame, key: str | None, cols):
    if key is not None:
        a, b = a.set_index(key), b.set_index(key)
    only_a, only_b = a.index.difference(b.index), b.index.difference(a.index)
    i = a.index.intersection(b.index)
    out = {"rows_a": len(a), "rows_b": len(b), "only_agg": len(only_a), "only_orig": len(only_b),
           "only_agg_first": [str(x) for x in only_a[:5]], "only_orig_first": [str(x) for x in only_b[:5]]}
    for c in cols:
        x, y = a.loc[i, c].astype(float).to_numpy(), b.loc[i, c].astype(float).to_numpy()
        both = ~(np.isnan(x) & np.isnan(y))
        d = np.abs(x - y)[both]
        rel = (np.abs(x - y) / np.maximum(np.abs(y), 1e-12))[both]
        out[c] = {"max_abs": float(np.nanmax(d)) if d.size else 0.0, "max_rel": float(np.nanmax(rel)) if rel.size else 0.0,
                  "n_diff_rel_gt_1e-9": int(np.sum(rel > 1e-9)), "nan_mismatch": int(np.sum(np.isnan(x) != np.isnan(y)))}
    return out


def main():
    agg, nat = pb.Sources(0), pb.Sources(0, native=True)
    res = {}
    kc = ["open", "high", "low", "close", "volume", "quote_volume", "num_trades", "taker_buy_volume", "taker_buy_quote_volume"]
    for s in pb.SYMS:
        a, b = agg.perp_4h(s), nat.perp_4h(s)
        a, b = a[a.open_time < END], b[b.open_time < END]
        res[f"perp4h_{s}"] = cmp(a, b, "open_time", kc)
        pa, pn = agg.spot_prefix_4h(s), nat.spot_prefix_4h(s)
        if pa is not None:
            lim = b.open_time.iloc[0]
            res[f"spot_prefix_{s}"] = cmp(pa[pa.open_time < lim], pn[pn.open_time < lim], "open_time", kc)
        fa, fn = agg.flow_table(s), nat.flow_table(s)
        fa, fn = fa[fa.index < END], fn[fn.index < END]
        res[f"flow4h_{s}"] = cmp(fa, fn, None, list(fn.columns))
    v114 = pb._load("v114_chk", pb.RD / "v114/v114_bitstamp_history.py")
    for prod in ("BTC-USD", "ETH-USD"):
        res[f"cb4h_{prod}"] = cmp(agg.cb_bars_ext(prod, "4h", 3), v114.cb_bars_ext(prod, "4h", 3), "open_time",
                                 ["open", "high", "low", "close", "volume", "quote_volume"])
    v150 = pb._load("v150_chk", pb.RD / "v150/v150_options_flow.py")
    o = v150.opt_features()
    res["options"] = cmp(agg.opt_frame(), o, "t", [c for c in o.columns if c != "t"])
    v111 = pb._load("v111_chk", pb.RD / "v111/v111_coinbase_premium.py")
    g = pb.standard_p103_grid()
    ref = v111.add_cb(g).drop(columns="sym").drop_duplicates("t")
    res["cb_premium"] = cmp(agg.cb_frame(g), ref, "t", list(v111.CB))
    (pb.OUT / "check_inputs_s0.json").write_text(json.dumps(res, indent=1, default=str))
    for k, v in res.items():
        worst = max((vv["max_rel"] for vv in v.values() if isinstance(vv, dict)), default=0.0)
        nanm = sum(vv["nan_mismatch"] for vv in v.values() if isinstance(vv, dict))
        print(k, "rows", v["rows_a"], v["rows_b"], "only_agg", v["only_agg"], v["only_agg_first"][:2], "only_orig", v["only_orig"],
              v["only_orig_first"][:2], "max_rel", f"{worst:.2e}", "nan_mismatch", nanm, flush=True)


if __name__ == "__main__":
    main()
