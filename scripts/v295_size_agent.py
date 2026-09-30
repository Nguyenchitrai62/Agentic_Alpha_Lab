"""Frozen v295 S1 size agent for the paper pipeline CS (CB + learned dip-rung sizing) - research output only, no orders.

v295 S1: a HistGradientBoosting model (two cross-fitted halves) predicts the net return of a filled dip rung under the default exit from
seven state features; the rung is sized x1.5 if both halves predict > 2 mu, x0.5 if both predict < 0, else x1.0 (mu = mean training
return). Trained on the pooled, survivorship-free dip experience of 35 coins (5 majors + the U2020 alts, training only).
DEPLOYED FORM (research/diagnostics/s1_exec, 'placement at the bar open'): the size of every rung of a 4h bar is decided once when the
ladder is placed, from the state at the close of minute 0 of the holding bar (known at minute 1, when the backend cycle runs):
walk-forward in research 5y 5.987, most recent year 5.266, worst dev year 3.425, DD 17.20 (CB 5.725 / 5.167 / 3.005 / 18.39).
  python scripts/v295_size_agent.py freeze [YYYY-MM-DD]     # train on fills that exited before the cutoff (default 2026-09-11)
"""

from __future__ import annotations

import importlib.util
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
MODELS = ROOT / "models/frozen/v295_size_models.pkl"
RUNGS = (2.5, 3.0, 3.5, 4.0)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def freeze(cutoff: pd.Timestamp) -> None:
    from sklearn.ensemble import HistGradientBoostingRegressor
    v294 = _load("v294_freeze", RD / "v294/v294_wide_pool_exit_agent.py")
    v293 = v294.v293
    eu = _load("engine_user_freeze", RD / "engine_user/engine_user.py")
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    parts = []
    for s in v293.MAJORS + v294.universe():
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
        if len(d):
            parts.append(d.assign(sym=s))
        del A
    allf = pd.concat(parts, ignore_index=True)
    keep = np.asarray(allf.t_exit < cutoff)
    X = allf.loc[keep, [f"x{q}" for q in range(7)]].to_numpy(float)
    y = np.clip(allf.loc[keep, "y1.0"].to_numpy(float), -0.10, 0.08)
    half = (allf.loc[keep, "j"] % 2).to_numpy()
    models = [HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                            random_state=40 + h).fit(X[half == h], y[half == h]) for h in (0, 1)]
    MODELS.parent.mkdir(parents=True, exist_ok=True)
    MODELS.write_bytes(pickle.dumps({"models": models, "mu": float(y.mean()), "cutoff": str(cutoff), "rows": int(keep.sum()),
                                     "frozen_at": datetime.now(timezone.utc).isoformat()}))
    print("saved", MODELS, "rows", int(keep.sum()), "mu", round(float(y.mean()), 5), flush=True)


class LiveState:
    """The seven v293 state features from live data: 4h opens (>= 150 days) and 1m klines (>= 1 day before the bar)."""

    def __init__(self, opens4h: pd.DataFrame, k1: dict):
        self.o = opens4h.sort_index()
        pc = self.o.pct_change()
        self.sig = pc.rolling(360, min_periods=120).std().shift(1)
        self.volreg = self.sig / self.sig.rolling(540, min_periods=180).median()
        self.trend = (np.log(self.o) - np.log(self.o.shift(42))) / (self.sig * np.sqrt(42))
        self.k1 = {s: m.sort_index() for s, m in k1.items()}

    def _sp30(self, s, t_min):
        m = self.k1[s]
        c = m["close"][m.index <= t_min]
        if len(c) < 1441:
            return np.nan
        lr = np.log(c).diff().iloc[-1440:]
        s1 = float(lr.std())
        return float(np.log(c.iloc[-1] / c.iloc[-31]) / (s1 * np.sqrt(30))) if s1 > 0 else np.nan

    def features(self, s: str, bar_start: pd.Timestamp, rung: int, minute: int = 0) -> np.ndarray:
        t_min = bar_start + pd.Timedelta(minutes=minute)   # close of this minute (known one minute later)
        m = self.k1[s]
        sg = float(self.sig[s].get(bar_start, np.nan))
        hi = m["high"][(m.index <= t_min) & (m.index > t_min - pd.Timedelta(minutes=1440))].max()
        c = m["close"][m.index <= t_min].iloc[-1]
        return np.array([self._sp30(s, t_min), RUNGS[rung], float(self.volreg[s].get(bar_start, np.nan)),
                         float(self.trend[s].get(bar_start, np.nan)), self._sp30("BTCUSDT", t_min),
                         np.log(c / hi) / sg if hi > 0 and sg > 0 else np.nan, (bar_start.hour + minute // 60) % 24], float)


def multiplier(x: np.ndarray, frozen: dict) -> float:
    pa, pb = (float(mm.predict(x[None, :])[0]) for mm in frozen["models"])
    if pa > 2 * frozen["mu"] and pb > 2 * frozen["mu"]:
        return 1.5
    if pa < 0 and pb < 0:
        return 0.5
    return 1.0


def load() -> dict:
    return pickle.loads(MODELS.read_bytes())


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze(pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp("2026-09-11", tz="UTC"))
