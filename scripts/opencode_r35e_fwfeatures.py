"""Opencode R35-E (v102): forward INFERENCE features — BUILDERS ONLY.

SEALED forward window 2026-03-23 -> 2026-09-08 (PRISTINE). Reuse the frozen
133-feature builder pattern VERBATIM via IMPORT (no copied logic, no new
formulas, no fitted parameters):

  [:40]  price : SwingStore.sample -> context_features (src/.../data/swing.py,
            same call as scripts/build_swing_research.py FEATURE part)
  [40:80]deriv : daily_context(lag 48) + asof_features (derivatives_features.py,
            same calls as scripts/cache_derivatives_features.py)
  [80:120]flow : build_flow (opencode_r6m_bigmodel_features.py)
  [120:125]fund: build_funding (same module, as-of funding_time < signal_time)
  [125:129]macro: build_macro (same module, strict T-1)
  [129:133]cal : build_calendar (same module, deterministic)

Warmup history (causal past-only, already-opened research data, NEVER fitted):
  research candles + research funding[funding_time < cutoff] +
  research spy/dxy[date < cutoff] + frozen derivatives metrics (ends 2026-03-22).
Sealed forward files are authoritative for >= cutoff. Post-cutoff rows of the
research funding/macro crawls are NEVER used.

STRICTLY FORBIDDEN HERE (script contains NONE of this; fail-closed otherwise):
  labels, returns, PnL, distributions of outcomes, plots, thresholds, training,
  fitting (incl. normalization), or ANY outcome-looking on the forward window.
Output (new dir only): data/processed/opencode_forward_20260323/features/
  features.npz + decisions_forward.parquet (timestamps/bar indices ONLY) +
  builder_manifest.json + SHA256SUMS.txt
"""
import torch  # noqa: F401  (torch truoc pandas: tranh loi DLL tren host nay)
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from agentic_alpha_lab.data.swing import SwingStore, context_features  # noqa: E402
from agentic_alpha_lab.data import derivatives_features  # noqa: E402
from agentic_alpha_lab.data.training import validate_source  # noqa: E402
from opencode_r19m_v39_features import (  # noqa: E402  (re-export cua r6m builder goc)
    N_CAL,
    N_DERIV,
    N_FLAT,
    N_FLOW,
    N_FUND,
    N_MACRO,
    N_PRICE,
    build_calendar,
    build_flow,
    build_funding,
    build_macro,
)
from opencode_r6m_bigmodel_features import (  # noqa: E402  (ten cot block, cung module goc)
    CAL_NAMES,
    FUND_NAMES,
    MACRO_NAMES,
)

assert N_FLAT == 133
assert (N_PRICE, N_DERIV, N_FLOW, N_FUND, N_MACRO, N_CAL) == (40, 40, 40, 5, 4, 4)

CUTOFF = pd.Timestamp("2026-03-23T00:00:00Z")
STRIDE = 72  # 6h lattice, tu configs/kronos_swing.json (research: range(0, N-span, 72))
N_RESEARCH = 444096
N_FORWARD = 48819
FIRST_CONCAT = N_RESEARCH  # 444096 = 72 * 6168 -> grid phase lien mach

