"""Opencode v26 (R7-A2 retry lan 3 cua R5-A2/R6-A2; 2 lan truoc rate-limit phia provider).

Kien truc DONG BANG theo configs/opencode_v26_multitask.json (byte-identical logic R6-A2):
  in 44 (40 frozen past-only + 4 calendar-only) -> 64 -> 32 -> heads:
  - direction: logits 3-class (SHORT/WAIT/LONG) tai H=48 bars, band 8bps
  - quantile: P10/P50/P90 cua return H=48 (pinball loss)
  - excursion: up MFE + down MAE tai H=48 (MSE tren log1p, softplus>=0)
Loss tong (trong so DONG BANG): CE + 1.0*mean(pinball) + 0.5*mean(MSE).
Walk-forward theo thang, train 730d, embargo 8d, seed 1729, CPU.
Policy 2 nhanh (dong bang): mt_p10gate (chat) / mt_p50gate (long) x {1x, dd_guard}.
Tin hieu -> geometry co dinh moi side (offset 0.5 ATR5, stop/TP1/TP2 2/2/4, giu 7d).
Backtest: run_backtest (normal / fee 0.00055) + run_stress execution.
Exploratory: development interval only. No live approval.
"""
import torch  # noqa: F401  (torch truoc pandas: tranh loi DLL tren host nay)
import argparse
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.swing import grid, prices
from agentic_alpha_lab.data.training import sha256

BARS_PER_DAY = 288
H = 48  # horizon bars (4h), theo config heads
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]
QUANTS = [0.1, 0.5, 0.9]


def build_labels(decisions, candles, horizon=H):
    """Labels dung future (cho phep); features khong bao gio thay doi."""
    o = candles["open"].to_numpy(float)
    h = candles["high"].to_numpy(float)
    low = candles["low"].to_numpy(float)
    c = candles["close"].to_numpy(float)
    bi = decisions["bar_index"].to_numpy()
    if (bi + horizon + 1 >= len(c)).any():
        raise ValueError("Thieu tuong lai H=48 cho mot so decision")
    ret = c[bi + horizon] / c[bi] - 1.0
    up = np.stack([h[bi + k] for k in range(1, horizon + 1)]).max(0) / c[bi] - 1.0
    dn = 1.0 - np.stack([low[bi + k] for k in range(1, horizon + 1)]).min(0) / c[bi]
    return ret.astype(np.float64), np.clip(up, 0, None), np.clip(dn, 0, None)


def derived_calendar(signal_time):
    """4 dac trung lich, causal tam thuong (khong market future)."""
    t = pd.to_datetime(signal_time, utc=True)
    hh, mm, ss = t.dt.hour, t.dt.minute, t.dt.second
    hod = hh + mm / 60.0 + ss / 3600.0
    mins_to_next = ((8 - (hh % 8)) % 8) * 60 - mm - ss / 60.0
    mins_to_next = np.where(mins_to_next <= 0, mins_to_next + 480, mins_to_next)
    return np.stack([
        mins_to_next / 5.0,  # bars_to_funding
        np.sin(2 * np.pi * hod / 24.0),
        np.cos(2 * np.pi * hod / 24.0),
        ((t.dt.dayofweek >= 5).astype(float)),  # is_weekend_utc
    ], -1).astype(np.float64)


class MultiHead(torch.nn.Module):
    def __init__(self, n_in, hidden, p_drop):
        super().__init__()
        self.trunk = torch.nn.Sequential(
            torch.nn.Linear(n_in, hidden[0]), torch.nn.ReLU(), torch.nn.Dropout(p_drop),
            torch.nn.Linear(hidden[0], hidden[1]), torch.nn.ReLU(), torch.nn.Dropout(p_drop))
        self.dir = torch.nn.Linear(hidden[1], 3)
        self.q = torch.nn.Linear(hidden[1], 3)
        self.ex = torch.nn.Linear(hidden[1], 2)

    def forward(self, x):
        h = self.trunk(x)
        return self.dir(h), self.q(h), torch.nn.functional.softplus(self.ex(h))


