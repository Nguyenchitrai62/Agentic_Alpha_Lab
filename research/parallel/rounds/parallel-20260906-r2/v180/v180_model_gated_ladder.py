"""v180: model-gated limit ladder under the stress budget (registry v180).

EX POST CONTEXT: built after v173-v179 on the same span; hypothesis-grade.
Why: v179's budget (open sleeve notional <= 1/6 equity per bar) fixes the realistic 1m DD but cancels 60% of the rungs
in time order, good and bad alike. v173 showed trigger-state features rank rebound quality (IC 0.08-0.18). Here a
walk-forward model decides, one minute BEFORE each potential fill, whether the resting bid stays live; the budget is
then spent only on bids the model keeps. This is deployable: the state at minute f-1 is known before the fill at f.
Fixed before running:
- Candidates: every rung fill of the v178 ladder (k = 2.5, 3, 3.5, 4; fill minute f in 16..238, maker at the bid on a
  1m trade-through, taker exit at the next 4h open, crash-aware exit slippage, funding). Target: the rung's net return.
- Features at minute f-1: depth = (close/open(T) - 1)/sigma, r5 and r15 = (close(f-1)/close(f-6 | f-16) - 1)/sigma,
  vspike = volume(f-5..f-1) / (5 * mean volume(0..f-6)), taker15 = taker-buy share of (f-15..f-1), rng = (high-low)/close
  of minute f-1 / sigma, breadth = other majors with depth <= -2 at f-1, btc_depth at f-1, trend = open(T)/mean(last 42
  4h opens) - 1, r1d = (open(T)/open(T-24h) - 1)/sigma, last settled funding, rung k, asset code.
- Model per anchor: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=50,
  l2_regularization=1.0, random_state=0) on candidates whose exit is before anchor - 1 day (from 2020-03-02).
- Policy: a rung's bid is live at its fill minute only if the prediction > 0; kept fills then go through the v179
  budget (time order, notional <= 0.05/0.30 of equity). Vol leg: kept (uncapped) sleeve unit shifted by 2 bars.
- Rows: normal and stress costs (the gate uses the stress row too), gate DD = max(4h, 1m-marked); IC per anchor.
Reference v179: 4.141 / 19.81 (normal), 3.729 / 20.72 (stress).

  python research/parallel/rounds/parallel-20260906-r2/v180/v180_model_gated_ladder.py
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
FEATS = ["depth", "r5", "r15", "vspike", "taker15", "rng", "breadth", "btc_depth", "trend", "r1d", "funding", "k", "asset"]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v179 = _load("v179", HERE.parent / "v179/v179_stress_budget_ladder.py")
v173 = _load("v173", HERE.parent / "v173/v173_rebound_model.py")
diag, v178, v176, v171, v170, er = v179.diag, v179.v178, v179.v176, v179.v171, v179.v170, v179.er
PD = er.PD


def features(G, cols, A, fmins):
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1 = opens.shift(-1).to_numpy()
    sig = opens.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    trend = (opens / opens.rolling(42, min_periods=42).mean() - 1).shift(-1).to_numpy()
    r1d = (opens.shift(-1) / opens.shift(5) - 1).to_numpy()
    fset = np.column_stack([er.funding_at_bar_open(s, G).to_numpy() for s in cols])
    last_f = pd.DataFrame(fset, index=G).replace(0.0, np.nan).ffill().fillna(0.0).to_numpy()
    H, L, C, V, TB = (A[k] for k in ("high", "low", "close", "volume", "taker_buy_volume"))
    bi = cols.index("BTCUSDT")
    rows = []
    for r, k in enumerate(v178.RUNGS):
        gi, a = np.nonzero(fmins[r] >= 0)
        f = fmins[r][gi, a]
        p = f - 1
        s = sig[gi, a]
        dep_all = C[gi, p, :] / o1[gi, :] - 1
        dep_s_all = dep_all / sig[gi, :]
        rows.append(pd.DataFrame({
            "rung": r, "gi": gi, "a": a, "f": f, "k": k, "asset": a,
            "depth": dep_s_all[np.arange(len(gi)), a],
            "r5": (C[gi, p, a] / C[gi, p - 5, a] - 1) / s, "r15": (C[gi, p, a] / C[gi, p - 15, a] - 1) / s,
            "vspike": np.array([V[x, q - 4:q + 1, y].sum() / max(V[x, 0:q - 5, y].mean() * 5, 1e-9) for x, q, y in zip(gi, p, a)]),
            "taker15": np.array([TB[x, q - 14:q + 1, y].sum() / max(V[x, q - 14:q + 1, y].sum(), 1e-9) for x, q, y in zip(gi, p, a)]),
            "rng": (H[gi, p, a] - L[gi, p, a]) / C[gi, p, a] / s,
            "breadth": (dep_s_all <= -2).sum(axis=1) - (dep_s_all[np.arange(len(gi)), a] <= -2),
            "btc_depth": dep_s_all[:, bi], "trend": trend[gi, a], "r1d": r1d[gi, a] / s, "funding": last_f[gi, a]}))
    d = pd.concat(rows, ignore_index=True)
    d["T"] = G[d["gi"].to_numpy()] + pd.Timedelta(hours=4)
    return d


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v173.cube(G, cols)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    lims, fmins, rets = v179.rung_table(G, cols, A, 0.0002, 0.0005, 0.0)
    d = features(G, cols, A, fmins)
    d["y"] = rets[d["rung"].to_numpy(), d["gi"].to_numpy(), d["a"].to_numpy()]
    keep = np.zeros(len(d), dtype=bool)
    ic = {}
    for an in v171.ANCHORS:
        a0 = pd.Timestamp(an, tz="UTC")
        tr = d[(d["T"] + pd.Timedelta(hours=4) < a0 - pd.Timedelta(days=1)) & (d["T"] >= v171.START + pd.Timedelta(days=30))]
        te = (d["T"] - pd.Timedelta(hours=4) >= a0) & (d["T"] - pd.Timedelta(hours=4) < a0 + pd.Timedelta(days=365))
        mdl = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=50,
                                            l2_regularization=1.0, random_state=0).fit(tr[v180_feats()], tr["y"])
        pred = mdl.predict(d.loc[te, v180_feats()])
        keep[te.to_numpy()] = pred > 0
        ic[an] = {"ic": round(float(pd.Series(pred).corr(d.loc[te, "y"].reset_index(drop=True), method="spearman")), 4),
                  "test_fills": int(te.sum()), "kept": int((pred > 0).sum()), "train": int(len(tr))}
        print(an, ic[an], flush=True)
    gate = np.zeros(fmins.shape, dtype=bool)
    gate[d["rung"].to_numpy()[keep], d["gi"].to_numpy()[keep], d["a"].to_numpy()[keep]] = True
    out = {"version": "v180", "ic": ic, "reference_v179": {"normal": (4.141, 19.81), "stress": (3.729, 20.72)}}
    for key, maker, taker, extra, ex in (("primary_normal", 0.0002, 0.0005, 0.0, ex60),
                                         ("stress", 0.0004, 0.0007, 0.0005, diag.stress_exec(idx, cols))):
        lk, fk, rk = v179.rung_table(G, cols, A, maker, taker, extra)
        fk = np.where(gate, fk, -1)
        rk = np.where(gate, rk, 0.0)
        r = v179.run(books, dict(base, exec=ex), A["close"], G, lk, fk, rk)
        out[key] = r
        print(key, r["monthly_pct"], "4hDD", r["full_path_dd"], "1mDD", r["dd_1m_mark"], r["dd_1m_worst_bar"], "gateDD", r["gate_dd"],
              "rungs", r["rungs_taken"], "cancelled", r["rungs_cancelled"],
              [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v180_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


def v180_feats():
    return FEATS


if __name__ == "__main__":
    main()
