"""R75 parity + causal audit + execution-gap report. RESEARCH ONLY, no tuning.

Compares the clock-driven replay (scripts/opencode_r75_streaming.py) against the
frozen batch reference, proves prefix invariance, audits every causal claim in
code, and writes:
  artifacts/research/opencode_r75_practical/streaming/streaming_parity.json
  artifacts/research/opencode_r75_practical/streaming/execution_gap_report.md

Bit-level bar: the streaming signal SET must be IDENTICAL to the frozen batch
reference (bar_index, direction, geometry floats exact after parquet roundtrip).
Any diff FAILS promotion (documented, never silently repaired).
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.data.swing import choose

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r75_streaming as S  # noqa: E402

OUT_DIR = ROOT / "artifacts/research/opencode_r75_practical/streaming"
FLOAT_COLS = ["entry_limit", "stop_loss", "take_profit_1", "take_profit_2",
              "expected_net_percent", "ohlc_fill_score", "conditional_win_score"]


def compare_signal_frames(batch: pd.DataFrame, stream: pd.DataFrame) -> dict:
    b = batch.sort_values("bar_index").reset_index(drop=True)
    s = stream.sort_values("bar_index").reset_index(drop=True)
    rep = {"n_batch": int(len(b)), "n_stream": int(len(s))}
    rep["bar_index_equal"] = bool((b["bar_index"].to_numpy() == s["bar_index"].to_numpy()).all()) \
        if len(b) == len(s) else False
    rep["direction_equal"] = bool((b["direction"].to_numpy() == s["direction"].to_numpy()).all()) \
        if len(b) == len(s) else False
    maxdiff = {}
    exact = {}
    for c in FLOAT_COLS + ["leverage"]:
        if c in b.columns and c in s.columns and len(b) == len(s):
            d = np.abs(b[c].to_numpy(float) - s[c].to_numpy(float))
            maxdiff[c] = float(d.max()) if len(d) else 0.0
            exact[c] = bool((d == 0.0).all())
    rep["max_abs_diff"] = maxdiff
    rep["bit_exact_floats"] = exact
    rep["all_bit_exact"] = bool(rep["bar_index_equal"] and rep["direction_equal"]
                                and exact and all(exact.values()))
    for c in ("candidate_id", "holding_bars", "entry_expiry_bars"):
        if c in b.columns and c in s.columns and len(b) == len(s):
            rep[c + "_equal"] = bool((b[c].to_numpy() == s[c].to_numpy()).all())
    return rep


def batch_guard_leverage(signals: pd.DataFrame, control_exits) -> np.ndarray:
    """Verbatim batch formula from the v15 driver (reference for the audit)."""
    eq = pd.Series({ts: e for ts, e in control_exits}).sort_index()
    out = []
    for ts in pd.to_datetime(signals["signal_time"], utc=True):
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}),
                           past]).sort_index()
        peak = float(curve.cummax().iloc[-1])
        level = float(curve.iloc[-1])
        out.append(0.5 if level / peak < 1.0 - 0.10 else 1.0)
    return np.array(out, dtype=float)


def audit_choose_row_invariance(part: pd.DataFrame, preds: dict, ds_cfg: dict) -> dict:
    """choose() output for row i must not depend on any other row (no window
    inspection, no top-k/percentile/fallback across rows)."""
    n = len(part)
    probes = [0, n // 3, n // 2, n - 1]
    ok = True
    for i in probes:
        row = part.iloc[i]
        a = choose(preds["isotonic_4"][i], row["close"], row["atr5"], row["atr4"], ds_cfg)
        # recompute after reversing the whole prediction array order
        rev = preds["isotonic_4"][::-1].copy()
        b = choose(rev[n - 1 - i], row["close"], row["atr5"], row["atr4"], ds_cfg)
        if json.dumps(a, sort_keys=True, default=str) != json.dumps(b, sort_keys=True, default=str):
            ok = False
    # no window-wide ops anywhere in the decision chain source: look for actual
    # call patterns (a bare "quantile" substring would false-positive on the
    # per-row output key "conditional_net_quantiles_percent").
    src = (ROOT / "src/agentic_alpha_lab/data/swing.py").read_text()
    chain_src = src[src.index("def choose"):]
    bad_tokens = ["np.percentile(", ".quantile(", "argsort(", "argpartition(",
                  "rankdata(", "nlargest(", "nsmallest(", "topk", "top_k",
                  "sort_values(", "np.sort("]
    found = [t for t in bad_tokens if t in chain_src]
    return {"rows_probed": probes, "row_invariant": bool(ok),
            "window_tokens_in_choose": found, "no_window_inspection": bool(ok and not found)}


def audit_guard_cutoff(part: pd.DataFrame, preds: dict, ds_cfg: dict,
                       candles: pd.DataFrame, control_exits, policy: dict) -> dict:
    """Guard leverage at T must be invariant to dropping control exits >= T."""
    r = S.R75StreamReplay(policy, candles, part, preds, ds_cfg, control_exits)
    times = sorted({pd.Timestamp(t) for t, _ in control_exits})[:6]
    if not times:
        return {"checked": 0, "cutoff_invariant": True, "note": "no control exits"}
    ok = True
    checked = 0
    for t in times:
        probe = t + pd.Timedelta(microseconds=1)
        full = r.guard_leverage(probe)
        trimmed = S.R75StreamReplay(policy, candles, part, preds, ds_cfg,
                                    [(ts, e) for ts, e in control_exits if ts < probe])
        part_lev = trimmed.guard_leverage(probe)
        if full != part_lev:
            ok = False
        checked += 1
    return {"checked": checked, "cutoff_invariant": bool(ok)}


def _utc_ns(values) -> np.ndarray:
    """Normalize any datetime-like array to UTC int64 ns (naive treated as UTC,
    consistent with the dataset convention proven by direct timestamp match)."""
    return pd.to_datetime(values, utc=True).tz_convert("UTC").astype("int64")


def audit_decision_alignment(candles: pd.DataFrame, part: pd.DataFrame,
                             signals: pd.DataFrame) -> dict:
    ct = _utc_ns(candles["close_time"].values)
    st = _utc_ns(part["signal_time"].values)
    in_set = int(pd.Series(st).isin(pd.Series(ct)).sum())
    bi = part["bar_index"].to_numpy()
    exact = int((_utc_ns(candles.iloc[bi]["close_time"].values) == st).sum())
    sig_bi = signals["bar_index"].to_numpy()
    sig_ok = int((_utc_ns(candles.iloc[sig_bi]["close_time"].values)
                  == _utc_ns(signals["signal_time"].values)).sum())
    atr_finite = bool(np.isfinite(part[["close", "atr5", "atr4"]].to_numpy(float)).all())
    return {"decision_rows": int(len(part)),
            "signal_time_in_candle_closes": f"{in_set}/{len(part)}",
            "bar_index_close_exact": f"{exact}/{len(part)}",
            "emitted_signal_bar_close_exact": f"{sig_ok}/{len(signals)}",
            "atr_finite": atr_finite,
            "verdict": bool(in_set == len(part) and exact == len(part)
                            and sig_ok == len(signals) and atr_finite)}


def audit_1m_ordering(candles: pd.DataFrame, trades_csv: Path) -> dict:
    """Read-only 1m check: 5m OHLC consistency + intrabar touch order where the
    audit-day files exist. Ambiguity stays explicit."""
    m1dir = ROOT / "data/raw/opencode_1m_audit_20260907"
    trades = pd.read_csv(trades_csv)
    batch_ref = pd.read_parquet(
        ROOT / "artifacts/research/opencode_v15_mapensemble/confirmed_dd_guard/signals.parquet")
    geom = batch_ref.set_index("bar_index")[["stop_loss", "take_profit_2", "direction"]]
    trades = trades.join(geom, on="signal_index", rsuffix="_sig")
    have_days = {p.stem[-8:] for p in m1dir.glob("klines_BTCUSDT_1m_*.parquet")}
    checked = consistent = ambiguous = resolved = 0
    notes = []
    for t in trades.itertuples():
        for col in ("entry_index", "exit_index"):
            idx = int(getattr(t, col))
            bar = candles.iloc[idx]
            day = pd.Timestamp(bar["open_time"]).strftime("%Y%m%d")
            if day not in have_days:
                continue
            f = m1dir / f"klines_BTCUSDT_1m_{day}.parquet"
            try:
                m1 = pd.read_parquet(f)
            except Exception as exc:  # keep audit going; record the gap
                notes.append(f"{day}: unreadable ({exc})")
                continue
            lo = pd.Timestamp(bar["open_time"]).tz_convert("UTC")
            hi = pd.Timestamp(bar["close_time"]).tz_convert("UTC")
            mt = pd.to_datetime(m1["open_time"], utc=True)
            seg = m1[(mt >= lo) & (mt < hi)]
            if seg.empty:
                continue
            checked += 1
            ok = (abs(float(seg["high"].max()) - float(bar["high"])) < 1e-6
                  and abs(float(seg["low"].min()) - float(bar["low"])) < 1e-6)
            consistent += int(ok)
            if col == "exit_index" and t.exit_reason in ("stop", "tp2"):
                stop_px, tp_px = float(t.stop_loss), float(t.take_profit_2)
                if int(t.direction) == 1:
                    hit_stop = seg["low"] <= stop_px
                    hit_tp = seg["high"] >= tp_px
                else:
                    hit_stop = seg["high"] >= stop_px
                    hit_tp = seg["low"] <= tp_px
                eng_hit = hit_stop if t.exit_reason == "stop" else hit_tp
                oth_hit = hit_tp if t.exit_reason == "stop" else hit_stop
                if eng_hit.any() and not oth_hit.any():
                    resolved += 1  # 1m confirms the engine's level alone
                elif eng_hit.any() and oth_hit.any():
                    first_eng = pd.to_datetime(
                        seg[eng_hit].iloc[0]["open_time"], utc=True)
                    first_oth = pd.to_datetime(
                        seg[oth_hit].iloc[0]["open_time"], utc=True)
                    if first_eng <= first_oth:
                        resolved += 1
                    else:
                        ambiguous += 1
                        notes.append(f"trade@{t.signal_index}: 1m first-touch order "
                                     f"disagrees (engine={t.exit_reason})")
                else:
                    ambiguous += 1
                    notes.append(f"trade@{t.signal_index}: engine exit level "
                                 f"{t.exit_reason} untouched in 1m sample")
    return {"trades": int(len(trades)), "bars_checked_1m": checked,
            "ohlc_consistent_1m": consistent, "order_resolved_1m": resolved,
            "order_ambiguous_or_offsample": ambiguous,
            "cover_days": len(have_days), "notes": notes[:10]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="configs/opencode_r75_policy.json")
    ap.add_argument("--prefix-rows", type=int, default=2000)
    a = ap.parse_args()
    policy = S.load_policy(ROOT / a.policy)
    candles, decisions, part, didx, preds, ds_cfg = S.load_inputs(policy)
    batch_ref = pd.read_parquet(
        ROOT / policy["reference_signals"]["path"])
    control_sigs, control_exits = S.batch_control_reference(policy, candles, ds_cfg)

    findings: dict = {"policy_id": policy["policy_id"], "frozen": True}

    # (1) control regeneration parity (same streaming loop, iso4_only vote)
    ctrl_stream, ctrl_log = S.run_stream(policy, candles, part, preds, ds_cfg,
                                         control_exits, vote=S.VOTE_ISO4_ONLY)
    findings["control_parity"] = compare_signal_frames(control_sigs, ctrl_stream)

    # (2) reference parity: full streaming run vs frozen batch confirmed signals
    stream, log = S.run_stream(policy, candles, part, preds, ds_cfg, control_exits)
    findings["reference_parity"] = compare_signal_frames(batch_ref, stream)
    parity_ok = bool(findings["reference_parity"]["all_bit_exact"])

    # (3) guard: incremental vs verbatim batch formula
    batch_lev = batch_guard_leverage(batch_ref, control_exits)
    probe = S.R75StreamReplay(policy, candles, part, preds, ds_cfg, control_exits)
    incr_lev = np.array([probe.guard_leverage(pd.Timestamp(t))[0]
                         for t in batch_ref["signal_time"]])
    findings["guard_incr_vs_batch"] = {
        "max_abs_diff": float(np.abs(batch_lev - incr_lev).max()),
        "identical": bool((batch_lev == incr_lev).all())}
    findings["guard_cutoff_audit"] = audit_guard_cutoff(
        part, preds, ds_cfg, candles, control_exits, policy)

    # (4) prefix invariance: truncated run == prefix of full run; future
    # mutation (predictions AND candles beyond K) cannot move earlier outputs
    K = int(a.prefix_rows)
    pre_stream, _ = S.run_stream(policy, candles, part, preds, ds_cfg,
                                 control_exits, end_row=K)
    full_head = stream.iloc[:len(pre_stream)].reset_index(drop=True)
    pre_reset = pre_stream.reset_index(drop=True)
    findings["prefix_invariance"] = {
        "K": K, "n_prefix": int(len(pre_stream)),
        "bar_equal": bool((full_head["bar_index"].to_numpy()
                           == pre_reset["bar_index"].to_numpy()).all()),
        "dir_equal": bool((full_head["direction"].to_numpy()
                           == pre_reset["direction"].to_numpy()).all()),
        "lev_equal": bool((full_head["leverage"].to_numpy()
                           == pre_reset["leverage"].to_numpy()).all())}
    mut_preds = {m: v.copy() for m, v in preds.items()}
    mut_preds["isotonic_4"][K:] = 0.0
    mut_preds["isotonic_all"][K:] = 0.0
    mut_stream, _ = S.run_stream(policy, candles, part, mut_preds, ds_cfg,
                                 control_exits, end_row=K)
    findings["future_pred_mutation"] = {
        "prefix_unchanged": bool(
            (mut_stream["bar_index"].to_numpy()
             == pre_reset["bar_index"].to_numpy()).all()) if len(mut_stream) == len(pre_reset)
        else False}
    mut_candles = candles.copy()
    klast = int(part.iloc[K - 1]["bar_index"])
    mut_candles.loc[mut_candles.index > klast, "close"] *= 2.0
    mut_candles.loc[mut_candles.index > klast, "high"] *= 2.0
    mut_candles.loc[mut_candles.index > klast, "low"] *= 2.0
    mut2, _ = S.run_stream(policy, mut_candles, part, preds, ds_cfg,
                           control_exits, end_row=K)
    findings["future_candle_mutation"] = {
        "prefix_unchanged": bool(
            (mut2["bar_index"].to_numpy()
             == pre_reset["bar_index"].to_numpy()).all()) if len(mut2) == len(pre_reset)
        else False}
    findings["prefix_ok"] = bool(
        findings["prefix_invariance"]["bar_equal"]
        and findings["prefix_invariance"]["dir_equal"]
        and findings["prefix_invariance"]["lev_equal"]
        and findings["future_pred_mutation"]["prefix_unchanged"]
        and findings["future_candle_mutation"]["prefix_unchanged"])

    # (5) causal audits
    findings["causal_alignment"] = audit_decision_alignment(candles, part, stream)
    findings["choose_row_invariance"] = audit_choose_row_invariance(part, preds, ds_cfg)
    findings["htf_note"] = (
        "decisions carry precomputed atr5/atr4; SwingStore.sample(as_of) uses "
        "searchsorted(side=right)-1 (last CLOSED bar) per timeframe; round14 v47 "
        "proved 5628/5628 close_last<=T on this dataset; re-verified here that "
        "every decision signal_time equals its signal-bar candle close_time.")
    findings["funding_note"] = (
        "engine applies funding only on bars whose open_time hits the 8h UTC grid "
        "(_is_funding_time), charging notional/entry*bar_open*remaining*rate: "
        "mark price is proxied by bar open; publication lag unmodeled (proxy gap).")
    findings["window_ops_note"] = (
        "choose() argmax is WITHIN one row over 16 candidates, never across rows; "
        "frequency loop and guard touch only past rows/exits; no percentile, "
        "quantile, top-k, argsort or rankdata across the window (audited in code).")

    # (6) portfolio: same engine on streamed signals (normal + fee stress)
    costs = CostModel(**ds_cfg["costs"])
    cap = int(max(ds_cfg["holding_days"]) * 288)
    exe_lo = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                             max_holding_bars=cap, leverage=0.25, max_leverage=1.0)
    res_n, trades_n = run_backtest(candles, stream, 100, costs, exe_lo)
    fee_costs = CostModel(**{**ds_cfg["costs"], "fee_rate_per_fill": 0.00055})
    res_f, _ = run_backtest(candles, stream, 100, fee_costs, exe_lo)
    ref_n, _ = run_backtest(candles, batch_ref, 100, costs, exe_lo)
    findings["portfolio_stream"] = {
        "normal": {"final_equity": res_n.final_equity, "trades": res_n.trades,
                   "max_drawdown": res_n.max_drawdown, "gross_pnl": res_n.gross_pnl,
                   "fees": res_n.fees, "funding": res_n.funding},
        "fee_stress": {"final_equity": res_f.final_equity, "trades": res_f.trades,
                       "max_drawdown": res_f.max_drawdown},
        "batch_final_equity": ref_n.final_equity,
        "equity_match": bool(abs(res_n.final_equity - ref_n.final_equity) < 1e-9
                             and res_n.trades == ref_n.trades)}
    # non-circular cross-check: streamed book vs the SAVED v15 published numbers
    saved = json.load((ROOT / "artifacts/research/opencode_v15_mapensemble/summary.json").open()) \
        ["branches"]["confirmed_dd_guard"]["normal"]
    findings["saved_numbers_crosscheck"] = {
        "saved": {"final_equity": saved["final_equity"], "trades": saved["trades"],
                  "max_drawdown": saved["max_drawdown"]},
        "match": bool(abs(res_n.final_equity - saved["final_equity"]) < 1e-9
                      and res_n.trades == saved["trades"]
                      and abs(res_n.max_drawdown - saved["max_drawdown"]) < 1e-12)}
    ref_trades_path = ROOT / ("artifacts/research/opencode_v15_mapensemble/"
                              "confirmed_dd_guard/normal_trades.csv")
    findings["ordering_1m"] = audit_1m_ordering(candles, ref_trades_path)

    # (7) L3-combo frozen comparison: SKIPPED with reason (do not rebuild)
    findings["l3_comparison"] = {
        "status": "SKIPPED",
        "reasons": [
            "forward-window L3combo_dd_guard_tp075 (v159 fwdevaltop3) lives on the "
            "SEALED forward interval on a different clock/dataset; replaying it "
            "here would touch sealed evaluation data owned by track A.",
            "development-window L3 (v75 dd_guard_tp075) is a DIFFERENT policy clock "
            "(tp1_fraction 0.75, own-book tp075 guard reference, L1-union+L2-filter "
            "multi-stage chain), not the same-policy comparison this parity needs.",
            "per mission: record why skipped, do not rebuild."],
        "chain_paths_checked": [
            "artifacts/research/opencode_v159_fwdevaltop3/L3combo_dd_guard_tp075/signals.parquet",
            "artifacts/research/opencode_v75_L3real/dd_guard_tp075/signals.parquet"]}

    verdict = bool(parity_ok and findings["prefix_ok"]
                   and findings["guard_incr_vs_batch"]["identical"]
                   and findings["causal_alignment"]["verdict"]
                   and findings["choose_row_invariance"]["no_window_inspection"]
                   and findings["guard_cutoff_audit"]["cutoff_invariant"]
                   and findings["control_parity"]["all_bit_exact"]
                   and findings["saved_numbers_crosscheck"]["match"])
    findings["parity_verdict"] = "IDENTICAL" if verdict else "FAIL"
    findings["promotion"] = ("HOLD: parity holds on plumbing only; exploratory "
                             "development data, no edge claim." if verdict
                             else "STOP promotion: parity/causal invariance FAILED; "
                             "document, do not silently repair (repair = new version).")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "streaming_parity.json").write_text(
        json.dumps(findings, indent=2, default=str))
    write_gap_report(findings)
    print(json.dumps({"parity_verdict": findings["parity_verdict"],
                      "reference_parity": findings["reference_parity"]["all_bit_exact"],
                      "prefix_ok": findings["prefix_ok"],
                      "promotion": findings["promotion"]}, indent=2))
    if not verdict:
        raise SystemExit(1)


def write_gap_report(f: dict) -> None:
    p = f["reference_parity"]
    gaps = []
    gaps.append(("G1 signal set", "identical" if p["all_bit_exact"] else "DIFF",
                 f"batch n={p['n_batch']} stream n={p['n_stream']}; "
                 f"max float diffs: {p.get('max_abs_diff')}"))
    g = f["guard_incr_vs_batch"]
    gaps.append(("G2 guard sizing path", "identical" if g["identical"] else "DIFF",
                 f"incremental binary-search guard vs verbatim batch formula: "
                 f"max diff {g['max_abs_diff']}. Both read only exits strictly "
                 f"before T; control book itself is causal given frozen signals."))
    gaps.append(("G3 censored tail / boundary positions",
                 "same rule both sides; live-behavior gap documented",
                 "engine rejects signals whose entry+holding window exceeds the data "
                 "end (no truncated windows). In a live loop those tail positions "
                 "would be OPEN/PENDING carried in streaming state; the batch book "
                 "silently drops them into rejected_or_unfilled. This book fits "
                 "fully (no truncation), but the rule matters at every live boundary."))
    gaps.append(("G4 drawdown sampling", "same proxy both sides; gap vs exchange truth",
                 "trade-candle-close sampled DD, not mark-price/intrabar DD. "
                 "Direction: understates true adverse excursion; magnitude unmeasured "
                 "from OHLC alone."))
    gaps.append(("G5 funding mark proxy", "same proxy both sides; gap vs exchange truth",
                 "funding charged on notional/entry*bar_open; bar open proxies mark; "
                 "publication/as-of lag unmodeled. Long-only cost 0.0001/8h, shorts 0."))
    gaps.append(("G6 intrabar entry-candle TP suppression", "same both sides; conservative",
                 "engine suppresses TP fills on the intrabar entry candle when entry "
                 "was not at open (ordering unknown). Direction: weakly conservative "
                 "(removes ambiguous winners)."))
    gaps.append(("G7 stop-first", "same both sides; conservative",
                 "bars touching both stop and target resolve stop-first. Direction: "
                 "conservative for longs (understates PnL vs TP-first); magnitude "
                 "here: 0 same-touch bars per round7 v31 1m audit on this book "
                 "(stop-first is a no-op so far, kept as the fail-safe rule)."))
    gaps.append(("G8 limit-entry queue realism", "OPTIMISTIC vs live; not claimed",
                 "touch fills the full notional at limit with no queue/partial model. "
                 "Do NOT claim maker probability from OHLC. Sensitivity reference "
                 "(v30 prob-fill, assumption-labeled): book survives p_fill=0.2; "
                 "no new probabilistic numbers are asserted in this round."))
    gaps.append(("G9 stop/timeout exits", "market-like + scenario fees both sides",
                 "exits modeled market-like at the scenario fee (0.0002 normal, "
                 "0.00055 fee stress) plus 5bps stress variant; slippage beyond that "
                 "unmodeled."))
    o = f["ordering_1m"]
    gaps.append(("G10 1m touch-order resolution (read-only audit)",
                 "measured where coverage exists",
                 f"{o['bars_checked_1m']} entry/exit bars had 1m coverage; "
                 f"5m-OHLC consistent {o['ohlc_consistent_1m']}; stop-vs-target order "
                 f"resolved {o['order_resolved_1m']}, ambiguous/off-sample "
                 f"{o['order_ambiguous_or_offsample']}. Residual ambiguity explicit."))
    lines = ["# R75 execution gap report (streaming truth vs batch reference)",
             "",
             "Policy: `opencode_r75_confirmed_dd_guard` (frozen; exploratory development "
             "data, no promotion claim). Engine `ohlc-v2`, stop-first, costs per bundle.",
             "",
             "Every gap between the batch reference book and streaming truth, with "
             "direction and magnitude where measurable:",
             ""]
    for name, status, body in gaps:
        lines += [f"## {name} — {status}", "", body, ""]
    lines += ["## Verdict",
              "",
              f"parity={f['parity_verdict']}; prefix_ok={f['prefix_ok']}; "
              + f["promotion"],
              "",
              "L3-combo frozen comparison: SKIPPED (see streaming_parity.json: "
              "sealed forward clock + different development policy clock; not rebuilt).",
              ""]
    (OUT_DIR / "execution_gap_report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()