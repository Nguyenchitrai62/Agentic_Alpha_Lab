"""Opencode v72 (R24-L1-BUILDER): high-recall Layer-1 pool + FIRST-EVER MAE metric.

Pre-spec: configs/opencode_v72_L1pool.json (viet TRUOC khi chay; driver assert).
Frozen sources (set ops only, never refit, causal past-only):
  v38_identity artifacts/research/opencode_v59_v38cal/v38-identity/signals.parquet (135)
  v33_identity artifacts/research/opencode_v42_v33cal/v33-identity/signals.parquet (123)
  majority_1x   artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
Union: dedup by (bar_index, direction), first-seen priority
  v38_identity > v33_identity > majority_1x; conflicts/geo-diffs recorded.
Handoff L2: pool/signals.parquet voi source tags + full score-column union.
Characterize WITHOUT filtering: pool_1x x 3 scenarios
  (normal / fee 0.00055 / FillStress(5,5,5,.00055,False)) + MAE/MFE per filled trade.
Nhan exploratory: khoang 2023-2026 da mo, khong phai kiem dinh doc lap.
Chi backtest local, khong dat lenh live.
"""
import torch  # noqa: F401  (thu tu import: torch truoc pandas tren host nay)
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
sys.path.insert(0, str(ROOT / "scripts"))
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest  # noqa: E402
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress  # noqa: E402
from agentic_alpha_lab.data.training import sha256  # noqa: E402
import opencode_mae  # noqa: E402  (scripts/opencode_mae.py, new cung round)

