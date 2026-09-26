"""Live advisory for the v99 candidate (advisory only, no orders).

freeze: train the v92 HGB and the three v94 HGBs on all rows whose labels are realised before the freeze cutoff
        (same features/targets/hyperparameters as the audited research code) and save them.
advise: fetch closed Binance USD-M 4h/1d bars and funding for the five majors, rebuild the audited v92 features,
        predict, form the v92 long-only and v94 long/short books with their causal vol targets, add the carry
        state, apply the 15% portfolio vol target and return per-asset target weights.

  python scripts/v99_advisor.py freeze
  python scripts/v99_advisor.py advise
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
MODELS = ROOT / "models/frozen/v99_models.pkl"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, RD / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", "v94/v94_long_short_ensemble.py")
v99 = _load("v99", "v99/v99_candidate.py")
EXCLUDE = ("y", "t", "open", "sym", "bar")


def _hgb():
    return HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)


def freeze(cutoff: pd.Timestamp) -> None:
    panel = v94.add_targets(v92.build())
    feats = [c for c in panel.columns if c not in EXCLUDE and not c.startswith("y")]
    models = {"feats": feats, "cutoff": str(cutoff), "frozen_at": datetime.now(timezone.utc).isoformat()}
    for h in (42,) + v94.HORIZONS:
        col = "y" if h == 42 and "y" in panel else f"y{h}"
        tr = panel[(panel.t < cutoff) & panel[f"y{h}"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        m = _hgb().fit(tr[feats], tr[f"y{h}"])
        models[f"h{h}"] = m
        models[f"rows_h{h}"] = len(tr)
        print("trained horizon", h, "rows", len(tr), flush=True)
    MODELS.parent.mkdir(parents=True, exist_ok=True)
    MODELS.write_bytes(pickle.dumps(models))
    print("saved", MODELS)


def live_panel(session: requests.Session, now: datetime) -> pd.DataFrame:
    from agentic_alpha_lab.data.binance_usdm import BASE_URL, fetch_klines
    rows = []
    for i, s in enumerate(v92.SYMS):
        b = fetch_klines(s, "4h", now - timedelta(days=500), session=session)
        d = fetch_klines(s, "1d", now - timedelta(days=800), session=session)
        f = pd.DataFrame(session.get(f"{BASE_URL}/fapi/v1/fundingRate", params={"symbol": s, "limit": 1000}, timeout=60).json())
        f["fundingRate"] = f["fundingRate"].astype(float)
        f["fundingTime"] = pd.to_datetime(f["fundingTime"], unit="ms", utc=True)
        x, y = v92.features(b.reset_index(drop=True), d.reset_index(drop=True), f.sort_values("fundingTime"))
        x["asset"], x["y"], x["t"], x["open"], x["sym"], x["bar"] = i, y, b["open_time"].to_numpy(), b["open"].to_numpy(), s, np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    return panel.join(btc, on="t")


def advise() -> dict:
    models = pickle.loads(MODELS.read_bytes())
    feats = models["feats"]
    now = datetime.now(timezone.utc)
    s = requests.Session()
    panel = live_panel(s, now)
    recent = panel[panel.t >= panel.t.max() - pd.Timedelta(days=120)].copy()
    lo = recent.assign(pred=models["h42"].predict(recent[feats]))
    ls = recent.assign(pred=np.mean([models[f"h{h}"].predict(recent[feats]) for h in v94.HORIZONS], axis=0))
    W_lo = v92.weights_from(lo, "model")
    W_ls = v94.weights_ls(ls, True)
    idx = W_lo.index.union(W_ls.index)
    books = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(panel, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W_ls.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(panel, W_ls).reindex(idx).fillna(1.0), axis=0)
    # carry state with the frozen portfolio_v1 carry parameters (funding prints only)
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
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)  # carry leg omitted from the live vol estimate (no live carry return history)
    vol = realized.rolling(60 * v92.PD, min_periods=20 * v92.PD).std() * np.sqrt(v92.PD * 365)
    scale = float(min(v99.CAP, v99.TARGET / vol.iloc[-1])) if np.isfinite(vol.iloc[-1]) and vol.iloc[-1] > 0 else 1.0
    last = books.index[-1]
    perp = {sym: round(float(books.at[last, sym] * v99.W_BOOKS * scale), 4) for sym in books.columns}
    carry_notional = v99.W_CARRY * v99.CARRY_LEV * scale / len(v92.SYMS) / 1.2
    spot = {}
    for sym in v92.SYMS:
        n = carry_notional * carry_state[sym]
        perp[sym] = round(perp.get(sym, 0.0) - n, 4)
        spot[sym] = round(n, 4)
    closes = panel[panel.t == last].set_index("sym")["open"]
    return dict(candidate="v99_models_portfolio", decision_bar_close=str(last + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1)),
                perp_weight=perp, spot_weight=spot, portfolio_scale=round(scale, 3), carry_on=carry_state,
                predictions={"v92_7d": {r.sym: round(float(r.pred), 3) for r in lo[lo.t == last].itertuples()},
                             "v94_ensemble": {r.sym: round(float(r.pred), 3) for r in ls[ls.t == last].itertuples()}},
                models_cutoff=models["cutoff"], note="advisory only; v99 candidate (2.27%/month OOS 2021-2026, worst-year DD 15.3%); not a guarantee")


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        cutoff = pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp.now(tz="UTC").floor("D") - pd.Timedelta(days=17)
        freeze(cutoff)
    else:
        print(json.dumps(advise(), indent=1))