def pinball(pred, y, qs=QUANTS):
    e = y.unsqueeze(1) - pred
    q = torch.tensor(qs, dtype=pred.dtype, device=pred.device).unsqueeze(0)
    return torch.maximum(q * e, (q - 1) * e).mean()


def fit_fold(Xtr, ydir, yret, yup, ydn, cfg_m, seed, epochs, patience, batch):
    torch.manual_seed(seed)
    rng = np.random.RandomState(seed)
    n = len(Xtr)
    n_val = max(32, int(n * cfg_m["val_fraction"]))
    idx = np.arange(n)
    tr_idx, va_idx = idx[:-n_val], idx[-n_val:]  # val = doan cuoi theo thoi gian
    mu, sd = Xtr[tr_idx].mean(0), Xtr[tr_idx].std(0) + 1e-8
    Xt = torch.from_numpy(((Xtr - mu) / sd).astype(np.float32))
    yd = torch.from_numpy(ydir.astype(np.int64))
    yr = torch.from_numpy(yret.astype(np.float32))
    ye = torch.from_numpy(np.stack([yup, ydn], -1).astype(np.float32))
    counts = np.bincount(ydir[tr_idx], minlength=3).astype(float) + 1.0
    cw = torch.from_numpy((counts.sum() / (3 * counts)).astype(np.float32))
    ce = torch.nn.CrossEntropyLoss(weight=cw)
    net = MultiHead(Xtr.shape[1], cfg_m_hidden(cfg_m), cfg_m["dropout"])
    opt = torch.optim.Adam(net.parameters(), lr=cfg_m["lr"], weight_decay=cfg_m["weight_decay"])
    w = cfg_m_arch_weights()
    best, bad, best_state = np.inf, 0, None
    order = tr_idx.copy()
    for ep in range(epochs):
        net.train()
        rng.shuffle(order)
        for s in range(0, len(order), batch):
            b = order[s:s + batch]
            d, q, e = net(Xt[b])
            loss = ce(d, yd[b]) + w[1] * pinball(q, yr[b]) + w[2] * torch.nn.functional.mse_loss(
                torch.log1p(e), torch.log1p(ye[b]))
            opt.zero_grad()
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            d, q, e = net(Xt[va_idx])
            vl = ce(d, yd[va_idx]) + w[1] * pinball(q, yr[va_idx]) + w[2] * torch.nn.functional.mse_loss(
                torch.log1p(e), torch.log1p(ye[va_idx]))
        vl = float(vl)
        if vl < best - 1e-6:
            best, bad = vl, 0
            best_state = {k: v.cpu().clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    net.load_state_dict(best_state)
    net.eval()
    return net, mu, sd, best


def cfg_m_hidden(cfg_m):
    return cfg_m["hidden"]


def cfg_m_arch_weights():
    return (1.0, 1.0, 0.5)  # CE, pinball, excursion (DONG BANG theo config)


def predict_fold(net, mu, sd, X):
    net.eval()
    with torch.no_grad():
        Xt = torch.from_numpy(((X - mu) / sd).astype(np.float32))
        d, q, e = net(Xt)
        prob = torch.softmax(d, -1).numpy()
        return prob, q.numpy(), e.numpy()


def gen_signals(part, prob, qret, branch, cfg_all, ds_cfg):
    """Policy dong bang: p10gate/p50gate + cooldown 5d + max 4/thang."""
    pol = cfg_all["policy_branches"][branch]
    strict = (branch == "mt_p10gate")
    band = cfg_all["architecture"]["heads"]["direction"]["wait_band_bps"] / 1e4
    min_prob = 0.45
    cls = prob.argmax(1)
    conf = prob.max(1)
    rows = []
    for i, row in enumerate(part.itertuples()):
        c = int(cls[i])
        if strict:
            ok_long = c == 2 and qret[i, 0] > band and conf[i] >= min_prob
            ok_short = c == 0 and qret[i, 2] < -band and conf[i] >= min_prob
        else:
            ok_long = c == 2 and qret[i, 1] > band and conf[i] >= min_prob
            ok_short = c == 0 and qret[i, 1] < -band and conf[i] >= min_prob
        if ok_long:
            side = 1
        elif ok_short:
            side = -1
        else:
            continue
        cand = np.array([side, 0.5, 2.0, 2.0, 4.0, 7], np.float32)
        px = prices(float(row.close), float(row.atr5), float(row.atr4), cand, ds_cfg)
        rows.append({"bar_index": row.bar_index, "signal_time": pd.Timestamp(row.signal_time),
                     "direction": side, "prob": float(conf[i]),
                     "q10": float(qret[i, 0]), "q50": float(qret[i, 1]), "q90": float(qret[i, 2]),
                     **px})
    if not rows:
        return pd.DataFrame(columns=["bar_index", "direction", "signal_time"])
    sig = pd.DataFrame(rows).sort_values("signal_time").reset_index(drop=True)
    out, monthly = [], Counter()
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    for _, r in sig.iterrows():
        ts = pd.Timestamp(r["signal_time"])
        month = ts.strftime("%Y-%m")
        if ts < next_allowed or monthly[month] >= ds_cfg["policy"]["maximum_signals_per_month"]:
            continue
        out.append(r)
        monthly[month] += 1
        next_allowed = ts + pd.Timedelta(days=ds_cfg["policy"]["cooldown_days"])
    return pd.DataFrame(out) if out else pd.DataFrame(columns=["bar_index", "direction", "signal_time"])


def dd_guard_leverage(signals, trades):
    eq = pd.Series({pd.Timestamp(t.exit_time): t.equity_after for t in trades}).sort_index()
    out = []
    for ts in pd.to_datetime(signals["signal_time"], utc=True):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}), past]).sort_index()
        out.append(0.5 if float(curve.iloc[-1]) / float(curve.cummax().iloc[-1]) < 0.9 else 1.0)
    return np.array(out, dtype=float)


