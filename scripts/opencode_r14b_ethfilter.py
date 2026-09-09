"""Opencode v46 (R14-B, dispatch 2): ETH cross-asset filter tren majority_1x dong bang.

Pre-spec: configs/opencode_v46_ethfilter.json (viet TRUOC khi chay).
Dau vao dong bang: artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet
  (94 tin hieu) + data/raw/opencode_eth_6h_20260907/eth_ETHUSDT_6h.parquet (4104 bars
  6h, 0 gap) + data/processed/swing_regime_research_v4/{candles.parquet,config.json}.
Dac trung causal (chi ETH bar close_time <= signal_time, bar dang-forming LOAI):
  eth_trend_rel, eth_ret30d, btc_ret30d (+2 dau dan xuat eth_trend_sign, btc_eth_agree).
Loc: {control, eth_trend_agree, eth_up_only, mom_agree} x sizing {1x, dd_guard} = 8 nhanh.
  Guard tham chieu equity control_1x CUA CHINH NHANH NAY (qua khu, 1-microsecond).
Cong control: control_1x normal == majority_1x xuat ban (+165.18%/-20.09%/63) neu khong STOP.
Scenarios: normal / fee 0.00055 / FillStress(5,5,5,.00055,False). Headline Normal.
Monthly geometric theo configs/swing_v15_continuous_folds.json.
Nhan exploratory, causal past-only, local only, khong live.
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402

SPEC_PATH = ROOT / "configs/opencode_v46_ethfilter.json"
EXPECTED_BRANCHES = ["control_1x", "control_dd_guard",
                     "eth_trend_agree_1x", "eth_trend_agree_dd_guard",
                     "eth_up_only_1x", "eth_up_only_dd_guard",
                     "mom_agree_1x", "mom_agree_dd_guard"]
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]
BARS_PER_DAY = 288
LOOKBACK_30D_BARS = 120  # 120 x 6h = 30d


def build_features(sig, eth, btc_close_time, btc_close):
    """Gan dac trung ETH causal vao tung tin hieu BTC (chi bar close_time<=S)."""
    eth_ct = pd.to_datetime(eth["close_time"], utc=True).to_numpy(dtype="datetime64[ns]")
    eth_cl = eth["close"].to_numpy(dtype=float)
    btc_ct = pd.to_datetime(pd.Series(btc_close_time), utc=True).to_numpy(dtype="datetime64[ns]")
    sig_ts = pd.to_datetime(sig["signal_time"], utc=True).to_numpy(dtype="datetime64[ns]")
    j = np.searchsorted(eth_ct, sig_ts, side="right") - 1
    assert bool((j >= LOOKBACK_30D_BARS).all()), "thieu lich su 30d cho tin hieu"
    ref_ct = eth_ct[j]
    assert bool((ref_ct <= sig_ts).all()), "vi pham nhan qua ETH"
    # Bar ke tiep (dang-forming tai S) bi loai: kiem tra ref+1 co close_time > S.
    assert bool((eth_ct[np.minimum(j + 1, len(eth) - 1)] > sig_ts).all()), "loi loai forming-bar"
    close_now = eth_cl[j]
    ma20 = np.array([eth_cl[k - 19:k + 1].mean() for k in j])
    eth_trend_rel = (close_now - ma20) / ma20
    eth_ret30d = close_now / eth_cl[j - LOOKBACK_30D_BARS] - 1.0
    # BTC lay mau tai ref_close_time (<=S, causal) va ref-30d.
    anchor = ref_ct
    ib_now = np.searchsorted(btc_ct, anchor, side="right") - 1
    ib_then = np.searchsorted(btc_ct,
                              anchor - np.timedelta64(30, "D"), side="right") - 1
    assert bool((ib_now >= 0).all()) and bool((ib_then >= 0).all()), "thieu nen BTC"
    btc_now, btc_then = btc_close[ib_now], btc_close[ib_then]
    assert bool((btc_ct[ib_now] <= anchor).all())
    assert bool((btc_ct[ib_then] <= anchor - np.timedelta64(30, "D")).all())
    btc_ret30d = btc_now / btc_then - 1.0
    out = sig.copy().reset_index(drop=True)
    out["eth_ref_close_time"] = pd.to_datetime(ref_ct, utc=True)
    out["eth_close"] = close_now
    out["eth_ma20"] = ma20
    out["eth_trend_rel"] = eth_trend_rel
    out["eth_trend_sign"] = np.sign(eth_trend_rel).astype(int)
    out["eth_ret30d"] = eth_ret30d
    out["btc_ret30d"] = btc_ret30d
    out["btc_eth_agree"] = ((np.sign(eth_ret30d) == np.sign(btc_ret30d))
                            & (eth_ret30d != 0) & (btc_ret30d != 0)).astype(int)
    out["eth_lag_hours"] = ((sig_ts - ref_ct) / np.timedelta64(1, "h")).astype(float)
    assert bool(out[["eth_trend_rel", "eth_ret30d", "btc_ret30d"]].notna().all().all())
    assert bool(np.isfinite(out[["eth_trend_rel", "eth_ret30d", "btc_ret30d"]].to_numpy()).all())
    return out


def loc_theo_nhanh(df, loc):
    if loc == "control":
        return df.copy().reset_index(drop=True)
    if loc == "eth_trend_agree":
        return df[df["eth_trend_sign"] == df["direction"]].copy().reset_index(drop=True)
    if loc == "eth_up_only":
        return df[df["eth_trend_sign"] > 0].copy().reset_index(drop=True)
    if loc == "mom_agree":
        return df[df["btc_eth_agree"] == 1].copy().reset_index(drop=True)
    raise ValueError(f"loc la {loc}")


def dd_guard_leverage(signals, ref_trades):
    """Guard tu equity control_1x CUA NHANH NAY; past-only 1-microsecond, seed 100."""
    equity_at = sorted((pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades)
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in pd.to_datetime(signals["signal_time"], utc=True):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
        peak, level = float(curve.cummax().iloc[-1]), float(curve.iloc[-1])
        out.append(0.5 if level / peak < 0.9 else 1.0)
    return np.array(out, dtype=float)


def run_branch(candles, signals, costs, execution, years):
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    stress, st, diag = run_stress(candles, signals, 100, costs, execution,
                                  FillStress(5, 5, 5, 0.00055, False))
    out = {}
    for label, res, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                              ("execution_stress", stress, st)):
        ratio = res.final_equity / 100
        out[label] = {**asdict(res),
                      "annual_geometric_net": float(ratio ** (1 / years) - 1),
                      "monthly_geometric_net": float(ratio ** (1 / (12 * years)) - 1)}
        out[label]["_trades_rows"] = [asdict(t) for t in items]
    out["execution_stress"]["diagnostics"] = diag
    return out, trades


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    a = p.parse_args()
    spec = json.loads(Path(a.config).read_text())
    assert list(spec["branches"]) == EXPECTED_BRANCHES, "branches phai pre-spec dung 8 nhanh v46"
    assert list(spec["sizings"]) == ["1x", "dd_guard"]
    assert spec["scenarios"] == ["normal", "fee_stress", "execution_stress"]
    if a.output.exists():
        raise FileExistsError("Khong ghi de lich su; chon output dir moi")
    base = spec["base"]
    ds = ROOT / base["dataset"]
    cfg = json.loads((ds / "config.json").read_text())
    parent = json.loads((ROOT / base["parent_plan"]).read_text())
    candles = pd.read_parquet(ds / "candles.parquet")
    maj = pd.read_parquet(ROOT / base["majority_signals"])
    eth = pd.read_parquet(ROOT / spec["eth_data"]["file"]).sort_values(
        "close_time").reset_index(drop=True)
    assert len(maj) == 94, "majority base phai 94 tin hieu"
    assert set(maj["direction"].unique()) <= {1, -1}

    feat = build_features(maj, eth, candles["close_time"].to_numpy(),
                          candles["close"].to_numpy(dtype=float))
    agree = {
        "n_signals": int(len(feat)),
        "n_long": int((feat["direction"] == 1).sum()),
        "n_short": int((feat["direction"] == -1).sum()),
        "eth_trend_sign": {str(k): int(v) for k, v in
                           feat["eth_trend_sign"].value_counts().items()},
        "trend_agree_rate": float((feat["eth_trend_sign"] == feat["direction"]).mean()),
        "up_only_rate": float((feat["eth_trend_sign"] > 0).mean()),
        "mom_agree_rate": float(feat["btc_eth_agree"].mean()),
        "eth_trend_rel_median": float(feat["eth_trend_rel"].median()),
        "eth_ret30d_median": float(feat["eth_ret30d"].median()),
        "btc_ret30d_median": float(feat["btc_ret30d"].median()),
        "eth_lag_hours_median": float(feat["eth_lag_hours"].median()),
        "eth_lag_hours_max": float(feat["eth_lag_hours"].max()),
        "keep_counts": {},
    }
    sigsets = {}
    for loc in ("control", "eth_trend_agree", "eth_up_only", "mom_agree"):
        sub = loc_theo_nhanh(feat, loc)
        sigsets[loc] = sub
        agree["keep_counts"][loc] = {
            "n": int(len(sub)),
            "n_long": int((sub["direction"] == 1).sum()) if len(sub) else 0,
            "n_short": int((sub["direction"] == -1).sum()) if len(sub) else 0}
    print(json.dumps({"agreement": agree}, default=str), flush=True)

    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * BARS_PER_DAY)
    assert cap == 2016, "holding cap"
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(spec, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())
    feat.to_parquet(a.output / "eth_features.parquet", index=False)
    exec1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    execdd = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=0.25, max_leverage=1.0)

    # ---- CONTROL CHECK (STOP neu lech) ----
    ref = spec["control_reference"]
    ctrl = sigsets["control"].drop(columns=["leverage"], errors="ignore")
    EXEC_COLS = ("bar_index", "direction", "signal_time", "entry_limit", "stop_loss",
                 "take_profit_1", "take_profit_2", "holding_bars",
                 "entry_expiry_bars", "tp1_fraction", "leverage")
    exec_cols = [c for c in EXEC_COLS if c in ctrl.columns]
    res_c, ref_trades = run_backtest(candles, ctrl[exec_cols], 100, costs, exec1x)
    check = {"reproduced": {"total_return": res_c.total_return,
                            "max_drawdown": res_c.max_drawdown,
                            "trades": res_c.trades,
                            "n_signals": int(len(ctrl))},
             "reference": {k: ref[k] for k in ("total_return", "max_drawdown", "trades", "n_signals")},
             "match": bool(abs(res_c.total_return - ref["total_return"]) < ref["tolerance"]
                           and abs(res_c.max_drawdown - ref["max_drawdown"]) < ref["tolerance"]
                           and res_c.trades == ref["trades"]
                           and len(ctrl) == ref["n_signals"])}
    print(json.dumps({"control_check": check}, default=str), flush=True)
    if not check["match"]:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(check, indent=2, default=str))
        print("CONTROL MISMATCH: STOP", flush=True)
        sys.exit(1)

    gate = spec["gate"]
    results, diagnostics, guard_info = {}, {}, {}

    def gate_flags(d):
        try:
            m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
            dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
            f_ok = bool(d["trades"] >= gate["fills_min"])
        except (KeyError, TypeError):
            m_ok = dd_ok = f_ok = False
        return {"monthly_geometric_net_ge_5pct": m_ok, "drawdown_within_20pct": dd_ok,
                "fills_ge_30": f_ok, "pass_all": bool(m_ok and dd_ok and f_ok)}

    for loc, base_sig in sigsets.items():
        for sizing in ("1x", "dd_guard"):
            branch = f"{loc}_{sizing}"
            bdir = a.output / branch
            bdir.mkdir()
            sig = base_sig.copy()
            if sizing == "dd_guard":
                levs = dd_guard_leverage(sig, ref_trades) if len(sig) else np.array([], dtype=float)
                sig["leverage"] = levs
                guard_info[branch] = {"reference": "OWN control_1x equity (this run)",
                                      "n_guarded": int((levs == 0.5).sum()) if len(sig) else 0,
                                      "guard_fraction": float((levs == 0.5).mean()) if len(sig) else 0.0}
                execution = execdd
            else:
                sig = sig.drop(columns=["leverage"], errors="ignore")
                execution = exec1x
            keep = [c for c in EXEC_COLS if c in sig.columns]
            sig.to_parquet(bdir / "signals.parquet", index=False)
            exec_sig = sig[keep].copy() if len(sig) else pd.DataFrame(
                columns=["bar_index", "direction", "signal_time"])
            scen, _ = run_branch(candles, exec_sig, costs, execution, years)
            branch_metrics = {}
            for label in ("normal", "fee_stress", "execution_stress"):
                rows = scen[label].pop("_trades_rows")
                d = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                     for k, v in scen[label].items() if k != "diagnostics"}
                if label == "execution_stress":
                    d["diagnostics"] = scen[label].get("diagnostics")
                d["gate"] = gate_flags(d)
                branch_metrics[label] = d
                if rows:
                    pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
                else:
                    pd.DataFrame(columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
                (bdir / f"{label}_metrics.json").write_text(json.dumps(d, indent=2, default=str))
            results[branch] = branch_metrics
            diagnostics[branch] = {
                "n_signals": int(len(sig)),
                "n_long": int((sig["direction"] == 1).sum()) if len(sig) else 0,
                "n_short": int((sig["direction"] == -1).sum()) if len(sig) else 0,
                "eth_trend_rel_median": float(sig["eth_trend_rel"].median()) if len(sig) else None,
                "mom_agree_rate": float(sig["btc_eth_agree"].mean()) if len(sig) else None,
                "dd_guard": guard_info.get(branch, {"reference": "none (1x)"})}
            print(json.dumps({"branch": branch, "signals": int(len(sig)),
                              "metrics": {s: {k: branch_metrics[s][k] for k in
                                              ("total_return", "max_drawdown", "trades",
                                               "monthly_geometric_net", "gross_pnl", "fees",
                                               "funding", "profit_factor", "win_rate")}
                                          for s in ("normal", "fee_stress", "execution_stress")},
                              "gate": {s: branch_metrics[s]["gate"] for s in
                                       ("normal", "fee_stress", "execution_stress")}}, default=str), flush=True)
    input_files = [base["majority_signals"], spec["eth_data"]["file"],
                   spec["eth_data"]["manifest"], base["candles"],
                   "data/processed/swing_regime_research_v4/config.json",
                   base["parent_plan"], "configs/opencode_v46_ethfilter.json",
                   "scripts/opencode_r14b_ethfilter.py", "scripts/opencode_crawl_eth.py"]
    report = {"experiment": spec["experiment"], "family": spec["family"],
              "hypothesis": spec["hypothesis"], "branches": results,
              "diagnostics": diagnostics, "control_check": check,
              "agreement_eth": agree, "guard_info": guard_info,
              "duration_years": years, "gate": gate,
              "formulas": {"features": spec["features_exactly_3"],
                           "derived_signs": spec["derived_signs"],
                           "causality": spec["causality"],
                           "monthly_geometric_net": spec["monthly_formula"],
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False)",
                           "dd_guard": spec["dd_guard"]["formula"]},
              "config": spec, "independent_test": False, "exploratory": True,
              "live_approved": False,
              "causality": ("past-only closed-candle: ETH ref = last bar close_time<=signal_time, "
                            "forming-bar excluded; BTC sampled at ref_close_time (<=S); guard tu "
                            "strictly-past control exits; fill tu nen ke tiep"),
              "warning": ("Opened development interval 2023-2026 only. Labels exploratory. "
                          "Drawdown trade-candle-close sampled, not true mark/intrabar. "
                          "Stop/timeout market-like o scenario fee. Khong live approval."),
              "input_sha256": {q: sha256(ROOT / q) for q in input_files},
              "output_note": "moi file duoi output dir la moi; khong ghi de lich su"}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))

    def fsha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    out_hashes = {}
    for q in sorted(a.output.rglob("*")):
        if q.is_file() and q.name != "summary.json":
            out_hashes[q.relative_to(a.output).as_posix()] = fsha(q)
    rep2 = json.loads((a.output / "summary.json").read_text())
    rep2["output_sha256"] = out_hashes
    (a.output / "summary.json").write_text(json.dumps(rep2, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
