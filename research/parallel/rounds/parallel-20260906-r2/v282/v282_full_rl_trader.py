"""v282: a FULL-ACTION RL trader (user suggestion 2026-09-30) - the agent decides direction, size / leverage, reversals, stop and target,
and may move the stop and the target at every bar, on top of the pipeline's signals.

Why: every earlier learned agent controlled only a slice of the trader's job (take / skip, cut, tighten, entry offset, risk dial) around
the G2 rule. A real trader decides everything: long or short, how big (possibly > 100% of the account in total), whether to reverse, where
to put the stop and the target, and whether to move them while in the trade. Here one PPO policy does all of that per coin and 4h bar.
Fixed before running.
Simulator (per coin, 4h holding bars; everything at the decision is known at the bar close; the dip sleeve is NOT touched - its PnL
comes from the C4 engine run's attribution):
  actions (three categorical heads): target position level in {-2, -1, -0.5, 0, 0.5, 1, 2} x U (U = 0.15 of equity -> up to 0.30 per
  coin, 1.50 over the five coins), stop distance in {2, 4, 6} sigma_d, target distance in {3, 6, 12} sigma_d (both around the position's
  average entry, re-chosen every bar = the agent can move them).
  execution: a change of position is ONE limit order 0.25 sigma_4h better than the bar open for the full difference (adds, reductions,
  exits and reversals alike), filled only if the bar trades through it from minute 5 on (maker 0.02%); otherwise the order expires.
  Stop = market (taker 0.055%, fill at min(stop, open) if gapped), target = limit (maker); stop first when both are touched in a bar;
  exits are checked from the bar after a fill. Longs pay 0.01% per settlement bar.
  reward per bar = PnL of the coin position in % of equity (mark to market, fees and funding included) - kappa x PnL^2.
  state: the C4 book target and the four members' targets (A, B, Aq, Bq) of the coin, TradingView SuperTrend / market structure / WVF,
  order-level fl_big_imb6, 6- and 42-bar returns and the sigma regime, hour, current level, unrealised PnL in sd, bars held, stop / target
  choice.
PPO: MLP 18-64-64 (tanh) with three policy heads and a value head, 40 envs (5 coins x 8 random starts), rollout 128, 150 updates, 4 epochs,
minibatch 1024, lr 3e-4, clip 0.2, gamma 0.99, GAE 0.95, entropy 0.01. Walk-forward: the policy for anchor year Y trains on holding bars
from 2021-09-24 until Y - 7 days; 2021 is traded by the G2-like reference rule. FIVE seeds per variant (seed = 282 + 10 x anchor + s).
  K1_kappa005   kappa 0.05
  K2_kappa020   kappa 0.20
Evaluation (labelled SIMULATOR evaluation): each seed's greedy policy trades the five coins sequentially over 2021-09-24 .. end; portfolio
bar return = sum of the coins' simulated book PnL + the C4 dip-sleeve PnL of that bar (engine attribution); equity compounds per bar;
DD = max drawdown of the 4h-close equity. Reference: the G2 rule in the v258 simulator (fidelity 0.985 with the engine) + the same sleeve.
DECISION RULE: a variant is adopted only if its MEDIAN seed (by dev4) beats the reference under the robust criterion (dev DD <= 20, no
losing dev year, dev4 >= 5, then the higher worst dev year); the most recent year is reported for the median seed only.

  python research/parallel/rounds/parallel-20260906-r2/v282/v282_full_rl_trader.py
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
EMBARGO = pd.Timedelta(days=7)
MAKER, TAKER, FUND = 0.0002, 0.00055, 0.0001
LEVELS = np.array([-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0])
U = 0.15
SLS = np.array([2.0, 4.0, 6.0])
TPS = np.array([3.0, 6.0, 12.0])
K_OFF = 0.25
N_ENV, T_ROLL, UPDATES, EPOCHS, MB = 40, 128, 150, 4, 1024
SEEDS = (0, 1, 2, 3, 4)
C4 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Net(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(d, 64), nn.Tanh(), nn.Linear(64, 64), nn.Tanh())
        self.h_lv, self.h_sl, self.h_tp, self.v = nn.Linear(64, len(LEVELS)), nn.Linear(64, len(SLS)), nn.Linear(64, len(TPS)), nn.Linear(64, 1)

    def forward(self, x):
        h = self.body(x)
        return self.h_lv(h), self.h_sl(h), self.h_tp(h), self.v(h).squeeze(-1)


class Env:
    """Vectorised per-coin full-action trade simulator."""

    def __init__(self, D, rows, rng, n_env=N_ENV, sequential=False):
        self.D, self.rows, self.rng, self.n = D, rows, rng, n_env
        self.coin = np.arange(n_env) % D["na"]
        self.ptr = np.full(n_env, rows[0]) if sequential else rng.choice(rows[:-2], n_env)
        z = lambda: np.zeros(n_env)
        self.w, self.entry, self.sdv, self.held, self.slc, self.tpc = z(), z(), np.ones(n_env), z(), np.ones(n_env), np.ones(n_env)

    def obs(self):
        D, i, a = self.D, self.ptr, self.coin
        up = np.where(self.w != 0, (D["O0"][i, a] / np.where(self.entry > 0, self.entry, 1) - 1) * np.sign(self.w) / self.sdv, 0.0)
        x = np.column_stack([D["X"][i, a], self.w / U, np.clip(np.nan_to_num(up), -10, 10), self.held / 42, self.slc / 6, self.tpc / 12])
        return np.nan_to_num(x).astype(np.float32)

    def step(self, a_lv, a_sl, a_tp):
        D, i, a = self.D, self.ptr, self.coin
        O0, hi, lo, cl, s4, st = D["O0"][i, a], D["hi"][i, a], D["lo"][i, a], D["cl"][i, a], D["s4"][i, a], D["settle"][i, a]
        ok = np.isfinite(O0) & np.isfinite(hi) & np.isfinite(lo) & np.isfinite(cl) & np.isfinite(s4)
        sd = s4 * np.sqrt(6)
        r = np.zeros(self.n)
        w0 = self.w.copy()
        side0 = np.sign(w0)
        # stop / target of the position held from the previous bar (chosen now, around the average entry)
        self.slc = np.where(w0 != 0, SLS[a_sl], self.slc)
        self.tpc = np.where(w0 != 0, TPS[a_tp], self.tpc)
        sl = self.entry * (1 - side0 * self.slc * self.sdv)
        tp = self.entry * (1 + side0 * self.tpc * self.sdv)
        held = ok & (w0 != 0)
        stop = held & np.where(side0 > 0, lo <= sl, hi >= sl)
        tph = held & ~stop & np.where(side0 > 0, hi > tp, lo < tp)
        ex_px = np.where(stop, np.where(side0 > 0, np.minimum(sl, O0), np.maximum(sl, O0)), np.where(tph, tp, np.nan))
        ex_fee = np.where(stop, TAKER, np.where(tph, MAKER, 0.0))
        exited = held & np.isfinite(ex_px)
        # PnL of the held position over the bar (to the exit or the close)
        end = np.where(exited, ex_px, cl)
        r += np.where(held, 100 * w0 * (end / O0 - 1), 0.0)
        r -= np.where(exited, 100 * np.abs(w0) * ex_fee, 0.0)
        r -= np.where(held & (w0 > 0) & st, 100 * w0 * FUND, 0.0)
        w1 = np.where(exited, 0.0, w0)
        # a new target: one limit order for the difference, filled on a trade-through from minute 5 (not after an exit this bar)
        tgt = LEVELS[a_lv] * U
        dw = np.where(ok & ~exited, tgt - w1, 0.0)
        px = O0 * (1 - np.sign(dw) * K_OFF * s4)
        fill = (dw != 0) & np.where(dw > 0, lo < px, hi > px)
        r += np.where(fill, 100 * dw * (cl / px - 1) - 100 * np.abs(dw) * MAKER, 0.0)
        new_w = np.where(fill, w1 + dw, w1)
        grow = fill & (np.sign(new_w) == np.sign(w1)) & (np.abs(new_w) > np.abs(w1))
        flip = fill & (np.sign(new_w) != np.sign(w1)) & (new_w != 0)
        self.entry = np.where(flip | (fill & (w1 == 0)), px, np.where(grow, (np.abs(w1) * self.entry + np.abs(dw) * px) / np.maximum(np.abs(new_w), 1e-12), self.entry))
        self.sdv = np.where(flip | (fill & (w1 == 0)), sd, self.sdv)
        opened = flip | (fill & (w1 == 0))
        self.slc = np.where(opened, SLS[a_sl], self.slc)
        self.tpc = np.where(opened, TPS[a_tp], self.tpc)
        self.held = np.where(new_w != 0, np.where(opened, 0.0, self.held + 1), 0.0)
        self.w = new_w
        self.ptr = self.ptr + 1
        done = self.ptr >= self.rows[-1]
        if done.any():
            self.ptr[done] = self.rng.choice(self.rows[:-2], int(done.sum()))
            self.w[done] = 0.0
        return np.nan_to_num(r), done


def train(D, rows, seed, kappa):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    env = Env(D, rows, rng)
    x = env.obs()
    net = Net(x.shape[1])
    opt = torch.optim.Adam(net.parameters(), lr=3e-4)
    for _ in range(UPDATES):
        B = {k: [] for k in ("x", "a1", "a2", "a3", "lp", "v", "r", "d")}
        for _t in range(T_ROLL):
            with torch.no_grad():
                l1, l2, l3, v = net(torch.from_numpy(x))
                d1, d2, d3 = (torch.distributions.Categorical(logits=l) for l in (l1, l2, l3))
                a1, a2, a3 = d1.sample(), d2.sample(), d3.sample()
                lp = d1.log_prob(a1) + d2.log_prob(a2) + d3.log_prob(a3)
            pnl, done = env.step(a1.numpy(), a2.numpy(), a3.numpy())
            for k, val in (("x", x), ("a1", a1.numpy()), ("a2", a2.numpy()), ("a3", a3.numpy()), ("lp", lp.numpy()), ("v", v.numpy()),
                           ("r", pnl - kappa * pnl ** 2), ("d", done)):
                B[k].append(val)
            x = env.obs()
        with torch.no_grad():
            nv = net(torch.from_numpy(x))[3].numpy()
        adv = np.zeros((T_ROLL, N_ENV))
        last = np.zeros(N_ENV)
        for t in reversed(range(T_ROLL)):
            nd = 1.0 - B["d"][t]
            delta = B["r"][t] + 0.99 * nv * nd - B["v"][t]
            last = delta + 0.99 * 0.95 * nd * last
            adv[t] = last
            nv = B["v"][t]
        ret = adv + np.array(B["v"])
        X = torch.from_numpy(np.concatenate(B["x"]))
        A1, A2, A3 = (torch.from_numpy(np.concatenate(B[k])) for k in ("a1", "a2", "a3"))
        LP = torch.from_numpy(np.concatenate(B["lp"]))
        ADV = torch.from_numpy(adv.reshape(-1).astype(np.float32))
        ADV = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
        RET = torch.from_numpy(ret.reshape(-1).astype(np.float32))
        n = len(A1)
        for _e in range(EPOCHS):
            perm = torch.from_numpy(rng.permutation(n))
            for s in range(0, n, MB):
                j = perm[s:s + MB]
                l1, l2, l3, v = net(X[j])
                d1, d2, d3 = (torch.distributions.Categorical(logits=l) for l in (l1, l2, l3))
                lp = d1.log_prob(A1[j]) + d2.log_prob(A2[j]) + d3.log_prob(A3[j])
                ratio = torch.exp(lp - LP[j])
                pl = -torch.min(ratio * ADV[j], torch.clamp(ratio, 0.8, 1.2) * ADV[j]).mean()
                ent = d1.entropy().mean() + d2.entropy().mean() + d3.entropy().mean()
                loss = pl + 0.5 * ((v - RET[j]) ** 2).mean() - 0.01 * ent
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()
    return net.eval()


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v232 = _load("v232_f", RD / "v232/v232_disciplined_rl.py")
    v240 = _load("v240_f", RD / "v240/v240_order_level_flow.py")
    v258 = _load("v258_f", RD / "v258/v258_ppo_disciplined.py")
    eu, v216 = v221.eu, v221.v216
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    Cc = eu.er.CACHE
    m = {k: pd.read_parquet(Cc / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    n, na = len(idx), len(cols)
    t_hold = idx + pd.Timedelta(hours=4)

    # ---- the C4 engine run: sleeve PnL per bar (attribution) and the G2-rule book for the reference
    att = []
    ref = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)), win_start=5, attrib=att,
                      **dict(v221.KW, **C4))
    assert abs(ref["monthly_dev4"] - 6.026) < 0.002, "the C4 engine run must reproduce v269 M1"
    pos_i = {t: k for k, t in enumerate(t_hold)}
    sleeve = np.zeros(n)
    for t, bp, sp in att:
        if t in pos_i:
            sleeve[pos_i[t]] = float(sp)

    # ---- simulator arrays and state
    o = opens.reindex(idx)[cols]
    realized = eu.v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
    vol = (realized.rolling(60 * eu.PD, min_periods=20 * eu.PD).std() * np.sqrt(eu.PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), 2.0))
    tg = eu.v99.W_BOOKS * s[:, None] * books.to_numpy()
    tv = v232.tv_frames(idx, cols)
    lo1 = np.log(o.shift(-1))
    sig = lo1.diff().rolling(360, min_periods=120).std()
    fl = pd.DataFrame({c: v240.flo.flow_features(c, idx)["fl_big_imb6"].to_numpy() for c in cols}, index=idx)
    frames = [pd.DataFrame(tg, index=idx, columns=cols) * 5] + [m[k] * 5 for k in ("A", "B", "Aq", "Bq")] + \
             [tv["tv_st_dir"], tv["tv_ms_trend"], tv["tv_wvf_z"], fl * 10, lo1.diff(6) / (sig * np.sqrt(6)), lo1.diff(42) / (sig * np.sqrt(42)),
              sig / sig.rolling(540, min_periods=180).median()]
    X = np.stack([f.reindex(idx)[cols].to_numpy(float) for f in frames], axis=2)
    X = np.concatenate([X, np.repeat((np.array([t.hour for t in t_hold], float) / 24)[:, None, None], na, axis=1)], axis=2)
    D = dict(na=na, X=np.nan_to_num(X), tg=tg, sgn=np.where(np.abs(tg) >= 0.05, np.sign(tg), 0.0), s4=prep["sig4"],
             O0=prep["O"][:, 0, :].astype(float), hi=np.nanmax(prep["H"][:, 5:, :].astype(float), axis=1),
             lo=np.nanmin(prep["L"][:, 5:, :].astype(float), axis=1), cl=prep["C"][:, 239, :].astype(float),
             settle=np.asarray(prep["settle"], bool)[:, None].repeat(na, axis=1))
    ok_bar = np.isfinite(D["O0"]).all(axis=1) & np.isfinite(D["cl"]).all(axis=1) & np.isfinite(D["s4"]).all(axis=1)
    live = np.flatnonzero(np.asarray(t_hold >= anchors[0]))

    def year_of(i):
        return max(jj for jj, a0 in enumerate(anchors) if t_hold[i] >= a0) if t_hold[i] >= anchors[0] else 0

    yr = np.array([year_of(i) for i in range(n)])

    def metrics(book_pnl):
        r = book_pnl + sleeve
        eq = np.cumprod(1 + np.where(np.arange(n) >= live[0], r, 0.0))
        res = {"yearly": []}
        for j in range(len(anchors)):
            sel = np.flatnonzero((yr == j) & (np.arange(n) >= live[0]))
            if len(sel) == 0:
                continue
            e0 = eq[sel[0] - 1] if sel[0] > 0 else 1.0
            e = eq[sel] / e0
            dd = float(np.max(1 - e / np.maximum.accumulate(np.r_[1.0, e])[1:]))
            net = float(e[-1] - 1)
            months = len(sel) / (6 * 365 / 12)
            res["yearly"].append({"anchor": str(anchors[j].date()), "net_pct": round(100 * net, 2), "dd_pct": round(100 * dd, 2),
                                  "monthly": round(100 * ((1 + net) ** (1 / months) - 1), 3)})
        dev = res["yearly"][:4]
        res["dev4"] = round(float(np.mean([y["monthly"] for y in dev])), 3)
        res["worst"] = round(float(min(y["monthly"] for y in dev)), 3)
        res["dev_dd"] = round(float(max(y["dd_pct"] for y in dev)), 2)
        res["last_year"] = res["yearly"][4]["monthly"] if len(res["yearly"]) > 4 else None
        return res

    # ---- reference: the G2 rule in the v258 simulator (fidelity 0.985), same sleeve
    Dv = dict(D, X=D["X"][:, :, :9])
    ref_env = v258.Env(Dv, np.r_[live, live[-1] + 1], np.random.default_rng(0), n_env=na, sequential=True)
    ref_env.coin = np.arange(na)
    ref_pnl = np.zeros(n)
    for k in live:
        rr, _ = ref_env.step(np.zeros(na, int))
        ref_pnl[k] = rr.sum() / 100
    out = {"version": "v282", "reference_G2_sim": metrics(ref_pnl), "variants": {}}
    print("reference G2 (simulator + C4 sleeve)", {k: out["reference_G2_sim"][k] for k in ("dev4", "worst", "dev_dd")}, flush=True)

    def evaluate(nets):
        env = Env(D, np.r_[live, live[-1] + 1], np.random.default_rng(1), n_env=na, sequential=True)
        env.coin = np.arange(na)
        pnl = np.zeros(n)
        g_env = v258.Env(Dv, np.r_[live, live[-1] + 1], np.random.default_rng(0), n_env=na, sequential=True)
        g_env.coin = np.arange(na)
        lev = []
        for k in live:
            jj = yr[k]
            if jj == 0:  # 2021: the G2 reference rule
                rr, _ = g_env.step(np.zeros(na, int))
                env.ptr += 1
            else:
                x = env.obs()
                with torch.no_grad():
                    l1, l2, l3, _ = nets[jj](torch.from_numpy(x))
                rr, _ = env.step(l1.argmax(-1).numpy(), l2.argmax(-1).numpy(), l3.argmax(-1).numpy())
                g_env.ptr += 1
                lev.append(float(np.abs(env.w).sum()))
            pnl[k] = rr.sum() / 100
        res = metrics(pnl)
        res["mean_gross_leverage"] = round(float(np.mean(lev)), 3) if lev else 0.0
        return res

    for key, kappa in (("K1_kappa005", 0.05), ("K2_kappa020", 0.20)):
        seeds = {}
        for sd_ in SEEDS:
            nets = {}
            for j in range(1, len(anchors)):
                rows = np.flatnonzero(ok_bar & np.asarray((t_hold >= anchors[0]) & (t_hold + pd.Timedelta(hours=4) < anchors[j] - EMBARGO)))
                nets[j] = train(D, rows, 282 + 10 * j + sd_, kappa)
            seeds[sd_] = evaluate(nets)
            print(key, "seed", sd_, {k: seeds[sd_][k] for k in ("dev4", "worst", "dev_dd", "mean_gross_leverage")}, flush=True)
        order = sorted(seeds, key=lambda k: seeds[k]["dev4"])
        med = seeds[order[len(order) // 2]]
        R = out["reference_G2_sim"]
        ok_med = med["dev_dd"] <= 20 and all(y["net_pct"] >= 0 for y in med["yearly"][:4]) and med["dev4"] >= 5
        adopted = bool(ok_med and (med["worst"], med["dev4"]) > (R["worst"], R["dev4"]))
        out["variants"][key] = {"seeds": {str(k): {kk: v for kk, v in s_.items() if kk != "last_year"} for k, s_ in seeds.items()},
                                "median_seed": order[len(order) // 2], "adopted": adopted,
                                "median_last_year": med["last_year"]}
        print(key, "MEDIAN", {k: med[k] for k in ("dev4", "worst", "dev_dd")}, "adopted", adopted, "last year (median seed only)", med["last_year"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v282_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
