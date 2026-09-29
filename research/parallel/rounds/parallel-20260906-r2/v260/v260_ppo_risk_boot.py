"""v260: PPO risk manager trained on BOOTSTRAPPED market paths, judged on the median of five seeds (fix of v259's seed luck).

Why: v259's daily risk manager passed the whole gate with its registered seed (5y 5.114, most recent year 5.309, DD 17.45) but four other
seeds of the same method gave the most recent year 2.3-3.6 and dev4 4.5-5.0: the policy learned from 1-3 years of 30-day episodes has a
large seed variance (too little training data). Standard RL remedy: train on many resampled paths. Each training episode is built from
random 30-day blocks (180 bars) of the pre-anchor bars, the strategy PnL and the market state resampled JOINTLY (stationary block
bootstrap), so the policy sees thousands of different sequences of regimes instead of one history.
Fixed before running.
Everything as v259 (environment v247 B18 with the risk_mult hook, actions {0.5, 0.75, 1.0, 1.25} daily, state, reward with lam 5 = v259
K2, PPO net / lr / clip / entropy / gamma / GAE, walk-forward training bars from 2021-09-24 to anchor - 7 days, 2021 at m = 1), except:
episodes = 90 daily decisions made of three random 30-day blocks; 100 updates of 32 episodes.
  B1_boot   seeds 260 + anchor + {0, 1000, 2000, 3000, 4000} (five seeds)
DECISION RULE (fixed): the method is adopted only if the MEDIAN seed (by dev4) beats the v247 B18 reference under the robust criterion
(dev4 >= 5, no losing dev year, DD <= 20, then the worst dev year). The most recent year is reported for every seed and the median (the
method is the finalist; no seed is picked).

  python research/parallel/rounds/parallel-20260906-r2/v260/v260_ppo_risk_boot.py
"""

from __future__ import annotations

import torch  # noqa: F401  (import torch before pandas on this Windows host)
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch.nn as nn

HERE = Path(__file__).parent
RD = HERE.parent
BUDGET = 0.18
EMBARGO = pd.Timedelta(days=7)
ACTS = np.array([0.5, 0.75, 1.0, 1.25])
STEP, EP_DEC, BLOCK = 6, 90, 180
N_ENV, UPDATES, EPOCHS, MB = 32, 100, 4, 512
SEEDS = (0, 1000, 2000, 3000, 4000)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Net(nn.Module):
    def __init__(self, d, k):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(d, 64), nn.Tanh(), nn.Linear(64, 64), nn.Tanh())
        self.pi, self.v = nn.Linear(64, k), nn.Linear(64, 1)

    def forward(self, x):
        h = self.body(x)
        return self.pi(h), self.v(h).squeeze(-1)


