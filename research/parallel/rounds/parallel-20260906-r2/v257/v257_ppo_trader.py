"""v257: a SEQUENTIAL reinforcement-learning trader (PPO, small neural policy) managing the book on top of the O1 pipeline.

Why (user goal: RL on top of the pipeline, trader-like actions, higher return / win rate, lower DD, general, no leakage): every learned
layer so far was one-step (fitted-Q v214, one-step improvement v215 / v232, bandits v220 / v235 / v248 / v249 / v256) or parameter search
(v217 ES, v241 sizing). None learned a sequential policy that plans over a whole trade. Here a PPO actor-critic learns, bar by bar, when
to take a signal, when to exit early and when to tighten the stop, from the discounted mark-to-market PnL of a fast per-coin trade
simulator; it is then evaluated in the real engine.
Fixed before running.
Foundation / environment for evaluation = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings: G2 grid trader, rung x1.75, minute-5
rule, limits, SL market / TP limit, break-even, governor, aligned sleeve, Bybit fees, adverse funding).
Training simulator (per coin, 4h holding bars; everything the engine uses at the decision is known at the bar close): target
tg = 0.8 * s_i * book (s_i = the engine's vol-target scale), signal sgn = sign(tg) if |tg| >= 0.05; high / low of the holding bar from
minute 5 on (the minute-5 rule), sd = sigma_4h * sqrt(6). Flat with a signal: open = limit 0.25 sigma_4h better than the bar open, filled
if the bar trades through it (maker 0.02%), size |tg|, SL 4 sd (market, taker 0.055%), TP 8 sd (limit, maker), break-even after +2 sd;
stop / TP are checked from the next bar (stop first). In a position: hold (the rule's close on signal flip / loss is applied), close
(limit 0.25 sigma_4h, filled if traded through, else market at the bar close), tighten (stop to 1.5 sd from the bar open). Longs pay 0.01%
per settlement bar. Reward = mark-to-market PnL of the coin in % of equity (weight x return) minus fees and funding.
State (13): |tg| / its 540-bar median, sigma regime, r6 / r42 in sigma units along the side, SuperTrend / market-structure along the side,
WVF z, order-level fl_big_imb6 along the side, hour / 24, in-position flag, unrealised PnL in sd, bars held / 42, break-even flag.
Actions: 0 = the rule (open when flat / hold in a position), 1 = wait (flat) / close (in a position), 2 = tighten (position only; masked
when flat). PPO: MLP 13-64-64 (tanh), separate value head, 40 parallel envs (5 coins x 8 random starts), rollout 128, 150 updates,
4 epochs, minibatch 1024, lr 3e-4, clip 0.2, gamma 0.99, GAE 0.95, entropy 0.01, torch seed 257 + anchor.
Walk-forward: the policy for anchor year Y (2022..2025) trains on holding bars from the first anchor (2021-09-24, out-of-sample books)
until Y - 7 days; 2021 uses the rule.
  R1_ppo         pure PPO
  R2_ppo_prior   PPO + 0.5 x cross-entropy toward action 0 (the rule): conservative RL, deviates only where the advantage is large
Evaluation in the engine (policy hook): flat with a signal -> the agent's open / wait; in a position -> close / tighten if the agent says
so, otherwise the G2 grid rule (adds / reduces / exit on signal loss). Reference: G2 through the hook (must reproduce 5.777).
SELECTION = robust criterion among R1, R2; the most recent year is scored once for the selected row. Reported: action shares, trades.

  python research/parallel/rounds/parallel-20260906-r2/v257/v257_ppo_trader.py
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
MAKER, TAKER, FUND = 0.0002, 0.00055, 0.0001
M_SL, M_TP, BE_K, TIGHT, K_OFF, THETA = 4.0, 8.0, 2.0, 1.5, 0.25, 0.05
N_ENV, T_ROLL, UPDATES, EPOCHS, MB = 40, 128, 150, 4, 1024


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Net(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(d, 64), nn.Tanh(), nn.Linear(64, 64), nn.Tanh())
        self.pi, self.v = nn.Linear(64, 3), nn.Linear(64, 1)

    def forward(self, x, mask):
        h = self.body(x)
        logits = self.pi(h).masked_fill(~mask, -1e9)
        return logits, self.v(h).squeeze(-1)


class Env:
    """Vectorised per-coin trade simulator over holding bars [lo_i, hi_i) (cube rows)."""

    def __init__(self, D, rows, rng):
        self.D, self.rows, self.rng = D, rows, rng
        self.reset_all()

    def reset_all(self):
        self.coin = np.arange(N_ENV) % self.D["na"]
        self.ptr = self.rng.choice(self.rows[:-2], N_ENV)
        self.pos = np.zeros(N_ENV)
        self.entry = np.zeros(N_ENV)
        self.w = np.zeros(N_ENV)
        self.sl = np.zeros(N_ENV)
        self.tp = np.zeros(N_ENV)
        self.sdv = np.ones(N_ENV)
        self.be = np.zeros(N_ENV)
        self.held = np.zeros(N_ENV)

    def obs(self):
        D, i, a = self.D, self.ptr, self.coin
        sgn = D["sgn"][i, a]
        side = np.where(self.pos != 0, self.pos, sgn)
        upnl = np.where(self.pos != 0, (D["O0"][i, a] / np.where(self.entry > 0, self.entry, 1) - 1) * self.pos / self.sdv, 0.0)
        x = np.column_stack([D["X"][i, a, :2], D["X"][i, a, 2:7] * side[:, None], D["X"][i, a, 7:9],
                             (self.pos != 0).astype(float), np.clip(upnl, -10, 10), self.held / 42, self.be])
        mask = np.ones((N_ENV, 3), bool)
        mask[:, 2] = self.pos != 0
        mask[:, 1] = (self.pos != 0) | (sgn != 0)
        return np.nan_to_num(x).astype(np.float32), mask

    def step(self, act):
        D, i, a = self.D, self.ptr, self.coin
        O0, hi, lo, cl, s4 = D["O0"][i, a], D["hi"][i, a], D["lo"][i, a], D["cl"][i, a], D["s4"][i, a]
        sd, sgn, tg, st = s4 * np.sqrt(6), D["sgn"][i, a], np.abs(D["tg"][i, a]), D["settle"][i, a]
        r = np.zeros(N_ENV)
        flat = self.pos == 0
        # --- flat: open (action 0) at a limit, filled on a trade-through
        do_open = flat & (sgn != 0) & (act == 0) & np.isfinite(s4) & (tg > 0)
        px = O0 * (1 - sgn * K_OFF * s4)
        filled = do_open & np.where(sgn > 0, lo < px, hi > px)
        r[filled] -= 100 * tg[filled] * MAKER
        prev_mark = np.where(filled, px, O0)
        self.pos = np.where(filled, sgn, self.pos)
        self.entry = np.where(filled, px, self.entry)
        self.w = np.where(filled, tg, self.w)
        self.sdv = np.where(filled, sd, self.sdv)
        self.sl = np.where(filled, px * (1 - sgn * M_SL * sd), self.sl)
        self.tp = np.where(filled, px * (1 + sgn * M_TP * sd), self.tp)
        self.be = np.where(filled, 0.0, self.be)
        self.held = np.where(filled, 0.0, self.held)
        # --- in a position from an earlier bar
        inpos = (~flat) & (self.pos != 0)
        side = self.pos
        rule_close = inpos & (sgn != side)
        want_close = inpos & ((act == 1) | rule_close)
        tight = inpos & (act == 2)
        new_sl = O0 * (1 - side * TIGHT * sd)
        better = tight & ((new_sl - self.sl) * side > 0) & ((O0 - new_sl) * side > 0)
        self.sl = np.where(better, new_sl, self.sl)
        exit_px = np.full(N_ENV, np.nan)
        exit_fee = np.zeros(N_ENV)
        # stop first, then TP, then a requested close
        stop_hit = inpos & np.where(side > 0, lo <= self.sl, hi >= self.sl)
        exit_px = np.where(stop_hit, np.where(side > 0, np.minimum(self.sl, O0), np.maximum(self.sl, O0)), exit_px)
        exit_fee = np.where(stop_hit, TAKER, exit_fee)
        tp_hit = inpos & ~stop_hit & np.where(side > 0, hi > self.tp, lo < self.tp)
        exit_px = np.where(tp_hit, self.tp, exit_px)
        exit_fee = np.where(tp_hit, MAKER, exit_fee)
        cpx = O0 * (1 + side * K_OFF * s4)
        c_fill = want_close & ~stop_hit & ~tp_hit & np.where(side > 0, hi > cpx, lo < cpx)
        exit_px = np.where(c_fill, cpx, exit_px)
        exit_fee = np.where(c_fill, MAKER, exit_fee)
        c_mkt = want_close & ~stop_hit & ~tp_hit & ~c_fill
        exit_px = np.where(c_mkt, cl, exit_px)
        exit_fee = np.where(c_mkt, TAKER, exit_fee)
        exited = np.isfinite(exit_px)
        # mark-to-market reward over the bar (from the open / fill price to the exit or the close)
        holding = self.pos != 0
        end_px = np.where(exited, exit_px, cl)
        base = np.where(filled, px, O0)
        r += np.where(holding, 100 * self.w * self.pos * (end_px / np.where(base > 0, base, 1) - 1), 0.0)
        r -= np.where(exited, 100 * self.w * exit_fee, 0.0)
        r -= np.where(holding & (self.pos > 0) & st, 100 * self.w * FUND, 0.0)
        # break-even after +2 sd (from the next bar)
        fav = np.where(self.pos > 0, hi / np.where(self.entry > 0, self.entry, 1) - 1, 1 - lo / np.where(self.entry > 0, self.entry, 1))
        to_be = holding & ~exited & (fav >= BE_K * self.sdv) & (self.be == 0)
        self.sl = np.where(to_be, self.entry * (1 + self.pos * 0.001), self.sl)
        self.be = np.where(to_be, 1.0, self.be)
        self.pos = np.where(exited, 0.0, self.pos)
        self.held = np.where(self.pos != 0, self.held + 1, 0.0)
        # advance; restart envs that ran off the training window
        self.ptr = self.ptr + 1
        done = self.ptr >= self.rows[-1]
        if done.any():
            self.ptr[done] = self.rng.choice(self.rows[:-2], int(done.sum()))
            self.pos[done] = 0.0
        return np.nan_to_num(r), done


def train(D, rows, seed, prior):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    env = Env(D, rows, rng)
    net = Net(13)
    opt = torch.optim.Adam(net.parameters(), lr=3e-4)
    x, mask = env.obs()
    for _ in range(UPDATES):
        bx, bm, ba, blp, bv, br, bd = [], [], [], [], [], [], []
        for _t in range(T_ROLL):
            with torch.no_grad():
                lg, v = net(torch.from_numpy(x), torch.from_numpy(mask))
                dist = torch.distributions.Categorical(logits=lg)
                a = dist.sample()
            r, d = env.step(a.numpy())
            bx.append(x), bm.append(mask), ba.append(a.numpy()), blp.append(dist.log_prob(a).numpy()), bv.append(v.numpy())
            br.append(r), bd.append(d)
            x, mask = env.obs()
        with torch.no_grad():
            _, v_last = net(torch.from_numpy(x), torch.from_numpy(mask))
        adv = np.zeros((T_ROLL, N_ENV))
        last = np.zeros(N_ENV)
        nv = v_last.numpy()
        for t in reversed(range(T_ROLL)):
            nd = 1.0 - bd[t]
            delta = br[t] + 0.99 * nv * nd - bv[t]
            last = delta + 0.99 * 0.95 * nd * last
            adv[t] = last
            nv = bv[t]
        ret = adv + np.array(bv)
        X = torch.from_numpy(np.concatenate(bx))
        M = torch.from_numpy(np.concatenate(bm))
        A = torch.from_numpy(np.concatenate(ba))
        LP = torch.from_numpy(np.concatenate(blp))
        ADV = torch.from_numpy(adv.reshape(-1).astype(np.float32))
        ADV = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
        RET = torch.from_numpy(ret.reshape(-1).astype(np.float32))
        n = len(A)
        for _e in range(EPOCHS):
            perm = torch.from_numpy(rng.permutation(n))
            for s in range(0, n, MB):
                j = perm[s:s + MB]
                lg, v = net(X[j], M[j])
                dist = torch.distributions.Categorical(logits=lg)
                ratio = torch.exp(dist.log_prob(A[j]) - LP[j])
                pl = -torch.min(ratio * ADV[j], torch.clamp(ratio, 0.8, 1.2) * ADV[j]).mean()
                loss = pl + 0.5 * ((v - RET[j]) ** 2).mean() - 0.01 * dist.entropy().mean()
                if prior > 0:
                    loss = loss + prior * nn.functional.cross_entropy(lg, torch.zeros_like(A[j]))
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()
    return net


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v232 = _load("v232_p", RD / "v232/v232_disciplined_rl.py")
    v240 = _load("v240_p", RD / "v240/v240_order_level_flow.py")
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
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    base_pol = v216.grid_policy(v221.B_ABS, v221.B_REL)
    n, na = len(idx), len(cols)

    # ---- simulator arrays (row i = decision i, holding bar = cube row i)
    o = opens.reindex(idx)[cols]
    realized = eu.v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
    vol = (realized.rolling(60 * eu.PD, min_periods=20 * eu.PD).std() * np.sqrt(eu.PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), 2.0))
    tg = eu.v99.W_BOOKS * s[:, None] * books.to_numpy()
    sgn = np.where(np.abs(tg) >= THETA, np.sign(tg), 0.0)
    tv = v232.tv_frames(idx, cols)
    o1 = o.shift(-1)
    lo1 = np.log(o1)
    sig = lo1.diff().rolling(360, min_periods=120).std()
    ab = pd.DataFrame(np.abs(tg), index=idx, columns=cols)
    feats = [ab / ab.rolling(540, min_periods=180).median().replace(0, np.nan), sig / sig.rolling(540, min_periods=180).median(),
             lo1.diff(6) / (sig * np.sqrt(6)), lo1.diff(42) / (sig * np.sqrt(42)), tv["tv_st_dir"], tv["tv_ms_trend"],
             pd.DataFrame({c: v240.flo.flow_features(c, idx)["fl_big_imb6"].to_numpy() for c in cols}, index=idx), tv["tv_wvf_z"]]
    X = np.stack([f.reindex(idx)[cols].to_numpy(float) for f in feats], axis=2)
    # column order: 0 strength, 1 vol, 2..6 signed (r6, r42, st, ms, flow), 7 wvf, 8 hour
    X = np.concatenate([X, np.repeat((np.array([(t + pd.Timedelta(hours=4)).hour for t in idx], float) / 24)[:, None, None], na, axis=1)], axis=2)
    D = dict(na=na, X=np.nan_to_num(X), tg=tg, sgn=sgn, s4=prep["sig4"], O0=prep["O"][:, 0, :].astype(float),
             hi=np.nanmax(prep["H"][:, 5:, :].astype(float), axis=1), lo=np.nanmin(prep["L"][:, 5:, :].astype(float), axis=1),
             cl=prep["C"][:, 239, :].astype(float), settle=np.asarray(prep["settle"], bool)[:, None].repeat(na, axis=1))
    t_hold = idx + pd.Timedelta(hours=4)
    ok_bar = np.isfinite(D["O0"]).all(axis=1) & np.isfinite(D["cl"]).all(axis=1) & np.isfinite(D["s4"]).all(axis=1)

    def state_engine(i, a, st, pos):
        side = pos if pos != 0 else st["sgn"]
        x = np.r_[D["X"][i, a, :2], D["X"][i, a, 2:7] * side, D["X"][i, a, 7:9],
                  [float(pos != 0), np.clip(st.get("upnl", 0.0), -10, 10) if pos != 0 else 0.0, st.get("bars", 0) / 42 if pos != 0 else 0.0,
                   float(st.get("be", False)) if pos != 0 else 0.0]]
        return np.nan_to_num(x).astype(np.float32)

    def year(i):
        t = t_hold[i]
        return max(jj for jj, a0 in enumerate(anchors) if t >= a0) if t >= anchors[0] else 0

    out = {"version": "v257", "rows": {}, "trades": {}, "train_bars": {}}
    nets = {}
    for key, prior in (("R1_ppo", 0.0), ("R2_ppo_prior", 0.5)):
        nets[key] = {}
        for j in range(1, len(anchors)):
            rows = np.flatnonzero(ok_bar & np.asarray((t_hold >= anchors[0]) & (t_hold + pd.Timedelta(hours=4) < anchors[j] - EMBARGO)))
            nets[key][j] = train(D, rows, 257 + j, prior).eval()
            out["train_bars"][f"{key}_{anchors[j].date()}"] = int(len(rows))
            print(key, "trained for", anchors[j].date(), "on", len(rows), "bars", flush=True)

    def agent(key):
        stats = {"flat_open": 0, "flat_wait": 0, "hold": 0, "close": 0, "tighten": 0}

        def pol(i, a, st):
            jj = year(i)
            rule = base_pol(i, a, st)
            if jj == 0:
                return rule
            pos = st["pos"]
            mask = np.array([True, True, pos != 0])
            with torch.no_grad():
                lg, _ = nets[key][jj](torch.from_numpy(state_engine(i, a, st, pos)[None, :]), torch.from_numpy(mask[None, :]))
            act = int(lg.argmax())
            if pos == 0:
                stats["flat_open" if act == 0 else "flat_wait"] += 1
                return "open" if act == 0 else "wait"
            if act == 1 and "close" in st["valid"]:
                stats["close"] += 1
                return "close"
            if act == 2:
                stats["tighten"] += 1
                return {"tighten": 1} if isinstance(rule, str) and rule == "hold" else rule
            stats["hold"] += 1
            return rule
        pol.stats = stats
        return pol

    for key, pol in (("v247_B18", base_pol), ("R1_ppo", agent("R1_ppo")), ("R2_ppo_prior", agent("R2_ppo_prior"))):
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if hasattr(pol, "stats"):
            r["agent"] = dict(pol.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], r.get("agent"), flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "G2 through the hook must reproduce v247 B18"
    cands = ("R1_ppo", "R2_ppo_prior")
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
    (HERE / "v257_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
