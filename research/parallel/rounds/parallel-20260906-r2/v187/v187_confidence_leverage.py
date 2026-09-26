"""v187: confidence-gated leverage above 2x with realistic Binance margin and liquidation checks (registry v187).

User rule (2026-09-27): leverage above 2x is allowed when the model's confidence is high, evaluated as realistically as
possible; majors only; DD <= 20% unchanged. The v186 frontier showed the 2x portfolio cap binds.
Fixed before running:
- Base: v183 (v154 books + v170 execution + TP limit dip ladder with the open-notional budget, engine_real, target
  0.25, 20% governor), unchanged except the portfolio scale cap.
- Confidence (known at the decision): with the three v154 members A (base), B (options), D (Coinbase premium) and the
  combined book W = (A+B+D)/3, agree_t = sum_j |W_j| * 1[sign A_j = sign B_j = sign D_j != 0] / sum_j |W_j|.
  Cap_t = 2 if agree_t < 0.6; 3 if 0.6 <= agree_t < 0.8; 4 if agree_t >= 0.8. s_t = min(0.25 / vol_t, Cap_t).
- Realistic margin: Binance USD-M cross margin at an account leverage setting of 10x (initial margin 10% of perp gross,
  engine budget spot cash + perp gross/10 <= 95% of equity); maintenance margin 1% of perp notional (conservative
  vs Binance tier-1 0.4-0.5%); every live bar the futures-wallet equity at its worst 1m mark (total equity minus the
  carry spot cash) is checked against maintenance on the perp notional (books + carry short + all rungs taken in that
  bar); any breach is reported as a liquidation.
- Rows (normal and stress costs): primary = confidence-gated cap; secondary = flat cap 4 (no confidence gate);
  reference = cap 2 with the 10x margin setting (v183 check). Gate DD = max(4h, 1m-marked); a liquidation fails.

  python research/parallel/rounds/parallel-20260906-r2/v187/v187_confidence_leverage.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
MMR = 0.01
LEV_SETTING = 10.0


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v183 = _load("v183", HERE.parent / "v183/v183_tp_exit_open_budget.py")
diag, v172, v171, v170, er = v183.diag, v183.v172, v183.v171, v183.v170, v183.er


def members():
    cache = er.CACHE / "members_v154.parquet"
    if cache.exists():
        m = pd.read_parquet(cache)
        return {k: m.xs(k, axis=1, level=0) for k in ("A", "B", "D")}
    v151 = _load("v151", HERE.parent / "v151/v151_info_ensemble.py")
    v154 = _load("v154", HERE.parent / "v154/v154_ensemble_coinbase.py")
    _, A = er.v144.books_v142()
    _, B = v151.books_with_options()
    _, D = v154.books_coinbase()
    idx = A.index.union(B.index).union(D.index)
    out = {k: X.reindex(idx).fillna(0.0) for k, X in (("A", A), ("B", B), ("D", D))}
    pd.concat(out, axis=1).to_parquet(cache)
    return out


def confidence_cap(books, mem):
    cols = list(books.columns)
    A, B, D = (mem[k].reindex(books.index).fillna(0.0)[cols].to_numpy() for k in ("A", "B", "D"))
    W = books.to_numpy()
    sa, sb, sd = np.sign(A), np.sign(B), np.sign(D)
    agree = (sa == sb) & (sb == sd) & (sa != 0)
    tot = np.abs(W).sum(axis=1)
    share = np.where(tot > 0, (np.abs(W) * agree).sum(axis=1) / np.where(tot > 0, tot, 1.0), 0.0)
    cap = np.where(share >= 0.8, 4.0, np.where(share >= 0.6, 3.0, 2.0))
    return cap, share


def patched(cap_expr):
    src = Path(v183.__file__).read_text(encoding="utf-8")
    a = "np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), v99.CAP)"
    assert src.count(a) == 1
    src = src.replace(a, f"np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), {cap_expr})")
    b = "            eq_min[i] = prev_eq * (1 + min(0.0, float(np.nanmin(path))) - ex + min(fnd, 0.0))\n"
    assert src.count(b) == 1
    liq = (b + "            fut_eq = eq_min[i] - prev_eq * c * expo[i] / er.CARRY_CAPITAL\n"
               "            gross_n = prev_eq * (np.abs(w).sum() + c * expo[i] / er.CARRY_CAPITAL + rn * len(taken))\n"
               "            if fut_eq < MMR * gross_n:\n"
               "                LIQ.append(str(idx[i]))\n")
    src = src.replace(b, liq)
    ns = {"__file__": v183.__file__, "__name__": "v187_patched"}
    exec(compile(src.replace('if __name__ == "__main__":\n    main()', ""), v183.__file__, "exec"), ns)
    ns["er"].MARGIN = LEV_SETTING
    ns["MMR"] = MMR
    return ns


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    mem = members()
    cap, share = confidence_cap(books, mem)
    live = np.asarray((idx >= er.v110.START) & (idx < er.v110.END))
    print("agree share mean", round(float(share[live].mean()), 3), "cap dist",
          {c: round(float((cap[live] == c).mean()), 3) for c in (2.0, 3.0, 4.0)}, flush=True)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    exs = diag.stress_exec(idx, cols)
    out = {"version": "v187", "cap_share": {c: round(float((cap[live] == c).mean()), 3) for c in (2.0, 3.0, 4.0)},
           "reference_v183": {"normal": (4.284, 19.01), "stress": (3.882, 19.13)}}
    for key, cap_expr in (("primary_confidence_cap", "CAPV"), ("secondary_flat_cap4", "4.0"), ("reference_cap2_margin10", "v99.CAP")):
        ns = patched(cap_expr)
        ns["CAPV"] = cap
        row = {}
        for sc, maker, taker, extra, ex in (("normal", 0.0002, 0.0005, 0.0, ex60), ("stress", 0.0004, 0.0007, 0.0005, exs)):
            ns["LIQ"] = []
            t = ns["rung_table_tp"](G, cols, A, maker, taker, extra)
            r = ns["run"](books, dict(base, exec=ex), A["close"], G, *t)
            r["liquidations"] = list(ns["LIQ"])
            row[sc] = r
            print(key, sc, r["monthly_pct"], "4hDD", r["full_path_dd"], "1mDD", r["dd_1m_mark"], r["dd_1m_worst_bar"], "gateDD", r["gate_dd"],
                  "liq", len(r["liquidations"]), [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
        out[key] = row
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v187_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
