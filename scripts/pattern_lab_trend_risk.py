"""pattern_lab_r3: fixed risk/sizing variants of the 4h EMA20/200 ribbon trend rule.

  python scripts/pattern_lab_trend_risk.py dev
  python scripts/pattern_lab_trend_risk.py opened   # once
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).parent))
from pattern_lab_meta import idx_first, idx_last, primary_trades  # noqa: E402

from agentic_alpha_lab.backtest.ma_ribbon import ACTUAL_FUNDING, NORMAL, STRESS, backtest, funding_per_bar, ribbon_target, summarize
from agentic_alpha_lab.models.pattern_pipeline import build_matrix, daily_context, join_daily
from agentic_alpha_lab.patterns.common import load_bars, load_funding

PROTOCOL = Path("configs/pattern_lab_r3_protocol.json")
PROTOCOL_SHA = "cf9e5207b6b79fb482d0f603b34603bd56a993d0c4d99ca3f44d62e6eb819fe8"
R1 = json.loads(Path("configs/pattern_lab_r1_protocol.json").read_text())
OUT = Path("artifacts/research/pattern_lab/trend_risk_4h")
SCEN = {"normal": NORMAL, "stress": STRESS, "actual_funding": ACTUAL_FUNDING}
REFIT, EMBARGO = 540, 12


def paint(n, trades, take, sizes):
    tgt, size = np.zeros(n, dtype=int), np.ones(n)
    for a, b, s, ok, z in zip(trades.entry, trades.exit_decision, trades.side, take, sizes):
        if ok:
            tgt[int(a):int(b)] = s
            size[int(a):int(b)] = z
    return tgt, size


def evaluate(bars, tgt, size, rng, fr, fc):
    out = {}
    for k, c in SCEN.items():
        s = summarize(backtest(bars, tgt, rng[0], rng[1], c, fr, fc, size))
        out[k] = {m: round(v, 4) if isinstance(v, float) else v for m, v in s.items()}
    return out


def model_sizes(bars, daily, funding, trades, first, last, fit_limit=None):
    x = build_matrix(bars, daily, funding, ("cdl", "chp", "ind"))
    xt = np.column_stack([x.to_numpy(np.float32)[trades.entry.to_numpy()], trades.side.to_numpy()])
    y = trades.net.to_numpy()
    entry, exit_fill = trades.entry.to_numpy(), trades.exit_fill.to_numpy()
    size = np.ones(len(trades))
    for r in range(first, last + 1, REFIT):
        cutoff = r if fit_limit is None else min(r, fit_limit)
        sel = (entry >= r) & (entry < min(r + REFIT, last + 1))
        tr = exit_fill + EMBARGO < cutoff
        if not sel.any() or tr.sum() < 40:
            continue
        m = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=30, l2_regularization=1.0, random_state=0)
        m.fit(xt[tr], y[tr])
        size[sel] = np.where(m.predict(xt[sel]) > 0, 1.0, 0.25)
    return size


def main(phase: str) -> None:
    if hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() != PROTOCOL_SHA:
        raise SystemExit("protocol changed")
    opened = phase == "opened"
    bars = load_bars("4h", include_opened_year=opened)
    daily = load_bars("1d", include_opened_year=opened)
    funding = load_funding(include_opened_year=opened)
    fr, fc = funding_per_bar(bars, funding)
    OUT.mkdir(parents=True, exist_ok=True)
    n = len(bars)
    ctx = join_daily(bars, daily, daily_context(daily))
    d_rib = ctx["d_ribbon"].to_numpy()
    vol_size = np.minimum(1.0, 0.60 / (ctx["d_vol30"].to_numpy() * np.sqrt(365)))
    vol_size = np.where(np.isfinite(vol_size), vol_size, 1.0)

    long_t = ribbon_target(bars["close"], 20, 200, "ribbon", "long", "EMA")
    short_t = np.where(ribbon_target(bars["close"], 20, 200, "ribbon", "long_short", "EMA") == -1, -1, 0)
    lt, st = primary_trades(long_t, bars, fc), primary_trades(short_t, bars, fc)
    both = pd.concat([lt, st]).sort_values("entry").reset_index(drop=True)
    e_l, e_b = lt.entry.to_numpy(), both.entry.to_numpy()
    ones_l, ones_b = np.ones(len(lt)), np.ones(len(both))
    gate_l = d_rib[e_l] != -1
    gate_b = np.where(both.side.to_numpy() > 0, d_rib[e_b] != -1, d_rib[e_b] == -1)

    wf_first = idx_first(bars, "2021-01-01")
    dev_last = idx_last(bars, R1["windows"]["development_decisions"][1])
    val_first = idx_first(bars, R1["windows"]["selection_validation"][0])
    if opened:
        marker = OUT / "opened_year_evaluated.txt"
        if marker.exists():
            raise SystemExit("opened-year check already run")
        marker.write_text(pd.Timestamp.utcnow().isoformat())
        ho = (idx_first(bars, R1["windows"]["opened_year_check"][0]), idx_last(bars, R1["windows"]["opened_year_check"][1]))
        g_first, g_last, g_lim = ho[0], ho[1], ho[0]
    else:
        g_first, g_last, g_lim = wf_first, dev_last, None

    variants = {
        "A": (lt, np.ones(len(lt), bool), ones_l),
        "B": (lt, gate_l, ones_l),
        "C": (lt, np.ones(len(lt), bool), vol_size[e_l]),
        "D": (lt, gate_l, vol_size[e_l]),
        "E": (both, gate_b, vol_size[e_b]),
        "F": (both, gate_b, ones_b),
    }
    try:
        variants["G"] = (both, gate_b, model_sizes(bars, daily, funding, both, g_first, g_last, g_lim))
    except ImportError as exc:
        print("G skipped:", exc)

    report = {"protocol_sha256": PROTOCOL_SHA, "phase": phase, "rows": {}}
    if opened:
        frozen = json.loads((OUT / "frozen_selection.json").read_text())
        report["selected"] = frozen["selected"]
        bh = summarize(backtest(bars, np.ones(n, dtype=int), ho[0], ho[1], NORMAL, fr, fc))
        report["buy_hold"] = {k: round(v, 4) if isinstance(v, float) else v for k, v in bh.items()}
        for k, (tr, take, sz) in variants.items():
            tgt, size = paint(n, tr, take, sz)
            report["rows"][k] = evaluate(bars, tgt, size, ho, fr, fc)
            r = report["rows"][k]
            print(k, "net", r["normal"]["net_pct"], "stress", r["stress"]["net_pct"], "dd", r["normal"]["dd_intrabar_pct"], "trades", r["normal"]["trades"], "sharpe", r["normal"]["sharpe"], flush=True)
        (OUT / "opened_year_report.json").write_text(json.dumps(report, indent=1, default=str))
        return

    for k, (tr, take, sz) in variants.items():
        tgt, size = paint(n, tr, take, sz)
        report["rows"][k] = {w: evaluate(bars, tgt, size, r, fr, fc) for w, r in
                             (("wf", (wf_first, dev_last)), ("pre_val", (wf_first, val_first - 1)), ("val", (val_first, dev_last)))}
        r = report["rows"][k]
        print(k, "wf net", r["wf"]["normal"]["net_pct"], "stress", r["wf"]["stress"]["net_pct"], "dd", r["wf"]["normal"]["dd_intrabar_pct"],
              "sharpe", r["wf"]["normal"]["sharpe"], "trades", r["wf"]["normal"]["trades"], "| pre_val", r["pre_val"]["normal"]["net_pct"],
              "val", r["val"]["normal"]["net_pct"], "val sharpe", r["val"]["normal"]["sharpe"], "monthly", r["wf"]["normal"]["monthly_geo_pct"], flush=True)
    elig = [k for k, r in report["rows"].items() if r["wf"]["stress"]["net_pct"] > 0 and r["wf"]["normal"]["dd_intrabar_pct"] <= 25]
    selected = max(elig, key=lambda k: report["rows"][k]["val"]["normal"]["sharpe"]) if elig else None
    report["eligible"], report["selected"] = elig, selected
    print("eligible", elig, "selected", selected)
    (OUT / "dev_report.json").write_text(json.dumps(report, indent=1, default=str))
    if "G" in variants:
        (OUT / "frozen_selection.json").write_text(json.dumps({"protocol_sha256": PROTOCOL_SHA, "frozen_at": pd.Timestamp.utcnow().isoformat(), "selected": selected, "eligible": elig}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["dev", "opened"])
    main(ap.parse_args().phase)
