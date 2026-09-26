"""v182: rebound gate trained on 11 assets (majors + six alts), applied to the majors' ladder (registry v182).

Why: v181 showed the ladder rebound is not specific to the majors (six unseen perps: +36 bps per rung, 5/5 years). The
v180 gate model was weak in early years (IC 0.02-0.07) with only majors' fills to learn from. Pooling the fills of all
11 assets (alts for training only; trading stays majors-only) roughly doubles the training data for the same mechanism.
Fixed before running:
- Candidates: every v178 ladder rung fill on the 11 assets (majors: data/raw/{btc,majors}_intraday_20260924; alts:
  data/raw/alts_intraday_20260926), normal-cost net return as target.
- Features at minute f-1 as v180, except: no asset code (pooled mechanism), and breadth = number of the five majors
  with depth <= -2 sigma at minute f-1 (same definition for every candidate); btc_depth = BTC depth at f-1.
- Model per anchor: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=50,
  l2_regularization=1.0, random_state=0) on pooled candidates with exit < anchor - 1 day (from 2020-03-02).
- Policy on the majors: rung live iff pred > 0; then the v179 budget (sleeve notional <= 1/6 equity per bar) and the
  v179 loop (books v154 + v170 execution, engine_real, target 0.25, governor); normal and stress rows; gate DD =
  max(4h, 1m-marked). IC on majors' test fills per anchor. References: v179 4.141 / 19.81, v180 4.088 / 21.03.

  python research/parallel/rounds/parallel-20260906-r2/v182/v182_pooled_gate.py
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
ROOT = HERE.parents[4]
ALTS = ("DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT", "TRXUSDT")
ALT_DIR = ROOT / "data/raw/alts_intraday_20260926"
FEATS = ["depth", "r5", "r15", "vspike", "taker15", "rng", "breadth", "btc_depth", "trend", "r1d", "funding", "k"]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v180 = _load("v180", HERE.parent / "v180/v180_model_gated_ladder.py")
v179, v173, v178, v171, v170, er, diag = v180.v179, v180.v173, v180.v178, v180.v171, v180.v170, v180.er, v180.diag
PD = er.PD


def asset_cube(G, sym, directory):
    starts = G + pd.Timedelta(hours=4)
    n = len(G)
    keys = ("open", "high", "low", "close", "volume", "taker_buy_volume")
    A = {k: np.full((n, 240), np.nan, dtype=np.float32) for k in keys}
    pos = pd.Series(np.arange(n), index=starts)
    m = pd.concat([pd.read_parquet(f, columns=["open_time", *keys]) for f in sorted(directory.glob(f"{sym}_1m_20*.parquet"))])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time")
    T = m["open_time"].dt.floor("4h")
    i = pos.reindex(T).to_numpy()
    ok = ~np.isnan(i)
    off = ((m["open_time"] - T).dt.total_seconds() // 60).astype(int).to_numpy()
    for k in keys:
        A[k][i[ok].astype(int), off[ok]] = m[k].to_numpy(float)[ok]
    for k in ("open", "high", "low", "close"):
        X = A[k]
        for mm in range(1, 240):
            miss = np.isnan(X[:, mm])
            X[:, mm][miss] = X[:, mm - 1][miss]
    for k in ("volume", "taker_buy_volume"):
        A[k] = np.nan_to_num(A[k])
    return A


def asset_candidates(G, sym, A, maj_dep, btc_dep):
    """Rung fills of one asset with minute f-1 features and normal-cost target."""
    k4 = pd.read_parquet(er.XS / f"{sym}_4h.parquet")
    o = pd.Series(k4["open"].to_numpy(float), index=pd.to_datetime(k4["open_time"], utc=True)).reindex(G)
    o1, o2 = o.shift(-1).to_numpy(), o.shift(-2).to_numpy()
    sig = o.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    trend = (o / o.rolling(42, min_periods=42).mean() - 1).shift(-1).to_numpy()
    r1d = (o.shift(-1) / o.shift(5) - 1).to_numpy()
    fs = er.funding_at_bar_open(sym, G)
    last_f = fs.replace(0.0, np.nan).ffill().fillna(0.0).to_numpy()
    fund_exit = fs.shift(-2).fillna(0.0).to_numpy()
    O, H, L, C, V, TB = (A[k] for k in ("open", "high", "low", "close", "volume", "taker_buy_volume"))
    xr = np.full(len(G), np.nan)
    xr[:-1] = (H[1:, 0] - L[1:, 0]) / O[1:, 0]
    s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr))
    rows = []
    for k in v178.RUNGS:
        lim = o1 * (1 - k * sig)
        hit = L[:, 16:239].astype(float) < lim[:, None]
        filled = hit.any(axis=1) & np.isfinite(o2) & np.isfinite(lim)
        gi = np.nonzero(filled)[0]
        f = np.argmax(hit[gi], axis=1) + 16
        p = f - 1
        s = sig[gi]
        y = o2[gi] * (1 - s_out[gi]) / lim[gi] - 1 - 0.0002 - 0.0005 - fund_exit[gi]
        rows.append(pd.DataFrame({
            "gi": gi, "f": f, "k": k, "y": y,
            "depth": (C[gi, p] / o1[gi] - 1) / s,
            "r5": (C[gi, p] / C[gi, p - 5] - 1) / s, "r15": (C[gi, p] / C[gi, p - 15] - 1) / s,
            "vspike": np.array([V[x, q - 4:q + 1].sum() / max(V[x, 0:q - 5].mean() * 5, 1e-9) for x, q in zip(gi, p)]),
            "taker15": np.array([TB[x, q - 14:q + 1].sum() / max(V[x, q - 14:q + 1].sum(), 1e-9) for x, q in zip(gi, p)]),
            "rng": (H[gi, p] - L[gi, p]) / C[gi, p] / s,
            "breadth": (maj_dep[gi, p, :] <= -2).sum(axis=1), "btc_depth": btc_dep[gi, p],
            "trend": trend[gi], "r1d": r1d[gi] / s, "funding": last_f[gi]}))
    d = pd.concat(rows, ignore_index=True)
    d["sym"] = sym
    d["T"] = G[d["gi"].to_numpy()] + pd.Timedelta(hours=4)
    return d[np.isfinite(d["y"])]


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v173.cube(G, cols)
    o_maj = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    sig_maj = o_maj.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    maj_dep = ((A["close"] / o_maj.shift(-1).to_numpy()[:, None, :] - 1) / sig_maj[:, None, :]).astype(np.float32)
    btc_dep = maj_dep[:, :, cols.index("BTCUSDT")]
    parts = []
    for j, s in enumerate(cols):
        one = {k: A[k][:, :, j] for k in ("open", "high", "low", "close", "volume", "taker_buy_volume")}
        parts.append(asset_candidates(G, s, one, maj_dep, btc_dep).assign(a=j, major=True))
    for s in ALTS:
        parts.append(asset_candidates(G, s, asset_cube(G, s, ALT_DIR), maj_dep, btc_dep).assign(a=-1, major=False))
        print("alt candidates", s, len(parts[-1]), flush=True)
    d = pd.concat(parts, ignore_index=True)
    rung_of = {k: r for r, k in enumerate(v178.RUNGS)}
    d["rung"] = d["k"].map(rung_of)
    print("candidates", len(d), "majors", int(d["major"].sum()), flush=True)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    lims, fmins, rets = v179.rung_table(G, cols, A, 0.0002, 0.0005, 0.0)
    gate = np.zeros(fmins.shape, dtype=bool)
    ic = {}
    for an in v171.ANCHORS:
        a0 = pd.Timestamp(an, tz="UTC")
        tr = d[(d["T"] + pd.Timedelta(hours=4) < a0 - pd.Timedelta(days=1)) & (d["T"] >= v171.START + pd.Timedelta(days=30))]
        te = d[d["major"] & (d["T"] - pd.Timedelta(hours=4) >= a0) & (d["T"] - pd.Timedelta(hours=4) < a0 + pd.Timedelta(days=365))]
        mdl = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=50,
                                            l2_regularization=1.0, random_state=0).fit(tr[FEATS], tr["y"])
        pred = mdl.predict(te[FEATS])
        kept = te[pred > 0]
        gate[kept["rung"].to_numpy(), kept["gi"].to_numpy(), kept["a"].to_numpy()] = True
        ic[an] = {"ic": round(float(pd.Series(pred).corr(te["y"].reset_index(drop=True), method="spearman")), 4),
                  "train": int(len(tr)), "train_alts": int((~tr["major"]).sum()), "test": int(len(te)), "kept": int(len(kept))}
        print(an, ic[an], flush=True)
    out = {"version": "v182", "ic": ic, "reference": {"v179": (4.141, 19.81), "v180": (4.088, 21.03)}}
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
    (HERE / "v182_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
