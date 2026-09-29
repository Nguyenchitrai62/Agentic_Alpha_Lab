"""v258: disciplined sequential RL trader - PPO in a simulator that PYRAMIDS like the G2 grid, allowed to cut only LOSING positions.

Why: v257's pure PPO learned a high-win-rate style (win 56.5%) but cut the trend trades (median hold 20h vs 44h, dev4 3.9). Two design
faults explain it: (1) its simulator held a fixed size, while the real G2 trader ADDS to positions as the signal grows (347 of 1052 dev
trades have adds) - the value of holding a trend was understated; (2) nothing stopped it from closing winners. A disciplined trader cuts
losers and lets winners run and grow. v232 tried that discipline with one-step value RL; here it is a sequential PPO policy in a faithful
pyramiding simulator.
Fixed before running.
Evaluation environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings: G2 grid trader, rung x1.75, minute-5 rule, limits,
SL market / TP limit, break-even, governor, aligned sleeve, Bybit fees, adverse funding).
Simulator (per coin, 4h holding bars, all inputs known at the decision-bar close): v257's (limit entries 0.25 sigma_4h filled on a
trade-through from minute 5, SL 4 sd market, TP 8 sd limit, break-even after +2 sd, stop first, fees, adverse funding, rule close on
signal flip / loss) PLUS the G2 size rule in a position: at most once per 6 bars, if |tg| - w > max(3%, 40% |tg|) add (limit 0.25
sigma_4h better, filled on a trade-through; average entry updated), if w - |tg| > that band reduce by min(1, (w - |tg|) / w) (limit 0.25
sigma_4h better, else kept). Reward = mark-to-market coin PnL in % of equity minus fees and funding.
State (13) as v257 (w / |tg| replaces the break-even flag). PPO as v257 (MLP 64-64, 40 envs, rollout 128, 150 updates, 4 epochs,
minibatch 1024, lr 3e-4, clip 0.2, gamma 0.99, GAE 0.95, entropy 0.01, torch seed 258 + anchor).
Actions: 0 = the rule (open when flat / G2 in a position), 1 = wait (flat) / close (position), 2 = tighten (position). DISCIPLINE MASK:
close and tighten are allowed only while the position's unrealised PnL is negative (in the simulator and in the engine).
Walk-forward as v257: the policy for anchor year Y trains on holding bars from 2021-09-24 until Y - 7 days; 2021 uses the rule.
  S1_disciplined      open / wait when flat + cut / tighten losers
  S2_losers_only      always take the signal (no wait); the agent only cuts / tightens losers
Fidelity check (reported, dev years only): per-month correlation of the simulator's rule-only book PnL with the engine's book PnL
attribution.
Reference: G2 through the hook (must reproduce 5.777). SELECTION = robust criterion among S1, S2; the most recent year is scored once for
the selected row. Reported: action shares, trade statistics.

  python research/parallel/rounds/parallel-20260906-r2/v258/v258_ppo_disciplined.py
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
B_ABS, B_REL, COOL = 0.03, 0.40, 6
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
        return self.pi(h).masked_fill(~mask, -1e9), self.v(h).squeeze(-1)


class Env:
    """Vectorised per-coin G2 trade simulator (N parallel envs = coin x random start)."""

    def __init__(self, D, rows, rng, n_env=N_ENV, no_wait=False, sequential=False):
        self.D, self.rows, self.rng, self.n, self.no_wait = D, rows, rng, n_env, no_wait
        self.coin = np.arange(n_env) % D["na"]
        self.ptr = np.full(n_env, rows[0]) if sequential else rng.choice(rows[:-2], n_env)
        z = lambda: np.zeros(n_env)
        self.pos, self.entry, self.w, self.sl, self.tp, self.sdv, self.be, self.held, self.since = z(), z(), z(), z(), z(), np.ones(n_env), z(), z(), z()

    def upnl(self):
        i, a = self.ptr, self.coin
        return np.where(self.pos != 0, (self.D["O0"][i, a] / np.where(self.entry > 0, self.entry, 1) - 1) * self.pos / self.sdv, 0.0)

    def obs(self):
        D, i, a = self.D, self.ptr, self.coin
        sgn, tg = D["sgn"][i, a], np.abs(D["tg"][i, a])
        side = np.where(self.pos != 0, self.pos, sgn)
        up = np.nan_to_num(self.upnl())
        x = np.column_stack([D["X"][i, a, :2], D["X"][i, a, 2:7] * side[:, None], D["X"][i, a, 7:9],
                             (self.pos != 0).astype(float), np.clip(up, -10, 10), self.held / 42,
                             np.where((self.pos != 0) & (tg > 0), np.clip(self.w / np.where(tg > 0, tg, 1), 0, 5), 0.0)])
        mask = np.ones((self.n, 3), bool)
        losing = (self.pos != 0) & (up < 0)
        mask[:, 1] = losing | ((self.pos == 0) & (sgn != 0) & (not self.no_wait))
        mask[:, 2] = losing
        return np.nan_to_num(x).astype(np.float32), mask

    def step(self, act):
        D, i, a = self.D, self.ptr, self.coin
        O0, hi, lo, cl, s4 = D["O0"][i, a], D["hi"][i, a], D["lo"][i, a], D["cl"][i, a], D["s4"][i, a]
        sd, sgn, tg, st = s4 * np.sqrt(6), D["sgn"][i, a], np.abs(D["tg"][i, a]), D["settle"][i, a]
        ok = np.isfinite(O0) & np.isfinite(hi) & np.isfinite(lo) & np.isfinite(cl) & np.isfinite(s4)
        r = np.zeros(self.n)
        flat = (self.pos == 0) & ok
        # ---- flat: open at a limit (rule), unless the agent waits
        do_open = flat & (sgn != 0) & (act == 0) & (tg > 0)
        px = O0 * (1 - sgn * K_OFF * s4)
        filled = do_open & np.where(sgn > 0, lo < px, hi > px)
        r[filled] -= 100 * tg[filled] * MAKER
        r[filled] += 100 * tg[filled] * sgn[filled] * (cl[filled] / px[filled] - 1)
        for name, val in (("pos", sgn), ("entry", px), ("w", tg), ("sdv", sd), ("sl", px * (1 - sgn * M_SL * sd)),
                          ("tp", px * (1 + sgn * M_TP * sd)), ("be", 0.0), ("held", 0.0), ("since", 0.0)):
            setattr(self, name, np.where(filled, val, getattr(self, name)))
        # ---- in a position from an earlier bar
        inpos = (~flat) & (self.pos != 0) & ok & ~filled
        side = self.pos
        up = self.upnl()
        losing = up < 0
        want_close = inpos & ((sgn != side) | ((act == 1) & losing))
        tight = inpos & ((act == 2) & losing | (sgn == -side))
        new_sl = O0 * (1 - side * TIGHT * sd)
        better = tight & ((new_sl - self.sl) * side > 0) & ((O0 - new_sl) * side > 0)
        self.sl = np.where(better, new_sl, self.sl)
        # G2 size adjustment (only when not closing)
        band = np.maximum(B_ABS, B_REL * tg)
        diff = tg - self.w
        adj = inpos & ~want_close & (self.since >= COOL) & (sgn == side)
        add = adj & (diff > band)
        red = adj & (-diff > band) & (self.w > 0)
        apx = O0 * (1 - side * K_OFF * s4)
        rpx = O0 * (1 + side * K_OFF * s4)
        add_f = add & np.where(side > 0, lo < apx, hi > apx)
        red_f = red & np.where(side > 0, hi > rpx, lo < rpx)
        # stop first, then TP, then a requested close
        stop_hit = inpos & np.where(side > 0, lo <= self.sl, hi >= self.sl)
        sp = np.where(side > 0, np.minimum(self.sl, O0), np.maximum(self.sl, O0))
        tp_hit = inpos & ~stop_hit & np.where(side > 0, hi > self.tp, lo < self.tp)
        cpx = O0 * (1 + side * K_OFF * s4)
        c_fill = want_close & ~stop_hit & ~tp_hit & np.where(side > 0, hi > cpx, lo < cpx)
        c_mkt = want_close & ~stop_hit & ~tp_hit & ~c_fill
        exit_px = np.select([stop_hit, tp_hit, c_fill, c_mkt], [sp, self.tp, cpx, cl], np.nan)
        exit_fee = np.select([stop_hit, tp_hit, c_fill, c_mkt], [TAKER, MAKER, MAKER, TAKER], 0.0)
        exited = inpos & np.isfinite(exit_px)
        end_px = np.where(exited, exit_px, cl)
        # PnL of the held weight from the bar open, of an add from its fill, of a reduce up to its fill
        rf = np.where(red_f & ~exited, np.minimum(1.0, -diff / np.where(self.w > 0, self.w, 1)), 0.0)
        wr = self.w * rf
        r += np.where(inpos, 100 * side * ((self.w - wr) * (end_px / O0 - 1) + wr * (rpx / O0 - 1)), 0.0)
        r -= np.where(red_f & ~exited, 100 * wr * MAKER, 0.0)
        dw = np.where(add_f & ~exited, diff, 0.0)
        r += np.where(dw > 0, 100 * side * dw * (end_px / apx - 1) - 100 * dw * MAKER, 0.0)
        r -= np.where(exited, 100 * self.w * exit_fee, 0.0)
        r -= np.where((inpos | filled) & (self.pos > 0) & st, 100 * np.where(inpos, self.w, 0.0) * FUND, 0.0)
        new_w = self.w - wr + dw
        self.entry = np.where(dw > 0, (self.w * self.entry + dw * apx) / np.where(new_w > 0, new_w, 1), self.entry)
        self.w = np.where(inpos, new_w, self.w)
        self.since = np.where(add_f | red_f, 0.0, self.since + 1)
        fav = np.where(self.pos > 0, hi / np.where(self.entry > 0, self.entry, 1) - 1, 1 - lo / np.where(self.entry > 0, self.entry, 1))
        to_be = inpos & ~exited & (fav >= BE_K * self.sdv) & (self.be == 0)
        self.sl = np.where(to_be, self.entry * (1 + self.pos * 0.001), self.sl)
        self.be = np.where(to_be, 1.0, self.be)
        self.pos = np.where(exited | (self.w <= 1e-9), 0.0, self.pos)
        self.held = np.where(self.pos != 0, self.held + 1, 0.0)
        self.ptr = self.ptr + 1
        done = self.ptr >= self.rows[-1]
        if done.any():
            self.ptr[done] = self.rng.choice(self.rows[:-2], int(done.sum()))
            self.pos[done] = 0.0
        return np.nan_to_num(r), done


def train(D, rows, seed, no_wait):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    env = Env(D, rows, rng, no_wait=no_wait)
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
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()
    return net


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v232 = _load("v232_q", RD / "v232/v232_disciplined_rl.py")
    v240 = _load("v240_q", RD / "v240/v240_order_level_flow.py")
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
    na = len(cols)

    o = opens.reindex(idx)[cols]
    realized = eu.v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
    vol = (realized.rolling(60 * eu.PD, min_periods=20 * eu.PD).std() * np.sqrt(eu.PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), 2.0))
    tg = eu.v99.W_BOOKS * s[:, None] * books.to_numpy()
    sgn = np.where(np.abs(tg) >= THETA, np.sign(tg), 0.0)
    tv = v232.tv_frames(idx, cols)
    lo1 = np.log(o.shift(-1))
    sig = lo1.diff().rolling(360, min_periods=120).std()
    ab = pd.DataFrame(np.abs(tg), index=idx, columns=cols)
    feats = [ab / ab.rolling(540, min_periods=180).median().replace(0, np.nan), sig / sig.rolling(540, min_periods=180).median(),
             lo1.diff(6) / (sig * np.sqrt(6)), lo1.diff(42) / (sig * np.sqrt(42)), tv["tv_st_dir"], tv["tv_ms_trend"],
             pd.DataFrame({c: v240.flo.flow_features(c, idx)["fl_big_imb6"].to_numpy() for c in cols}, index=idx), tv["tv_wvf_z"]]
    X = np.stack([f.reindex(idx)[cols].to_numpy(float) for f in feats], axis=2)
    X = np.concatenate([X, np.repeat((np.array([(t + pd.Timedelta(hours=4)).hour for t in idx], float) / 24)[:, None, None], na, axis=1)], axis=2)
    D = dict(na=na, X=np.nan_to_num(X), tg=tg, sgn=sgn, s4=prep["sig4"], O0=prep["O"][:, 0, :].astype(float),
             hi=np.nanmax(prep["H"][:, 5:, :].astype(float), axis=1), lo=np.nanmin(prep["L"][:, 5:, :].astype(float), axis=1),
             cl=prep["C"][:, 239, :].astype(float), settle=np.asarray(prep["settle"], bool)[:, None].repeat(na, axis=1))
    t_hold = idx + pd.Timedelta(hours=4)
    ok_bar = np.isfinite(D["O0"]).all(axis=1) & np.isfinite(D["cl"]).all(axis=1) & np.isfinite(D["s4"]).all(axis=1)
    out = {"version": "v258", "rows": {}, "trades": {}, "train_bars": {}}

    # ---- fidelity check on the dev years: simulator rule-only book PnL vs engine attribution
    dev_rows = np.flatnonzero(np.asarray((t_hold >= anchors[0]) & (t_hold < anchors[4])))
    sim = Env(D, np.r_[dev_rows, dev_rows[-1] + 1], np.random.default_rng(0), n_env=na, sequential=True)
    sim.coin = np.arange(na)
    pnl = []
    for _ in range(len(dev_rows)):
        rr, _ = sim.step(np.zeros(na, int))
        pnl.append(rr.sum())
    att = []
    eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=base_pol), win_start=5, attrib=att, **KW)
    eng = pd.Series({t: 100 * float(np.sum(p)) for t, p, _ in att})
    simm = pd.Series(pnl, index=t_hold[dev_rows]).resample("MS").sum()
    engm = eng[(eng.index >= anchors[0]) & (eng.index < anchors[4])].resample("MS").sum()
    jm = pd.concat([simm, engm], axis=1).dropna()
    out["fidelity"] = {"monthly_corr": round(float(jm.corr().iloc[0, 1]), 3), "sim_sum_pct": round(float(simm.sum()), 1),
                       "engine_sum_pct": round(float(engm.sum()), 1)}
    print("fidelity (dev, monthly book PnL sim vs engine)", out["fidelity"], flush=True)

    def state_engine(i, a, st, pos):
        side = pos if pos != 0 else st["sgn"]
        tgv = abs(st["tg"])
        x = np.r_[D["X"][i, a, :2], D["X"][i, a, 2:7] * side, D["X"][i, a, 7:9],
                  [float(pos != 0), np.clip(st.get("upnl", 0.0), -10, 10) if pos != 0 else 0.0, st.get("bars", 0) / 42 if pos != 0 else 0.0,
                   np.clip(st.get("w", 0.0) / tgv, 0, 5) if (pos != 0 and tgv > 0) else 0.0]]
        return np.nan_to_num(x).astype(np.float32)

    def year(i):
        t = t_hold[i]
        return max(jj for jj, a0 in enumerate(anchors) if t >= a0) if t >= anchors[0] else 0

    nets = {}
    for key, no_wait in (("S1_disciplined", False), ("S2_losers_only", True)):
        nets[key] = {}
        for j in range(1, len(anchors)):
            rows = np.flatnonzero(ok_bar & np.asarray((t_hold >= anchors[0]) & (t_hold + pd.Timedelta(hours=4) < anchors[j] - EMBARGO)))
            nets[key][j] = train(D, rows, 258 + j, no_wait).eval()
            out["train_bars"][f"{key}_{anchors[j].date()}"] = int(len(rows))
            print(key, "trained for", anchors[j].date(), "on", len(rows), "bars", flush=True)

    def agent(key, no_wait):
        stats = {"flat_open": 0, "flat_wait": 0, "rule": 0, "cut": 0, "tighten": 0}

        def pol(i, a, st):
            rule = base_pol(i, a, st)
            jj = year(i)
            if jj == 0:
                return rule
            pos = st["pos"]
            losing = pos != 0 and st.get("upnl", 0.0) < 0
            mask = np.array([True, losing or (pos == 0 and not no_wait), losing])
            with torch.no_grad():
                lg, _ = nets[key][jj](torch.from_numpy(state_engine(i, a, st, pos)[None, :]), torch.from_numpy(mask[None, :]))
            act = int(lg.argmax())
            if pos == 0:
                stats["flat_open" if act == 0 else "flat_wait"] += 1
                return "open" if act == 0 else "wait"
            if act == 1 and "close" in st["valid"]:
                stats["cut"] += 1
                return "close"
            if act == 2 and isinstance(rule, str) and rule == "hold":
                stats["tighten"] += 1
                return "tighten"
            stats["rule"] += 1
            return rule
        pol.stats = stats
        return pol

    for key, pol in (("v247_B18", base_pol), ("S1_disciplined", agent("S1_disciplined", False)), ("S2_losers_only", agent("S2_losers_only", True))):
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
    cands = ("S1_disciplined", "S2_losers_only")
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
    (HERE / "v258_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
