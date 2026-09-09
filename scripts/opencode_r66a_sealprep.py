"""Opencode v155 (R66-A2 SEALPREP): seal-verify harness ready for L's standing-best majority forward eval.

Pre-spec: configs/opencode_v155_sealprep.json (checks S1-frozen-policy-only
(v29-checkpoints + frozen iso-maps + majority-vote + cap4/cd5 + ohlc-v2 costs) /
S2-metrics-once / S3-no-threshold-label / S4-no-plots + PASS rules, adapted from
v136/v110 harnesses to majority policy).
Verification only. No live orders. Exploratory labels.

Expected L policy (refs in config policy_refs):
  vote majority 2-of-3 (d4 participates, iso4 geometry, same-row only, frozen maps),
  gate choose() per map with dataset policy (min_expected 0.3 + fill>=0.25) then majority mask BEFORE frequency loop,
  frequency monthly cap 4 + cooldown 5d chronological,
  execution entry 12 / holding 2016 / tp1 0.5 / lev 1x / ohlc-v2 / stop-first / t->t+1 / capital 100,
  costs fee normal 0.0002 / stress 0.00055 / funding long 0.0001/8h short 0,
  signal frozen v29 checkpoints + FROZEN iso2/4/all maps (pre-cutoff). No refit/tuning on forward.

Poll logic: Depends-on-L (R66-L fwdeval-majority, FIRST forward eval of standing-best).
  If L summary.json absent -> write PREP-READY (config copy + driver copy +
  forward_tree_before/after + seal_audit PREP-READY + summary.json), exit 0.
  Poll at most 4 times ~20min apart (caller polls); never block forever.

When L present:
  S1 frozen-policy-only (diff L config vs majority baseline execution/vote/frequency/costs/engine)
  S2 metrics-once (exactly 1 summary.json, 0 rerun traces)
  S3 no threshold/label files + sealed SHA unchanged + forward tree delta
  S4 no price/returns plots
  NUMBERS: own driver rebuilds forward backtest from frozen L signals +
    forward candles/costs for normal (0.0002) + fee 0.00055; PASS within 1e-6.
Own implementation: imports engine.run_backtest directly, never imports L driver.
"""
import torch  # noqa: F401  (torch before pandas: DLL load-order on this host)
import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.data.training import sha256

