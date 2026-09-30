"""Frozen v301 G2 dip agents for the paper pipeline G2 (CB + learned dip size AND take-profit, sleeve budget 0.26) - research only.

G2 = v296 J1 agents with the dip-sleeve risk budget 0.26 (v301, audited). Both agents read the seven v293 state features and were trained
on the pooled, survivorship-free dip experience of 35 coins (majors + U2020 alts, training only):
  size   x1.5 if both cross-fitted halves predict > 2 mu, x0.5 if both < 0, else x1 (v295 S1 rule)
  TP     take-profit multiple in {0.5, 1.0, 1.5} sigma_4h: deviate from 1.0 only if both halves prefer the same action by > 0.0010 (v294 X4)
DEPLOYED FORM (research/diagnostics/g2_exec): every decision of a 4h bar's ladder is taken once at the bar open (state at the close of
minute 0): walk-forward 5y 6.272, most recent year 5.349, worst dev year 3.736, DD 17.09 (CS 5.987 / 5.266 / 3.425 / 17.20).
  python scripts/v301_dip_agents.py freeze [YYYY-MM-DD]     # default cutoff 2026-09-11
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
MODELS = ROOT / "models/frozen/v301_dip_agents.pkl"
ACTIONS = (0.5, 1.0, 1.5)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sa = _load("v295_size_agent_for_v301", ROOT / "scripts/v295_size_agent.py")
LiveState, RUNGS = sa.LiveState, sa.RUNGS


def freeze(cutoff: pd.Timestamp) -> None:
    from sklearn.ensemble import HistGradientBoostingRegressor
    v294 = _load("v294_freeze301", RD / "v294/v294_wide_pool_exit_agent.py")
    v293 = v294.v293
    eu = _load("engine_user_freeze301", RD / "engine_user/engine_user.py")
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
    Y = np.clip(allf.loc[keep, [f"y{mu}" for mu in ACTIONS]].to_numpy(float), -0.10, 0.08)
    half = (allf.loc[keep, "j"] % 2).to_numpy()

    def hgb(seed):
        return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                             random_state=seed)
    y1 = Y[:, ACTIONS.index(1.0)]
    size = [hgb(40 + h).fit(X[half == h], y1[half == h]) for h in (0, 1)]
    tp = [[hgb(50 + h + 3 * c).fit(X[half == h], Y[half == h, c]) for c in range(len(ACTIONS))] for h in (0, 1)]
    MODELS.parent.mkdir(parents=True, exist_ok=True)
    MODELS.write_bytes(pickle.dumps({"size": size, "tp": tp, "mu": float(y1.mean()), "cutoff": str(cutoff), "rows": int(keep.sum()),
                                     "frozen_at": datetime.now(timezone.utc).isoformat()}))
    print("saved", MODELS, "rows", int(keep.sum()), "mu", round(float(y1.mean()), 5), flush=True)


def size_multiplier(x: np.ndarray, fz: dict) -> float:
    pa, pb = (float(m.predict(x[None, :])[0]) for m in fz["size"])
    if pa > 2 * fz["mu"] and pb > 2 * fz["mu"]:
        return 1.5
    if pa < 0 and pb < 0:
        return 0.5
    return 1.0


def tp_multiple(x: np.ndarray, fz: dict) -> float:
    pa = np.array([float(m.predict(x[None, :])[0]) for m in fz["tp"][0]])
    pb = np.array([float(m.predict(x[None, :])[0]) for m in fz["tp"][1]])
    ba, bb, base = int(np.argmax(pa)), int(np.argmax(pb)), ACTIONS.index(1.0)
    if ba == bb and ba != base and pa[ba] - pa[base] > 0.0010 and pb[bb] - pb[base] > 0.0010:
        return ACTIONS[ba]
    return 1.0


def load() -> dict:
    return pickle.loads(MODELS.read_bytes())


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze(pd.Timestamp(sys.argv[2], tz="UTC") if len(sys.argv) > 2 else pd.Timestamp("2026-09-11", tz="UTC"))
