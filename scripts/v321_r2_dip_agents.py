"""Frozen v321 R2 dip agents for the BOT paper pipeline R2 (CB books + dip ladder 2.5 / 3.0 / 3.5 / 4.0 / 5.0 sigma_4h) - research only.

R2 = the v306 seed chosen walk-forward in every dev fold and on dev4 (v321): G2 rules with a 5-sigma rung added, the dip size / take-profit agents
fitted on the pooled survivorship-free dip experience of ALL seven rung depths 2.0 .. 5.0 (v306 gene tables, fit "U"), sleeve budget 0.26, C4 rules.
Decisions are taken once per bar at the bar open (state at the close of minute 0), exactly the v306 bar-open form:
  size   x1.5 if both cross-fitted halves predict > 2 mu, x0.5 if both < 0, else x1          (v295 S1 rule)
  TP     {0.5, 1.0, 1.5} sigma_4h: deviate from 1.0 only if both halves prefer the same action by > 0.0010  (v294 X4)
Walk-forward record (research, engine_user): 5y 6.793 %/month, most recent year 5.655 (scored once, v321), full-path DD 18.39, all-trade win 0.664.
  python scripts/v321_r2_dip_agents.py freeze [YYYY-MM-DD]     # default cutoff 2026-09-11 (same as the v301 G2 agents)
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
MODELS = ROOT / "models/frozen/v321_r2_dip_agents.pkl"
ACTIONS = (0.5, 1.0, 1.5)
FIT_RUNGS = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)   # experience of every depth (v306 fit "U")
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)                 # the R2 ladder


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sa = _load("v295_size_agent_for_v321", ROOT / "scripts/v295_size_agent.py")


class LiveState(sa.LiveState):
    """The seven v293 state features; the rung-depth feature is the R2 ladder depth of rung index r."""

    def features(self, s: str, bar_start: pd.Timestamp, rung: int, minute: int = 0) -> np.ndarray:
        x = super().features(s, bar_start, 0, minute)
        x[1] = RUNGS[rung]
        return x


def freeze(cutoff: pd.Timestamp) -> None:
    from sklearn.ensemble import HistGradientBoostingRegressor
    v294 = _load("v294_freeze321", RD / "v294/v294_wide_pool_exit_agent.py")
    v293 = v294.v293
    v293.RUNGS = FIT_RUNGS
    eu = _load("engine_user_freeze321", RD / "engine_user/engine_user.py")
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
                                     "fit_rungs": FIT_RUNGS, "rungs": RUNGS, "frozen_at": datetime.now(timezone.utc).isoformat()}))
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