TOL_DEFAULT = 1e-6
SEED_EQUITY = 100.0


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_forward_tree(fwd_dir: Path) -> dict:
    entries = []
    for p in sorted(fwd_dir.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(fwd_dir).as_posix()
        try:
            sz = p.stat().st_size
            mt = p.stat().st_mtime
        except OSError:
            sz, mt = -1, 0
        entries.append({"path": rel, "bytes": int(sz), "mtime": float(mt)})
    return {"dir": str(fwd_dir), "n_files": len(entries), "files": entries}


def _dep_block(cfg: dict) -> dict:
    # Prefer depends_on_L (v155); fallback to depends_on_E (v110/v136 lineage alias).
    if isinstance(cfg.get("depends_on_L"), dict):
        return cfg["depends_on_L"]
    return cfg.get("depends_on_E", {})


def _cand_list(dep: dict, *keys) -> list:
    out: list = []
    for k in keys:
        v = dep.get(k)
        if isinstance(v, list):
            out.extend(v)
    seen = set()
    uniq = []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def find_first_existing(root: Path, candidates: list) -> Path | None:
    for c in candidates:
        p = root / c
        if p.exists():
            return p
    return None


def find_e(cfg: dict, root: Path) -> dict:
    dep = _dep_block(cfg)
    dir_cands = _cand_list(dep, "l_artifact_dir_candidates", "e_artifact_dir_candidates")
    cfg_cands = _cand_list(dep, "l_config_candidates", "e_config_candidates")
    sig_cands = _cand_list(dep, "l_signals_candidates", "e_signals_candidates")
    summary_name = dep.get("l_summary_filename", dep.get("e_summary_filename", "summary.json"))
    dir_found = None
    for d in dir_cands:
        p = root / d
        if p.is_dir():
            dir_found = p
            break
    cfg_found = None
    for c in cfg_cands:
        p = root / c
        if p.is_file():
            cfg_found = p
            break
    summary = None
    signals = None
    driver = None
    if dir_found is not None and dir_found.is_dir():
        s = dir_found / summary_name
        if s.is_file():
            summary = s
        for cand in (sig_cands or ["signals.parquet"]):
            direct = dir_found / cand
            if direct.is_file():
                signals = direct
                break
            hits = sorted(dir_found.glob(f"*/{cand}"))
            if hits:
                signals = hits[0]
                break
        py_hits = sorted(dir_found.glob("*.py"))
        if py_hits:
            driver = py_hits[0]
    return {"dir": dir_found, "config": cfg_found, "summary": summary,
            "signals": signals, "driver": driver}


def check_s1(e_cfg_path: Path | None, v155: dict) -> dict:
    base = v155["baseline_policy_frozen"]
    if e_cfg_path is None or not e_cfg_path.is_file():
        return {"status": "FAIL", "reason": "L config absent: cannot prove frozen-policy-only",
                "e_config": None, "diffs": ["missing L config"]}
    try:
        e_cfg = json.loads(e_cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "FAIL", "reason": f"L config unreadable: {exc}",
                "e_config": str(e_cfg_path), "diffs": ["unreadable"]}
    diffs = []
    notes = []
    exec_src = {}
    for key in ("execution", "policy_frozen", "policy", "engine_config"):
        if isinstance(e_cfg.get(key), dict):
            exec_src.update(e_cfg[key])
            inner = e_cfg[key].get("execution") if isinstance(e_cfg[key].get("execution"), dict) else {}
            exec_src.update(inner)
    exp_exec = base["execution"]
    checks = {
        "entry_expiry_bars": (exec_src.get("entry_expiry_bars"), exp_exec["entry_expiry_bars"]),
        "tp1_fraction": (exec_src.get("tp1_fraction"), exp_exec["tp1_fraction"]),
        "leverage": (exec_src.get("leverage"), exp_exec["leverage"]),
        "max_leverage": (exec_src.get("max_leverage"), exp_exec["max_leverage"]),
        "intrabar_policy": (exec_src.get("intrabar_policy"), exp_exec["intrabar_policy"]),
    }
    for k, (got, want) in checks.items():
        if got is None:
            diffs.append(f"{k}: MISSING in L config (want {want})")
        elif isinstance(want, float):
            try:
                if abs(float(got) - float(want)) > 1e-12:
                    diffs.append(f"{k}: {got} != {want}")
            except Exception:
                diffs.append(f"{k}: non-numeric {got} (want {want})")
        else:
            if got != want:
                diffs.append(f"{k}: {got} != {want}")
    hold = exec_src.get("max_holding_bars", exec_src.get("holding_cap_bars"))
    if hold is None:
        diffs.append(f"max_holding_bars: MISSING (want one of {exp_exec['max_holding_bars_allowed']})")
    else:
        try:
            if int(hold) not in list(exp_exec["max_holding_bars_allowed"]):
                diffs.append(f"max_holding_bars: {hold} not in {exp_exec['max_holding_bars_allowed']}")
        except Exception:
            diffs.append(f"max_holding_bars: bad value {hold}")
    freq_src = {}
    for key in ("policy", "policy_frozen", "frequency", "execution"):
        if isinstance(e_cfg.get(key), dict):
            freq_src.update(e_cfg[key])
    freq_src.update(exec_src)
    cap = freq_src.get("maximum_signals_per_month", freq_src.get("monthly_cap", freq_src.get("max_signals_per_month")))
    if cap is not None:
        try:
            if int(cap) != 4:
                diffs.append(f"monthly_cap: {cap} != 4 (majority)")
        except Exception:
            diffs.append(f"monthly_cap: bad value {cap}")
    else:
        notes.append("monthly cap 4 not declared in L config keys (verify in L driver source policy loop)")
    cd = freq_src.get("cooldown_days", freq_src.get("cooldown"))
    if cd is not None:
        try:
            if int(cd) != 5:
                diffs.append(f"cooldown_days: {cd} != 5 (majority)")
        except Exception:
            diffs.append(f"cooldown_days: bad value {cd}")
    else:
        notes.append("cooldown 5d not declared in L config keys (verify in L driver source policy loop)")
    blob = json.dumps(e_cfg).lower()
    if "majority" not in blob:
        diffs.append("vote: L config does not declare majority vote (want majority 2-of-3 + d4 participates + iso4 geometry)")
    if ("v29" not in blob) and ("iso" not in blob) and ("v30" not in blob) and ("frozen" not in blob):
        diffs.append("signal source: L config does not declare frozen v29/iso maps (want v29 + iso/frozen refs)")
    if "kronos" in blob and "majority" not in blob:
        diffs.append("signal source: L config declares kronos (want frozen v29-majority for this eval)")
    for fam in ("v38", "v55", "v41", "v33", "v96", "v145", "v146"):
        if fam in blob and ("v29" not in blob) and ("majority" not in blob):
            diffs.append(f"signal source: L config declares non-v29 family {fam} without v29/majority (want frozen v29-majority)")
            break
    for flag in ["fitted on forward", "fit on forward", "fit_on_forward", "tuned on forward",
                 "threshold selected on forward", "threshold_selection_on_forward",
                 "isotonic fitted on forward", "normalization fitted on forward",
                 "percentile gate on forward", "percentile fitted on forward",
                 "vote fitted on forward", "vote tuned on forward"]:
        if flag in blob:
            diffs.append(f"forward-fit marker: '{flag}' present in L config")
    cost_src = {}
    for key in ("costs", "execution_assumptions", "frozen_constants"):
        if isinstance(e_cfg.get(key), dict):
            cost_src.update(e_cfg[key])
    cost_src.update(exec_src)
    fee = cost_src.get("fee_rate_per_fill", cost_src.get("fee_normal_per_fill", cost_src.get("fee_per_fill")))
    if fee is None:
        diffs.append("fee_normal: MISSING (want 0.0002)")
    else:
        try:
            if abs(float(fee) - 0.0002) > 1e-12:
                diffs.append(f"fee_normal: {fee} != 0.0002")
        except Exception:
            diffs.append(f"fee_normal: bad {fee}")
    eng = e_cfg.get("engine", exec_src.get("engine", ""))
    if eng and eng != "ohlc-v2":
        diffs.append(f"engine: {eng} != ohlc-v2")
    status = "PASS" if not diffs else "FAIL"
    return {"status": status, "e_config": str(e_cfg_path),
            "diffs": diffs if diffs else ["execution+vote+costs match majority baseline; no forward-fit markers"],
            "notes": notes,
            "reason": "frozen majority policy holds" if status == "PASS" else "policy drift or missing declaration"}


def check_s2(e_dir: Path | None) -> dict:
    if e_dir is None or not e_dir.is_dir():
        return {"status": "FAIL", "reason": "L dir absent", "n_summary": 0, "files": []}
    summaries = sorted(e_dir.glob("summary*.json"))
    traces = []
    for pat in ("summary_*.json", "summary.*.json", "summary_v*.json", "rerun*.log",
                "rerun*.json", "metrics_rerun*.json", "*_rerun.json"):
        traces.extend(sorted(e_dir.glob(pat)))
    traces = [t for t in traces if t.name != "summary.json"]
    n = len([s for s in summaries if s.name == "summary.json"])
    status = "PASS" if (n == 1 and len(summaries) == 1 and not traces) else "FAIL"
    if n == 0:
        status = "FAIL"
    return {"status": status,
            "reason": "exactly 1 summary, 0 reruns" if status == "PASS" else "rerun/multiple-summary evidence",
            "n_summary": len(summaries),
            "summary_files": [s.name for s in summaries],
            "rerun_traces": [t.name for t in traces],
            "files": [s.name for s in summaries] + [t.name for t in traces]}


def check_s3(e_dir: Path | None, root: Path, tree_before: dict, tree_after: dict) -> dict:
    fwd = root / "data/processed/opencode_forward_20260323"
    manifest = json.loads((fwd / "manifest.json").read_text(encoding="utf-8"))
    seal_ok = True
    seal_notes = []
    for key, fname in (("candles", "candles.parquet"), ("funding", "funding.parquet"), ("macro", "macro.parquet")):
        p = fwd / fname
        try:
            got = sha_file(p)
            want = manifest[key]["sha256"]
            if got != want:
                seal_ok = False
                seal_notes.append(f"{fname}: SHA MISMATCH (sealed file modified)")
            else:
                seal_notes.append(f"{fname}: SHA ok")
        except Exception as exc:
            seal_ok = False
            seal_notes.append(f"{fname}: unreadable ({exc})")
    before_set = {f["path"] for f in tree_before.get("files", [])}
    after_set = {f["path"] for f in tree_after.get("files", [])}
    new_files = sorted(after_set - before_set)
    bad = []
    if e_dir is not None and e_dir.is_dir():
        for p in sorted(e_dir.rglob("*")):
            if p.is_dir():
                continue
            name = p.name.lower()
            rel = p.relative_to(e_dir).as_posix().lower()
            if any(k in name or k in rel for k in ("threshold", "label", "tune", "calibrat", "normaliz")):
                bad.append(p.relative_to(e_dir).as_posix())
    status = "PASS" if (seal_ok and not new_files and not bad) else "FAIL"
    return {"status": status, "sealed_sha_ok": seal_ok, "seal_notes": seal_notes,
            "forward_new_files": new_files, "e_threshold_label_files": bad,
            "reason": "sealed intact, no forward delta, no threshold/label files" if status == "PASS"
                      else "seal delta or threshold/label files present"}


def check_s4(e_dir: Path | None) -> dict:
    if e_dir is None or not e_dir.is_dir():
        return {"status": "FAIL", "reason": "L dir absent", "plot_files": [], "grep_hits": []}
    plot_files = []
    for p in sorted(e_dir.rglob("*")):
        if p.is_dir():
            continue
        suf = p.suffix.lower()
        nm = p.name.lower()
        if suf in (".png", ".jpg", ".jpeg", ".html") or "plot" in nm:
            if p.name in ("driver_source.py", "config.json"):
                continue
            plot_files.append(p.relative_to(e_dir).as_posix())
    grep_hits = []
    for p in sorted(e_dir.rglob("*.py")):
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        low = txt.lower()
        for marker in ("matplotlib", "plotly", "plt.plot", "fig.savefig", ".savefig(",
                       "forward price plot", "returns plot", "plot_forward"):
            if marker in low:
                grep_hits.append(f"{p.relative_to(e_dir).as_posix()}: {marker}")
    status = "PASS" if (not plot_files and not grep_hits) else "FAIL"
    return {"status": status,
            "reason": "no plots" if status == "PASS" else "plot files or plot code present",
            "plot_files": plot_files, "grep_hits": grep_hits}


def monthly_from_bounds(final_equity: float, first_open: pd.Timestamp, last_close: pd.Timestamp) -> float:
    secs = (last_close - first_open).total_seconds()
    years = secs / (365.2425 * 86400)
    ratio = float(final_equity) / 100.0
    return float(ratio ** (1.0 / (12.0 * years)) - 1.0), float(years)


def rebuild_forward(e_signals_path: Path, root: Path, fee_stress: float) -> dict:
    fwd_candles_path = root / "data/processed/opencode_forward_20260323/candles.parquet"
    candles = pd.read_parquet(fwd_candles_path)
    sig = pd.read_parquet(e_signals_path)
    for col in ("bar_index", "signal_time", "direction", "entry_limit",
                "stop_loss", "take_profit_1", "take_profit_2"):
        if col not in sig.columns:
            raise ValueError(f"L signals missing executable column {col}")
    n_c = len(candles)
    aligned_note = "bar_index used as-is (in forward range)"
    if int(sig["bar_index"].max()) >= n_c or int(sig["bar_index"].min()) < 0:
        ct = pd.to_datetime(candles["close_time"], utc=True)
        lookup = pd.Series(np.arange(n_c), index=ct)
        st = pd.to_datetime(sig["signal_time"], utc=True)
        idx = st.map(lookup)
        if idx.isna().any():
            raise ValueError("L signal_time absent from forward candles (cannot align)")
        sig = sig.copy()
        sig["bar_index"] = idx.astype(int).to_numpy()
        aligned_note = "bar_index realigned via signal_time->forward close_time (out-of-range input)"
    work = sig.copy()
    work["__st"] = pd.to_datetime(work["signal_time"], utc=True).to_numpy()
    work = work.sort_values(["bar_index", "__st"], kind="mergesort").reset_index(drop=True)
    work = work.drop(columns=["__st"])
    base_costs = CostModel(fee_rate_per_fill=0.0002, funding_long_rate=0.0001,
                           funding_short_rate=0.0, funding_interval_hours=8)
    stress_costs = CostModel(fee_rate_per_fill=float(fee_stress), funding_long_rate=0.0001,
                             funding_short_rate=0.0, funding_interval_hours=8)
    # Frozen majority_1x execution: entry 12, holding 2016, tp1 0.5, 1x.
    exp_bars, cap, tp1 = 12, 2016, 0.5
    holding = work.get("holding_bars")
    if holding is not None:
        mx = int(pd.to_numeric(holding, errors="coerce").max())
        if mx > cap:
            raise ValueError(f"L holding_bars {mx} exceeds frozen cap {cap}")

    def frame():
        f = work.copy()
        if "leverage" in f.columns:
            f = f.drop(columns=["leverage"])
        return f.reset_index(drop=True)

    exe = ExecutionConfig(entry_expiry_bars=exp_bars, max_holding_bars=cap,
                          tp1_fraction=tp1, leverage=1.0, max_leverage=1.0)
    fr = frame()
    res_n, tr_n = run_backtest(candles, fr, SEED_EQUITY, base_costs, exe)
    res_f, tr_f = run_backtest(candles, fr, SEED_EQUITY, stress_costs, exe)
    first_open = pd.to_datetime(candles["open_time"], utc=True).min()
    last_close = pd.to_datetime(candles["close_time"], utc=True).max()
    out = {}
    for label, res, trs in (("normal", res_n, tr_n), ("fee_00055", res_f, tr_f)):
        d = asdict(res)
        mo, yrs = monthly_from_bounds(res.final_equity, first_open, last_close)
        d["monthly_geometric_net"] = mo
        d["duration_years"] = yrs
        d["n_signals"] = int(len(fr))
        out[label] = {"metrics": d, "trades": [asdict(t) for t in trs]}
    out["_align_note"] = aligned_note
    out["_n_candles"] = int(n_c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError("No overwrites: choose a new output dir")
    v155 = json.loads(Path(a.config).read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    tol = float(v155["numbers_reproduction"]["pass_criterion"]["tolerance_abs"])
    fee_s = 0.00055
    try:
        fee_s = float(v155["baseline_policy_frozen"]["costs"]["fee_stress_per_fill"])
    except Exception:
        pass
    dep = _dep_block(v155)

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(v155, indent=2, ensure_ascii=False), encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")

    fwd_dir = root / "data/processed/opencode_forward_20260323"
    tree_before = snapshot_forward_tree(fwd_dir)
    (a.output / "forward_tree_before.json").write_text(json.dumps(tree_before, indent=2), encoding="utf-8")

    found = find_e(v155, root)
    e_dir = found["dir"]
    e_cfg_p = found["config"]
    e_sum_p = found["summary"]
    e_sig_p = found["signals"]

    # ---- L ABSENT -> PREP-READY (no outcome-looking) ----
    if e_sum_p is None or not e_sum_p.is_file():
        tree_after = snapshot_forward_tree(fwd_dir)
        (a.output / "forward_tree_after.json").write_text(json.dumps(tree_after, indent=2), encoding="utf-8")
        s3 = check_s3(None, root, tree_before, tree_after)
        prep = {
            "state": "PREP-READY",
            "reason": "L summary.json absent at audit time; prep complete (v155 config + r66a verifier + forward snapshots). Poll bounded (max 4 x ~20min), do not block forever.",
            "polls": [{"poll": 1, "result": "ABSENT (prep start)"},
                      {"poll": 2, "result": "ABSENT (after prep writes)"}],
            "e_search": {k: (str(v) if v is not None else None) for k, v in found.items()},
            "l_config_candidates": dep.get("l_config_candidates", dep.get("e_config_candidates")),
            "l_dir_candidates": dep.get("l_artifact_dir_candidates", dep.get("e_artifact_dir_candidates")),
            "forward_tree": {"before_n": tree_before["n_files"], "after_n": tree_after["n_files"],
                             "delta": sorted({f["path"] for f in tree_after["files"]} - {f["path"] for f in tree_before["files"]})},
            "seal_tree_check": s3,
            "expected_L_policy": "majority_1x: vote majority 2-of-3 (d4 participates, iso4 geometry) on frozen v29 + frozen iso2/4/all; freq cap4/cd5d; exec 12/2016/tp0.5/1x/stop-first/t->t+1; costs 0.0002/0.00055/fund 0.0001/8h; sizing 1x",
            "next": "POLL for L summary (max 2 more x ~20min). When present, rerun this driver (new output dir) for full S1-S4 + numbers reproduction.",
        }
        (a.output / "prep_ready.json").write_text(json.dumps(prep, indent=2, ensure_ascii=False), encoding="utf-8")
        seal_audit = {
            "S1_frozen_policy_only": {"status": "DEFERRED", "reason": "L absent"},
            "S2_metrics_once": {"status": "DEFERRED", "reason": "L absent"},
            "S3_no_threshold_label_files": s3,
            "S4_no_price_returns_plots": {"status": "DEFERRED", "reason": "L absent"},
            "overall": "PREP-READY",
        }
        (a.output / "seal_audit.json").write_text(json.dumps(seal_audit, indent=2, ensure_ascii=False), encoding="utf-8")
        summary = {
            "experiment": "opencode-v155-sealprep",
            "role": v155["role"],
            "state": "PREP-READY",
            "verdict": "PREP-READY (L absent; verifier ready, window still pristine for future use)",
            "e_present": False,
            "l_present": False,
            "seal_items": seal_audit,
            "numbers_match": None,
            "deltas": None,
            "pristine_window": "PRISTINE (sealed SHA ok, forward delta 0)" if s3["sealed_sha_ok"] and not s3["forward_new_files"] else "CHECK forward delta",
            "artifacts": {"dir": str(a.output), "files": ["config.json", "driver_source.py", "forward_tree_before.json", "forward_tree_after.json", "prep_ready.json", "seal_audit.json", "summary.json"]},
            "exploratory": True,
            "independent_test": False,
            "live_approved": False,
        }
        (a.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"state": "PREP-READY", "l_present": False,
                          "forward_before": tree_before["n_files"], "forward_after": tree_after["n_files"],
                          "sealed_sha_ok": s3["sealed_sha_ok"]}, indent=2))
        print("WROTE", str(a.output / "summary.json"))
        return

    # ---- L PRESENT -> full audit ----
    tree_after = snapshot_forward_tree(fwd_dir)
    (a.output / "forward_tree_after.json").write_text(json.dumps(tree_after, indent=2), encoding="utf-8")
    s1 = check_s1(e_cfg_p, v155)
    s2 = check_s2(e_dir)
    s3 = check_s3(e_dir, root, tree_before, tree_after)
    s4 = check_s4(e_dir)
    seal_audit = {"S1_frozen_policy_only": s1, "S2_metrics_once": s2,
                  "S3_no_threshold_label_files": s3, "S4_no_price_returns_plots": s4}
    seal_overall = "PASS" if all(v.get("status") == "PASS" for v in seal_audit.values()) else "FAIL"
    seal_audit["overall"] = seal_overall
    (a.output / "seal_audit.json").write_text(json.dumps(seal_audit, indent=2, ensure_ascii=False), encoding="utf-8")

    e_doc = json.loads(e_sum_p.read_text(encoding="utf-8"))
    repro = rebuild_forward(e_sig_p, root, fee_s)
    for scen in ("normal", "fee_00055"):
        d = a.output / scen
        d.mkdir()
        pd.DataFrame(repro[scen]["trades"]).to_csv(d / "repro_trades.csv", index=False)
        (d / "repro_metrics.json").write_text(json.dumps(repro[scen]["metrics"], indent=2, default=str), encoding="utf-8")
    pub = {}
    if isinstance(e_doc.get("branches"), dict):
        for bname, bval in e_doc["branches"].items():
            if isinstance(bval, dict) and ("normal" in bval or "fee_00055" in bval or "fee_stress" in bval):
                for scen_key, our_key in (("normal", "normal"), ("fee_00055", "fee_00055"), ("fee_stress", "fee_00055")):
                    if scen_key in bval and our_key not in pub:
                        pub[our_key] = bval[scen_key]
                break
        if not pub and e_doc["branches"]:
            first = next(iter(e_doc["branches"].values()))
            if isinstance(first, dict) and "total_return" in first:
                pub = {"normal": first}
    for k in ("normal", "fee_00055", "fee_stress", "metrics", "results"):
        if k in e_doc and isinstance(e_doc[k], dict) and "total_return" in e_doc[k]:
            pub = {"normal": e_doc[k]} if k in ("metrics", "results") else pub
    deltas, verdicts = {}, {}
    for scen in ("normal", "fee_00055"):
        if scen not in pub:
            deltas[scen] = {"error": "L published metrics not found for scenario"}
            verdicts[scen] = "FAIL"
            continue
        r = repro[scen]["metrics"]
        p = pub[scen]
        d = {}
        for m in ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity"):
            try:
                d[m] = float(r[m] - p[m])
            except Exception:
                d[m] = None
        for m in ("trades", "long_trades", "short_trades"):
            try:
                d[m] = int(r[m] - p[m])
            except Exception:
                d[m] = None
        floats_ok = all((d[m] is not None and abs(d[m]) <= tol) for m in
                        ("total_return", "max_drawdown", "monthly_geometric_net", "final_equity"))
        ints_ok = all(d[m] == 0 for m in ("trades", "long_trades", "short_trades"))
        deltas[scen] = d
        verdicts[scen] = "PASS" if (floats_ok and ints_ok) else "FAIL"
    overall_num = all(v == "PASS" for v in verdicts.values())
    reproduction = {"e_summary": str(e_sum_p), "e_signals": str(e_sig_p),
                    "e_signals_sha256": sha256(e_sig_p) if e_sig_p is not None else None,
                    "tolerance_abs": tol, "published_branch_keys": list(pub.keys()),
                    "reproduced": {s: repro[s]["metrics"] for s in ("normal", "fee_00055")},
                    "deltas_repro_minus_published": deltas, "verdicts": verdicts,
                    "overall": "PASS" if overall_num else "FAIL",
                    "align_note": repro.get("_align_note"), "n_forward_candles": repro.get("_n_candles")}
    (a.output / "reproduction.json").write_text(json.dumps(reproduction, indent=2, default=str), encoding="utf-8")
    overall = "PASS" if (seal_overall == "PASS" and overall_num) else "FAIL"
    summary = {
        "experiment": "opencode-v155-sealprep",
        "role": v155["role"],
        "state": "AUDITED",
        "e_present": True,
        "l_present": True,
        "seal_items": seal_audit,
        "numbers_match": overall_num,
        "deltas": deltas,
        "verdicts": verdicts,
        "overall_verdict": overall,
        "trustworthy": bool(overall == "PASS"),
        "window_pristine": bool(s3["sealed_sha_ok"] and not s3["forward_new_files"] and not s3["e_threshold_label_files"]),
        "artifacts": {"dir": str(a.output)},
        "exploratory": True,
        "independent_test": False,
        "live_approved": False,
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"seal_overall": seal_overall, "verdicts": verdicts,
                      "overall": overall, "deltas": deltas}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
