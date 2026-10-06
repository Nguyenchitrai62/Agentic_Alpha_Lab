"""Opencode R78 W2: real-model non-WAIT pipeline evidence (ONE dev interval).

RESEARCH/PAPER ONLY. Exploratory. No live orders, no cloud, no training/
fitting/tuning, no threshold/architecture/frequency/ensemble changes.

Pre-spec: configs/opencode_r78_nonwait.json (written BEFORE this script ran;
interval + policy refs + SHAs frozen before execution).

Tested (raw-model) path -- actual runner path, denied stored artifacts:
  closed candles -> core.infer_full (real checkpoint forward, fail-closed)
  -> AdvisorStrategy replay stream (incremental FeedExecAccount fills/equity).
Independent batch reference (harness-only, runs AFTER the raw path):
  own forward invocation + own gates -> verbatim ohlc-v2 run_backtest 1x.
Chunk/restart: split at boundary bar, snapshot, resume, assert identity.

torch is imported before pandas (Windows DLL load-order rule).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import opencode_r76_infer as r76  # noqa: E402
import opencode_r77_advisor_core as core  # noqa: E402
import opencode_r76_feedexec as fx  # noqa: E402
from agentic_alpha_lab.backtest.engine import (  # noqa: E402
    CostModel, ExecutionConfig, run_backtest)
from agentic_alpha_lab.data.sequence_context import encode_windows  # noqa: E402
from agentic_alpha_lab.data.swing import choose, grid  # noqa: E402
from agentic_alpha_lab.data.training import validate_source  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.models.residual_temporal_value import (  # noqa: E402
    residual_predict)
from safetensors.torch import load_file  # noqa: E402

SPEC_PATH = ROOT / "configs" / "opencode_r78_nonwait.json"
RUNNER_CONFIG_PATH = ROOT / "configs" / "opencode_r77_advisor.json"
OUT_DIR = ROOT / "artifacts" / "research" / "opencode_r78_rolling" / "w2"

# The tested raw-model path must never load these. The harness-only batch
# reference below is explicitly allowed (it runs strictly after the raw path;
# runtime order is asserted and recorded in provenance.json).
FORBIDDEN_FOR_RAW = [
    r"predictions\.npz",
    r"replay\.npz",
    r"signals\.parquet",
    r"decisions\.parquet",
    r"decision_indices",
    r"control.*\.(csv|parquet)",
    r"normal_trades\.csv",
    r"baseline_trades",
]
_REFERENCE_LOADED = {"flag": False, "what": [], "raw_done": False}


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha_lf(path: Path) -> str:
    """SHA256 with line endings normalised to LF.

    Git-tracked text files (configs/*.json, scripts/*.py) are committed
    with LF, but core.autocrlf converts them to CRLF on a Windows
    checkout, so the raw working-tree bytes hash differently from the
    frozen (committed LF) bytes. Normalising CRLF->LF (and lone CR->LF)
    before hashing recovers the canonical bytes. Frozen SHA values are
    unchanged: they already are the committed LF bytes.
    """
    raw = Path(path).read_bytes()
    norm = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(norm).hexdigest()


def _matches_frozen(path: Path, want: str) -> bool:
    """True if the raw or the LF-normalised bytes match the frozen SHA.

    Accepts both so tracked text verifies on LF checkouts (raw matches)
    and CRLF checkouts (normalised matches). Binary checkpoints
    (.safetensors) keep strict raw comparison at their call site: they
    are git-ignored (no autocrlf conversion) and may contain natural
    CRLF bytes, so normalising them would corrupt the comparison. The
    same holds for git-ignored JSON artifacts whose frozen SHAs were
    recorded on the working bytes as-is (raw matches there too).
    """
    return _sha(path) == want or _sha_lf(path) == want


def load_prespec() -> dict:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["experiment"] == "opencode-r78-W2-nonwait-pipeline"
    assert spec["status"].startswith("PRE-SPEC")
    assert spec["frozen_policy"]["cooldown_days"] == 5
    assert spec["frozen_policy"]["frequency_cap_per_month"] == 4
    assert spec["execution"]["entry_expiry_bars"] == 12
    assert spec["execution"]["max_holding_bars"] == 2016
    assert spec["execution"]["tp1_fraction"] == 0.5
    return spec


def verify_frozen(spec: dict) -> dict:
    """SHA-verify every frozen asset against the pre-spec (fail-closed)."""
    fp = spec["frozen_policy"]
    recs = {}
    rc = fp["research_config"]
    assert _matches_frozen(ROOT / rc["path"], rc["sha256"]), \
        "research config drift"
    recs["research_config"] = rc["sha256"][:16]
    for rel, want in zip(fp["checkpoints"]["paths"],
                         fp["checkpoints"]["sha256"]):
        assert _sha(ROOT / rel) == want, f"checkpoint drift: {rel}"
    recs["checkpoints"] = [s[:16] for s in fp["checkpoints"]["sha256"]]
    for key in ("iso2", "iso4", "isoall"):
        m = fp["calibrators"][key]
        assert _matches_frozen(ROOT / m["path"], m["sha256"]), \
            f"calibrator drift {key}"
    recs["calibrators"] = {k: fp["calibrators"][k]["sha256"][:16]
                           for k in ("iso2", "iso4", "isoall")}
    assert _matches_frozen(RUNNER_CONFIG_PATH, fp["runner_config_sha256"]), \
        "runner config drift"
    for name, rel, key in (
            ("infer", "scripts/opencode_r76_infer.py", "infer_sha256"),
            ("core", "scripts/opencode_r77_advisor_core.py", "core_sha256"),
            ("feedexec", "scripts/opencode_r76_feedexec.py",
             "feedexec_sha256")):
        assert _matches_frozen(ROOT / rel, spec["runner_path"][key]), \
            f"{name} drift"
    recs["runner"] = "ok"
    return recs


def audit_runner_sources() -> dict:
    """Two-leg denial audit for the TESTED raw-model path.

    Leg 1 (static): scan the runner sources for stored-artifact loads.
      Naive pattern hits are reported with line numbers and classified:
      - REPLAY_INPUT_KEYS deny-list constant + own-output writes are benign
        mentions, not loads.
      - scripts/opencode_r76_feedexec.py main() keeps a legacy replay CLI
        branch (read_parquet of --signals at L742-743) which the W2 tested
        path never invokes (asserted in leg 2).
    Leg 2 (call-graph): this script must not reference the legacy replay
      entry points (feedexec.main / run_replay / --signals).
    Leg 3 (runtime order): the harness reference section runs strictly after
      run_raw_path (asserted at runtime; recorded in provenance.json).
    """
    compiled = [(p, re.compile(p)) for p in FORBIDDEN_FOR_RAW]
    hits: dict[str, list[str]] = {}
    for rel in ("scripts/opencode_r76_infer.py",
                "scripts/opencode_r77_advisor_core.py",
                "scripts/opencode_r76_feedexec.py"):
        lines = (ROOT / rel).read_text(encoding="utf-8",
                                       errors="replace").splitlines()
        found = []
        for i, ln in enumerate(lines, 1):
            for p, rx in compiled:
                if rx.search(ln):
                    found.append(f"L{i}:{p}:{ln.strip()[:160]}")
                    break
        hits[rel] = found
    load_rx = re.compile(
        r"read_parquet|read_csv|np\.load|joblib|pickle\.load")
    loads: dict[str, list[str]] = {}
    for rel in ("scripts/opencode_r76_infer.py",
                "scripts/opencode_r77_advisor_core.py"):
        lines = (ROOT / rel).read_text(encoding="utf-8",
                                       errors="replace").splitlines()
        loads[rel] = [f"L{i}:{ln.strip()[:160]}" for i, ln in
                      enumerate(lines, 1) if load_rx.search(ln)]
    own_lines = (ROOT / "scripts" / "opencode_r78_nonwait.py").read_text(
        encoding="utf-8").splitlines()
    # Exclude the audit function's own body (self-mentions live there).
    in_audit, code_lines = False, []
    for ln in own_lines:
        if ln.startswith("def audit_runner_sources"):
            in_audit = True
        elif ln.startswith("def ") and in_audit:
            in_audit = False
        if not in_audit:
            code_lines.append(ln)
    code = "\n".join(code_lines)
    legacy_calls = sorted({
        s for s, rx in (
            ("feedexec.main()", re.compile(r"feedexec\.main\s*\(")),
            ("fx.main()", re.compile(r"(?<![\w.])fx\.main\s*\(")),
            ("run_replay(", re.compile(r"run_replay\s*\(")),
            ("--signals", re.compile(r"--signals")),
            ("a.signals", re.compile(r"a\.signals")),
        ) if rx.search(code)})
    # core/r76 must carry ZERO stored-artifact loads except the frozen
    # checkpoint safetensors loader (load_file on ckpt paths only).
    non_ckpt_loads = [ln for ln in loads["scripts/opencode_r76_infer.py"]
                      if "load_file(str(ckpt))" not in ln]
    verdict = bool(len(non_ckpt_loads) == 0
                   and len(loads["scripts/opencode_r77_advisor_core.py"]) == 0
                   and len(legacy_calls) == 0)
    return {"pattern_hits": hits, "loader_lines": loads,
            "legacy_replay_calls_in_w2": legacy_calls,
            "non_checkpoint_loads_in_infer": non_ckpt_loads,
            "note": "feedexec legacy replay branch (main, L740-753) loads "
                    "--signals but is never invoked by the W2 path; W2 "
                    "drives fx.FeedExecAccount via AdvisorStrategy with "
                    "core.infer_full rows only",
            "pass": verdict}


def load_slice_candles(spec: dict) -> pd.DataFrame:
    full = pd.read_parquet(ROOT / spec["interval"]["candle_source"])
    m = re.match(r"\[(\d+),\s*(\d+)\)", spec["interval"]["candle_bars"])
    lo, hi = int(m.group(1)), int(m.group(2))
    df = full.iloc[lo:hi].reset_index(drop=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df


# ------------------------------------------------------- raw path ---
def run_raw_path(df: pd.DataFrame, rspec: dict) -> tuple[list[dict], dict]:
    """Tested path: real checkpoint inference on observed candles ONLY.

    Refuses if the harness reference section already ran (order denial).
    """
    assert not _REFERENCE_LOADED["flag"], \
        "REFUSED: reference section ran before the raw path"
    t0 = time.time()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    t_inf0 = time.time()
    rows = core.infer_full(df, rspec)
    t_inf1 = time.time()
    calls = sum(1 for r in rows if r.get("status") == "READY_RAW")
    proof = {"device": str(device),
             "cuda_available": bool(torch.cuda.is_available()),
             "n_raw_rows": len(rows),
             "ready_raw_rows": calls,
             "inference_s": round(t_inf1 - t_inf0, 3),
             "total_s": round(time.time() - t0, 3),
             "first_row_keys": sorted(rows[0].keys()) if rows else []}
    assert calls >= 1, "no READY_RAW rows (cannot evidence non-WAIT)"
    _REFERENCE_LOADED["raw_done"] = True
    return rows, proof


def stream_replay(df: pd.DataFrame, config: dict, raw_rows: list[dict],
                  start_bar: int = 0, snap: dict | None = None,
                  n_bars: int | None = None,
                  observed_at: str | None = None) -> core.AdvisorStrategy:
    """Replay stream through the ACTUAL runner (AdvisorStrategy)."""
    rspec = r76.load_prespec()
    strategy = core.AdvisorStrategy(config, n_bars=(len(df) if n_bars is None
                                                   else n_bars))
    identity = strategy.identity_block(config, rspec)
    strategy._identity = identity
    if observed_at is None:
        observed_at = pd.Timestamp.now(tz="UTC").isoformat()
    if snap is not None:
        strategy.restore_state(snap, identity)
    else:
        shadow = df["close_time"].iloc[0].isoformat()
        strategy.begin_observation(shadow, observed_at)
    raw_by_bar = {int(r["bar_index"]): r for r in raw_rows
                  if r.get("status") == "READY_RAW"}
    for pos in range(start_bar, len(df)):
        row = df.iloc[pos]
        bar = {"open_time": row["open_time"], "close_time": row["close_time"],
               "open": float(row["open"]), "high": float(row["high"]),
               "low": float(row["low"]), "close": float(row["close"]),
               "volume": float(row["volume"])}
        strategy.observe_bar(pos, bar, raw_by_bar.get(pos), observed_at)
    return strategy


def strategy_metrics(strategy: core.AdvisorStrategy) -> dict:
    op_ev = [e for e in strategy.operating.events if e.get("kind") == "EXIT"]
    ct_ev = [e for e in strategy.control.events if e.get("kind") == "EXIT"]
    op_path = [float(e["equity_after"]) for e in op_ev if "equity_after" in e]
    ct_path = [float(e["equity_after"]) for e in ct_ev if "equity_after" in e]

    def _dd(path: list[float], start: float) -> float:
        peak, worst = start, 0.0
        for v in path:
            peak = max(peak, v)
            worst = min(worst, (v - peak) / peak if peak else 0.0)
        return float(worst)

    dec = strategy.decision_log
    return {
        "n_decisions": len(dec),
        "n_ready": sum(1 for d in dec if d.get("status") == "READY"),
        "n_wait_action": sum(1 for d in dec if d.get("action") == "WAIT"),
        "n_nonwait_action": sum(1 for d in dec
                                if d.get("action") in ("LONG", "SHORT")),
        "control_intents": strategy.counters.get("control_admitted", 0),
        "operating_intents": strategy.counters.get("operating_admitted", 0),
        "operating_equity": float(strategy.operating.equity),
        "control_equity": float(strategy.control.equity),
        "operating_exits": len(op_path),
        "control_exits": len(ct_path),
        "operating_equity_after": op_path,
        "control_equity_after": ct_path,
        "operating_drawdown": _dd(op_path, 100.0),
        "control_drawdown": _dd(ct_path, 100.0),
        "operating_net": float(sum(e.get("net_pnl", 0.0)
                                   for e in strategy.operating.events)),
        "control_net": float(sum(e.get("net_pnl", 0.0)
                                 for e in strategy.control.events)),
        "counters": dict(strategy.counters),
    }


# ------------------------------------------- independent batch ref ---
class _Gate:
    """Independently written cap4/cd5 gate (same frozen rule)."""

    def __init__(self, cap: int, cd_days: int):
        self.monthly: dict[str, int] = {}
        self.next_allowed = pd.Timestamp.min.tz_localize("UTC")
        self.cap, self.cd = cap, cd_days

    def attempt(self, ts: pd.Timestamp) -> tuple[bool, str]:
        t = pd.Timestamp(ts)
        ts = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
        month = ts.strftime("%Y-%m")
        if ts < self.next_allowed:
            return False, "cooldown"
        if self.monthly.get(month, 0) >= self.cap:
            return False, "monthly_cap"
        self.monthly[month] = self.monthly.get(month, 0) + 1
        self.next_allowed = ts + pd.Timedelta(days=self.cd)
        return True, "admitted"


def run_batch_reference(df: pd.DataFrame, rspec: dict, spec: dict) -> dict:
    """Harness-only reference: own forward + own gates + verbatim settlement.

    Runs strictly AFTER the raw path; allowed to read stored artifacts for
    diagnosis (records what it loaded).
    """
    assert _REFERENCE_LOADED["raw_done"], \
        "REFUSED: raw path must run before the harness reference"
    t0 = time.time()
    cfg, calibs = r76.load_frozen_assets(rspec)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    candidates = np.asarray(grid(cfg), dtype=np.float32)
    candles = validate_source(df)
    store = r76.SwingStore(candles, cfg)
    opens = pd.DatetimeIndex(pd.to_datetime(candles["open_time"], utc=True))
    closes = pd.DatetimeIndex(pd.to_datetime(candles["close_time"], utc=True))
    bars = r76.decision_bars(len(candles), opens)
    ready = [int(b) for b in bars
             if r76._frames_ready(store, closes, int(b), cfg["context"])]
    seqs, feats, rows = [], [], []
    for bar in ready:
        dt = closes[int(bar)]
        windows, _, _ = store.at(dt)
        seqs.append(encode_windows(windows))
        _, _, _, feat40, atr5, atr4 = store.sample(dt)
        feats.append(np.asarray(feat40, dtype=np.float32))
        rows.append({"bar_index": int(bar), "decision_time": dt,
                     "close": float(candles["close"].iloc[int(bar)]),
                     "atr5": float(atr5), "atr4": float(atr4)})
    seqs = np.stack(seqs).astype(np.float32)
    feats = np.stack(feats).astype(np.float32)
    outs = []
    for seed in r76.SEEDS:
        model = r76._load_model(seed, candidates, rspec, device)
        outs.append(residual_predict(model, seqs, feats,
                                     batch_size=r76.BATCH))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    stacked = np.stack(outs).astype(np.float64)
    base, details = combine(stacked, 0.0)
    # Verbatim r76/core shapes: score/fill are (n_decisions, 16) per
    # candidate; calibration reshapes back; choose() acts per decision on
    # the (16,6) lattice. The recorded scalar mirrors core.infer_full
    # exactly (ravel-indexed float(score1[j])), so the comparison below is
    # a determinism check of the same extraction on both paths.
    score = np.asarray(details["selection_score_percent"], dtype=np.float64)
    fill = np.asarray(details["mean_fill_score"], dtype=np.float64)
    score1 = np.asarray(score).ravel()
    fill1 = np.asarray(fill).ravel()
    cal = {}
    for short in ("isotonic_2", "isotonic_4", "isotonic_all"):
        cal[short] = calibs[short]
    preds = {}
    for m in r76.MAPS:
        mapped = np.interp(score.ravel(), cal[m]["x"],
                           cal[m]["y"]).reshape(score.shape)
        arr = np.asarray(base, dtype=np.float64).copy()
        arr[..., 0] = mapped / np.clip(fill, 1e-6, 1 - 1e-6)
        preds[m] = arr
    per_map, dirs = {}, {}
    for m in r76.MAPS:
        olist, dlist = [], []
        for j in range(len(ready)):
            o = choose(preds[m][j], rows[j]["close"], rows[j]["atr5"],
                       rows[j]["atr4"], cfg)
            olist.append(o)
            dlist.append(1 if o.get("action") == "LONG"
                         else (-1 if o.get("action") == "SHORT" else 0))
        per_map[m] = olist
        dirs[m] = np.asarray(dlist, dtype=int)
    d2, d4, dall = dirs["isotonic_2"], dirs["isotonic_4"], dirs["isotonic_all"]
    cap = spec["frozen_policy"]["frequency_cap_per_month"]
    cd = spec["frozen_policy"]["cooldown_days"]
    g_iso, g_conf = _Gate(cap, cd), _Gate(cap, cd)
    ctrl_rows, op_rows, gate_log = [], [], []
    for j in range(len(ready)):
        iso4 = per_map["isotonic_4"][j]
        act = iso4.get("action", "WAIT")
        confirmed = bool((d4[j] != 0) and (dall[j] == d4[j]))
        majority = bool((d4[j] != 0) and ([d2[j], d4[j], dall[j]].count(
            int(d4[j])) >= 2))
        dt = rows[j]["decision_time"]
        c_adm, c_why, o_adm, o_why = False, "ineligible", False, "ineligible"
        if act in ("LONG", "SHORT"):
            c_adm, c_why = g_iso.attempt(dt)
            if c_adm:
                ctrl_rows.append(_sig_row(rows[j], iso4, 1.0))
        if confirmed and act in ("LONG", "SHORT"):
            o_adm, o_why = g_conf.attempt(dt)
            if o_adm:
                op_rows.append(_sig_row(rows[j], iso4, 1.0))
        gate_log.append({"bar_index": rows[j]["bar_index"],
                         "decision_time": dt.isoformat(),
                         "iso4_action": act,
                         "vote_majority": majority,
                         "vote_confirmed": confirmed,
                         "score": float(score1[j]),
                         "fill": float(fill1[j]),
                         "control_admitted": bool(c_adm),
                         "control_gate": c_why,
                         "operating_admitted": bool(o_adm),
                         "operating_gate": o_why})
    # Diagnosis-only stored anchor (never into the model path).
    anchor = pd.read_parquet(
        ROOT / "artifacts/research/opencode_v15_mapensemble/"
        "confirmed_dd_guard/signals.parquet")
    _REFERENCE_LOADED["flag"] = True
    _REFERENCE_LOADED["what"].append(
        "artifacts/research/opencode_v15_mapensemble/confirmed_dd_guard/"
        f"signals.parquet ({len(anchor)} rows, diagnosis only)")
    anchor_bars = sorted(int(b) for b in anchor["bar_index"].to_numpy())
    admitted_op = sorted(r["bar_index"] for r in gate_log
                         if r["operating_admitted"])
    anchor_hit = [b for b in spec["interval"]["known_anchor_signals"]
                  if b["bar_index"] in admitted_op]
    # Verbatim settlement, fixed 1x baselines.
    costs = CostModel(fee_rate_per_fill=0.0002, funding_long_rate=0.0001,
                      funding_short_rate=0.0, funding_interval_hours=8)
    execution = ExecutionConfig(entry_expiry_bars=12, max_holding_bars=2016,
                                tp1_fraction=0.5, leverage=1.0,
                                max_leverage=1.0)
    settled = {}
    for name, srows in (("control_iso4_only_1x", ctrl_rows),
                        ("operating_confirmed_1x", op_rows)):
        sig = pd.DataFrame(srows)
        if len(sig):
            equity, trades = run_backtest(df, sig, 100.0, costs, execution)
            settled[name] = {
                "final_equity": float(equity.final_equity),
                "gross_pnl": float(equity.gross_pnl),
                "fees": float(equity.fees),
                "funding": float(equity.funding),
                "net_pnl": float(equity.net_profit),
                "max_drawdown": float(equity.max_drawdown),
                "trade_count": int(equity.trades),
                "coverage_signals": len(sig),
                "per_trade_equity_after": [float(t.equity_after)
                                           for t in trades],
                "exit_reasons": [str(t.exit_reason) for t in trades],
            }
        else:
            settled[name] = {"final_equity": 100.0, "gross_pnl": 0.0,
                             "fees": 0.0, "funding": 0.0, "net_pnl": 0.0,
                             "max_drawdown": 0.0, "trade_count": 0,
                             "coverage_signals": 0,
                             "per_trade_equity_after": [],
                             "exit_reasons": []}
    return {"batch_s": round(time.time() - t0, 3),
            "n_decisions": len(ready),
            "gate_log": gate_log,
            "control_signals": ctrl_rows,
            "operating_signals": op_rows,
            "anchor_bars_published": anchor_bars,
            "anchor_hits": [a["bar_index"] for a in anchor_hit],
            "settled": settled}


def _sig_row(row: dict, iso4: dict, lev: float) -> dict:
    act = iso4.get("action", "WAIT")
    return {"bar_index": int(row["bar_index"]),
            "signal_time": pd.Timestamp(row["decision_time"]).isoformat(),
            "direction": 1 if act == "LONG" else -1,
            "entry_limit": float(iso4["entry_limit"]),
            "stop_loss": float(iso4["stop_loss"]),
            "take_profit_1": float(iso4["take_profit_1"]),
            "take_profit_2": float(iso4["take_profit_2"]),
            "holding_bars": min(int(iso4.get("holding_bars", 2016)), 2016),
            "leverage": float(lev),
            "entry_expiry_bars": 12,
            "tp1_fraction": 0.5}


def compare_scores(raw_rows: list[dict], gate_log: list[dict],
                   lo_bar: int, hi_bar: int) -> dict:
    raw = {int(r["bar_index"]): r for r in raw_rows
           if r.get("status") == "READY_RAW"}
    n, exact, maxd_s, maxd_f = 0, 0, 0.0, 0.0
    for g in gate_log:
        b = g["bar_index"]
        if not (lo_bar <= b < hi_bar):
            continue
        r = raw.get(b)
        if r is None:
            continue
        n += 1
        ds = abs(float(r["scores"]["selection_score_percent"]) - g["score"])
        df_ = abs(float(r["scores"]["mean_fill_score"]) - g["fill"])
        maxd_s, maxd_f = max(maxd_s, ds), max(maxd_f, df_)
        if ds == 0.0 and df_ == 0.0:
            exact += 1
    return {"n_compared": n, "n_bitexact": exact,
            "max_abs_d_score": maxd_s, "max_abs_d_fill": maxd_f,
            "pass": n > 0 and exact == n}


def main() -> None:
    t_all = time.time()
    spec = load_prespec()
    frozen = verify_frozen(spec)
    audit = audit_runner_sources()
    assert audit["pass"], f"raw-path source audit failed: {audit}"
    rspec = r76.load_prespec()
    config = json.loads(RUNNER_CONFIG_PATH.read_text(encoding="utf-8"))
    assert config.get("allow_live_orders", True) is False
    df = load_slice_candles(spec)
    print(f"[w2] candles={len(df)} "
          f"{df['open_time'].iloc[0]}..{df['close_time'].iloc[-1]}",
          flush=True)

    # (1) Tested raw-model path through the actual runner.
    raw_rows, proof = run_raw_path(df, rspec)
    print(f"[w2] infer_full: {proof['ready_raw_rows']} READY_RAW on "
          f"{proof['device']} in {proof['inference_s']}s", flush=True)
    observed_at = pd.Timestamp.now(tz="UTC").isoformat()
    full = stream_replay(df, config, raw_rows, observed_at=observed_at)
    met_full = strategy_metrics(full)
    print(f"[w2] stream: decisions={met_full['n_decisions']} "
          f"nonWAIT={met_full['n_nonwait_action']} "
          f"op_intents={met_full['operating_intents']} "
          f"ctrl_intents={met_full['control_intents']} "
          f"op_eq={met_full['operating_equity']:.6f} "
          f"ctrl_eq={met_full['control_equity']:.6f}", flush=True)

    # (2) Independent batch reference (harness-only, after raw path).
    ref = run_batch_reference(df, rspec, spec)
    m = re.match(r"\[(\d+),\s*(\d+)\)", spec["interval"]["decision_rows"])
    slice_rows = (int(m.group(1)), int(m.group(2)))
    lo_bar = 36864 + slice_rows[0] * 72
    hi_bar = 36864 + slice_rows[1] * 72
    score_cmp = compare_scores(raw_rows, ref["gate_log"], lo_bar, hi_bar)

    # Geometry + admission identity on the slice.
    stream_dec = [d for d in full.decision_log
                  if d.get("status") == "READY"]
    by_bar = {}
    for d in stream_dec:
        b = None
        for g in ref["gate_log"]:
            if g["decision_time"] == d.get("decision_time"):
                b = g["bar_index"]
                break
        if b is not None and lo_bar <= b < hi_bar:
            by_bar[b] = d
    geo_rows = []
    for g in ref["gate_log"]:
        if lo_bar <= g["bar_index"] < hi_bar:
            d = by_bar.get(g["bar_index"], {})
            geo_rows.append({
                "bar_index": g["bar_index"],
                "iso4_action_batch": g["iso4_action"],
                "iso4_action_stream": d.get("iso4_raw_action"),
                "action_match": g["iso4_action"] == d.get("iso4_raw_action"),
                "vote_confirmed_batch": g["vote_confirmed"],
                "vote_confirmed_stream": d.get("vote_confirmed"),
                "vote_match": bool(g["vote_confirmed"])
                == bool(d.get("vote_confirmed")),
                "control_adm_batch": g["control_admitted"],
                "control_intent_stream": d.get("control_intent_id")
                is not None,
                "operating_adm_batch": g["operating_admitted"],
                "operating_intent_stream": d.get("operating_intent_id")
                is not None,
            })
    # Full-prefix admission identity (causal gate state, not reseeded).
    stream_ctrl_times = sorted(
        v["signal_time"] for v in full.intents.values()
        if v.get("portfolio") == "iso4_only_1x")
    stream_op_times = sorted(
        v["signal_time"] for v in full.intents.values()
        if v.get("portfolio") == "operating")
    batch_ctrl_by_time = {s["signal_time"]: s for s in ref["control_signals"]}
    batch_op_by_time = {s["signal_time"]: s for s in ref["operating_signals"]}
    admission_identity = {
        "control_batch_n": len(batch_ctrl_by_time),
        "control_stream_n": len(stream_ctrl_times),
        "control_times_match": (sorted(batch_ctrl_by_time)
                                == stream_ctrl_times),
        "operating_batch_n": len(batch_op_by_time),
        "operating_stream_n": len(stream_op_times),
        "operating_times_match": (sorted(batch_op_by_time)
                                  == stream_op_times),
    }
    # Numeric geometry on matched admissions (bit-exact; leverage compared
    # with the overlay note: batch is pure 1x, streaming may carry guard).
    geo_numeric = []
    for port, bmap in (("iso4_only_1x", batch_ctrl_by_time),
                       ("operating", batch_op_by_time)):
        for v in full.intents.values():
            if v.get("portfolio") != port:
                continue
            b = bmap.get(v["signal_time"])
            if b is None:
                geo_numeric.append({"portfolio": port,
                                    "signal_time": v["signal_time"],
                                    "matched": False})
                continue
            row = {"portfolio": port, "signal_time": v["signal_time"],
                   "matched": True}
            for sk, ik in (("entry_limit", "entry_limit"),
                           ("stop_loss", "sl"),
                           ("take_profit_1", "tp1"),
                           ("take_profit_2", "tp2"),
                           ("holding_bars", None)):
                if ik is None:
                    continue
                row[f"d_{sk}"] = abs(float(b[sk]) - float(v[ik]))
            row["d_holding_vs_cap"] = abs(int(b["holding_bars"])
                                            - min(int(b["holding_bars"]),
                                                  2016))
            row["batch_leverage"] = float(b["leverage"])
            row["stream_leverage"] = float(v.get("leverage", 1.0))
            geo_numeric.append(row)
    geo_exact = all(r.get("matched")
                    and all(abs(r.get(k, 0.0)) == 0.0
                            for k in r if k.startswith("d_"))
                    for r in geo_numeric) and len(geo_numeric) > 0
    op_leverage = sorted({float(v.get("leverage", 1.0))
                          for v in full.intents.values()
                          if v.get("portfolio") == "operating"})
    n_slice_nonwait = sum(
        1 for g in ref["gate_log"]
        if lo_bar <= g["bar_index"] < hi_bar
        and g["iso4_action"] in ("LONG", "SHORT"))

    # (3) Chunk/restart identity with nonempty state.
    boundary = int(spec["chunk_restart"]["boundary_bar"])
    assert 0 < boundary < len(df)
    probe = stream_replay(df.iloc[:boundary].reset_index(drop=True), config,
                          [r for r in raw_rows
                           if int(r.get("bar_index", -1)) < boundary],
                          n_bars=len(df), observed_at=observed_at)
    snap = probe.snapshot_state(probe._identity)
    snap_state = {
        "operating_open": probe.operating.snapshot().get("open"),
        "operating_pending": probe.operating.snapshot().get("pending"),
        "control_open": probe.control.snapshot().get("open"),
        "control_pending": probe.control.snapshot().get("pending"),
        "operating_exits": probe.operating.exits,
        "control_exits": probe.control.exits,
        "operating_equity": float(probe.operating.equity),
        "control_equity": float(probe.control.equity),
        "gate_counters": dict(probe.counters),
    }
    nonempty = bool(
        snap_state["operating_open"] or snap_state["operating_pending"]
        or snap_state["control_open"] or snap_state["control_pending"]
        or snap_state["operating_exits"] or snap_state["control_exits"]
        or snap_state["gate_counters"].get("operating_admitted")
        or snap_state["gate_counters"].get("control_admitted"))
    resumed = stream_replay(df, config, raw_rows, start_bar=boundary,
                            snap=snap, n_bars=len(df),
                            observed_at=observed_at)
    met_res = strategy_metrics(resumed)
    restart_cmp = {
        "boundary_bar": boundary,
        "snapshot_state": snap_state,
        "state_nonempty": bool(nonempty),
        "d_operating_equity": abs(met_full["operating_equity"]
                                  - met_res["operating_equity"]),
        "d_control_equity": abs(met_full["control_equity"]
                                - met_res["control_equity"]),
        "intents_match": (sorted(full.intents.keys())
                          == sorted(resumed.intents.keys())),
        "fills_match": (sorted(full.fills.keys())
                        == sorted(resumed.fills.keys())),
        "decision_tail_match": (
            full.decision_log[len(probe.decision_log):]
            == resumed.decision_log[len(probe.decision_log):]),
    }
    restart_cmp["pass"] = bool(
        nonempty and restart_cmp["d_operating_equity"] == 0.0
        and restart_cmp["d_control_equity"] == 0.0
        and restart_cmp["intents_match"] and restart_cmp["fills_match"]
        and restart_cmp["decision_tail_match"])

    # Portfolio deltas: streaming incremental vs batch 1x baselines.
    tol = spec["batch_reference"]["tolerances"]
    deltas = {}
    for stream_eq, stream_path, name in (
            (met_full["control_equity"], met_full["control_equity_after"],
             "control_iso4_only_1x"),
            (met_full["operating_equity"],
             met_full["operating_equity_after"],
             "operating_confirmed_1x")):
        b = ref["settled"][name]
        n = min(len(stream_path), len(b["per_trade_equity_after"]))
        d_path = max((abs(a - c) for a, c in zip(
            stream_path[:n], b["per_trade_equity_after"][:n])), default=0.0)
        deltas[name] = {
            "batch_final": b["final_equity"], "stream_final": stream_eq,
            "d_final": abs(b["final_equity"] - stream_eq),
            "batch_trades": b["trade_count"],
            "stream_exits": (met_full["control_exits"]
                             if name.startswith("control")
                             else met_full["operating_exits"]),
            "d_path": d_path,
            "batch_gross": b["gross_pnl"], "batch_fees": b["fees"],
            "batch_funding": b["funding"], "batch_net": b["net_pnl"],
            "batch_dd": b["max_drawdown"],
        }

    blocked = (n_slice_nonwait == 0) or (
        met_full["operating_intents"] == 0
        and met_full["control_intents"] == 0)
    verdict = "BLOCKED" if blocked else ("PASS" if (
        score_cmp["pass"]
        and all(g["action_match"] and g["vote_match"] for g in geo_rows)
        and admission_identity["control_times_match"]
        and admission_identity["operating_times_match"]
        and geo_exact
        and len(ref["anchor_hits"]) >= 1
        and restart_cmp["pass"]) else "MISMATCH-DIAGNOSE")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(raw_rows).to_csv(OUT_DIR / "raw_decisions.csv", index=False)
    pd.DataFrame(full.decision_log).to_csv(
        OUT_DIR / "stream_decisions.csv", index=False)
    pd.DataFrame(list(full.intents.values())).to_csv(
        OUT_DIR / "intents.csv", index=False)
    pd.DataFrame(full.operating.events).to_csv(
        OUT_DIR / "operating_exits.csv", index=False)
    pd.DataFrame(full.control.events).to_csv(
        OUT_DIR / "control_exits.csv", index=False)
    pd.DataFrame(ref["control_signals"]).to_csv(
        OUT_DIR / "batch_control_signals.csv", index=False)
    pd.DataFrame(ref["operating_signals"]).to_csv(
        OUT_DIR / "batch_operating_signals.csv", index=False)
    pd.DataFrame(ref["gate_log"]).to_csv(
        OUT_DIR / "batch_gate_log.csv", index=False)
    summary = {
        "experiment": spec["experiment"], "exploratory": True,
        "verdict": verdict,
        "interval": spec["interval"],
        "frozen": frozen,
        "raw_inference_proof": proof,
        "no_replay_audit": {**audit,
                            "runtime_order": "raw path before harness "
                            f"reference ({_REFERENCE_LOADED['what']})"},
        "stream_full_prefix": met_full,
        "stream_slice_note": f"slice bars [{lo_bar},{hi_bar}) = decision "
        f"rows {slice_rows}; prefix admissions are causal gate state, "
        "reported as part of the book, not reseeded",
        "batch_reference": {
            "n_decisions": ref["n_decisions"],
            "batch_s": ref["batch_s"],
            "n_control_signals": len(ref["control_signals"]),
            "n_operating_signals": len(ref["operating_signals"]),
            "anchor_hits": ref["anchor_hits"],
            "settled": ref["settled"],
        },
        "score_comparison_slice": score_cmp,
        "geometry_gate_slice": geo_rows,
        "admission_identity_full_prefix": admission_identity,
        "geometry_numeric_matched": {"n": len(geo_numeric),
                                     "bit_exact": bool(geo_exact),
                                     "rows": geo_numeric},
        "n_slice_nonwait_raw": n_slice_nonwait,
        "operating_intent_leverage_1x_baseline_vs_overlay": {
            "streaming_operating_leverages": op_leverage,
            "batch_is_pure_1x": True,
        },
        "portfolio_deltas_stream_vs_batch1x": deltas,
        "restart": restart_cmp,
        "blocked": bool(blocked),
        "elapsed_s": round(time.time() - t_all, 1),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=1,
                                                     default=str))
    (OUT_DIR / "provenance.json").write_text(json.dumps({
        "prespec": str(SPEC_PATH), "runner_config": str(RUNNER_CONFIG_PATH),
        "frozen": frozen, "raw_inference_proof": proof,
        "reference_loads": _REFERENCE_LOADED["what"],
        "out_dir": str(OUT_DIR)}, indent=1, default=str))
    print(f"[w2] verdict={verdict} slice_nonWAIT_raw={n_slice_nonwait} "
          f"anchors={ref['anchor_hits']} restart_pass={restart_cmp['pass']} "
          f"-> {OUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
