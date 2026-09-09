"""Opencode R56-A A2-ARCH: audit harness for round56 regime + maelabels (v147 pre-spec).

Pre-spec: configs/opencode_v147_harness.json (viet TRUOC khi outputs land).
Chay NAY la smoke-plumbing only: DRY-RUN tren v41 smoke predictions
(artifacts/research/opencode_v91_v41/smoke/... (64,16,6) = test[:64]/validation[:64])
lam stand-in cho CA HAI models de chung minh MOT harness chay end-to-end
cho tung model. So lieu smoke-harness la PLUMBING, KHONG phai ket qua
nghien cuu, KHONG ket luan ve regime/maelabels, KHONG so standing_best.

Full audit sau (khi cloud COMPLETE tung model): cung script, --source tro toi
download dir 33 folds (seed*/temporal_neural/fold_*/predictions.npy).
Checklist per-model o config audit_checklist_on_complete_per_model.

Format expected (v35/v41 conventions, (n,16,6) map-v8 RAW TRADEABLE percent):
  predictions.npy (n_test,16,6) + val_predictions.npy (n_val,16,6) +
  indices.npz{train,validation,test} + value_scale.json + metadata + replay.npz.
Fallback reader (ghi nhan read_branch): (n,16,6) standard [A]; ranklist (n,16)
+ map-v8 [B]; logits (n,16) student-style [C]; regime sidecar diagnostic [D].
Policy VERBATIM v91b: exp=ch0*sigmoid(ch4); gate en_best>0 + top-8 fallback;
deterministic_best_index eps=1e-6 fill-desc holding-asc. Branches per model:
{model}-1x + {model}-dd_guard (conditional). Scenarios: normal (fee 0.0002) +
fee_stress (0.00055) + execution_stress FillStress(5,5,5,0.00055,False).
Gate: monthly>=5%, DD<20%, fills>=30.

Rules: no live; never touch registry/CONTINUOUS_RESEARCH/NEXT_AGENT/rounds/
Kronos/worktrees; no register/commit/push; no overwrites; causal; exploratory;
inference plumbing only (no training).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)
import argparse
import hashlib
import json
import sys
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.swing import grid  # noqa: E402
from agentic_alpha_lab.data.swing import prices as swing_prices  # noqa: E402

try:
    from opencode_r30m_v41_model import deterministic_best_index as _dbi_v41  # noqa: E402
    _DBI_SOURCE = "opencode_r30m_v41_model.deterministic_best_index"
    _DBI_EPS = 1e-6
    _probe = np.zeros((16, 6), dtype=np.float64)
    _probe[:, 5] = 3.0
    assert int(_dbi_v41(np.zeros(16), np.zeros(16), _probe)) == 0
    deterministic_best_index = _dbi_v41
except Exception as exc:  # fallback inline (ghi nhan)
    _DBI_SOURCE = f"inline-fallback (v41 import failed: {type(exc).__name__})"

    def deterministic_best_index(expected_row, fill_row, candidates, eps=1e-6):  # noqa: F811
        exp = np.asarray(expected_row, dtype=np.float64).reshape(-1)
        fil = np.asarray(fill_row, dtype=np.float64).reshape(-1)
        cand = np.asarray(candidates)
        if exp.shape[0] != 16 or fil.shape[0] != 16 or cand.shape != (16, 6):
            raise ValueError("Tie-break expects (16,) expected/fill + (16,6) candidates")
        if not float(eps) == 1e-6:
            raise ValueError("tie_break_eps phai 1e-6")
        m = float(np.max(exp))
        tied = np.flatnonzero((m - exp) < float(eps))
        if len(tied) == 1:
            return int(tied[0])
        fmax = float(np.max(fil[tied]))
        tied_f = tied[(fil[tied] >= fmax - 1e-9)]
        if len(tied_f) == 1:
            return int(tied_f[0])
        holdings = cand[tied_f, 5].astype(np.float64)
        hmin = float(np.min(holdings))
        tied_h = tied_f[holdings <= hmin + 1e-12]
        return int(np.min(tied_h))

try:
    from agentic_alpha_lab.models.ensemble_value import combine as _combine  # noqa: E402
    _COMBINE_SOURCE = "agentic_alpha_lab.models.ensemble_value.combine"
except Exception as exc:
    _COMBINE_SOURCE = f"np.mean-fallback (combine import failed: {type(exc).__name__})"
    _combine = None

SPEC_PATH = ROOT / "configs/opencode_v147_harness.json"
POLICY_MARGIN = 0.0  # pre-spec v91b: zero-margin tren unconditional percent
POLICY_N_MIN = 8  # pre-spec v91b: N_MIN_PER_FOLD_TEST
TOPK = 408
RTOL, ATOL = 1e-4, 1e-4  # train-driver parity spec
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def qstats(x):
    x = np.asarray(x, dtype=np.float64)
    return {"mean": float(x.mean()), "std": float(x.std()), "min": float(x.min()),
            "p10": float(np.quantile(x, 0.10)), "p50": float(np.quantile(x, 0.50)),
            "p90": float(np.quantile(x, 0.90)), "p95": float(np.quantile(x, 0.95)),
            "p99": float(np.quantile(x, 0.99)), "max": float(x.max())}


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(np.asarray(x, dtype=np.float64), -40, 40)))


def rank_corr_per_decision(net, tgt):
    a = pd.DataFrame(net).rank(axis=1).to_numpy()
    b = pd.DataFrame(tgt).rank(axis=1).to_numpy()
    a -= a.mean(1, keepdims=True)
    b -= b.mean(1, keepdims=True)
    den = np.sqrt((a * a).sum(1) * (b * b).sum(1))
    valid = den > 0
    out = np.full(net.shape[0], np.nan)
    out[valid] = (a * b).sum(1)[valid] / den[valid]
    return out


def detect_source(source):
    """Phan biet full cloud download vs smoke-sample stand-in."""
    full = sorted(source.glob("seed*/temporal_neural/fold_*/predictions.npy"))
    smoke = sorted(source.glob("seed*/fold_*/predictions_sample.npy"))
    if full and not smoke:
        return "full", full
    if smoke and not full:
        return "smoke-sample", smoke
    if full and smoke:
        raise ValueError("Source lan lon full + smoke-sample; tach rieng")
    raise FileNotFoundError(f"Khong thay predictions nao duoi {source}")


def read_predictions_fallback(path, val_path=None):
    """Doc export thuc te theo bang fallback (config export_fallback_reader).

    Tra ve dict {read_branch, exp (n,16) unconditional, fill_logits (n,16),
    raw_shape, assumption}. Branch A: (n,16,6) standard. Branch C: (n,16)
    logits-style. Unknown -> raise (khong doan mo).
    """
    arr = np.load(path, allow_pickle=False)
    if not np.isfinite(arr).all():
        raise ValueError(f"Nonfinite predictions {path}")
    if arr.ndim == 3 and arr.shape[1:] == (16, 6):
        fill_logits = np.asarray(arr[..., 4], dtype=np.float64)
        exp = np.asarray(arr[..., 0], dtype=np.float64) * sigmoid(fill_logits)
        return {"read_branch": "A-standard-v41",
                "assumption": "(n,16,6) map-v8 RAW: exp=ch0*sigmoid(ch4), fill=ch4",
                "exp": exp, "fill_logits": fill_logits,
                "raw_shape": list(arr.shape)}
    if arr.ndim == 2 and arr.shape[1] == 16:
        exp = np.asarray(arr, dtype=np.float64)
        return {"read_branch": "C-logits-alt",
                "assumption": "(n,16) free units: exp=array truc tiep, fill=zeros "
                              "(tie-break roi ve holding-asc/index-min); bias lens khac don vi",
                "exp": exp, "fill_logits": np.zeros_like(exp),
                "raw_shape": list(arr.shape)}
    raise ValueError(f"Unknown predictions shape {arr.shape} o {path}: "
                     "mo rong reader theo export_spec thuc te, khong doan mo")


def build_signals(exp_mat, fill_logits, cand_grid, fold_of, part, cfg):
    """Policy VERBATIM v91b: gate en_best>0 + fallback top-8/fold-test."""
    exp_mat = np.asarray(exp_mat, dtype=np.float64)
    fill_logits = np.asarray(fill_logits, dtype=np.float64)
    n = len(part)
    if exp_mat.shape != (n, 16) or fill_logits.shape != (n, 16):
        raise ValueError("expected/fill shape mismatch")
    if len(fold_of) != n:
        raise ValueError("fold index mismatch")
    if not np.isfinite(exp_mat).all() or not np.isfinite(fill_logits).all():
        raise ValueError("Nonfinite policy inputs")
    en_best = exp_mat.max(1)
    selected = set()
    gate_hits, fallback_adds = {}, {}
    for f in sorted(set(np.asarray(fold_of).tolist())):
        idx = np.flatnonzero(np.asarray(fold_of) == f)
        gate = idx[en_best[idx] > POLICY_MARGIN]
        gate_hits[str(f)] = int(len(gate))
        if len(gate) >= POLICY_N_MIN:
            selected.update(gate.tolist())
            fallback_adds[str(f)] = 0
        else:
            top = idx[np.argsort(-en_best[idx], kind="stable")[:min(POLICY_N_MIN, len(idx))]]
            selected.update(gate.tolist())
            selected.update(top.tolist())
            fallback_adds[str(f)] = int(len(set(top.tolist()) - set(gate.tolist())))
    policy, signals = cfg["policy"], []
    monthly, next_allowed = Counter(), pd.Timestamp.min.tz_localize("UTC")
    for i, row in enumerate(part.itertuples()):
        if i not in selected:
            continue
        timestamp = pd.Timestamp(row.signal_time)
        month = timestamp.strftime("%Y-%m")
        if timestamp < next_allowed or monthly[month] >= policy["maximum_signals_per_month"]:
            continue
        k = deterministic_best_index(exp_mat[i], fill_logits[i], cand_grid, eps=1e-6)
        sig = swing_prices(float(row.close), float(row.atr5), float(row.atr4),
                           cand_grid[k], cfg)
        signals.append({"bar_index": int(row.bar_index), "signal_time": timestamp,
                        "fold_test": int(fold_of[i]),
                        "action": "LONG" if cand_grid[k, 0] == 1 else "SHORT",
                        "direction": int(cand_grid[k, 0]), "candidate_id": int(k),
                        "entry_limit": float(sig["entry_limit"]),
                        "stop_loss": float(sig["stop_loss"]),
                        "take_profit_1": float(sig["take_profit_1"]),
                        "take_profit_2": float(sig["take_profit_2"]),
                        "holding_bars": int(sig["holding_bars"]),
                        "expected_net_percent": float(exp_mat[i, k]),
                        "en_best": float(en_best[i]),
                        "ohlc_fill_score": float(sigmoid(fill_logits[i, k])),
                        "calibrated": False,
                        "entry_expiry_bars": int(cfg["entry_expiry_bars"]),
                        "tp1_fraction": 0.5})
    frame = pd.DataFrame(signals)
    info = {"gate_hits_by_fold": gate_hits, "fallback_adds_by_fold": fallback_adds,
            "n_selected": len(selected), "n_signals": len(frame),
            "policy_margin": POLICY_MARGIN, "policy_n_min": POLICY_N_MIN,
            "tie_break": "eps 1e-6 fill-desc holding-asc index-min",
            "tie_break_source": _DBI_SOURCE}
    return frame, info, en_best


def dd_guard_leverage(signals, trades):
    equity_at = sorted((pd.Timestamp(t.exit_time), t.equity_after) for t in trades)
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


def sig_info(exp_mat, part, cfg, labels_sub, signals, fold_of):
    exp_mat = np.asarray(exp_mat, dtype=np.float64)
    best = exp_mat.max(axis=1)
    n = len(part)
    pass_net = best > POLICY_MARGIN
    months = signals.signal_time.dt.strftime("%Y-%m").value_counts().sort_index() if len(signals) else {}
    truth = np.asarray(labels_sub, dtype=np.float64)
    take = min(TOPK, n)
    order = np.argsort(best, kind="stable")[-take:]
    k = exp_mat[order].argmax(axis=1)
    pe = exp_mat[order, k]
    rn = truth[order, k, 0]
    per = rank_corr_per_decision(exp_mat, truth[:, :, 0])
    valid = per[~np.isnan(per)]
    return {
        "score_distribution": {f"en_best_{kk}": vv for kk, vv in qstats(best).items()},
        "threshold_pass_0": {"pass_n": int(pass_net.sum()),
                             "pass_rate": float(pass_net.mean())},
        "n_decisions": int(n), "n_signals": int(len(signals)),
        "coverage": float(len(signals) / n) if n else 0.0,
        "directions": {str(kk): int(vv) for kk, vv in signals.direction.value_counts().items()}
        if len(signals) and "direction" in signals else {},
        "candidates": {str(kk): int(vv) for kk, vv in signals.candidate_id.value_counts().items()}
        if len(signals) and "candidate_id" in signals else {},
        "holdings": {str(kk): int(vv) for kk, vv in signals.holding_bars.value_counts().items()}
        if len(signals) and "holding_bars" in signals else {},
        "active_months": int(len(months)),
        "first_signal": str(signals.signal_time.min()) if len(signals) else None,
        "last_signal": str(signals.signal_time.max()) if len(signals) else None,
        "by_month": {str(kk): int(vv) for kk, vv in months.items()} if len(signals) else {},
        "topdecile": {"n": int(take), "pred_exp_mean": float(pe.mean()),
                      "obs_net_mean": float(rn.mean()),
                      "bias_note": "map-v8: cung don vi percent; logits-alt: RECORD only"},
        "rank_overall": {"n": int(n), "n_valid": int(len(valid)),
                         "rank_corr_mean": float(valid.mean()) if len(valid) else None,
                         "rank_corr_std": float(valid.std()) if len(valid) else None},
    }


def gate_flags(d, gate):
    try:
        m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
        dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
        f_ok = bool(d["trades"] >= gate["fills_min"])
    except (KeyError, TypeError):
        m_ok = dd_ok = f_ok = False
    return {"monthly_geometric_net_ge_5pct": m_ok, "drawdown_within_20pct": dd_ok,
            "fills_ge_30": f_ok, "pass_all": bool(m_ok and dd_ok and f_ok)}


def run_one_model(model, source, out_root, ds, cfg, parent, candles, decisions,
                  labels_all, years, costs, exec1x, cap, mode, pred_files, gate):
    """Chay full skeleton cho 1 model; tra ve (results, diagnostics, audit)."""
    mdir = out_root / model
    mdir.mkdir()
    b1 = f"{model}-1x"
    replay_records, read_branches = [], []
    if mode == "full":
        raise NotImplementedError(
            "Full-mode skeleton: chua co cloud outputs (round56 models BUILDING). "
            "Khi COMPLETE: lap seed*/temporal_neural/fold_*/predictions.npy + "
            "val_predictions.npy + indices.npz theo export_spec thuc te cua train script, "
            "stack (3,n,16,6) -> combine mean -> policy/moi duoi. Ghi nhan read_branch.")
    # smoke-sample: moi file = 1 fold sample (test[:64]); lap lai cho tung model
    # (cung stand-in, tag rieng per model) de chung minh harness chay per-model.
    assert len(pred_files) >= 1, "smoke expect >=1 sample file"
    sfile = pred_files[0]
    fold = int(sfile.parts[-2].replace("fold_", ""))
    seed = int(sfile.parts[-3].replace("seed", ""))
    ckpt_dir = sfile.parent
    with np.load(ckpt_dir / "indices.npz", allow_pickle=False) as ix:
        train, validation, test = ix["train"], ix["validation"], ix["test"]
    read = read_predictions_fallback(sfile)
    read_branches.append({"file": sfile.name, "shape": read["raw_shape"],
                          "read_branch": read["read_branch"],
                          "assumption": read["assumption"],
                          "sha256": sha(sfile)})
    assert read["exp"].shape == (64, 16), f"smoke sample shape changed: {read['exp'].shape}"
    vfile = ckpt_dir / "val_predictions_sample.npy"
    val = np.load(vfile, allow_pickle=False)
    assert val.shape == (64, 16, 6) and np.isfinite(val).all()
    replay_records.append({"seed": seed, "fold": fold, "decisions": 64,
                           "read_branch": read["read_branch"],
                           "weight_reload": "STUB-smoke (64-row sample; full reload deferred to COMPLETE)",
                           "val_rows": 64, "val_finite": True,
                           "note": "smoke-sample test[:64]; PLUMBING ONLY"})
    print(json.dumps({"model": model, "replay": replay_records[-1]}), flush=True)
    indices = test[:64]
    fold_of = np.full(64, fold, dtype=np.int64)
    ensemble_exp, ensemble_fill = read["exp"], read["fill_logits"]
    part = decisions.iloc[indices].reset_index(drop=True)
    labsub = labels_all[indices]

    cand_grid = np.asarray(grid(cfg), dtype=np.float64)
    if cand_grid.shape != (16, 6):
        raise ValueError("Unsupported candidate schema")

    # ---- Policy parity: double-compute bit-identical ----
    sig_a, info_a, _ = build_signals(ensemble_exp, ensemble_fill, cand_grid, fold_of, part, cfg)
    sig_b, _, _ = build_signals(ensemble_exp, ensemble_fill, cand_grid, fold_of, part, cfg)
    pd.testing.assert_frame_equal(sig_a.reset_index(drop=True), sig_b.reset_index(drop=True))
    policy_parity = {"compared": "double-compute signals bit-identical",
                     "pass": True, "tie_break_source": _DBI_SOURCE}
    print(json.dumps({"model": model, "branch_signals": b1,
                      "n_signals": int(len(sig_a)),
                      "coverage": float(len(sig_a) / len(part)) if len(part) else 0.0,
                      "policy_info": info_a}), flush=True)

    results, diagnostics = {}, {}
    empty_template = pd.DataFrame(columns=["bar_index", "direction", "signal_time"])
    exec_sig = sig_a.copy() if len(sig_a) else empty_template.copy()
    scen, trades = run_branch(candles, exec_sig, costs, exec1x, years)
    bdir = mdir / b1
    bdir.mkdir()
    sig_a.to_parquet(bdir / "signals.parquet", index=False)
    np.savez_compressed(bdir / "exp.npz", exp=np.asarray(ensemble_exp, dtype=np.float32),
                        fill_logits=np.asarray(ensemble_fill, dtype=np.float32),
                        decision_indices=np.asarray(indices))
    branch_metrics = {}
    for label in ("normal", "fee_stress", "execution_stress"):
        rows = scen[label].pop("_trades_rows")
        d = {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
             for k, v in scen[label].items() if k != "diagnostics"}
        if label == "execution_stress":
            d["diagnostics"] = scen[label].get("diagnostics")
        d["gate"] = gate_flags(d, gate)
        branch_metrics[label] = d
        if rows:
            pd.DataFrame(rows, columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
        else:
            pd.DataFrame(columns=TRADE_COLUMNS).to_csv(bdir / f"{label}_trades.csv", index=False)
        (bdir / f"{label}_metrics.json").write_text(json.dumps(d, indent=2, default=str))
    results[b1] = branch_metrics
    diagnostics[b1] = sig_info(ensemble_exp, part, cfg, labsub, sig_a, fold_of)
    diagnostics[b1]["policy_info"] = info_a
    (bdir / "diagnostics.json").write_text(json.dumps(diagnostics[b1], indent=2, default=str))
    print(json.dumps({"model": model, "branch": b1, "signals": int(len(sig_a)),
                      "metrics": {s: {k: branch_metrics[s][k] for k in
                                      ("total_return", "max_drawdown", "trades",
                                       "monthly_geometric_net", "gross_pnl", "fees",
                                       "funding", "profit_factor", "win_rate")}
                                  for s in ("normal", "fee_stress", "execution_stress")},
                      "gate": {s: branch_metrics[s]["gate"] for s in
                               ("normal", "fee_stress", "execution_stress")}}, default=str), flush=True)

    # ---- dd_guard conditional ----
    b2 = f"{model}-dd_guard"
    dd_info = {"ran": False, "reason": "", "branch": b2}
    if len(sig_a) == 0:
        dd_info = {"ran": False, "reason": "0 signals; skip dd_guard",
                   "branch": b2, "best": b1}
        (mdir / f"{b2}_SKIPPED.json").write_text(json.dumps(dd_info, indent=2))
    else:
        guard = dd_guard_leverage(sig_a, trades)
        gsig = sig_a.copy()
        gsig["leverage"] = guard
        execdd = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                                 max_holding_bars=cap, leverage=0.5, max_leverage=1.0)
        scen_dd, _ = run_branch(candles, gsig, costs, execdd, years)
        bdir_dd = mdir / b2
        bdir_dd.mkdir()
        gsig.to_parquet(bdir_dd / "signals.parquet", index=False)
        dd_metrics = {}
        for label in ("normal", "fee_stress", "execution_stress"):
            rows = scen_dd[label].pop("_trades_rows")
            d = {k: v for k, v in scen_dd[label].items() if k != "diagnostics"}
            if label == "execution_stress":
                d["diagnostics"] = scen_dd[label].get("diagnostics")
            d["gate"] = gate_flags(d, gate)
            dd_metrics[label] = d
            pd.DataFrame(rows, columns=TRADE_COLUMNS if rows else None).to_csv(
                bdir_dd / f"{label}_trades.csv", index=False)
            (bdir_dd / f"{label}_metrics.json").write_text(json.dumps(d, indent=2, default=str))
        results[b2] = dd_metrics
        diagnostics[b2] = deepcopy(diagnostics[b1])
        diagnostics[b2]["dd_guard"] = {
            "reference": f"{b1} own-book 1x (trigger 10%, lev 0.5/1.0, past-only)",
            "n_guarded": int((guard == 0.5).sum()),
            "guard_fraction": float((guard == 0.5).mean()) if len(guard) else 0.0}
        (bdir_dd / "diagnostics.json").write_text(json.dumps(diagnostics[b2], indent=2, default=str))
        dd_info = {"ran": True, "branch": b2, "best": b1,
                   "n_guarded": int((guard == 0.5).sum()),
                   "guard_fraction": float((guard == 0.5).mean()) if len(guard) else 0.0}
    print(json.dumps({"model": model, "dd_guard": dd_info}), flush=True)

    audit = {"model": model, "state": "plumbing-pass", "mode": mode,
             "device": "cpu", "torch": torch.__version__,
             "rtol": RTOL, "atol": ATOL, "folds": replay_records,
             "read_branches": read_branches,
             "policy_parity": policy_parity,
             "combine_source": _COMBINE_SOURCE if mode == "full" else "single-sample (no mean)",
             "standin_source": str(source),
             "independent_test": False, "live_approved": False,
             "plumbing_note": "SMOKE numbers are plumbing-only, NOT research"}
    (mdir / "audit.json").write_text(json.dumps(audit, indent=2, default=str))
    return results, diagnostics, dd_info, audit


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True,
                   help="cloud download dir (33 folds) hoac smoke dir (stand-in)")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    p.add_argument("--models", default="regime,maelabels",
                   help="comma-separated subset of {regime,maelabels}")
    a = p.parse_args()
    spec = json.loads(Path(a.config).read_text(encoding="utf-8"))
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    assert set(models) <= {"regime", "maelabels"} and models, "models phai trong {regime,maelabels}"
    assert spec["policy_branches_per_model"]["branch_names"] == ["{model}-1x", "{model}-dd_guard"]
    assert spec["gate"] == {"monthly_geometric_net_min": 0.05, "drawdown_max": 0.2, "fills_min": 30}
    if a.output.exists():
        raise FileExistsError("Khong ghi de lich su; chon output dir moi")
    mode, pred_files = detect_source(a.source)
    print(json.dumps({"harness_mode": mode, "n_pred_files": len(pred_files),
                      "models": models,
                      "warning": "SMOKE-PLUMBING ONLY" if mode.startswith("smoke") else "FULL AUDIT"}),
          flush=True)
    parent = json.loads((ROOT / "configs/swing_v15_continuous_folds.json").read_text(encoding="utf-8"))
    ds = ROOT / "data/processed/swing_regime_research_v4"
    cfg = json.loads((ds / "config.json").read_text(encoding="utf-8"))
    decisions = pd.read_parquet(ds / "decisions.parquet")
    candles = pd.read_parquet(ds / "candles.parquet")
    with np.load(ds / "examples.npz", allow_pickle=False) as z:
        labels_all = z["labels"]
    assert labels_all.shape == (len(decisions), 16, 3)
    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    costs = CostModel(**cfg["costs"])
    cap = int(max(cfg["holding_days"]) * 288)
    assert cap == 2016, "holding cap"
    exec1x = ExecutionConfig(entry_expiry_bars=int(cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    gate = {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30}

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(spec, indent=2))
    all_results, all_diag, all_dd, audits = {}, {}, {}, {}
    for model in models:
        res, diag, dd, audit = run_one_model(
            model, a.source, a.output, ds, cfg, parent, candles, decisions,
            labels_all, years, costs, exec1x, cap, mode, pred_files, gate)
        all_results[model] = res
        all_diag[model] = diag
        all_dd[model] = dd
        audits[model] = audit

    summary = {"experiment": spec["experiment"], "mode": mode, "models": models,
               "branches": all_results, "diagnostic_lens": all_diag,
               "dd_guard": all_dd, "duration_years": years, "gate": gate,
               "formulas": {"monthly_geometric_net": spec["execution"]["monthly_formula"],
                            "fee_stress": "fee_rate_per_fill=0.00055",
                            "execution_stress": "FillStress(5,5,5,0.00055,False)",
                            "dd_guard": "own-book 1x trigger 10% lev 0.5/1.0 past-only",
                            "policy_exp": "exp=ch0*sigmoid(ch4) unconditional percent (map-v8); fallback C: logits truc tiep"},
               "standing_best_anchor": spec["standing_best_anchor"],
               "standing_best_compared": False,
               "audit_checklist": spec["audit_checklist_on_complete_per_model"],
               "independent_test": False, "exploratory": True, "live_approved": False,
               "causality": "past-only closed-candle; train/val past-only embargo 8d; labels exploratory",
               "sources": {"tie_break": _DBI_SOURCE, "combine": _COMBINE_SOURCE},
               "warning": ("SMOKE-PLUMBING ONLY. Playback tren 64 sample rows fold_0 seed1729 "
                           "(v41 stand-in cho CA HAI models). KHONG phai ket qua nghien cuu; "
                           "KHONG ket luan ve regime/maelabels; KHONG so voi standing_best. "
                           "Drawdown trade-candle-close sampled. Stop/timeout market-like o "
                           "scenario fee. Khong live approval.")
               if mode.startswith("smoke") else
               "Opened development interval only. Labels exploratory. "
               "Drawdown trade-candle-close sampled. Stop/timeout market-like. Khong live approval."}
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    def fsha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    out_hashes = {}
    for q in sorted(a.output.rglob("*")):
        if q.is_file() and q.name != "summary.json":
            out_hashes[q.relative_to(a.output).as_posix()] = fsha(q)
    rep = json.loads((a.output / "summary.json").read_text(encoding="utf-8"))
    rep["output_sha256"] = out_hashes
    (a.output / "summary.json").write_text(json.dumps(rep, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"), flush=True)


if __name__ == "__main__":
    main()
