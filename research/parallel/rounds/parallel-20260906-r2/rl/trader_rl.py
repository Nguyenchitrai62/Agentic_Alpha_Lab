"""Offline reinforcement learning for the trade-mode trader agent (fitted Q iteration with gradient-boosted trees).

The environment is engine_user's trade mode (1m execution, limit entries with the minute-5 rule, SL market / TP limit,
break-even rule, Bybit fees, adverse funding, governor, aligned dip sleeve). At every 4h decision and for every coin the
agent picks a trader action through trade["policy"]:
  flat with a signal (|target| >= 5%):  wait | open (limit, 0.25 sigma_4h) | open_deep (limit, 0.75 sigma_4h)
  in a position:                        hold | tighten | reduce (50% limit) | close (100% limit) | add (limit, if allowed)
The direction and size come from the v205 pipeline (the foundation); the agent decides timing and trade management.

Causality: market features use 4h opens up to the decision (the holding bar's minute-0 price = the decision close), the
books of the decision row and the position state known at the decision. Rewards are the coin's realised book PnL of the
holding bar (fraction of equity, fees and funding included). A Q model for walk-forward year Y is fitted only on
transitions whose whole reward window ends before Y minus an embargo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

FLAT_ACTIONS = ("wait", "open", "open_deep")
POS_ACTIONS = ("hold", "tighten", "reduce", "close", "add")
ALL_ACTIONS = FLAT_ACTIONS + POS_ACTIONS
POS_KEYS = ("pos", "w", "tg", "upnl", "bars", "be", "nadd", "nred", "dsl", "dtp")
N_MARKET = 16  # number of market features (market_features); the position side follows them in the state vector
POS_INDEX = N_MARKET


def market_features(opens: pd.DataFrame, idx: pd.DatetimeIndex, cols: list[str], members: dict[str, pd.DataFrame]) -> np.ndarray:
    """(n, na, F) causal features for every decision row i (known at the close of bar idx[i]).

    The close of bar idx[i] is the next open (o1); returns are measured on o1 up to row i, scaled by sigma_4h.
    """
    o = opens.reindex(idx)[cols]
    o1 = o.shift(-1)  # decision-time price (close of the decision bar = open of the holding bar)
    lo1 = np.log(o1)
    r1 = lo1.diff()
    sig = r1.rolling(360, min_periods=120).std()
    f = {}
    for k in (1, 6, 42, 180):
        f[f"ret{k}"] = (lo1 - lo1.shift(k)) / (sig * np.sqrt(k))
    for k in (42, 180):
        f[f"hi{k}"] = (lo1 - lo1.rolling(k).max()) / sig
        f[f"lo{k}"] = (lo1 - lo1.rolling(k).min()) / sig
    f["vol_regime"] = sig / sig.rolling(540, min_periods=180).median()
    f["sig4"] = sig
    btc = lo1["BTCUSDT"] if "BTCUSDT" in cols else lo1.iloc[:, 0]
    bsig = btc.diff().rolling(360, min_periods=120).std()
    for k in (6, 42):
        f[f"btc{k}"] = pd.DataFrame({c: (btc - btc.shift(k)) / (bsig * np.sqrt(k)) for c in cols})
    for name, m in members.items():
        f[name] = m.reindex(idx)[cols]
    mats = [f[k].to_numpy(dtype=float) for k in f]
    return np.stack(mats, axis=2), list(f)


class Recorder:
    """Policy wrapper: calls the behaviour policy, records (i, a, features, action, valid)."""

    def __init__(self, feats, behaviour):
        self.feats, self.behaviour, self.rows = feats, behaviour, []

    def __call__(self, i, a, st):
        act = self.behaviour(i, a, st)
        self.rows.append((i, a, state_vector(self.feats, i, a, st), encode(act), st["valid"]))
        return act


def state_vector(feats, i, a, st):
    side = st.get("pos", 0)
    along = st["tg"] * (side if side != 0 else np.sign(st["tg"]))  # target measured along the position (or the signal)
    pos = [side, st.get("w", 0.0), along, st.get("upnl", 0.0), min(st.get("bars", 0), 500), float(bool(st.get("be", False))),
           st.get("nadd", 0), st.get("nred", 0), np.clip(st.get("dsl", 0.0), -20, 20), np.clip(st.get("dtp", 0.0), -20, 20),
           abs(st["tg"]), st.get("g", 1.0)]
    return np.concatenate([np.nan_to_num(feats[i, a], nan=0.0, posinf=0.0, neginf=0.0), np.array(pos, dtype=float)])


def encode(act):
    """A combined action (set) is recorded by its main component: close > reduce > add > tighten > hold."""
    if isinstance(act, str):
        return act
    for k in ("close", "reduce", "add", "open_deep", "open", "tighten", "wait"):
        if k in act:
            return k
    return "hold"


def build_dataset(rows, attrib, idx, gamma):
    """Transitions from a recorded run. attrib rows are (t = idx[i] + 4h, per-coin PnL, sleeve PnL)."""
    t_to_pnl = {t: bp for t, bp, _ in attrib}
    n = len(idx)
    na = len(next(iter(t_to_pnl.values())))
    pnl = np.zeros((n, na))
    for i in range(n):
        bp = t_to_pnl.get(idx[i] + pd.Timedelta(hours=4))
        if bp is not None:
            pnl[i] = bp
    by_coin = {}
    for r in rows:
        by_coin.setdefault(r[1], []).append(r)
    X, A, R, D, XN, VN, TEND, COIN, NPOS = [], [], [], [], [], [], [], [], []
    for a, rs in by_coin.items():
        rs.sort(key=lambda r: r[0])
        for k, (i, _, x, act, valid) in enumerate(rs):
            COIN.append(a)
            NPOS.append(rs[k + 1][2][POS_INDEX] if k + 1 < len(rs) else 0.0)
            if k + 1 < len(rs):
                j = rs[k + 1][0]
                disc = gamma ** np.arange(j - i)
                R.append(float((pnl[i:j, a] * disc).sum()))
                D.append(gamma ** (j - i))
                XN.append(rs[k + 1][2])
                VN.append(rs[k + 1][4])
                TEND.append(idx[j])
            else:
                R.append(float(pnl[i, a]))
                D.append(0.0)
                XN.append(x)
                VN.append(("hold",))
                TEND.append(idx[i] + pd.Timedelta(hours=4))
            X.append(x)
            A.append(act)
    ds = dict(X=np.array(X), A=np.array(A), R=np.array(R), D=np.array(D), XN=np.array(XN), VN=VN,
              TEND=pd.DatetimeIndex(TEND), COIN=np.array(COIN), NPOS=np.array(NPOS))
    # Monte Carlo return of the behaviour policy until the position of this decision is closed (flat next state -> stop)
    G = np.zeros(len(R))
    for k in range(len(R) - 1, -1, -1):
        cont = k + 1 < len(R) and COIN[k + 1] == COIN[k] and NPOS[k] != 0 and ds["D"][k] > 0
        G[k] = R[k] + (ds["D"][k] * G[k + 1] if cont else 0.0)
    ds["G"] = G
    return ds


class QModel:
    """One boosted-tree regressor per action. mode "fqi": fitted Q iteration; mode "mc": Monte Carlo returns of the
    behaviour policy until the position closes (one-step policy improvement, no bootstrapping)."""

    def __init__(self, mode="fqi", iters=10, reward_scale=100.0, loss_mult=1.0, seed=0, max_rows=250_000):
        self.mode, self.iters, self.scale, self.loss_mult, self.seed, self.max_rows = mode, iters, reward_scale, loss_mult, seed, max_rows
        self.models = {}

    def _reg(self):
        return HistGradientBoostingRegressor(max_depth=5, learning_rate=0.05, max_iter=200, min_samples_leaf=100,
                                             l2_regularization=1.0, random_state=self.seed)

    def _shape(self, r):
        r = r * self.scale
        return np.where(r < 0, r * self.loss_mult, r) if self.loss_mult != 1.0 else r

    def _fit_all(self, X, A, y):
        rng = np.random.default_rng(self.seed)
        for act in ALL_ACTIONS:
            rows = np.flatnonzero(A == act)
            if len(rows) < 50:
                continue
            if len(rows) > self.max_rows:
                rows = rng.choice(rows, self.max_rows, replace=False)
            self.models[act] = self._reg().fit(X[rows], y[rows])

    def q_all(self, X, valids):
        out = [dict() for _ in range(len(X))]
        for act, mdl in self.models.items():
            rows = [k for k, v in enumerate(valids) if act in v]
            if rows:
                for k, v in zip(rows, mdl.predict(X[rows])):
                    out[k][act] = v
        return out

    def fit(self, ds):
        X, A = ds["X"], ds["A"]
        if self.mode == "mc":
            self._fit_all(X, A, self._shape(ds["G"]))
            return self
        R = self._shape(ds["R"])
        y = R.copy()
        for _ in range(self.iters):
            self._fit_all(X, A, y)
            qn = self.q_all(ds["XN"], ds["VN"])
            y = R + ds["D"] * np.array([max(d.values()) if d else 0.0 for d in qn])
        return self


def onehot(actions):
    return np.array([[1.0 if a == b else 0.0 for b in ALL_ACTIONS] for a in actions])


class FQI:
    """Fitted Q iteration: Q(x, a) with one boosted-tree regressor on [x, onehot(a)]."""

    def __init__(self, iters=15, reward_scale=100.0, loss_mult=1.0, seed=0):
        self.iters, self.scale, self.loss_mult, self.seed = iters, reward_scale, loss_mult, seed
        self.model = None

    def _q(self, X, acts):
        return self.model.predict(np.hstack([X, onehot(acts)]))

    def q_all(self, X, valids):
        """Q of every valid action for each row -> list of dicts."""
        out = [dict() for _ in range(len(X))]
        for act in ALL_ACTIONS:
            rows = [k for k, v in enumerate(valids) if act in v]
            if rows:
                q = self._q(X[rows], [act] * len(rows))
                for k, v in zip(rows, q):
                    out[k][act] = v
        return out

    def fit(self, ds):
        R = ds["R"] * self.scale
        if self.loss_mult != 1.0:
            R = np.where(R < 0, R * self.loss_mult, R)  # losses count more (the user's "wrong and big must hurt")
        XA = np.hstack([ds["X"], onehot(ds["A"])])
        y = R.copy()
        for it in range(self.iters):
            self.model = HistGradientBoostingRegressor(max_depth=5, learning_rate=0.05, max_iter=250, min_samples_leaf=200,
                                                       l2_regularization=1.0, random_state=self.seed)
            self.model.fit(XA, y)
            qn = self.q_all(ds["XN"], ds["VN"])
            vmax = np.array([max(d.values()) if d else 0.0 for d in qn])
            y = R + ds["D"] * vmax
        return self
