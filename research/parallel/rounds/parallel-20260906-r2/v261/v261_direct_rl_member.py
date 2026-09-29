"""v261: a DIRECT-REINFORCEMENT foundation member - positions learned by policy gradient on the net trading Sharpe (Moody & Saffell).

Why: thirteen learned layers ON TOP of the pipeline (v214-v260) could not beat the rules; the only transfers came from the foundation
signal. The foundation members are supervised regressions of a 7-day vol-normalised return. A direct-reinforcement member instead learns
the position itself, p = tanh(f(x)), by maximising the differentiable Sharpe ratio of the NET portfolio return (position x next-bar return
minus turnover cost) - the objective the trader actually earns, including the cost of changing position. It is a different learning
principle on the verified information (TradingView indicators, order-level whale flow), i.e. model diversity inside the foundation.
Fixed before running.
Features per (decision row, coin), all known at the decision-bar close: the 17 TradingView indicators (v231/tv_indicators.py), the six
order-level flow features (v236 formulas on data/raw/aggflow_20260928_orders), 6-, 42- and 180-bar log returns in sigma units, sigma
regime (sigma / 540-bar median); standardised with the mean / std of the training rows only; NaN -> 0.
Reward: R_t = sum over coins p[t, a] * y[t, a] - 0.0004 * |p[t, a] - p[t-1, a]|, y = next holding-bar return (open t+2 / open t+1 - 1).
Objective: maximise mean(R) / std(R) (pooled over the training bars) - 1e-3 * |weights|^2, Adam, full batch, 400 epochs.
Walk-forward: the model for anchor year Y (2022..2025) trains on decision rows from 2021-09-24 whose holding bar ends before Y - 7 days;
2021 has no model (D = 0). D = p x k, k = mean |O1 book| / mean |p| on the training rows (so D has the O1 book's magnitude).
Five seeds per model, D = mean of the five seeds' positions (one method, no seed selection).
  D1_linear   f linear, lr 1e-2
  D2_mlp      f = MLP 27-32-1 (tanh), lr 3e-3
Books = 0.8 x O1 books + 0.2 x D. Environment = v247 B18 (sleeve budget 0.18, v218 D2 settings: G2 grid trader, rung x1.75, minute-5 rule,
limits, SL market / TP limit, break-even, governor, aligned sleeve, Bybit fees, adverse funding). Reference: O1 books (must reproduce
5.777). SELECTION = robust criterion among D1, D2; the most recent year is scored once for the selected row. Reported: the member's own
information coefficient per dev year (Spearman of D with the next 42-bar return).

  python research/parallel/rounds/parallel-20260906-r2/v261/v261_direct_rl_member.py
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
COST = 0.0004
SEEDS = (0, 1, 2, 3, 4)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fit(X, Y, kind, seed):
    """X (T, A, F), Y (T, A) -> trained module mapping features to positions."""
    torch.manual_seed(seed)
    F = X.shape[2]
    net = nn.Linear(F, 1) if kind == "linear" else nn.Sequential(nn.Linear(F, 32), nn.Tanh(), nn.Linear(32, 1))
    opt = torch.optim.Adam(net.parameters(), lr=1e-2 if kind == "linear" else 3e-3)
    Xt, Yt = torch.from_numpy(X.astype(np.float32)), torch.from_numpy(Y.astype(np.float32))
    for _ in range(400):
        p = torch.tanh(net(Xt).squeeze(-1))
        dp = torch.cat([p[:1] * 0, p[1:] - p[:-1]], dim=0)
        R = (p * Yt - COST * dp.abs()).sum(dim=1)
        loss = -R.mean() / (R.std() + 1e-8) + 1e-3 * sum((w ** 2).sum() for w in net.parameters())
        opt.zero_grad()
        loss.backward()
        opt.step()
    return net.eval()


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v232 = _load("v232_d", RD / "v232/v232_disciplined_rl.py")
    v240 = _load("v240_d", RD / "v240/v240_order_level_flow.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    o1_books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    KW = dict(v221.KW, sleeve_risk_budget=BUDGET)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    n, na = len(idx), len(cols)
    t_hold = idx + pd.Timedelta(hours=4)

    tv = v232.tv_frames(idx, cols)
    o = opens.reindex(idx)[cols]
    lo1 = np.log(o.shift(-1))
    sig = lo1.diff().rolling(360, min_periods=120).std()
    fl = {c: v240.flo.flow_features(c, idx) for c in cols}
    frames = [tv[k] for k in v232.v231.tvm.TV] + [pd.DataFrame({c: fl[c][k].to_numpy() for c in cols}, index=idx) for k in v240.flo.FL]
    frames += [lo1.diff(h) / (sig * np.sqrt(h)) for h in (6, 42, 180)] + [sig / sig.rolling(540, min_periods=180).median()]
    X = np.stack([f.reindex(idx)[cols].to_numpy(float) for f in frames], axis=2)  # (n, na, 27)
    Y = (o.shift(-2) / o.shift(-1) - 1).to_numpy(float)
    Yz = np.nan_to_num(Y)
    y42 = (o.shift(-43) / o.shift(-1) - 1).to_numpy(float)
    out = {"version": "v261", "n_features": int(X.shape[2]), "rows": {}, "trades": {}, "train_rows": {}, "ic": {}}

    def year_rows(j):
        return np.flatnonzero(np.asarray((t_hold >= anchors[j]) & (t_hold < (anchors[j + 1] if j + 1 < len(anchors) else t_hold[-1] + pd.Timedelta(hours=1)))))

    Ds = {}
    for kind in ("linear", "mlp"):
        D = np.zeros((n, na))
        for j in range(1, len(anchors)):
            tr = np.flatnonzero(np.asarray((t_hold >= anchors[0]) & (t_hold + pd.Timedelta(hours=4) < anchors[j] - EMBARGO)))
            mu = np.nanmean(X[tr].reshape(-1, X.shape[2]), axis=0)
            sd = np.nanstd(X[tr].reshape(-1, X.shape[2]), axis=0) + 1e-9
            Z = np.nan_to_num((X - mu) / sd)
            Z = np.clip(Z, -5, 5)
            ps_tr, ps_y = [], []
            yr = year_rows(j)
            for sd_ in SEEDS:
                net = fit(Z[tr], Yz[tr], kind, 261 + 10 * j + sd_)
                with torch.no_grad():
                    ps_tr.append(torch.tanh(net(torch.from_numpy(Z[tr].astype(np.float32))).squeeze(-1)).numpy())
                    ps_y.append(torch.tanh(net(torch.from_numpy(Z[yr].astype(np.float32))).squeeze(-1)).numpy())
            p_tr, p_y = np.mean(ps_tr, axis=0), np.mean(ps_y, axis=0)
            k = float(np.abs(o1_books.to_numpy()[tr]).mean() / max(np.abs(p_tr).mean(), 1e-9))
            D[yr] = p_y * k
            out["train_rows"][f"{kind}_{anchors[j].date()}"] = int(len(tr))
            if j < 4:
                yy = y42[yr].ravel()
                dd = D[yr].ravel()
                ok = np.isfinite(yy)
                out["ic"][f"{kind}_{anchors[j].year}"] = round(float(pd.Series(dd[ok]).corr(pd.Series(yy[ok]), method="spearman")), 4)
            print(kind, "model for", anchors[j].date(), "train rows", len(tr), "k", round(k, 4), flush=True)
        Ds[kind] = pd.DataFrame(D, index=idx, columns=cols)
    print("member IC (dev years)", out["ic"], flush=True)

    for key, bk in (("v247_B18", o1_books), ("D1_linear", 0.8 * o1_books + 0.2 * Ds["linear"]), ("D2_mlp", 0.8 * o1_books + 0.2 * Ds["mlp"])):
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
        if key == "v247_B18":
            assert abs(r["monthly_dev4"] - 5.777) < 0.002
    cands = ("D1_linear", "D2_mlp")
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
    (HERE / "v261_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