def run_branch(candles, signals, costs, execution, duration_years, out_dir):
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, _ = run_backtest(candles, signals, 100, fee_costs, execution)
    stress, st, diagnostic = run_stress(candles, signals, 100, costs, execution,
                                        FillStress(5, 5, 5, 0.00055, False))
    scenarios = {}
    for label, result, items in (("normal", normal, trades), ("fee_stress", fee, None),
                                 ("execution_stress", stress, st)):
        ratio = result.final_equity / 100
        scenarios[label] = {**asdict(result),
                            "annual_geometric_net": ratio ** (1 / duration_years) - 1,
                            "monthly_geometric_net": ratio ** (1 / (12 * duration_years)) - 1}
        rows = [asdict(t) for t in (items if items is not None else [])]
        pd.DataFrame(rows, columns=TRADE_COLUMNS if rows else None).to_csv(
            out_dir / f"{label}_trades.csv", index=False)
    scenarios["execution_stress"]["diagnostics"] = diagnostic
    return scenarios, trades


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--smoke", action="store_true")
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Chon output moi; khong ghi de lich su")
    torch.set_num_threads(2)
    torch.manual_seed(1729)
    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    decisions = pd.read_parquet(root / cfg["decisions"])
    candles = pd.read_parquet(root / cfg["candles"])
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text(encoding="utf-8"))
    parent = json.loads((root / cfg["parent_plan"]).read_text(encoding="utf-8"))
    with np.load(root / cfg["examples"]) as z:
        base40 = z["features"].astype(np.float64)
    assert len(decisions) == len(base40) == 5628
    assert decisions.signal_time.is_monotonic_increasing and not decisions.signal_time.duplicated().any()
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")

    t0 = time.perf_counter()
    ret48, up48, dn48 = build_labels(decisions, candles)
    band = cfg["architecture"]["heads"]["direction"]["wait_band_bps"] / 1e4
    ydir = np.select([ret48 < -band, ret48 > band], [0, 2], default=1)
    X = np.concatenate([base40, derived_calendar(decisions["signal_time"])], -1)
    assert X.shape == (5628, 44)
    print(json.dumps({"label_balance": {k: int((ydir == v).sum()) for k, v in
                                        (("SHORT", 0), ("WAIT", 1), ("LONG", 2))},
                      "ret48_mean": round(float(ret48.mean()), 6),
                      "up_mean": round(float(up48.mean()), 6),
                      "dn_mean": round(float(dn48.mean()), 6)}), flush=True)

    months = pd.date_range("2023-06-01", "2026-03-01", freq="MS", tz="UTC")
    assert len(months) == 34
    if a.smoke:
        months = months[-3:]
        epochs, patience = cfg["model"]["epochs_smoke"], cfg["model"]["patience_smoke"]
        mode = "SMOKE-3folds-CPU"
    else:
        epochs, patience = cfg["model"]["epochs_full"], cfg["model"]["patience_full"]
        mode = "FULL-34folds"
    oos_mask = (decisions.signal_time >= months[0]).to_numpy()
    oos_idx = np.where(oos_mask)[0]
    part = decisions.iloc[oos_idx].reset_index(drop=True)
    P = np.full((len(oos_idx), 3), np.nan)
    Q = np.full((len(oos_idx), 3), np.nan)
    E = np.full((len(oos_idx), 2), np.nan)
    oos_pos = {idx: i for i, idx in enumerate(oos_idx)}
    prov, facing = [], {"dir_acc": [], "pinball": [], "exc_mse_log1p": []}
    with threadpool_limits(limits=2):
        for fit_at in months:
            label = fit_at.strftime("%Y-%m")
            mask = ((decisions.label_end < fit_at - pd.Timedelta(days=8))
                    & (decisions.signal_time >= fit_at - pd.Timedelta(days=730))).to_numpy()
            if mask.sum() < 200:
                raise ValueError(f"Thieu mature train decisions tai {label}: {mask.sum()}")
            net, mu, sd, vl = fit_fold(X[mask], ydir[mask], ret48[mask], up48[mask], dn48[mask],
                                       cfg["model"], cfg["seeds"][0], epochs, patience,
                                       cfg["model"]["batch_size"])
            sel = (decisions.signal_time.dt.strftime("%Y-%m").to_numpy() == label) & oos_mask
            sel_idx = np.where(sel)[0]
            if len(sel_idx) == 0:
                continue
            if (decisions.signal_time.iloc[sel_idx] < fit_at).any():
                raise ValueError("Du bao truoc fitting clock")
            prob, qret, exc = predict_fold(net, mu, sd, X[sel_idx])
            rows = np.array([oos_pos[i] for i in sel_idx])
            P[rows], Q[rows], E[rows] = prob, qret, exc
            acc = float((prob.argmax(1) == ydir[sel_idx]).mean())
            e = ret48[sel_idx, None] - qret
            qq = np.array(QUANTS)[None, :]
            pb = float(np.maximum(qq * e, (qq - 1) * e).mean())
            em = float(np.mean((np.log1p(exc) - np.log1p(np.stack(
                [up48[sel_idx], dn48[sel_idx]], -1))) ** 2))
            facing["dir_acc"].append(acc)
            facing["pinball"].append(pb)
            facing["exc_mse_log1p"].append(em)
            prov.append({"fit_at": str(fit_at), "train_decisions": int(mask.sum()),
                         "eval_decisions": int(len(sel_idx)), "val_loss": round(vl, 6),
                         "dir_acc": round(acc, 4), "pinball": round(pb, 6)})
            print(json.dumps({"month": label, "train": int(mask.sum()),
                              "eval": int(len(sel_idx)), "acc": round(acc, 4)}), flush=True)
    if not (np.isfinite(P).all() and np.isfinite(Q).all() and np.isfinite(E).all()):
        raise ValueError("Thieu du bao OOS")
    np.save(a.output / "oos_prob.npy", P)
    np.save(a.output / "oos_quantile.npy", Q)
    np.save(a.output / "oos_excursion.npy", E)
    facing_mean = {k: round(float(np.mean(v)), 6) for k, v in facing.items()}
    print(json.dumps({"facing_OOS_mean": facing_mean, "mode": mode}), flush=True)

    costs = CostModel(**ds_cfg["costs"])
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400)) if not a.smoke else (
        (part.signal_time.max() - part.signal_time.min()).total_seconds() / (365.2425 * 86400))
    cap = int(max(ds_cfg["holding_days"]) * BARS_PER_DAY)
    gate = cfg.get("gate", {"monthly_geometric_net_min": 0.05, "drawdown_max": 0.2, "fills_min": 30})
    results = {}
    for branch in ("mt_p10gate", "mt_p50gate"):
        sig_base = gen_signals(part, P, Q, branch, cfg, ds_cfg)
        print(json.dumps({"branch": branch, "n_signals": int(len(sig_base))}), flush=True)
        ref_trades = []
        for sizing in ("1x", "dd_guard"):
            name = f"{branch}_{sizing}"
            bdir = a.output / name
            bdir.mkdir()
            if sizing == "1x":
                sig = sig_base.drop(columns=["leverage"], errors="ignore")
                execution = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                            max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
            else:
                execution = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                            max_holding_bars=cap, leverage=0.25, max_leverage=1.0)
                sig = sig_base.copy()
                sig["leverage"] = dd_guard_leverage(sig_base, ref_trades) if len(sig_base) else np.array([], dtype=float)
            sig.to_parquet(bdir / "signals.parquet", index=False)
            scenarios, trades = run_branch(candles, sig, costs, execution, duration, bdir)
            if sizing == "1x":
                ref_trades = trades
            results[name] = scenarios
            print(json.dumps({"branch": name, "metrics": {
                s: {k: scenarios[s][k] for k in ["total_return", "max_drawdown", "trades",
                                                 "monthly_geometric_net", "gross_pnl", "fees",
                                                 "funding", "profit_factor", "win_rate"]}
                for s in ("normal", "fee_stress", "execution_stress")}}, default=str), flush=True)
    for branch, scenarios in results.items():
        for scen, m in scenarios.items():
            if scen not in ("normal", "fee_stress", "execution_stress"):
                continue
            try:
                mp = bool(m["monthly_geometric_net"] >= gate["monthly_geometric_net_min"])
                dp = bool(m["max_drawdown"] >= -abs(gate["drawdown_max"]))
                fp = bool(m["trades"] >= gate["fills_min"])
            except (KeyError, TypeError):
                continue
            m["gate"] = {"monthly_ge_5pct": mp, "dd_within_20pct": dp,
                         "fills_ge_30": fp, "pass_all": bool(mp and dp and fp)}
    report = {"experiment": "opencode-v26-multitask", "mode": mode,
              "architecture": cfg["architecture"], "policy_branches": cfg["policy_branches"],
              "folds": prov, "facing_OOS_mean": facing_mean,
              "branches": results, "duration_years": duration,
              "standing_best_anchor": cfg["standing_best_anchor"],
              "smoke_warning": ("SMOKE 3 thang: monthly_geometric_net noi suy tu ~3 thang, "
                                "KHONG so sanh truc tiep voi standing_best; cho full Kaggle.")
              if a.smoke else "FULL 34 folds walk-forward.",
              "wall_s": round(time.perf_counter() - t0, 1),
              "independent_test": False, "live_approved": False, "exploratory": True,
              "input_sha256": {"decisions": sha256(root / cfg["decisions"]),
                               "candles": sha256(root / cfg["candles"]),
                               "dataset_config": sha256(root / cfg["dataset_config"]),
                               "parent_plan": sha256(root / cfg["parent_plan"]),
                               "examples": sha256(root / cfg["examples"])},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("WROTE", str(a.output / "summary.json"))