def eq_state(eqh, vol_hist):
    """Equity-derived state from an equity path ending at the lagged bar."""
    e = np.asarray(eqh, float)
    if len(e) < 3:
        return np.zeros(4)
    peak = e[-540:].max()
    dd = 1 - e[-1] / peak
    r7 = np.log(e[-1] / e[max(0, len(e) - 43)])
    r30 = np.log(e[-1] / e[max(0, len(e) - 181)])
    lr = np.diff(np.log(e[-181:]))
    v = float(lr.std() * np.sqrt(6 * 365)) if len(lr) > 5 else np.nan
    med = np.nanmedian(vol_hist) if len(vol_hist) else np.nan
    vr = v / med if np.isfinite(v) and np.isfinite(med) and med > 0 else 1.0
    return np.array([dd, r7, r30, vr])


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v232 = _load("v232_k", RD / "v232/v232_disciplined_rl.py")
    v240 = _load("v240_k", RD / "v240/v240_order_level_flow.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    KW = dict(v221.KW, sleeve_risk_budget=BUDGET)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    n = len(idx)
    t_hold = idx + pd.Timedelta(hours=4)

    # ---- market state per decision row (bar close)
    tv = v232.tv_frames(idx, cols)
    o = opens.reindex(idx)[cols]
    lo1 = np.log(o.shift(-1))
    sig = lo1.diff().rolling(360, min_periods=120).std()
    b = "BTCUSDT"
    mkt = np.nan_to_num(np.column_stack([
        (lo1[b].diff(42) / (sig[b] * np.sqrt(42))).to_numpy(), (sig[b] / sig[b].rolling(540, min_periods=180).median()).to_numpy(),
        books.abs().mean(axis=1).to_numpy() * 10, tv["tv_st_dir"].reindex(idx)[cols].mean(axis=1).to_numpy(),
        pd.DataFrame({c: v240.flo.flow_features(c, idx)["fl_big_imb6"].to_numpy() for c in cols}, index=idx).mean(axis=1).to_numpy() * 10]))

    # ---- reference run: per-bar book + sleeve PnL (attribution) -> training proxy
    att = []
    ref = eu.simulate(books, opens, prep, trade=trade, win_start=5, attrib=att, **KW)
    assert abs(ref["monthly_dev4"] - 5.777) < 0.002, "risk_mult None must reproduce v247 B18"
    pos_i = {t: k for k, t in enumerate(t_hold)}
    R = np.zeros(n)
    for t, bp, sp in att:
        k = pos_i.get(t)
        if k is not None:
            R[k] = float(np.sum(bp)) + float(sp)

    def train(rows, seed, lam):
        torch.manual_seed(seed)
        rng = np.random.default_rng(seed)
        net = Net(10, len(ACTS))
        opt = torch.optim.Adam(net.parameters(), lr=3e-4)
        starts_ok = rows[(rows + BLOCK) <= rows[-1]]
        nblk = EP_DEC * STEP // BLOCK
        for _ in range(UPDATES):
            seq = np.stack([np.concatenate([s0 + np.arange(BLOCK) for s0 in rng.choice(starts_ok, nblk)]) for _e in range(N_ENV)])
            eqs = [list(np.ones(200)) for _ in range(N_ENV)]  # flat warm-up history
            vh = [[] for _ in range(N_ENV)]
            mcur = np.ones(N_ENV)
            peak_dd = np.zeros(N_ENV)
            X, A, LP, V, RW = [], [], [], [], []
            for d in range(EP_DEC):
                i0 = seq[:, d * STEP]
                st = np.array([np.r_[eq_state(eqs[e][:-2] if len(eqs[e]) > 2 else eqs[e], vh[e]), mkt[i0[e]], mcur[e]] for e in range(N_ENV)], np.float32)
                with torch.no_grad():
                    lg, v = net(torch.from_numpy(st))
                    dist = torch.distributions.Categorical(logits=lg)
                    a = dist.sample()
                mcur = ACTS[a.numpy()]
                rew = np.zeros(N_ENV)
                for e in range(N_ENV):
                    for k in range(STEP):
                        r = mcur[e] * R[seq[e, d * STEP + k]]
                        eqs[e].append(eqs[e][-1] * (1 + r))
                        ee = np.asarray(eqs[e][-540:])
                        dd = 1 - ee[-1] / ee.max()
                        exc = max(0.0, dd - 0.10)
                        rew[e] += 100 * np.log1p(r) - lam * 100 * max(0.0, exc - peak_dd[e])
                        peak_dd[e] = max(peak_dd[e], exc)
                    lr_ = np.diff(np.log(np.asarray(eqs[e][-181:])))
                    vh[e].append(float(lr_.std() * np.sqrt(6 * 365)))
                X.append(st), A.append(a.numpy()), LP.append(dist.log_prob(a).numpy()), V.append(v.numpy()), RW.append(rew)
            adv = np.zeros((EP_DEC, N_ENV))
            last = np.zeros(N_ENV)
            nv = np.zeros(N_ENV)
            for t in reversed(range(EP_DEC)):
                delta = RW[t] + 0.97 * nv - V[t]
                last = delta + 0.97 * 0.95 * last
                adv[t] = last
                nv = V[t]
            ret = adv + np.array(V)
            Xt = torch.from_numpy(np.concatenate(X))
            At = torch.from_numpy(np.concatenate(A))
            LPt = torch.from_numpy(np.concatenate(LP))
            ADV = torch.from_numpy(adv.reshape(-1).astype(np.float32))
            ADV = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
            RET = torch.from_numpy(ret.reshape(-1).astype(np.float32))
            nn_ = len(At)
            for _e in range(EPOCHS):
                perm = torch.from_numpy(rng.permutation(nn_))
                for s in range(0, nn_, MB):
                    j = perm[s:s + MB]
                    lg, v = net(Xt[j])
                    dist = torch.distributions.Categorical(logits=lg)
                    ratio = torch.exp(dist.log_prob(At[j]) - LPt[j])
                    pl = -torch.min(ratio * ADV[j], torch.clamp(ratio, 0.8, 1.2) * ADV[j]).mean()
                    loss = pl + 0.5 * ((v - RET[j]) ** 2).mean() - 0.01 * dist.entropy().mean()
                    opt.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                    opt.step()
        return net.eval()

    def year(i):
        t = t_hold[i]
        return max(jj for jj, a0 in enumerate(anchors) if t >= a0) if t >= anchors[0] else 0

    out = {"version": "v260", "rows": {}, "trades": {}, "train_bars": {}}
    nets = {}
    SEED = [0]
    _train = train

    def train(rows, seed, lam):  # noqa: F811 - seed offset per run
        return _train(rows, seed + SEED[0], lam)

    keys = []
    for off in SEEDS:
        SEED[0] = off
        key = f"B1_boot_s{off}"
        keys.append(key)
        nets[key] = {}
        for j in range(1, len(anchors)):
            rows = np.flatnonzero(np.asarray((t_hold >= anchors[0]) & (t_hold + pd.Timedelta(hours=4) < anchors[j] - EMBARGO)))
            nets[key][j] = train(rows, 260 + j, 5.0)
            out["train_bars"][f"{key}_{anchors[j].date()}"] = int(len(rows))
        print(key, "trained", flush=True)

    def manager(key):
        st_ = {"m": 1.0, "vh": [], "log": []}

        def rm(i, eqh):
            jj = year(i)
            if jj == 0:
                return 1.0
            if i % STEP == 0:
                e = np.asarray(eqh, float)
                if len(e) > 181:
                    lr_ = np.diff(np.log(e[-181:]))
                    st_["vh"].append(float(lr_.std() * np.sqrt(6 * 365)))
                x = np.r_[eq_state(e, st_["vh"][:-1]), mkt[i], st_["m"]].astype(np.float32)
                with torch.no_grad():
                    lg, _ = nets[key][jj](torch.from_numpy(x[None, :]))
                st_["m"] = float(ACTS[int(lg.argmax())])
                st_["log"].append((str(t_hold[i]), st_["m"]))
            return st_["m"]
        rm.st = st_
        return rm

    for key, rm in [("v247_B18", None)] + [(k, manager(k)) for k in keys]:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, risk_mult=rm, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if rm is not None:
            lg_ = pd.Series([mm for _, mm in rm.st["log"]], index=pd.DatetimeIndex([t for t, _ in rm.st["log"]]))
            r["mean_mult_by_year"] = {str(anchors[j].year): round(float(lg_[(lg_.index >= anchors[j]) & (lg_.index < anchors[j + 1])].mean()), 3)
                                      for j in range(1, 4)}
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev win", out["trades"][key]["dev"].get("win_rate"), r.get("mean_mult_by_year"), flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002
    order = sorted(keys, key=lambda k: out["rows"][k]["monthly_dev4"])
    med = order[len(order) // 2]
    ref = out["rows"]["v247_B18"]
    mr = out["rows"][med]
    ok = mr["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in mr["yearly"][:4]) and mr["monthly_dev4"] >= 5
    beats = ok and (round(v204.worst_month(mr), 4), mr["monthly_dev4"]) > (round(v204.worst_month(ref), 4), ref["monthly_dev4"])
    out["median_seed"] = med
    out["adopted"] = bool(beats)
    out["selected"] = med
    out["final_score_all_seeds"] = {k: {"monthly_5y": out["rows"][k]["monthly_5y"], "monthly_last_year": out["rows"][k]["monthly_last_year"],
                                        "gate_dd": out["rows"][k]["gate_dd"], "gate_pass": out["rows"][k]["gate_pass"]} for k in keys}
    out["final_score_selected"] = {"monthly_5y": mr["monthly_5y"], "monthly_last_year": mr["monthly_last_year"],
                                   "losing_years": mr["losing_years"], "gate_dd": mr["gate_dd"], "gate_pass": mr["gate_pass"],
                                   "median_last_year_over_seeds": float(np.median([out["rows"][k]["monthly_last_year"] for k in keys])),
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in mr["yearly"]],
                                   "hidden_year_trades": out["trades"][med]["_hidden"]}
    for k in out["trades"]:
        out["trades"][k].pop("_hidden", None)
    print("MEDIAN SEED", med, "adopted", out["adopted"], out["final_score_selected"], flush=True)
    print("ALL SEEDS", out["final_score_all_seeds"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v260_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
