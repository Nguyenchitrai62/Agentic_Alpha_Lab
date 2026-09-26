"""v186: v183 with the dip-sleeve universe widened to 11 perps under the same budget (registry v186; RESEARCH ONLY).

User rule: trading is majors-only; alts would need the user's explicit OK before any deployment. This run only measures
whether spreading the sleeve over more independent flushes helps under the unchanged tail budget.
Why: in v183 the open-notional budget (1/6 equity) binds and majors' crash fills cluster in the same minutes. v181
showed the frozen ladder earns on DOGE/ADA/LINK/LTC/AVAX/TRX (5/5 years); alt-specific flushes happen at other times,
so a shared budget can take more, less correlated rungs.
Fixed before running: books unchanged (majors, v154 + v170 execution, engine_real, target 0.25, governor); sleeve =
v183 rules (ladder 2.5/3/3.5/4 sigma, TP at L(1+sigma), else next 4h open taker, crash-aware slippage, funding) on the
five majors followed by the six alts (column order BNB, BTC, ETH, SOL, XRP, DOGE, ADA, LINK, LTC, AVAX, TRX); one
shared open-notional budget 1/6 with the same rung notional; vol leg includes all 11 assets (unbudgeted, shift 2);
1m mark includes open alt rungs. Rows normal and stress; gate DD = max(4h, 1m-marked). Reference v183 4.284 / 19.01.

  python research/parallel/rounds/parallel-20260906-r2/v186/v186_sleeve_eleven_assets.py
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


v183 = _load("v183", HERE.parent / "v183/v183_tp_exit_open_budget.py")
v182 = _load("v182", HERE.parent / "v182/v182_pooled_gate.py")
diag, v172, v171, v170, er = v183.diag, v183.v172, v183.v171, v183.v170, v183.er


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    for s in v182.ALTS:
        one = v182.asset_cube(G, s, v182.ALT_DIR)
        for k in ("open", "high", "low", "close"):
            A[k] = np.concatenate([A[k], one[k][:, :, None]], axis=2)
        del one
    cols_all = cols + list(v182.ALTS)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    src = Path(v183.__file__).read_text(encoding="utf-8")
    patches = [("for a in range(len(cols)) if fmins[r, gi, a] >= 0", "for a in range(fmins.shape[2]) if fmins[r, gi, a] >= 0"),
               ("path = ((Cm / o1[i] - 1) * w).sum(axis=1)", "path = ((Cm[:, :len(cols)] / o1[i] - 1) * w).sum(axis=1)")]
    for a, b in patches:
        assert src.count(a) == 1, a
        src = src.replace(a, b)
    ns = {"__file__": v183.__file__, "__name__": "v183_eleven"}
    exec(compile(src.replace('if __name__ == "__main__":\n    main()', ""), v183.__file__, "exec"), ns)
    out = {"version": "v186", "sleeve_assets": cols_all, "reference_v183": {"normal": (4.284, 19.01), "stress": (3.882, 19.13)}}
    for key, maker, taker, extra, ex in (("primary_normal", 0.0002, 0.0005, 0.0, ex60),
                                         ("stress", 0.0004, 0.0007, 0.0005, diag.stress_exec(idx, cols))):
        t = ns["rung_table_tp"](G, cols_all, A, maker, taker, extra)
        r = ns["run"](books, dict(base, exec=ex), A["close"], G, *t)
        out[key] = r
        print(key, r["monthly_pct"], "4hDD", r["full_path_dd"], "1mDD", r["dd_1m_mark"], r["dd_1m_worst_bar"], "gateDD", r["gate_dd"],
              "rungs", r["rungs_taken"], "tp", r["tp_exits"], "cancelled", r["rungs_cancelled"],
              [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v186_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