SPEC_PATH = ROOT / "configs/opencode_v72_L1pool.json"
EXPECTED_BRANCHES = ["pool_1x"]
PRIORITY = ["v38_identity", "v33_identity", "majority_1x"]
TAG_COLS = ["src_v38_identity", "src_v33_identity", "src_majority_1x"]
TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def fsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def gate_flags(d, gate):
    try:
        m_ok = bool(d["monthly_geometric_net"] >= gate["monthly_min"])
        dd_ok = bool(d["max_drawdown"] >= -abs(gate["dd_max"]))
        f_ok = bool(d["trades"] >= gate["fills_min"])
    except (KeyError, TypeError):
        m_ok = dd_ok = f_ok = False
    return {"monthly_geometric_net_ge_5pct": m_ok, "drawdown_within_20pct": dd_ok,
            "fills_ge_30": f_ok, "pass_all": bool(m_ok and dd_ok and f_ok)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=SPEC_PATH)
    a = p.parse_args()
    spec = json.loads(Path(a.config).read_text())
    # --- Pre-spec asserts (config viet TRUOC khi chay) ---
    assert list(spec["branches"]) == EXPECTED_BRANCHES, "branches phai pre-spec ['pool_1x']"
    assert list(spec["sources"]) == PRIORITY, "sources phai pre-spec dung 3 keys"
    assert spec["union_rule"]["first_seen_priority"].startswith("v38_identity"), "uu tien first-seen"
    assert spec["union_rule"]["key"] == ["bar_index", "direction"], "union key"
    assert spec["scenarios"] == ["normal", "fee_stress", "execution_stress"], "scenarios pre-spec"
    assert "LONG" in spec["mae_def"] and "SHORT" in spec["mae_def"], "MAE def pre-spec"
    assert spec["sizings"] == ["1x"], "L1 chi 1x (khong loc, khong sizing)"
    if a.output.exists():
        raise FileExistsError("Chon output moi; khong ghi de bang chung lich su")

    # --- MAE self-check (3 hand-computed trades) chay TRUOC backtest ---
    mae_check = opencode_mae.self_check()
    print(json.dumps({"mae_self_check": mae_check}), flush=True)
    assert mae_check["assert"] == "PASS", "MAE self-check FAIL -> STOP"

    ds_cfg = json.loads((ROOT / spec["dataset_config"]).read_text())
    parent = json.loads((ROOT / spec["parent_plan"]).read_text())
    candles = pd.read_parquet(ROOT / spec["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)

    # --- VERIFY frozen sources (ton tai? counts? skip missing, khong invent) ---
    frames, verified, skipped = {}, {}, []
    for name in PRIORITY:
        rel = spec["sources"][name]
        q = ROOT / rel
        if not q.exists():
            skipped.append({"source": name, "path": rel, "reason": "missing file -> SKIP"})
            continue
        df = pd.read_parquet(q)
        actual = int(len(df))
        verified[name] = {"path": rel, "n_signals": actual,
                          "expected": int(spec["source_n_signals_expected"][name]),
                          "match_expected": bool(actual == int(spec["source_n_signals_expected"][name]))}
        assert set(["bar_index", "direction", "signal_time"]) <= set(df.columns), f"{name} thieu cot khoa"
        assert int(df.duplicated(subset=["bar_index", "direction"]).sum()) == 0, f"{name} trung key noi bo"
        frames[name] = df.drop(columns=["action"], errors="ignore").reset_index(drop=True)
    print(json.dumps({"sources_verified": verified, "skipped": skipped}), flush=True)
    if not frames:
        raise FileNotFoundError("Tat ca 3 nguon frozen deu missing; STOP, khong invent tin hieu")
    if skipped:
        print(json.dumps({"WARNING_skipped_sources": skipped}), flush=True)

    # --- Score availability per source (cho L2 gate design) ---
    score_availability = {}
    for name, df in frames.items():
        score_availability[name] = {
            "n_signals": int(len(df)),
            "columns": sorted(df.columns.tolist()),
            "score_cols": {c: {"non_null": int(df[c].notna().sum()),
                               "mean": float(df[c].mean()) if pd.api.types.is_numeric_dtype(df[c]) else None}
                           for c in ("expected_net_percent", "en_best", "ohlc_fill_score",
                                     "conditional_net_quantiles_percent", "conditional_win_score",
                                     "candidate_id", "holding_bars") if c in df.columns},
        }
    print(json.dumps({"score_availability": score_availability}), flush=True)

    # --- Overlap (trung thuc, truoc backtest) ---
    keys = {k: set(zip(v["bar_index"].astype(int), v["direction"].astype(int))) for k, v in frames.items()}
    overlap = {"n_per_source": {k: len(v) for k, v in keys.items()}}
    names = list(keys)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            overlap[f"{names[i]}_INTER_{names[j]}"] = len(keys[names[i]] & keys[names[j]])
    if len(names) == 3:
        overlap["triple_inter"] = len(keys[names[0]] & keys[names[1]] & keys[names[2]])
    union_keys = set().union(*keys.values()) if keys else set()
    overlap["union_size"] = len(union_keys)
    overlap["total_rows"] = int(sum(len(v) for v in keys.values()))
    overlap["n_conflicts_dup_keys"] = int(overlap["total_rows"] - overlap["union_size"])
    print(json.dumps({"overlap": overlap}), flush=True)

    # --- Dedup UNION (first-seen geometry+scores, tags per-signal) ---
    pooled, owner, conflicts, geo_diffs = {}, {}, 0, 0
    gcols = spec["union_rule"]["geometry_cols"]
    for name in PRIORITY:
        if name not in frames:
            continue
        for _, row in frames[name].iterrows():
            key = (int(row["bar_index"]), int(row["direction"]))
            if key not in pooled:
                pooled[key] = row
                owner[key] = name
            else:
                conflicts += 1
                try:
                    if not all(pooled[key][c] == row[c] for c in gcols if c in frames[name].columns):
                        geo_diffs += 1
                except Exception:
                    pass
    pool = pd.DataFrame(list(pooled.values())).reset_index(drop=True)
    for name, tag in zip(PRIORITY, TAG_COLS):
        pool[tag] = pool.apply(lambda r, n=name: (int(r["bar_index"]), int(r["direction"])) in keys.get(n, set()),
                               axis=1).astype(bool)
    pool["n_sources"] = pool[TAG_COLS].sum(axis=1).astype(int)
    short = {"v38_identity": "v38-identity", "v33_identity": "v33-identity", "majority_1x": "majority"}
    pool["sources"] = pool.apply(lambda r: "+".join(short[n] for n, t in zip(PRIORITY, TAG_COLS) if r[t]), axis=1)
    pool = pool.sort_values("signal_time").reset_index(drop=True)
    assert len(pool) == overlap["union_size"], "pool size lech overlap"
    assert int((pool["n_sources"] == 1).sum() + (pool["n_sources"] > 1).sum()) == len(pool)
    union_stats = {"n_pool": int(len(pool)), "conflicts_dup_keys": int(conflicts),
                   "geo_diffs_on_conflict": int(geo_diffs),
                   "member_counts_first_seen": {n: int(sum(1 for v in owner.values() if v == n)) for n in PRIORITY},
                   "n_multi_source": int((pool["n_sources"] > 1).sum()),
                   "n_single_source": int((pool["n_sources"] == 1).sum()),
                   "skipped_sources": skipped}
    print(json.dumps({"union_stats": union_stats}), flush=True)

    pool_stats = {
        "n_pool": int(len(pool)),
        "directions": {str(k): int(v) for k, v in pool["direction"].value_counts().items()},
        "first_signal": str(pool["signal_time"].min()), "last_signal": str(pool["signal_time"].max()),
        "by_n_sources": {str(k): int(v) for k, v in pool["n_sources"].value_counts().items()},
        "holdings": {str(k): int(v) for k, v in pool["holding_bars"].value_counts().items()} if "holding_bars" in pool else {},
        "by_month": {str(k): int(v) for k, v in pool["signal_time"].dt.strftime("%Y-%m").value_counts().sort_index().items()},
    }

    # --- Backtest pool_1x x 3 scenarios (KHONG loc) ---
    costs = CostModel(**ds_cfg["costs"])
    costs_fee = CostModel(**{**asdict(costs), "fee_rate_per_fill": float(spec["fee_stress_rate"])})
    stress = FillStress(int(spec["stress"]["entry_penetration_bps"]),
                        int(spec["stress"]["target_penetration_bps"]),
                        int(spec["stress"]["market_exit_slippage_bps"]),
                        float(spec["stress"]["market_exit_fee_rate"]),
                        bool(spec["stress"]["allow_limit_price_improvement"]))
    cap = int(max(ds_cfg["holding_days"]) * 288)
    assert cap == 2016, "holding cap"
    assert int(ds_cfg["entry_expiry_bars"]) == 12, "entry expiry"
    exec1x = ExecutionConfig(entry_expiry_bars=int(ds_cfg["entry_expiry_bars"]),
                             max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    years = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
             .total_seconds() / (365.2425 * 86400))
    engine_sig = pool.drop(columns=["leverage", "action"], errors="ignore").copy()

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())
    (a.output / "mae_source.py").write_text((ROOT / spec["mae_module"]).read_text())
    pooldir = a.output / "pool"
    pooldir.mkdir()
    pool.to_parquet(pooldir / "signals.parquet", index=False)
    bdir = a.output / "pool_1x"
    bdir.mkdir()
    engine_sig.to_parquet(bdir / "signals.parquet", index=False)

    res_n, tr_n = run_backtest(candles, engine_sig, 100, costs, exec1x)
    res_f, tr_f = run_backtest(candles, engine_sig, 100, costs_fee, exec1x)
    res_s, tr_s, diag_s = run_stress(candles, engine_sig, 100, costs, exec1x, stress)
    scenarios, mae_reports = {}, {}
    for label, res, trs in (("normal", res_n, tr_n), ("fee_stress", res_f, tr_f),
                            ("execution_stress", res_s, tr_s)):
        ratio = res.final_equity / 100
        d = {**asdict(res),
             "annual_geometric_net": float(ratio ** (1 / years) - 1),
             "monthly_geometric_net": float(ratio ** (1 / (12 * years)) - 1)}
        rows = [asdict(t) for t in trs]
        tdf = pd.DataFrame(rows, columns=TRADE_COLUMNS) if rows else pd.DataFrame(columns=TRADE_COLUMNS)
        if len(tdf):
            mm = opencode_mae.mae_mfe_for_trades(tdf, candles)
            tdf = tdf.merge(mm[["entry_index", "exit_index", "direction", "entry_price", "mae_frac", "mfe_frac"]],
                            on=["entry_index", "exit_index", "direction", "entry_price"], how="left")
            tdf["realized_net_frac"] = tdf["net_pnl"] / tdf["equity_before"]
            mae_reports[label] = opencode_mae.mae_distribution(tdf)
        else:
            mae_reports[label] = {"n": 0, "note": "0 filled trades"}
        tdf.to_csv(bdir / f"{label}_trades.csv", index=False)
        (bdir / f"{label}_metrics.json").write_text(json.dumps(d, indent=2, default=str))
        d_out = dict(d)
        if label == "execution_stress":
            d_out["diagnostics"] = diag_s
        d_out["gate"] = gate_flags(d, spec["gate"])
        scenarios[label] = d_out
        print(json.dumps({"branch": "pool_1x", "scenario": label,
                          "n_signals": int(len(pool)), "n_fills": int(res.trades),
                          "total_return": res.total_return, "max_drawdown": res.max_drawdown,
                          "monthly": d["monthly_geometric_net"],
                          "mae": {k: mae_reports[label].get(k) for k in
                                  ("n", "mae_mean", "mae_p90", "mae_max")},
                          "gate_pass": d_out["gate"]["pass_all"]}), flush=True)

    report = {
        "experiment": spec["experiment"], "family": spec["family"],
        "hypothesis": spec["hypothesis"],
        "sources_verified": verified, "skipped_sources": skipped,
        "pool_stats": pool_stats, "overlap": overlap, "union_stats": union_stats,
        "score_availability": score_availability,
        "branches": {"pool_1x": {"n_signals": int(len(pool)), "sizing": "1x",
                                 "scenarios": scenarios}},
        "mae": {"def": spec["mae_def"], "self_check": mae_check,
                "per_scenario": mae_reports,
                "headline": "normal-scenario filled trades (FIRST-EVER MAE in program)"},
        "duration_years": years, "gate": spec["gate"],
        "formulas": {"monthly_geometric_net": spec["monthly_formula"],
                     "fee_stress": "fee_rate_per_fill=0.00055",
                     "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x",
                     "union": spec["union_rule"], "sizing_1x": spec["sizing"]["1x"]},
        "handoff_L2": {"path": "artifacts/research/opencode_v72_L1pool/pool/signals.parquet",
                       "n_signals": int(len(pool)),
                       "source_tags": spec["union_rule"]["source_tags"],
                       "note": "per-signal source tags + full score-column union preserved; L2 thiet ke gate tu score_availability"},
        "config": spec, "independent_test": False, "exploratory": True, "live_approved": False,
        "causality": "past-only closed-candle; set ops tren tin hieu dong bang (khong refit); fill tu nen ke tiep; MAE/MFE tu OHLC lich su (khong dung tuong lai)",
        "warning": ("Opened development interval 2023-2026 only. Labels exploratory. "
                    "Drawdown trade-candle-close sampled, not true mark/intrabar. "
                    "Stop/timeout market-like o scenario fee. MAE tu OHLC (low/high) la proxy, "
                    "khong phai adverse excursion thuc trong nen. Khong live approval."),
        "input_sha256": {q: sha256(ROOT / q) for q in
                         [spec["candles"], spec["dataset_config"], spec["parent_plan"],
                          "configs/opencode_v72_L1pool.json", "scripts/opencode_r24L1_pool.py",
                          "scripts/opencode_mae.py"] + [v["path"] for v in verified.values()]},
    }
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    rep2 = json.loads((a.output / "summary.json").read_text())
    rep2["output_sha256"] = {q.relative_to(a.output).as_posix(): fsha(q)
                             for q in sorted(a.output.rglob("*")) if q.is_file() and q.name != "summary.json"}
    (a.output / "summary.json").write_text(json.dumps(rep2, indent=2, ensure_ascii=False, default=str))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