FWD = ROOT / "data/processed/opencode_forward_20260323"
OUT = FWD / "features"
RESEARCH = ROOT / "data/processed/swing_regime_research_v4"
FUND_RESEARCH = ROOT / "data/raw/opencode_funding_20260907/funding_BTCUSDT.parquet"
MACRO_RESEARCH = ROOT / "data/raw/opencode_macro_yahoo_20220101_20260907"
METRICS = ROOT / "data/processed/btc_derivatives_metrics_20260905_v1/metrics.parquet"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    plan = json.loads((ROOT / "configs/opencode_v102_fwfeatures.json").read_text(encoding="utf-8"))
    assert plan["experiment"] == "opencode-r35e-fwfeatures"
    if OUT.exists() and any(OUT.iterdir()):
        raise FileExistsError(f"Khong ghi de: {OUT} da ton tai output")

    # ---- 1. Sealed inputs: verify SHA + rows vs freeze manifest (structural) ----
    fz = json.loads((FWD / "manifest.json").read_text(encoding="utf-8"))
    for key, name in (("candles", "candles.parquet"), ("funding", "funding.parquet"),
                      ("macro", "macro.parquet")):
        p = FWD / name
        if sha(p) != fz[key]["sha256"]:
            raise ValueError(f"Sealed hash mismatch: {name}")
    fw_candles = pd.read_parquet(FWD / "candles.parquet")
    fw_funding = pd.read_parquet(FWD / "funding.parquet")
    fw_macro = pd.read_parquet(FWD / "macro.parquet")
    if len(fw_candles) != N_FORWARD != fz["candles"]["rows"]:
        raise ValueError("Forward candle row mismatch")
    if len(fw_funding) != fz["funding"]["rows"] or len(fw_macro) != fz["macro"]["rows"]:
        raise ValueError("Forward funding/macro row mismatch")

    # ---- 2. Research prefix (lookback ONLY, pre-cutoff rows) ----
    rs_meta = json.loads((RESEARCH / "manifest.json").read_text(encoding="utf-8"))
    if sha(RESEARCH / "candles.parquet") != rs_meta["files"]["candles.parquet"]:
        raise ValueError("Research candles changed")
    rs_candles = pd.read_parquet(RESEARCH / "candles.parquet")
    if len(rs_candles) != N_RESEARCH:
        raise ValueError("Research candle row mismatch")
    keep = [c for c in rs_candles.columns if c in fw_candles.columns]
    candles = pd.concat([rs_candles[keep], fw_candles[keep]], ignore_index=True)
    candles = validate_source(candles)  # structural: contiguity incl. 03-22 23:55->03-23 00:00
    if len(candles) != N_RESEARCH + N_FORWARD:
        raise ValueError("Concat candle length mismatch")
    bnd = (candles.open_time.iloc[N_RESEARCH - 1], candles.open_time.iloc[N_RESEARCH])
    if bnd[1] - bnd[0] != pd.Timedelta(minutes=5):
        raise ValueError(f"Boundary gap: {bnd}")

    # ---- 3. Decision clock: 6h lattice continuation (structural only) ----
    grid_idx = np.arange(FIRST_CONCAT, len(candles), STRIDE, dtype=np.int64)
    signals = pd.DatetimeIndex(candles.close_time.iloc[grid_idx]).tz_convert("UTC")
    if signals[0] != pd.Timestamp("2026-03-23T00:04:59.999Z"):
        raise ValueError(f"First forward signal off-grid: {signals[0]}")
    if not signals.is_monotonic_increasing or signals.duplicated().any():
        raise ValueError("Invalid forward chronology")
    if ((signals - signals[0]).total_seconds() % (6 * 3600) != 0).any():
        raise ValueError("Grid phase drift (not exact 6h lattice)")
    if (signals.minute != 4).any() or (signals.second != 59).any():
        raise ValueError("Grid phase != :04:59.999")
    sealed_last_close = pd.to_datetime(fw_candles["close_time"], utc=True).max()
    if (signals > sealed_last_close).any():
        raise ValueError("Decision beyond sealed closed candles")
    n = len(signals)
    decisions = pd.DataFrame({
        "signal_time": signals,
        "open_time": pd.DatetimeIndex(candles.open_time.iloc[grid_idx]).tz_convert("UTC"),
        "bar_index_forward": (grid_idx - FIRST_CONCAT).astype(np.int64),
        "bar_index_concat": grid_idx.astype(np.int64),
    })

    # ---- 4. price40: VERBATIM SwingStore.sample -> context_features (NO labels) ----
    swing_cfg = json.loads((ROOT / "configs/kronos_swing.json").read_text(encoding="utf-8"))
    if swing_cfg["stride"] != STRIDE:
        raise ValueError("Stride config mismatch")
    store = SwingStore(candles, swing_cfg)
    price_rows = []
    for ts in decisions["signal_time"]:
        windows, _, _, f40, _, _ = store.sample(ts)
        price_rows.append(np.asarray(f40, dtype=np.float64))
    price = np.stack(price_rows)
    if price.shape != (n, N_PRICE) or not np.isfinite(price).all():
        raise ValueError(f"price40 shape/finite: {price.shape}")

    # ---- 5. deriv40: VERBATIM daily_context(48) + asof_features ----
    metrics = pd.read_parquet(METRICS)
    if pd.to_datetime(metrics["create_time"], utc=True).max() >= CUTOFF:
        raise ValueError("Metrics contain post-cutoff rows (seal)")
    context = derivatives_features.daily_context(metrics, lag_hours=48)
    deriv, deriv_names, availability = derivatives_features.asof_features(
        context, pd.DatetimeIndex(decisions["signal_time"]))
    deriv = np.asarray(deriv, dtype=np.float64)
    if deriv.shape != (n, N_DERIV) or not np.isfinite(deriv).all():
        raise ValueError(f"deriv40 shape/finite: {deriv.shape}")
    deriv_missing = availability["source_day"].isna()
    deriv_mask = deriv[:, 20:]

    # ---- 6. flow40 / fund5 / macro4 / cal4: VERBATIM research builders ----
    flow, flow_names = build_flow(candles, decisions["signal_time"])
    flow = np.asarray(flow, dtype=np.float64)

    rs_fund = pd.read_parquet(FUND_RESEARCH)
    rs_fund["funding_time"] = pd.to_datetime(rs_fund["funding_time"], utc=True)
    fw_fund = fw_funding.copy()
    fw_fund["funding_time"] = pd.to_datetime(fw_fund["funding_time"], utc=True)
    if fw_fund["funding_time"].min() < CUTOFF:
        raise ValueError("Sealed funding starts before cutoff")
    fund_table = pd.concat([rs_fund[rs_fund["funding_time"] < CUTOFF], fw_fund],
                           ignore_index=True)
    fund_table = fund_table.sort_values("funding_time").reset_index(drop=True)
    if fund_table["funding_time"].duplicated().any():
        raise ValueError("Duplicate funding_time across boundary")
    fund_bnd = (fund_table.loc[fund_table["funding_time"] < CUTOFF, "funding_time"].max(),
                fund_table.loc[fund_table["funding_time"] >= CUTOFF, "funding_time"].min())

    rs_spy = pd.read_parquet(MACRO_RESEARCH / "spy.parquet")
    rs_dxy = pd.read_parquet(MACRO_RESEARCH / "dxy.parquet")
    fw_spy = fw_macro[fw_macro["symbol"] == "spy"].copy()
    fw_dxy = fw_macro[fw_macro["symbol"] == "dxy"].copy()
    for frame in (rs_spy, rs_dxy, fw_spy, fw_dxy):
        frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.normalize()
    cut = CUTOFF.normalize()
    spy = pd.concat([rs_spy[rs_spy["date"] < cut], fw_spy[fw_spy["date"] >= cut]],
                    ignore_index=True)
    dxy = pd.concat([rs_dxy[rs_dxy["date"] < cut], fw_dxy[fw_dxy["date"] >= cut]],
                    ignore_index=True)
    for frame, name in ((spy, "spy"), (dxy, "dxy")):
        frame = frame.sort_values("date").reset_index(drop=True)
        if frame["date"].duplicated().any():
            raise ValueError(f"Duplicate macro date: {name}")
        if name == "spy":
            spy = frame
        else:
            dxy = frame

    with tempfile.TemporaryDirectory(prefix="fwfeat-") as tmp:
        fund_path = Path(tmp) / "funding_asof.parquet"
        fund_table.to_parquet(fund_path, index=False)
        fund = np.asarray(build_funding(decisions["signal_time"], fund_path), dtype=np.float64)
        macro_dir = Path(tmp) / "macro"
        macro_dir.mkdir()
        spy.to_parquet(macro_dir / "spy.parquet", index=False)
        dxy.to_parquet(macro_dir / "dxy.parquet", index=False)
        macro = np.asarray(build_macro(decisions["signal_time"], macro_dir), dtype=np.float64)
    cal = np.asarray(build_calendar(decisions["signal_time"]), dtype=np.float64)

    blocks = {"price": price, "deriv": deriv, "flow": flow,
              "fund": fund, "macro": macro, "cal": cal}
    shapes = {k: list(v.shape) for k, v in blocks.items()}
    finite = {k: bool(np.isfinite(v).all()) for k, v in blocks.items()}
    if any(s[0] != n for s in shapes.values()) or not all(finite.values()):
        raise ValueError(f"Block shape/finite: {shapes} {finite}")
    flat = np.concatenate([price, deriv, flow, fund, macro, cal], axis=-1)
    if flat.shape != (n, N_FLAT) or not np.isfinite(flat).all():
        raise ValueError(f"Flat shape/finite: {flat.shape}")

    # ---- 7. Write NEW outputs only ----
    OUT.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(OUT / "features.npz", features=flat.astype(np.float32))
    decisions.to_parquet(OUT / "decisions_forward.parquet", index=False)
    manifest = {
        "experiment": "opencode-r35e-fwfeatures",
        "prespec": "configs/opencode_v102_fwfeatures.json",
        "builder": "scripts/opencode_r35e_fwfeatures.py via IMPORT of "
                   "scripts/opencode_r19m_v39_features.py "
                   "(build_flow/build_funding/build_macro/build_calendar) + "
                   "src/agentic_alpha_lab/data/swing.py (SwingStore/context_features) + "
                   "src/agentic_alpha_lab/data/derivatives_features.py "
                   "(daily_context lag48/asof_features); layout 40/40/40/5/4/4=133",
        "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "cutoff": CUTOFF.isoformat(),
        "inputs": {
            "sealed_forward": {name: sha(FWD / name) for name in
                               ("candles.parquet", "funding.parquet", "macro.parquet")},
            "research_prefix_lookback": {
                "swing_research_candles": sha(RESEARCH / "candles.parquet"),
                "funding_crawl_pre_cutoff_rows": int((rs_fund["funding_time"] < CUTOFF).sum()),
                "funding_crawl_post_cutoff_rows_USED": 0,
                "macro_spy_pre_cutoff_rows": int((rs_spy["date"] < cut).sum()),
                "macro_dxy_pre_cutoff_rows": int((rs_dxy["date"] < cut).sum()),
                "macro_post_cutoff_rows_USED_from_research_crawl": 0,
                "derivatives_metrics_sha_note": "frozen archive ends 2026-03-22 (all pre-cutoff)",
                "derivatives_metrics_max_create_time": str(
                    pd.to_datetime(metrics["create_time"], utc=True).max()),
            },
        },
        "clock": {
            "stride_bars": STRIDE,
            "n_decisions": n,
            "first_signal": str(signals[0]),
            "last_signal": str(signals[-1]),
            "step_hours": sorted({float(x) for x in (np.diff(signals.asi8) / 3.6e12)}),
            "boundary_candles": [str(bnd[0]), str(bnd[1])],
            "boundary_gap_is_5m": True,
            "research_series_last_signal": "2026-03-15T18:04:59.999+00:00 "
                "(label-span cutoff; lattice phase unchanged, no grid break)",
        },
        "blocks": shapes,
        "finite_rate": {k: 1.0 for k in blocks},
        "missing_handling": {
            "rule": "research builders raise on missing (no imputation); deriv uses "
                    "zero + explicit mask per derivatives_features (never filled)",
            "skips": 0,
            "deriv_rows_all_missing": int((deriv_mask.mean(axis=1) == 1.0).sum()),
            "deriv_rows_any_missing": int((deriv_mask.mean(axis=1) > 0).sum()),
            "deriv_mask_mean": float(deriv_mask.mean()),
            "funding_boundary_last_prefix_first_sealed": [str(fund_bnd[0]), str(fund_bnd[1])],
        },
        "names": {
            "fund": FUND_NAMES, "macro": MACRO_NAMES, "cal": CAL_NAMES,
            "deriv": list(deriv_names), "flow": list(flow_names),
            "price": "context_features order: 5 TFs (5min,15min,1h,4h,1d) x 8 stats",
        },
        "outputs": {
            "features.npz": {"key": "features", "dtype": "float32", "shape": [n, N_FLAT]},
            "decisions_forward.parquet": {"columns": list(decisions.columns),
                                          "note": "timestamps/bar indices ONLY"},
        },
        "seal_affirmation": {
            "labels_computed": False,
            "returns_computed": False,
            "pnl_computed": False,
            "distributions_inspected": False,
            "plots_created": False,
            "thresholds_selected": False,
            "training_or_fitting": False,
            "outcome_looking": False,
            "evidence": "script imports no label/return/pnl/backtest/threshold code "
                        "(only SwingStore/context_features + derivatives_features + "
                        "build_flow/build_funding/build_macro/build_calendar); "
                        "features/ dir contains only features.npz, "
                        "decisions_forward.parquet (no close/atr/label columns), "
                        "builder_manifest.json, SHA256SUMS.txt; sealed files unmodified "
                        "(SHA re-verified before run)",
        },
    }
    (OUT / "builder_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    sums = []
    for name in ("features.npz", "decisions_forward.parquet", "builder_manifest.json"):
        sums.append(f"{sha(OUT / name)}  {name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    manifest["outputs"]["sha256"] = {s.split()[1]: s.split()[0] for s in sums}
    (OUT / "builder_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"state": "fwfeatures_complete", "n": n,
                      "last_signal": str(signals[-1]),
                      "deriv_rows_all_missing": manifest["missing_handling"]["deriv_rows_all_missing"],
                      "out": str(OUT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
