"""v293: RL trader decision with MORE EXPERIENCE - a take-profit agent for the dip rungs, trained on 11 coins, trading the majors (registry v293).

Why (user 2026-09-30: focus on an RL agent that acts like a good trader): fourteen learned layers failed, audited causes (research-map):
fat-tailed payoffs defeat value estimates, and ~1000 decisions in four years make learned policies seed- / regime-lucky. The one
learned trader decision with a clear dev gain was the v248 dip-exit agent (choose the take-profit of each filled dip rung from exact
counterfactuals; dev4 6.05 vs 5.78) - rejected only because the O1 drawdown margin was thin (DD 20.7). This version (1) moves it to CB
(DD 18.39, the setting in which member D passed after failing on a thin margin) and (2) attacks the data problem directly: how to take
profit on a liquidation dip is a generic trading skill, so the agent learns from the dip rungs of 11 liquid perps (the five majors + six
large alts with Binance 1m history: ADA, AVAX, DOGE, LINK, LTC, TRX) - about twice the experience - while trading the majors only.
Exact counterfactuals (full-information bandit, no exploration, no bootstrapped values): a standalone replica of engine_user's dip ladder
(rungs 2.5 / 3 / 3.5 / 4 sigma_4h below the holding bar open, trade-through fills from minute 16, close5 stop at 4 sigma + 8-sigma
backstop, TP limit, timeout at the next 4h open incl. adverse funding, maker 0.0002 / taker 0.00055) gives each fill's net return under
every action. FIDELITY CHECK (asserted): on the majors, the replica's m = 1.0 return matches the engine's (which stores 1m prices as float32, so
exact equality is not expected) for >= 97% of the rungs the CB engine run takes within |diff| < 1e-4 and a mean |diff| < 2e-4, counting rungs filled from 60 days after the engine's first bar (the engine computes sigma_4h
only from its own index start, 2021-09-24, so its first 360 bars use a shorter window).
Actions at the fill: take-profit multiple m in {0.5, 1.0, 1.5} sigma_4h (engine hook sleeve_tp; stops and timeout unchanged).
State (known at minute f-1): sp30 = 30-minute log return / (sigma_1m sqrt 30) (sigma_1m = std of 1m log returns over the previous 1440
minutes); rung depth; volreg = sigma_4h / its 540-bar median; trend = 42-bar log return of the 4h opens / (sigma_4h sqrt 42);
btc_sp30 = BTC's sp30 at the same minute (market-wide flush); dd24 = log(close / 24h high) / sigma_4h; hour of the fill.
Model: per action HistGradientBoostingRegressor (depth 3, lr 0.05, 200 iter, min leaf 200, l2 1.0) on the net return clipped to
[-0.10, 0.08]; cross-fitted on even / odd bars; for the year starting at anchor Y the fits use only fills that EXITED before Y - 7 days
(the pooled data starts 2020-10, so 2021 has a model too). Policy: deviate from m = 1.0 only if both halves prefer the same action by
more than 0.0005 (v248 strict margin).
Fixed before running (everything else = CB / C4 rules):
  X1_majors   agent trained on the five majors' fills only
  X2_pooled   agent trained on the 11-coin fills (majors + six alts)
Reference: CB_ref (must reproduce dev4 5.864). SELECTION = v286.dev_select among X1, X2; replaces CB only if dev_select prefers it over
CB_ref; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
RD = HERE.parent
C4R = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ALTS = ("ADAUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT", "TRXUSDT")
ACTIONS = (0.5, 1.0, 1.5)
RUNGS, SLEEVE_START, M_SL, BACKSTOP = (2.5, 3.0, 3.5, 4.0), 16, 4.0, 8.0
START, END = pd.Timestamp("2020-08-01", tz="UTC"), pd.Timestamp("2026-09-24", tz="UTC")
EMBARGO, MARGIN = pd.Timedelta(days=7), 0.0005


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_1m(s):
    if s == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    elif s in MAJORS:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{s}_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/alts_intraday_20260926").glob(f"{s}_1m_20*.parquet"))
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    m = m[(m.index >= START) & (m.index < END)]
    return m.reindex(pd.date_range(START, END - pd.Timedelta(minutes=1), freq="1min"))


class Asset:
    """Continuous 1m arrays + 4h-bar quantities with engine_user's conventions (holding bar j starts at START + 4h j)."""

    def __init__(self, s):
        m = load_1m(s)
        self.O, self.H, self.L, self.C = (m[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        nb = len(m) // 240
        self.nb = nb
        opens = self.O[: nb * 240: 240]                           # open of each 4h bar (NaN when missing)
        self.o = opens
        pc = pd.Series(opens).pct_change()
        self.sig = pc.rolling(360, min_periods=120).std().shift(1).to_numpy()   # engine: opens up to the decision bar (T - 4h)
        self.volreg = (pd.Series(self.sig) / pd.Series(self.sig).rolling(540, min_periods=180).median()).to_numpy()
        self.trend = (np.log(pd.Series(opens)) - np.log(pd.Series(opens).shift(42))).to_numpy() / (self.sig * np.sqrt(42))
        lr = np.diff(np.log(pd.Series(self.C).ffill().to_numpy()), prepend=np.nan)
        self.sig1 = pd.Series(lr).rolling(1440, min_periods=720).std().to_numpy()
        self.hmax24 = pd.Series(self.H).rolling(1440, min_periods=720).max().to_numpy()
        self.t0 = m.index[: nb * 240: 240]

    def sp30(self, k):
        if k < 30 or not (self.sig1[k] > 0):
            return np.nan
        return np.log(self.C[k] / self.C[k - 30]) / (self.sig1[k] * np.sqrt(30))


def outcomes(A, j, lv, sg, f, mults, maker, taker, fund):
    """engine_user close5 + backstop exit for a rung filled at minute f of holding bar j, for each TP multiple."""
    base = j * 240
    Ha, La, Ca, Oa = (X[base: base + 240] for X in (A.H, A.L, A.C, A.O))
    o2 = A.o[j + 1] if j + 1 < A.nb else np.nan
    settle = (A.t0[j] + pd.Timedelta(hours=4)).hour in (0, 8, 16)
    sl, bl = lv * (1 - M_SL * sg), lv * (1 - BACKSTOP * sg)
    mi_ = np.arange(f + 1, 240)
    trig = (Ca[f + 1:240] <= sl) & ((mi_ + 1) % 5 == 0)
    ks = int(np.argmax(trig)) if trig.any() else None
    hb = La[f + 1:240] <= bl
    kb = int(np.argmax(hb)) if hb.any() else None
    res = []
    for mu in mults:
        tp = lv * (1 + mu * sg)
        ht = Ha[f + 1:240] > tp
        kt = int(np.argmax(ht)) if ht.any() else None
        if kb is not None and (ks is None or kb <= ks) and (kt is None or kb <= kt):
            x = f + 1 + kb
            ret = min(bl, Oa[x]) / lv - 1 - maker - taker
        elif kt is not None and (ks is None or kt < ks):
            x = f + 1 + kt
            ret = tp / lv - 1 - 2 * maker
        elif ks is not None:
            km = f + 1 + ks
            x, px_ = (km + 1, Oa[km + 1]) if km + 1 < 240 else (240, o2)
            ret = px_ / lv - 1 - maker - taker
        else:
            x = 240
            ret = o2 / lv - 1 - maker - taker - (fund if settle else 0.0)
        res.append((ret, A.t0[j] + pd.Timedelta(minutes=int(x))))
    return res


def fills_of(A, maker, taker, fund, btc):
    rows = []
    for j in range(1, A.nb - 1):
        sg, o1 = A.sig[j], A.o[j]
        if not (np.isfinite(sg) and np.isfinite(o1)):
            continue
        Lw = A.L[j * 240 + SLEEVE_START: j * 240 + 239]
        for r, k in enumerate(RUNGS):
            lv = o1 * (1 - k * sg)
            hit = Lw < lv
            if not hit.any():
                continue
            f = SLEEVE_START + int(np.argmax(hit))
            out = outcomes(A, j, lv, sg, f, ACTIONS, maker, taker, fund)
            if not all(np.isfinite(x[0]) for x in out):
                continue
            kk = j * 240 + f - 1
            state = [A.sp30(kk), k, A.volreg[j], A.trend[j], btc.sp30(kk),
                     np.log(A.C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, (A.t0[j].hour + f // 60) % 24]
            rows.append(dict(j=j, r=r, f=f, t_fill=A.t0[j] + pd.Timedelta(minutes=f), t_exit=max(x[1] for x in out),
                             **{f"y{mu}": x[0] for mu, x in zip(ACTIONS, out)}, **{f"x{q}": v for q, v in enumerate(state)}))
    return pd.DataFrame(rows)


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_x", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    kw = dict(v221.KW, **C4R)
    assets = {s: Asset(s) for s in MAJORS + ALTS}
    btc = assets["BTCUSDT"]
    data = {s: fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc).assign(sym=s) for s, A in assets.items()}
    print("fills per asset", {s: len(d) for s, d in data.items()}, flush=True)

    # fidelity: the replica's m = 1.0 outcome vs the engine's CB run (rungs the engine takes)
    ev = []
    ref = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, **kw)
    assert abs(ref["monthly_dev4"] - 5.864) < 0.002
    pend, eng = {}, []
    for e in ev:
        if e["kind"] == "rung_fill":
            pend[e["symbol"]] = e
        elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and e["symbol"] in pend:
            f0 = pend.pop(e["symbol"])
            eng.append((e["symbol"], f0["t"], f0["rung"], float(e["ret"])))
    look = {(s, t, RUNGS[int(r)]): y for s, d in data.items() if s in MAJORS for t, r, y in zip(d.t_fill, d.r, d["y1.0"])}
    t_ok = idx[0] + pd.Timedelta(days=60)
    eng = [e for e in eng if e[1] >= t_ok]
    diffs = np.array([abs(look[(s, t, rg)] - ret) if (s, t, rg) in look else np.inf for s, t, rg, ret in eng])
    share = float((diffs < 1e-4).mean())
    mad = float(diffs[np.isfinite(diffs)].mean())
    print(f"fidelity: engine rungs {len(eng)}, within 1e-4 {share:.4f}, mean |diff| {mad:.2e}", flush=True)
    assert share >= 0.97 and mad < 2e-4, "standalone replica does not reproduce the engine's dip outcomes"

    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    allf = pd.concat(data.values(), ignore_index=True)
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in ACTIONS]].to_numpy(float), -0.10, 0.08)
    half = (allf["j"] % 2).to_numpy()
    dev = np.asarray((allf.t_fill >= anchors[0]) & (allf.t_fill < anchors[4]))
    out = {"version": "v293", "fidelity_exact_share": round(share, 4), "fills": {s: len(d) for s, d in data.items()},
           "dev_mean_net_by_action_pct": {g: {str(mu): round(100 * float(Y[dev & allf.sym.isin(S).to_numpy(), c].mean()), 4)
                                              for c, mu in enumerate(ACTIONS)} for g, S in (("majors", MAJORS), ("alts", ALTS))},
           "train": {}, "rows": {}, "trades": {}}
    print("dev mean net by action %", out["dev_mean_net_by_action_pct"], flush=True)

    def fit(pool):
        models = {}
        for jj, a0 in enumerate(anchors):
            keep = np.asarray(allf.t_exit < a0 - EMBARGO) & allf.sym.isin(pool).to_numpy()
            pair = []
            for h in (0, 1):
                sel = keep & (half == h)
                pair.append([HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200,
                                                           l2_regularization=1.0, random_state=10 * jj + h + 3 * c).fit(X[sel], Y[sel, c])
                             for c in range(len(ACTIONS))])
            models[jj] = pair
            out["train"].setdefault(str(a0.date()), {})[str(len(pool))] = int(keep.sum())
        return models

    grid_t0 = btc.t0
    pos = pd.Series(np.arange(len(grid_t0)), index=grid_t0)

    def agent(models):
        stats = {"asked": 0, "changed": {str(mu): 0 for mu in ACTIONS}}
        base = ACTIONS.index(1.0)

        def pol(i, a, r, f):
            T = idx[i] + pd.Timedelta(hours=4)
            jj = max([q for q, a0 in enumerate(anchors) if T >= a0], default=None)
            if jj is None or T not in pos.index:
                return 1.0
            A, j = assets[cols[a]], int(pos[T])
            kk = j * 240 + f - 1
            sg = A.sig[j]
            x = np.array([[A.sp30(kk), RUNGS[r], A.volreg[j], A.trend[j], btc.sp30(kk),
                           np.log(A.C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, (A.t0[j].hour + f // 60) % 24]])
            pa = np.array([mm.predict(x)[0] for mm in models[jj][0]])
            pb = np.array([mm.predict(x)[0] for mm in models[jj][1]])
            ba, bb = int(np.argmax(pa)), int(np.argmax(pb))
            stats["asked"] += 1
            if ba == bb and ba != base and pa[ba] - pa[base] > MARGIN and pb[bb] - pb[base] > MARGIN:
                stats["changed"][str(ACTIONS[ba])] += 1
                return ACTIONS[ba]
            return 1.0
        pol.stats = stats
        return pol

    ref["worst_dev_month_pct"] = round(v204.worst_month(ref), 3)
    ref["dev_dd"] = v286.dev_dd(ref)
    out["rows"]["CB_ref"], out["trades"]["CB_ref"] = ref, v213.trade_stats(ev)
    for key, pool in (("X1_majors", MAJORS), ("X2_pooled", MAJORS + ALTS)):
        hook = agent(fit(pool))
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_tp=hook, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["agent"] = dict(hook.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], "agent", r["agent"],
              "dev win", out["trades"][key]["dev"]["win_rate"], flush=True)
    sel = v286.dev_select({k: out["rows"][k] for k in ("X1_majors", "X2_pooled")}, v204.worst_month)
    out["selected"] = sel
    out["replaces_cb"] = v286.dev_select({k: out["rows"][k] for k in ("CB_ref", sel)}, v204.worst_month) == sel
    s_ = out["rows"][sel]
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, "replaces CB:", out["replaces_cb"], out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v293_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
