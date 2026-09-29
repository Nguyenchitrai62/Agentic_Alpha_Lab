"""v259: a PPO RISK MANAGER - the trader's daily decision how much risk to run, learned with a drawdown-aware reward.

Why (user goal: RL trader, higher return, LOWER DD, general): a real trader sizes the whole book up or down day by day from how the
account and the market behave (drawdown, recent PnL, volatility, how broad the signals are). v251 tried a fixed rule (scale by the
strategy's trailing vol) and failed; the O1 robustness report shows the DD is the binding, fragile constraint. Here a PPO policy
learns the daily risk multiplier from a reward that pays log growth and charges drawdown beyond 10%, on random 180-day windows of the
training years (the episodes cover many start dates, so the policy cannot memorise one path).
Fixed before running.
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings: G2 grid trader, rung x1.75, minute-5 rule, limits, SL market /
TP limit, break-even, 20% DD governor, aligned sleeve, Bybit fees, adverse funding). New engine hook risk_mult(i, eq_hist): multiplier
on the governor of bar i (book targets and dip-rung sizes), eq_hist = equity up to bar i-2 (same lag as the governor).
Training proxy: the reference run's per-bar book and sleeve PnL (engine attribution, fractions of equity); a multiplier m scales both:
r_t(m) = m * (book_t + sleeve_t). Decisions every 6 bars (daily), actions m in {0.5, 0.75, 1.0, 1.25}.
State (known at the decision, equity lagged 2 bars as in the engine): DD from the 90-day peak, strategy log return over the last 7 and 30
days, strategy 30-day vol / its expanding median, BTC 42-bar return in sigma units, BTC sigma regime, mean |book| over the 5 coins, mean
TradingView SuperTrend direction, mean order-level fl_big_imb6, current m.
Reward per decision = sum over its 6 bars of log(1 + r_t) - lam * (increase of max(0, DD_t - 10%)), in percent units.
PPO: MLP 10-64-64 (tanh), 32 parallel episodes of 180 days (30 decisions) from random starts, 300 updates, 4 epochs, minibatch 512,
lr 3e-4, clip 0.2, gamma 0.97, GAE 0.95, entropy 0.01, seed 259 + anchor. Walk-forward: the policy for anchor year Y trains on bars
from 2021-09-24 until Y - 7 days; 2021 uses m = 1.
  K1_lam2   lam 2
  K2_lam5   lam 5
Evaluation: the full engine with risk_mult = the greedy policy on the engine's own equity. Reference: risk_mult None (must reproduce 5.777).
SELECTION = robust criterion among K1, K2; the most recent year is scored once for the selected row. Reported: mean multiplier per year.

  python research/parallel/rounds/parallel-20260906-r2/v259/v259_ppo_risk_manager.py
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
STEP, EP_DEC = 6, 30
N_ENV, UPDATES, EPOCHS, MB = 32, 300, 4, 512


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
        starts_ok = rows[(rows + EP_DEC * STEP) <= rows[-1]]
        for _ in range(UPDATES):
            starts = rng.choice(starts_ok, N_ENV)
            eqs = [list(np.ones(200)) for _ in range(N_ENV)]  # flat warm-up history
            vh = [[] for _ in range(N_ENV)]
            mcur = np.ones(N_ENV)
            peak_dd = np.zeros(N_ENV)
            X, A, LP, V, RW = [], [], [], [], []
            for d in range(EP_DEC):
                i0 = starts + d * STEP
                st = np.array([np.r_[eq_state(eqs[e][:-2] if len(eqs[e]) > 2 else eqs[e], vh[e]), mkt[i0[e]], mcur[e]] for e in range(N_ENV)], np.float32)
                with torch.no_grad():
                    lg, v = net(torch.from_numpy(st))
                    dist = torch.distributions.Categorical(logits=lg)
                    a = dist.sample()
                mcur = ACTS[a.numpy()]
                rew = np.zeros(N_ENV)
                for e in range(N_ENV):
                    for k in range(STEP):
                        r = mcur[e] * R[i0[e] + k]
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

    out = {"version": "v259", "rows": {}, "trades": {}, "train_bars": {}}
    nets = {}
    for key, lam in (("K1_lam2", 2.0), ("K2_lam5", 5.0)):
        nets[key] = {}
        for j in range(1, len(anchors)):
            rows = np.flatnonzero(np.asarray((t_hold >= anchors[0]) & (t_hold + pd.Timedelta(hours=4) < anchors[j] - EMBARGO)))
            nets[key][j] = train(rows, 259 + j, lam)
            out["train_bars"][f"{key}_{anchors[j].date()}"] = int(len(rows))
            print(key, "trained for", anchors[j].date(), "on", len(rows), "bars", flush=True)

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

    for key, rm in (("v247_B18", None), ("K1_lam2", manager("K1_lam2")), ("K2_lam5", manager("K2_lam5"))):
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
              "dev trades", out["trades"][key]["dev"], r.get("mean_mult_by_year"), flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002
    cands = ("K1_lam2", "K2_lam5")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
    s_ = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v259_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
