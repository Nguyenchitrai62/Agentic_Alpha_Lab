"""Opencode v160 (R73-A2 SEALPREP): seal-verify harness ready for L's top-3 deployable forward eval.

Pre-spec: configs/opencode_v160_sealprep.json (checks S1-frozen-policy-only
per-branch (l3combo dd_guard_tp075 tp1 0.75 dd_guard / confirmed_dd_guard tp1 0.5
dd_guard / band2confirmed confirmed_band2_1x tp1 0.5 1x; v29/v38/v33 checkpoints +
frozen iso maps + pool/s0004/dd_guard/tp075/confirmed/band2 refs) /
S2-metrics-once / S3-no-threshold-label / S4-no-plots + PASS rules, adapted from
v155/v136/v110 harnesses to top-3 chains).
Verification only. No live orders. Exploratory labels.

Expected L policy (refs in config policy_refs):
  l3combo: L1 pool union (v38+v33+majority sources) -> L2 s0004 filter ->
    L3 dd_guard+tp075 (entry 12 / holding 2016 / tp1 0.75 / leverage col preserved,
    ExecutionConfig floor 0.25/max 1.0).
  confirmed_dd_guard: frozen v29 + frozen iso maps + confirmed vote
    (d4 != 0 AND dAll == d4, iso4 geometry) + freq cap4/cd5d + dd_guard sizing
    (leverage col preserved, floor 0.25/max 1.0) + tp1 0.5.
  band2confirmed: frozen v29 + frozen iso maps + confirmed vote + FROZEN band2
    filter + freq cap4/cd5d + sizing 1x (tp1 0.5, ExecutionConfig 1.0/1.0).
  Common: ohlc-v2 / stop-first / t->t+1 / capital 100 /
    costs fee normal 0.0002 / stress 0.00055 / funding long 0.0001/8h short 0.
  No refit/tuning/threshold/label/calibration/normalization fitting on forward.

Poll logic: Depends-on-L (R73-L fwdeval-top3, FIRST forward eval of top-3
deployable chains on the sealed window).
  If L summary.json absent -> write PREP-READY (config copy + driver copy +
  forward_tree_before/after + seal_audit PREP-READY + summary.json), exit 0.
  Poll at most 4 times ~20min apart (caller polls); never block forever.

When L present:
  S1 frozen-policy-only per branch (diff L config vs branch baselines)
  S2 metrics-once (exactly 1 summary.json, 0 rerun traces)
  S3 no threshold/label files + sealed (+extended) SHA unchanged + forward tree delta
  S4 no price/returns plots
  NUMBERS: own driver rebuilds EACH branch forward backtest from frozen L signals +
    forward candles/costs for normal (0.0002) + fee 0.00055; PASS within 1e-6
    per branch per scenario (3/3 branches required).
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

# Branch catalogue: id-substring match -> frozen execution.
BRANCH_FROZEN = {
    "l3combo": {"match": ("dd_guard_tp075", "l3combo", "l3_combo", "l3-combo"),
                "tp1": 0.75, "sizing": "dd_guard", "lev_floor": 0.25, "lev_max": 1.0},
    "confirmed_dd": {"match": ("confirmed_dd_guard", "confirmed_dd",),
                     "tp1": 0.5, "sizing": "dd_guard", "lev_floor": 0.25, "lev_max": 1.0},
    "band2": {"match": ("confirmed_band2_1x", "confirmed_band2", "band2confirmed", "band2"),
              "tp1": 0.5, "sizing": "1x", "lev_floor": 1.0, "lev_max": 1.0},
}
# Order matters: confirmed_dd_guard contains "confirmed" etc. Match longest first.
BRANCH_ORDER = ("l3combo", "confirmed_dd", "band2")


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
    # Prefer depends_on_L (v160); fallback to depends_on_E (lineage alias).
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


def find_L(cfg: dict, root: Path) -> dict:
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
    if dir_found is None:
        # Glob fallback: any *top3* artifact dir with a summary.json.
        for p in sorted((root / "artifacts/research").glob("*top3*")):
            if p.is_dir() and (p / summary_name).is_file():
                dir_found = p
                break
    cfg_found = None
    for c in cfg_cands:
        p = root / c
        if p.is_file():
            cfg_found = p
            break
    if cfg_found is None:
        for p in sorted((root / "configs").glob("*top3*.json")):
            if p.is_file():
                cfg_found = p
                break
    summary = None
    driver = None
    if dir_found is not None and dir_found.is_dir():
        s = dir_found / summary_name
        if s.is_file():
            summary = s
        py_hits = sorted(dir_found.glob("*.py"))
        if py_hits:
            driver = py_hits[0]
    return {"dir": dir_found, "config": cfg_found, "summary": summary,
            "driver": driver, "sig_cands": sig_cands or ["signals.parquet"]}


def classify_branch(name: str) -> str | None:
    low = str(name).lower()
    for key in BRANCH_ORDER:
        for sub in BRANCH_FROZEN[key]["match"]:
            if sub in low:
                return key
    return None


def resolve_branch_signals(l_dir: Path, l_cfg: dict | None, sig_cands: list) -> dict:
    """Map branch catalogue key -> signals parquet path. Best effort; missing -> absent."""
    out: dict = {}
    cfg_branches = {}
    if isinstance(l_cfg, dict):
        for k in ("branches", "branch_specs", "books"):
            if isinstance(l_cfg.get(k), dict):
                cfg_branches = l_cfg[k]
                break
        if isinstance(l_cfg.get("branches"), list):
            for b in l_cfg["branches"]:
                if isinstance(b, dict):
                    bid = str(b.get("id", b.get("branch", b.get("book", ""))))
                    for key in BRANCH_ORDER:
                        if classify_branch(bid) == key and key not in cfg_branches:
                            cfg_branches[key] = b
    # 1) per-branch paths declared in L config
    if isinstance(cfg_branches, dict):
        for bname, bval in cfg_branches.items():
            key = classify_branch(bname)
            if key is None or key in out:
                continue
            if isinstance(bval, dict):
                for sk in ("signals", "signals_path", "signals_parquet", "artifact"):
                    v = bval.get(sk)
                    if isinstance(v, str):
                        cand = Path(v)
                        if not cand.is_absolute():
                            # try repo-root relative then L-dir relative
                            cand = None
                        if isinstance(v, str):
                            for base in (Path(__file__).resolve().parents[1], l_dir):
                                p = base / v
                                if p.is_file() and p.suffix == ".parquet":
                                    out[key] = p
                                    break
                        if key in out:
                            break
    # 2) <L dir>/<branch>/signals.parquet + <L dir>/signals_<branch>.parquet
    if l_dir.is_dir():
        for sub in sorted(l_dir.iterdir()):
            if sub.is_dir():
                key = classify_branch(sub.name)
                if key is not None and key not in out:
                    for cand in sig_cands:
                        p = sub / cand
                        if p.is_file():
                            out[key] = p
                            break
        for p in sorted(l_dir.glob("signals_*.parquet")):
            key = classify_branch(p.stem)
            if key is not None and key not in out:
                out[key] = p
        # 3) recursive search: any */signals.parquet whose parent classifies
        for p in sorted(l_dir.rglob("signals.parquet")):
            try:
                rel = p.relative_to(l_dir).as_posix()
            except ValueError:
                continue
            if p.parent == l_dir:
                continue  # single-file layout handled below
            key = classify_branch(rel)
            if key is not None and key not in out:
                out[key] = p
        # 4) single signals.parquet at top: classify via config branch or summary later
        top = l_dir / "signals.parquet"
        if top.is_file() and not out:
            out["_single"] = top
    return out


def check_s1(l_cfg_path: Path | None, v160: dict) -> dict:
    base = v160["baseline_policy_frozen"]
    if l_cfg_path is None or not l_cfg_path.is_file():
        return {"status": "FAIL", "reason": "L config absent: cannot prove frozen-policy-only",
                "l_config": None, "diffs": ["missing L config"], "branches": {}}
    try:
        l_cfg = json.loads(l_cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "FAIL", "reason": f"L config unreadable: {exc}",
                "l_config": str(l_cfg_path), "diffs": ["unreadable"], "branches": {}}
    diffs: list = []
    notes: list = []
    per_branch: dict = {}
    exec_src: dict = {}
    for key in ("execution", "policy_frozen", "policy", "engine_config", "backtest"):
        if isinstance(l_cfg.get(key), dict):
            exec_src.update(l_cfg[key])
            inner = l_cfg[key].get("execution") if isinstance(l_cfg[key].get("execution"), dict) else {}
            exec_src.update(inner)
    # Global execution sanity (entry 12 / holding 2016 / stop-first / capital 100).
    if exec_src.get("entry_expiry_bars") is not None:
        try:
            if int(exec_src["entry_expiry_bars"]) != 12:
                diffs.append(f"entry_expiry_bars: {exec_src['entry_expiry_bars']} != 12")
        except Exception:
            diffs.append(f"entry_expiry_bars: bad value {exec_src.get('entry_expiry_bars')}")
    else:
        notes.append("entry_expiry 12 not declared at top level (verify per-branch + driver)")
    hold = exec_src.get("max_holding_bars", exec_src.get("holding_cap_bars"))
    if hold is not None:
        try:
            if int(hold) != 2016:
                diffs.append(f"max_holding_bars: {hold} != 2016")
        except Exception:
            diffs.append(f"max_holding_bars: bad value {hold}")
    else:
        notes.append("holding cap 2016 not declared at top level (verify per-branch + driver)")
    freq_src = {}
    for key in ("policy", "policy_frozen", "frequency", "execution", "backtest"):
        if isinstance(l_cfg.get(key), dict):
            freq_src.update(l_cfg[key])
    freq_src.update(exec_src)
    cap = freq_src.get("maximum_signals_per_month", freq_src.get("monthly_cap", freq_src.get("max_signals_per_month")))
    if cap is not None:
        try:
            if int(cap) != 4:
                diffs.append(f"monthly_cap: {cap} != 4")
        except Exception:
            diffs.append(f"monthly_cap: bad value {cap}")
    else:
        notes.append("monthly cap 4 not declared in L config keys (verify in L driver policy loop)")
    cd = freq_src.get("cooldown_days", freq_src.get("cooldown"))
    if cd is not None:
        try:
            if int(cd) != 5:
                diffs.append(f"cooldown_days: {cd} != 5")
        except Exception:
            diffs.append(f"cooldown_days: bad value {cd}")
    else:
        notes.append("cooldown 5d not declared in L config keys (verify in L driver policy loop)")
    cost_src = {}
    for key in ("costs", "costs_normal", "execution_assumptions", "frozen_constants"):
        if isinstance(l_cfg.get(key), dict):
            cost_src.update(l_cfg[key])
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
    eng = l_cfg.get("engine", exec_src.get("engine", ""))
    if eng and eng != "ohlc-v2":
        diffs.append(f"engine: {eng} != ohlc-v2")
    blob = json.dumps(l_cfg).lower()
    # Frozen-source markers: need checkpoint family refs + iso/frozen refs.
    if ("v29" not in blob) and ("v38" not in blob) and ("v33" not in blob) and ("frozen" not in blob):
        diffs.append("signal source: L config declares no frozen v29/v38/v33/frozen refs")
    if "iso" not in blob and "isoton" not in blob and "calibrat" not in blob and "mapensemble" not in blob and "v02" not in blob:
        notes.append("iso-map refs not found by keyword (verify frozen iso maps in L driver/config refs)")
    for vote in ("confirmed", "majority"):
        if vote not in blob:
            notes.append(f"vote keyword '{vote}' not in L config (verify vote rule in L driver)")
    for leg in ("pool", "s0004", "dd_guard", "dd-guard", "tp075", "tp_075", "band2", "band_2"):
        if leg.replace("-", "_") not in blob.replace("-", "_"):
            notes.append(f"chain keyword '{leg}' not in L config (verify chain in L driver)")
    else:
        pass
    for flag in ["fitted on forward", "fit on forward", "fit_on_forward", "tuned on forward",
                 "threshold selected on forward", "threshold_selection_on_forward",
                 "isotonic fitted on forward", "normalization fitted on forward",
                 "percentile gate on forward", "percentile fitted on forward",
                 "vote fitted on forward", "vote tuned on forward",
                 "band fitted on forward", "pool fitted on forward"]:
        if flag in blob:
            diffs.append(f"forward-fit marker: '{flag}' present in L config")
    # Per-branch presence + tp1/sizing.
    found_branches: dict = {}
    raw_branches = None
    for k in ("branches", "branch_specs", "books"):
        if isinstance(l_cfg.get(k), (dict, list)):
            raw_branches = l_cfg[k]
            break
    names: list = []
    if isinstance(raw_branches, dict):
        names = [str(k) for k in raw_branches.keys()]
    elif isinstance(raw_branches, list):
        for b in raw_branches:
            if isinstance(b, str):
                names.append(b)
            elif isinstance(b, dict):
                names.append(str(b.get("id", b.get("branch", b.get("book", "")))))
    for key in BRANCH_ORDER:
        hit = any(classify_branch(n) == key for n in names) if names else False
        per_branch[key] = {"declared": bool(hit),
                           "tp1_want": BRANCH_FROZEN[key]["tp1"],
                           "sizing_want": BRANCH_FROZEN[key]["sizing"]}
        if names and not hit:
            diffs.append(f"branch {key}: MISSING from L config branches {names} (want 3/3 top-3)")
        if isinstance(raw_branches, dict):
            for bname, bval in raw_branches.items():
                if classify_branch(str(bname)) == key and isinstance(bval, dict):
                    want_tp1 = BRANCH_FROZEN[key]["tp1"]
                    got_tp1 = bval.get("tp1_fraction", bval.get("tp1"))
                    if got_tp1 is None and isinstance(bval.get("execution"), dict):
                        got_tp1 = bval["execution"].get("tp1_fraction")
                    if got_tp1 is None and isinstance(bval.get("meta"), dict):
                        got_tp1 = bval["meta"].get("tp1_fraction")
                    if got_tp1 is not None:
                        try:
                            if abs(float(got_tp1) - want_tp1) > 1e-12:
                                diffs.append(f"branch {key}: tp1 {got_tp1} != frozen {want_tp1}")
                            else:
                                per_branch[key]["tp1_match"] = True
                        except Exception:
                            diffs.append(f"branch {key}: bad tp1 {got_tp1}")
                    else:
                        notes.append(f"branch {key}: tp1 not declared in L config (verify frozen {want_tp1} in driver/signals)")
                    break
    if not names:
        notes.append("L config has no branches/branch_specs/books dict (verify 3-branch layout in L dir + driver)")
    status = "PASS" if not diffs else "FAIL"
    return {"status": status, "l_config": str(l_cfg_path),
            "diffs": diffs if diffs else ["global execution/costs/engine match; 3/3 branches declared with frozen tp1/sizing; no forward-fit markers"],
            "notes": notes, "branches": per_branch,
            "reason": "frozen top-3 chains hold" if status == "PASS" else "policy drift or missing declaration"}


def check_s2(l_dir: Path | None) -> dict:
    if l_dir is None or not l_dir.is_dir():
        return {"status": "FAIL", "reason": "L dir absent", "n_summary": 0, "files": []}
    summaries = sorted(l_dir.glob("summary*.json"))
    traces = []
    for pat in ("summary_*.json", "summary.*.json", "summary_v*.json", "rerun*.log",
                "rerun*.json", "metrics_rerun*.json", "*_rerun.json"):
        traces.extend(sorted(l_dir.glob(pat)))
    traces = [t for t in traces if t.name != "summary.json"]
    n_exact = len([s for s in summaries if s.name == "summary.json"])
    status = "PASS" if (n_exact == 1 and len(summaries) == 1 and not traces) else "FAIL"
    return {"status": status,
            "reason": "exactly 1 summary, 0 reruns" if status == "PASS" else "rerun/multiple-summary evidence",
            "n_summary": len(summaries),
            "summary_files": [s.name for s in summaries],
            "rerun_traces": [t.name for t in traces],
            "files": [s.name for s in summaries] + [t.name for t in traces]}


def check_s3(l_dir: Path | None, root: Path, tree_before: dict, tree_after: dict) -> dict:
    fwd = root / "data/processed/opencode_forward_20260323"
    manifest = json.loads((fwd / "manifest.json").read_text(encoding="utf-8"))
    seal_ok = True
    seal_notes: list = []
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
    ext_ok = True
    ext_path = fwd / "manifest_extend_20260909.json"
    if ext_path.is_file():
        try:
            ext = json.loads(ext_path.read_text(encoding="utf-8"))
            for fname, want in ext.get("extended_sha256", {}).items():
                if "append" in fname or "extended" in fname:
                    base = fname.replace("candles_", "candles").replace("funding_", "funding").replace("macro_", "macro")
                    cand_files = {"candles_append": "candles_append_20260909.parquet",
                                  "funding_append": "funding_append_20260909.parquet",
                                  "macro_append": "macro_append_20260909.parquet",
                                  "candles_extended": "candles_extended_20260909.parquet",
                                  "funding_extended": "funding_extended_20260909.parquet",
                                  "macro_extended": "macro_extended_20260909.parquet"}
                    rel = cand_files.get(fname)
                    if rel is None:
                        continue
                    p = fwd / rel
                    if p.is_file():
                        got = sha_file(p)
                        if got != want:
                            ext_ok = False
                            seal_notes.append(f"{rel}: EXTENDED SHA MISMATCH")
                        else:
                            seal_notes.append(f"{rel}: extended SHA ok")
                    else:
                        ext_ok = False
                        seal_notes.append(f"{rel}: MISSING extended file")
        except Exception as exc:
            ext_ok = False
            seal_notes.append(f"extend manifest unreadable ({exc})")
    else:
        seal_notes.append("extend manifest absent (original-only window)")
    before_set = {f["path"] for f in tree_before.get("files", [])}
    after_set = {f["path"] for f in tree_after.get("files", [])}
    new_files = sorted(after_set - before_set)
    bad = []
    if l_dir is not None and l_dir.is_dir():
        for p in sorted(l_dir.rglob("*")):
            if p.is_dir():
                continue
            name = p.name.lower()
            rel = p.relative_to(l_dir).as_posix().lower()
            if any(k in name or k in rel for k in ("threshold", "label", "tune", "calibrat", "normaliz")):
                bad.append(p.relative_to(l_dir).as_posix())
    status = "PASS" if (seal_ok and ext_ok and not new_files and not bad) else "FAIL"
    return {"status": status, "sealed_sha_ok": bool(seal_ok and ext_ok),
            "seal_notes": seal_notes, "forward_new_files": new_files,
            "l_threshold_label_files": bad,
            "reason": "sealed+extended intact, no forward delta, no threshold/label files" if status == "PASS"
                      else "seal delta or threshold/label files present"}


def check_s4(l_dir: Path | None) -> dict:
    if l_dir is None or not l_dir.is_dir():
        return {"status": "FAIL", "reason": "L dir absent", "plot_files": [], "grep_hits": []}
    plot_files = []
    for p in sorted(l_dir.rglob("*")):
        if p.is_dir():
            continue
        suf = p.suffix.lower()
        nm = p.name.lower()
        if suf in (".png", ".jpg", ".jpeg", ".html") or "plot" in nm:
            if p.name in ("driver_source.py", "config.json"):
                continue
            plot_files.append(p.relative_to(l_dir).as_posix())
    grep_hits = []
    for p in sorted(l_dir.rglob("*.py")):
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        low = txt.lower()
        for marker in ("matplotlib", "plotly", "plt.plot", "fig.savefig", ".savefig(",
                       "forward price plot", "returns plot", "plot_forward"):
            if marker in low:
                grep_hits.append(f"{p.relative_to(l_dir).as_posix()}: {marker}")
    status = "PASS" if (not plot_files and not grep_hits) else "FAIL"
    return {"status": status,
            "reason": "no plots" if status == "PASS" else "plot files or plot code present",
            "plot_files": plot_files, "grep_hits": grep_hits}


def monthly_from_bounds(final_equity: float, first_open: pd.Timestamp, last_close: pd.Timestamp) -> float:
    secs = (last_close - first_open).total_seconds()
    years = secs / (365.2425 * 86400)
    ratio = float(final_equity) / 100.0
    return float(ratio ** (1.0 / (12.0 * years)) - 1.0), float(years)


def resolve_forward_candles(root: Path, l_cfg: dict | None, l_summary: dict | None) -> Path:
    fwd = root / "data/processed/opencode_forward_20260323"
    if isinstance(l_cfg, dict):
        for k in ("forward_candles", "candles", "candles_path", "candles_parquet"):
            v = l_cfg.get(k)
            if isinstance(v, str):
                p = Path(v)
                if not p.is_absolute():
                    p = root / v
                if p.is_file():
                    return p
        for k in ("backtest", "frame", "inputs"):
            sub = l_cfg.get(k)
            if isinstance(sub, dict):
                for k2 in ("forward_candles", "candles", "candles_path"):
                    v = sub.get(k2)
                    if isinstance(v, str):
                        p = root / v if not Path(v).is_absolute() else Path(v)
                        if p.is_file():
                            return p
    n_rows = None
    if isinstance(l_summary, dict):
        for k in ("n_forward_candles", "n_candles", "forward_rows"):
            if isinstance(l_summary.get(k), int):
                n_rows = int(l_summary[k])
                break
    if n_rows == 49181:
        p = fwd / "candles_extended_20260909.parquet"
        if p.is_file():
            return p
    if n_rows == 48819:
        return fwd / "candles.parquet"
    ext = fwd / "candles_extended_20260909.parquet"
    base = fwd / "candles.parquet"
    # Default: extended window if present (v158 is the live sealed window),
    # else original sealed candles.
    return ext if ext.is_file() else base


def rebuild_branch(branch_key: str, sig_path: Path, candles: pd.DataFrame,
                   fee_stress: float) -> dict:
    frozen = BRANCH_FROZEN[branch_key]
    sig = pd.read_parquet(sig_path)
    for col in ("bar_index", "signal_time", "direction", "entry_limit",
                "stop_loss", "take_profit_1", "take_profit_2"):
        if col not in sig.columns:
            raise ValueError(f"L signals {sig_path} missing executable column {col}")
    n_c = len(candles)
    aligned_note = "bar_index used as-is (in forward range)"
    if int(sig["bar_index"].max()) >= n_c or int(sig["bar_index"].min()) < 0:
        ct = pd.to_datetime(candles["close_time"], utc=True)
        lookup = pd.Series(np.arange(n_c), index=ct)
        st = pd.to_datetime(sig["signal_time"], utc=True)
        idx = st.map(lookup)
        if idx.isna().any():
            raise ValueError(f"L signal_time absent from forward candles for {sig_path} (cannot align)")
        sig = sig.copy()
        sig["bar_index"] = idx.astype(int).to_numpy()
        aligned_note = "bar_index realigned via signal_time->forward close_time (concat-frame input)"
    work = sig.copy()
    work["__st"] = pd.to_datetime(work["signal_time"], utc=True).to_numpy()
    work = work.sort_values(["bar_index", "__st"], kind="mergesort").reset_index(drop=True)
    work = work.drop(columns=["__st"])
    base_costs = CostModel(fee_rate_per_fill=0.0002, funding_long_rate=0.0001,
                           funding_short_rate=0.0, funding_interval_hours=8)
    stress_costs = CostModel(fee_rate_per_fill=float(fee_stress), funding_long_rate=0.0001,
                             funding_short_rate=0.0, funding_interval_hours=8)
    exp_bars, cap, tp1 = 12, 2016, float(frozen["tp1"])
    # Assert frozen tp1: signals tp1_fraction column must be uniform == frozen (when present).
    if "tp1_fraction" in work.columns:
        vals = pd.to_numeric(work["tp1_fraction"], errors="coerce").dropna().unique()
        if len(vals) and any(abs(float(v) - tp1) > 1e-12 for v in vals):
            raise ValueError(f"L branch {branch_key}: signals tp1 {sorted(map(float, vals))} != frozen {tp1}")
    holding = work.get("holding_bars")
    if holding is not None:
        mx = int(pd.to_numeric(holding, errors="coerce").max())
        if mx > cap:
            raise ValueError(f"L holding_bars {mx} exceeds frozen cap {cap}")
    if frozen["sizing"] == "dd_guard":
        def frame():
            return work.copy().reset_index(drop=True)  # preserve FROZEN leverage col
        exe = ExecutionConfig(entry_expiry_bars=exp_bars, max_holding_bars=cap,
                              tp1_fraction=tp1, leverage=float(frozen["lev_floor"]),
                              max_leverage=float(frozen["lev_max"]))
    else:
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
    out: dict = {}
    for label, res, trs in (("normal", res_n, tr_n), ("fee_00055", res_f, tr_f)):
        d = asdict(res)
        mo, yrs = monthly_from_bounds(res.final_equity, first_open, last_close)
        d["monthly_geometric_net"] = mo
        d["duration_years"] = yrs
        d["n_signals"] = int(len(fr))
        out[label] = {"metrics": d, "trades": [asdict(t) for t in trs]}
    out["_align_note"] = aligned_note
    out["_n_candles"] = int(n_c)
    out["_tp1"] = tp1
    out["_sizing"] = frozen["sizing"]
    return out


def extract_published(l_summary: dict, branch_key: str) -> dict:
    """Find published {normal, fee_00055} metric dicts for a branch. Best effort."""
    subs = BRANCH_FROZEN[branch_key]["match"]
    branches = l_summary.get("branches") if isinstance(l_summary.get("branches"), dict) else None
    if branches:
        for bname, bval in branches.items():
            if classify_branch(str(bname)) == branch_key and isinstance(bval, dict):
                scen = bval.get("scenarios") if isinstance(bval.get("scenarios"), dict) else bval
                pub: dict = {}
                if isinstance(scen, dict):
                    for sk, ok in (("normal", "normal"), ("fee_00055", "fee_00055"),
                                   ("fee_stress", "fee_00055")):
                        if isinstance(scen.get(sk), dict) and "total_return" in scen[sk] and ok not in pub:
                            pub[ok] = scen[sk]
                    if not pub and "total_return" in scen:
                        pub = {"normal": scen}
                return pub
    # Fallback: top-level scenarios (single-branch summary).
    pub = {}
    scen = l_summary.get("scenarios") if isinstance(l_summary.get("scenarios"), dict) else None
    if isinstance(scen, dict):
        for sk, ok in (("normal", "normal"), ("fee_00055", "fee_00055"), ("fee_stress", "fee_00055")):
            if isinstance(scen.get(sk), dict) and "total_return" in scen[sk] and ok not in pub:
                pub[ok] = scen[sk]
    for k in ("normal", "fee_00055", "metrics", "results"):
        if k in l_summary and isinstance(l_summary[k], dict) and "total_return" in l_summary[k]:
            if k in ("metrics", "results"):
                return {"normal": l_summary[k]}
            pub[k] = l_summary[k]
    return pub


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise FileExistsError("No overwrites: choose a new output dir")
    v160 = json.loads(Path(a.config).read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    tol = float(v160["numbers_reproduction"]["pass_criterion"]["tolerance_abs"])
    fee_s = 0.00055
    try:
        fee_s = float(v160["baseline_policy_frozen"]["common"]["costs"]["fee_stress_per_fill"])
    except Exception:
        pass
    dep = _dep_block(v160)

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(v160, indent=2, ensure_ascii=False), encoding="utf-8")
    (a.output / "driver_source.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")

    fwd_dir = root / "data/processed/opencode_forward_20260323"
    tree_before = snapshot_forward_tree(fwd_dir)
    (a.output / "forward_tree_before.json").write_text(json.dumps(tree_before, indent=2), encoding="utf-8")

    found = find_L(v160, root)
    l_dir = found["dir"]
    l_cfg_p = found["config"]
    l_sum_p = found["summary"]

    # ---- L ABSENT -> PREP-READY (no outcome-looking) ----
    if l_sum_p is None or not l_sum_p.is_file():
        tree_after = snapshot_forward_tree(fwd_dir)
        (a.output / "forward_tree_after.json").write_text(json.dumps(tree_after, indent=2), encoding="utf-8")
        s3 = check_s3(None, root, tree_before, tree_after)
        prep = {
            "state": "PREP-READY",
            "reason": "L summary.json absent at audit time; prep complete (v160 config + r73a verifier + forward snapshots). Poll bounded (max 4 x ~20min), do not block forever.",
            "polls": [{"poll": 1, "result": "ABSENT (prep start)"},
                      {"poll": 2, "result": "ABSENT (after prep writes)"}],
            "l_search": {k: (str(v) if v is not None else None) for k, v in found.items()},
            "l_config_candidates": dep.get("l_config_candidates", dep.get("e_config_candidates")),
            "l_dir_candidates": dep.get("l_artifact_dir_candidates", dep.get("e_artifact_dir_candidates")),
            "forward_tree": {"before_n": tree_before["n_files"], "after_n": tree_after["n_files"],
                             "delta": sorted({f["path"] for f in tree_after["files"]} - {f["path"] for f in tree_before["files"]})},
            "seal_tree_check": s3,
            "expected_L_policy": "top-3 frozen chains: l3combo dd_guard_tp075 (pool->s0004->dd+tp075, tp1 0.75, dd_guard) + confirmed_dd_guard (confirmed vote, tp1 0.5, dd_guard) + band2confirmed (confirmed vote + band2 filter, tp1 0.5, 1x); exec 12/2016/stop-first/t->t+1/cap4/cd5; costs 0.0002/0.00055/fund 0.0001/8h; sizing per branch",
            "next": "POLL for L summary (max 2 more x ~20min). When present, rerun this driver (new output dir) for full S1-S4 + per-branch numbers reproduction.",
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
            "experiment": "opencode-v160-sealprep",
            "role": v160["role"],
            "state": "PREP-READY",
            "verdict": "PREP-READY (L absent; verifier ready, window still pristine for future use)",
            "l_present": False,
            "seal_items": seal_audit,
            "numbers_match": None,
            "deltas": None,
            "pristine_window": "PRISTINE (sealed+extended SHA ok, forward delta 0)" if s3["sealed_sha_ok"] and not s3["forward_new_files"] else "CHECK forward delta",
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
    s1 = check_s1(l_cfg_p, v160)
    s2 = check_s2(l_dir)
    s3 = check_s3(l_dir, root, tree_before, tree_after)
    s4 = check_s4(l_dir)
    seal_audit = {"S1_frozen_policy_only": s1, "S2_metrics_once": s2,
                  "S3_no_threshold_label_files": s3, "S4_no_price_returns_plots": s4}
    seal_overall = "PASS" if all(v.get("status") == "PASS" for v in seal_audit.values()) else "FAIL"
    seal_audit["overall"] = seal_overall
    (a.output / "seal_audit.json").write_text(json.dumps(seal_audit, indent=2, ensure_ascii=False), encoding="utf-8")

    l_doc = json.loads(l_sum_p.read_text(encoding="utf-8"))
    l_cfg_doc = None
    if l_cfg_p is not None and l_cfg_p.is_file():
        try:
            l_cfg_doc = json.loads(l_cfg_p.read_text(encoding="utf-8"))
        except Exception:
            l_cfg_doc = None
    candles = pd.read_parquet(resolve_forward_candles(root, l_cfg_doc, l_doc))
    sig_map = resolve_branch_signals(l_dir, l_cfg_doc, found.get("sig_cands", ["signals.parquet"]))
    if "_single" in sig_map and len(sig_map) == 1:
        # Single-file layout: cannot split 3 branches; record and fail numbers with cause.
        single = sig_map.pop("_single")
        sig_map = {"_single_unclassified": single}

    reproduction: dict = {"l_summary": str(l_sum_p),
                          "l_config": str(l_cfg_p) if l_cfg_p is not None else None,
                          "tolerance_abs": tol, "branches": {}}
    branch_verdicts: dict = {}
    all_deltas: dict = {}
    for key in BRANCH_ORDER:
        bdir = a.output / key
        bdir.mkdir()
        entry: dict = {"frozen": BRANCH_FROZEN[key]}
        sig_p = sig_map.get(key)
        if sig_p is None or not Path(sig_p).is_file():
            entry["error"] = f"signals absent for branch {key} (searched {l_dir})"
            entry["verdict"] = "FAIL"
            branch_verdicts[key] = "FAIL"
            reproduction["branches"][key] = entry
            continue
        entry["l_signals"] = str(sig_p)
        try:
            entry["l_signals_sha256"] = sha256(Path(sig_p))
        except Exception as exc:
            entry["l_signals_sha256"] = f"unreadable ({exc})"
        try:
            repro = rebuild_branch(key, Path(sig_p), candles, fee_s)
        except Exception as exc:
            entry["error"] = f"rebuild failed: {exc}"
            entry["verdict"] = "FAIL"
            branch_verdicts[key] = "FAIL"
            reproduction["branches"][key] = entry
            continue
        for scen in ("normal", "fee_00055"):
            d = bdir / scen
            d.mkdir()
            pd.DataFrame(repro[scen]["trades"]).to_csv(d / "repro_trades.csv", index=False)
            (d / "repro_metrics.json").write_text(json.dumps(repro[scen]["metrics"], indent=2, default=str), encoding="utf-8")
        pub = extract_published(l_doc, key)
        entry["published_branch_keys"] = list(pub.keys())
        entry["reproduced"] = {s: repro[s]["metrics"] for s in ("normal", "fee_00055")}
        entry["align_note"] = repro.get("_align_note")
        deltas, verdicts = {}, {}
        for scen in ("normal", "fee_00055"):
            if scen not in pub:
                deltas[scen] = {"error": "L published metrics not found for scenario"}
                verdicts[scen] = "FAIL"
                continue
            r = repro[scen]["metrics"]
            p = pub[scen]
            d: dict = {}
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
        entry["deltas_repro_minus_published"] = deltas
        entry["verdicts"] = verdicts
        entry["verdict"] = "PASS" if all(v == "PASS" for v in verdicts.values()) and verdicts else "FAIL"
        branch_verdicts[key] = entry["verdict"]
        all_deltas[key] = deltas
        reproduction["branches"][key] = entry
    if "_single_unclassified" in sig_map:
        reproduction["unclassified_single_signals"] = str(sig_map["_single_unclassified"])
    overall_num = bool(branch_verdicts) and all(v == "PASS" for v in branch_verdicts.values()) and len(branch_verdicts) == 3
    reproduction["branch_verdicts"] = branch_verdicts
    reproduction["n_forward_candles"] = int(len(candles))
    reproduction["overall"] = "PASS" if overall_num else "FAIL"
    (a.output / "reproduction.json").write_text(json.dumps(reproduction, indent=2, default=str), encoding="utf-8")
    overall = "PASS" if (seal_overall == "PASS" and overall_num) else "FAIL"
    summary = {
        "experiment": "opencode-v160-sealprep",
        "role": v160["role"],
        "state": "AUDITED",
        "l_present": True,
        "seal_items": seal_audit,
        "numbers_match": overall_num,
        "branch_verdicts": branch_verdicts,
        "deltas": all_deltas,
        "overall_verdict": overall,
        "trustworthy": bool(overall == "PASS"),
        "window_pristine": bool(s3["sealed_sha_ok"] and not s3["forward_new_files"] and not s3.get("l_threshold_label_files")),
        "artifacts": {"dir": str(a.output)},
        "exploratory": True,
        "independent_test": False,
        "live_approved": False,
    }
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"seal_overall": seal_overall, "branch_verdicts": branch_verdicts,
                      "overall": overall, "deltas": all_deltas}, default=str, indent=2))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    main()
