"""Live advisory for the v104 candidate (advisory only, no orders).

v104 = v99 wrapper (80% books + 20% carry x3, 15% portfolio vol target, cap 2) with books = 0.5 * v96 books
(v92 long-only + v94 long/short) + 0.5 * v103 long/short (1d/3d order-flow HGB). Same code paths as the audited
research scripts in research/parallel/rounds/parallel-20260906-r2.

  python scripts/v104_advisor.py freeze [YYYY-MM-DD]
  python scripts/v104_advisor.py advise
"""

from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
MODELS = ROOT / "models/frozen/v104_models.pkl"
PORT_TARGET = 0.15


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", RD / "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", RD / "v94/v94_long_short_ensemble.py")
v99 = _load("v99", RD / "v99/v99_candidate.py")
v103 = _load("v103", RD / "v103/v103_flow_short_horizon.py")


def _hgb():
    return HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)


def _fit(panel, feats, col, h, cutoff):
    tr = panel[(panel.t < cutoff) & panel[col].notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
    return _hgb().fit(tr[feats], tr[col]), len(tr)


def freeze(cutoff: pd.Timestamp) -> None:
    p94 = v94.add_targets(v92.build())
    f92 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    models = {"feats92": f92, "feats103": f103, "cutoff": str(cutoff), "frozen_at": datetime.now(timezone.utc).isoformat()}
    for h in (42,) + v94.HORIZONS:
        models[f"h{h}"], n = _fit(p94, f92, f"y{h}", h, cutoff)
        print("v92/v94 horizon", h, "rows", n, flush=True)
    for h in v103.HS:
        models[f"f{h}"], n = _fit(p103, f103, f"y{h}", h, cutoff)
        print("v103 horizon", h, "rows", n, flush=True)
    MODELS.write_bytes(pickle.dumps(models))
    print("saved", MODELS)


def live_panel(session: requests.Session, now: datetime) -> pd.DataFrame:
    from agentic_alpha_lab.data.binance_usdm import BASE_URL, fetch_klines
    rows = []
    for i, s in enumerate(v92.SYMS):
        b = fetch_klines(s, "4h", now - timedelta(days=500), session=session).reset_index(drop=True)
        d = fetch_klines(s, "1d", now - timedelta(days=800), session=session).reset_index(drop=True)
        f = pd.DataFrame(session.get(f"{BASE_URL}/fapi/v1/fundingRate", params={"symbol": s, "limit": 1000}, timeout=60).json())
        f["fundingRate"] = f["fundingRate"].astype(float)
        f["fundingTime"] = pd.to_datetime(f["fundingTime"], unit="ms", utc=True)
        x, y = v92.features(b, d, f.sort_values("fundingTime"))
        x = pd.concat([x, v103.flow_features(b, x["vol42"])], axis=1)
        x["asset"], x["y"], x["t"], x["open"], x["sym"], x["bar"] = i, y, b["open_time"].to_numpy(), b["open"].to_numpy(), s, np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    return panel.join(btc, on="t")


def _augment(recent):
    return recent


def _prep(lo, ls, fl, recent):
    return lo, ls, fl


def _w_lo(df):
    return v92.weights_from(df, "model")


def _w_ls(df):
    return v94.weights_ls(df, True)


def advise() -> dict:
    models = pickle.loads(MODELS.read_bytes())
    now = datetime.now(timezone.utc)
    s = requests.Session()
    panel = live_panel(s, now)
    recent = _augment(panel[panel.t >= panel.t.max() - pd.Timedelta(days=120)].copy())
    lo = recent.assign(pred=models["h42"].predict(recent[models["feats92"]]))
    ls = recent.assign(pred=np.mean([models[f"h{h}"].predict(recent[models["feats92"]]) for h in v94.HORIZONS], axis=0))
    fl = recent.assign(pred=np.mean([models[f"f{h}"].predict(recent[models["feats103"]]) for h in v103.HS], axis=0))
    lo, ls, fl = _prep(lo, ls, fl, recent)
    W_lo, W_ls, W_fl = _w_lo(lo), _w_ls(ls), _w_ls(fl)
    idx = W_lo.index.union(W_ls.index).union(W_fl.index)

    def scaled(W, fn):
        return W.reindex(idx).fillna(0.0).mul(fn(panel, W).reindex(idx).fillna(1.0), axis=0)

    books = 0.25 * scaled(W_lo, v92.vol_target_scale) + 0.25 * scaled(W_ls, v94.vol_target_scale) + 0.5 * scaled(W_fl, v94.vol_target_scale)
    from agentic_alpha_lab.data.binance_usdm import BASE_URL
    from agentic_alpha_lab.signals.portfolio_advisor import carry_on
    carry_cfg = json.loads((ROOT / "artifacts/research/advisor_shadow/portfolio_v1.json").read_text())["carry"]
    carry_state = {}
    for sym in v92.SYMS:
        f = pd.DataFrame(s.get(f"{BASE_URL}/fapi/v1/fundingRate", params={"symbol": sym, "limit": 1000}, timeout=60).json())
        f["fundingRate"] = f["fundingRate"].astype(float)
        f["fundingTime"] = pd.to_datetime(f["fundingTime"], unit="ms", utc=True)
        carry_state[sym] = carry_on(f, carry_cfg[sym])
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)  # carry leg omitted (no live carry return history)
    vol = realized.rolling(60 * v92.PD, min_periods=20 * v92.PD).std() * np.sqrt(v92.PD * 365)
    scale = float(min(v99.CAP, PORT_TARGET / vol.iloc[-1])) if np.isfinite(vol.iloc[-1]) and vol.iloc[-1] > 0 else 1.0
    last = books.index[-1]
    perp = {sym: round(float(books.at[last, sym] * v99.W_BOOKS * scale), 4) for sym in books.columns}
    carry_notional = v99.W_CARRY * v99.CARRY_LEV * scale / len(v92.SYMS) / 1.2
    spot = {}
    for sym in v92.SYMS:
        n = carry_notional * carry_state[sym]
        perp[sym] = round(perp.get(sym, 0.0) - n, 4)
        spot[sym] = round(n, 4)
    return dict(candidate="v104_models_portfolio", decision_bar_close=str(last + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1)),
                perp_weight=perp, spot_weight=spot, portfolio_scale=round(scale, 3), carry_on=carry_state,
                predictions={k: {r.sym: round(float(r.pred), 3) for r in df[df.t == last].itertuples()} for k, df in (("v92_7d", lo), ("v94_ensemble", ls), ("v103_flow", fl))},
                models_cutoff=models["cutoff"], note="advisory only; v104 candidate (2.44%/month OOS 2021-2026, worst-year DD 15.8%); not a guarantee")


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        cutoff = pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=17)
        freeze(cutoff)
    else:
        print(json.dumps(advise(), indent=1))
