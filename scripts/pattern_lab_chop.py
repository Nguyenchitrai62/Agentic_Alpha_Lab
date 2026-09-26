"""pattern_lab_r4: chop filters and an ML forward-efficiency filter on trend variant B.

  python scripts/pattern_lab_chop.py dev
  python scripts/pattern_lab_chop.py opened   # once, after dev freezes the selection
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).parent))
from pattern_lab_meta import idx_first, idx_last, primary_trades  # noqa: E402
from pattern_lab_trend_risk import evaluate, paint  # noqa: E402

from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, backtest, funding_per_bar, ribbon_target, summarize
from agentic_alpha_lab.models.pattern_pipeline import build_matrix, daily_context, join_daily
from agentic_alpha_lab.patterns import indicators
from agentic_alpha_lab.patterns.common import load_bars, load_funding

PROTOCOL = Path("configs/pattern_lab_r4_protocol.json")
PROTOCOL_SHA = "52369b2f173b0f667b6a557dae694ea81c439728d3e968ada49fecf21d91b09c"
R1 = json.loads(Path("configs/pattern_lab_r1_protocol.json").read_text())
OUT = Path("artifacts/research/pattern_lab/chop_4h")
REFIT, EMBARGO, H = 540, 12, 42


def efficiency_ratio_past(c: np.ndarray, n: int) -> np.ndarray:
    lc = np.log(c)
    d = np.abs(np.diff(lc, prepend=np.nan))
    path = pd.Series(d).rolling(n).sum().to_numpy()
    net = np.abs(lc - pd.Series(lc).shift(n).to_numpy())
    return net / path


def efficiency_ratio_forward(c: np.ndarray, n: int) -> np.ndarray:
    lc = np.log(c)
    d = np.abs(np.diff(lc, append=np.nan))  # d[t] = |lc[t+1] - lc[t]|
    path = pd.Series(d[::-1]).rolling(n).sum().to_numpy()[::-1]  # sum d[t..t+n-1]
    net = np.abs(pd.Series(lc).shift(-n).to_numpy() - lc)
    return net / path


def ml_filter(x: pd.DataFrame, y: np.ndarray, first: int, last: int, fit_limit: int | None):
    """Boolean 'enter allowed' per bar plus walk-forward predictions."""
    xv = x.to_numpy(np.float32)
    allow = np.zeros(len(x), bool)
    pred = np.full(len(x), np.nan)
    realized = np.arange(len(x)) + H
    for r in range(first, last + 1, REFIT):
        cutoff = r if fit_limit is None else min(r, fit_limit)
        tr = (realized + EMBARGO < cutoff) & ~np.isnan(y)
        idx = np.arange(r, min(r + REFIT, last + 1))
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=100, l2_regularization=1.0, random_state=0)
        m.fit(xv[tr], y[tr])
        med = np.median(m.predict(xv[tr]))
        pred[idx] = m.predict(xv[idx])
        allow[idx] = pred[idx] >= med
    return allow, pred


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
    c = bars["close"].to_numpy(float)
    d_rib = join_daily(bars, daily, daily_context(daily))["d_ribbon"].to_numpy()
    adx = indicators.compute(bars)["ind_adx_14"].to_numpy()
    er_past = efficiency_ratio_past(c, H)
    lt = primary_trades(ribbon_target(bars["close"], 20, 200, "ribbon", "long", "EMA"), bars, fc)
    e = lt.entry.to_numpy()
    gate_b = d_rib[e] != -1

    wf_first = idx_first(bars, "2021-01-01")
    dev_last = idx_last(bars, R1["windows"]["development_decisions"][1])
    val_first = idx_first(bars, R1["windows"]["selection_validation"][0])
    pre_last = idx_last(bars, "2023-12-31")
    if opened:
        marker = OUT / "opened_year_evaluated.txt"
        if marker.exists():
            raise SystemExit("opened-year check already run")
        frozen = json.loads((OUT / "frozen_selection.json").read_text())
        marker.write_text(pd.Timestamp.utcnow().isoformat())
        ho = (idx_first(bars, R1["windows"]["opened_year_check"][0]), idx_last(bars, R1["windows"]["opened_year_check"][1]))
        m_first, m_last, m_lim = ho[0], ho[1], ho[0]
    else:
        m_first, m_last, m_lim = wf_first, dev_last, None

    x = build_matrix(bars, daily, funding, ("cdl", "ind"))
    if opened:
        x = x[frozen["columns"]]
    else:
        dev_x = x.iloc[: dev_last + 1]
        x = x[[col for col in x.columns if dev_x[col].notna().mean() > 0.5 and dev_x[col].nunique(dropna=True) > 1]]
    y = efficiency_ratio_forward(c, H)
    allow, pred = ml_filter(x, y, m_first, m_last, m_lim)

    variants = {
        "R0": gate_b,
        "R1": d_rib[e] == 1,
        "R2": gate_b & (adx[e] > 20),
        "R3": gate_b & (er_past[e] > 0.30),
        "R4": gate_b & allow[e],
    }
    report = {"protocol_sha256": PROTOCOL_SHA, "phase": phase, "rows": {}}
    ones = np.ones(len(lt))
    if opened:
        sel, k = frozen["selected"], frozen["scale"]
        bh = summarize(backtest(bars, np.ones(n, dtype=int), ho[0], ho[1], NORMAL, fr, fc))
        report["buy_hold"] = {kk: round(v, 4) if isinstance(v, float) else v for kk, v in bh.items()}
        report["selected"], report["scale"] = sel, k
        for name, take in variants.items():
            for tag, z in (("1x", 1.0), (f"scaled_{k}", k)):
                tgt, size = paint(n, lt, take, ones * z)
                report["rows"][f"{name}|{tag}"] = r = evaluate(bars, tgt, size, ho, fr, fc)
                print(name, tag, "net", r["normal"]["net_pct"], "stress", r["stress"]["net_pct"], "dd", r["normal"]["dd_intrabar_pct"],
                      "trades", r["normal"]["trades"], "sharpe", r["normal"]["sharpe"], "monthly", r["normal"]["monthly_geo_pct"], flush=True)
        ok = ~np.isnan(y[ho[0]:ho[1] + 1]) & ~np.isnan(pred[ho[0]:ho[1] + 1])
        report["ml_spearman_opened"] = float(spearmanr(pred[ho[0]:ho[1] + 1][ok], y[ho[0]:ho[1] + 1][ok])[0])
        (OUT / "opened_year_report.json").write_text(json.dumps(report, indent=1, default=str))
        return

    ok = ~np.isnan(y[wf_first:dev_last + 1]) & ~np.isnan(pred[wf_first:dev_last + 1])
    report["ml_spearman_wf"] = float(spearmanr(pred[wf_first:dev_last + 1][ok], y[wf_first:dev_last + 1][ok])[0])
    print("ML forward-ER spearman (walk-forward dev):", round(report["ml_spearman_wf"], 4))
    for name, take in variants.items():
        tgt, size = paint(n, lt, take, ones)
        report["rows"][name] = r = {w: evaluate(bars, tgt, size, rg, fr, fc) for w, rg in
                                    (("wf", (wf_first, dev_last)), ("pre_val", (wf_first, pre_last)), ("val", (val_first, dev_last)))}
        print(name, "wf net", r["wf"]["normal"]["net_pct"], "stress", r["wf"]["stress"]["net_pct"], "dd", r["wf"]["normal"]["dd_intrabar_pct"],
              "sharpe", r["wf"]["normal"]["sharpe"], "trades", r["wf"]["normal"]["trades"], "| pre_val dd", r["pre_val"]["normal"]["dd_intrabar_pct"],
              "val net", r["val"]["normal"]["net_pct"], "val sharpe", r["val"]["normal"]["sharpe"], "val dd", r["val"]["normal"]["dd_intrabar_pct"], flush=True)
    elig = [k for k, r in report["rows"].items() if r["wf"]["stress"]["net_pct"] > 0]
    sel = max(elig, key=lambda k: report["rows"][k]["val"]["normal"]["sharpe"]) if elig else None
    k = None
    if sel:
        pre_dd = report["rows"][sel]["pre_val"]["normal"]["dd_intrabar_pct"]
        k = math.floor(min(1.0, 20.0 / pre_dd) * 20) / 20
        tgt, size = paint(n, lt, variants[sel], ones * k)
        report["selected_scaled"] = {w: evaluate(bars, tgt, size, rg, fr, fc) for w, rg in (("wf", (wf_first, dev_last)), ("val", (val_first, dev_last)))}
        s = report["selected_scaled"]
        print("selected", sel, "scale", k, "scaled wf net", s["wf"]["normal"]["net_pct"], "stress", s["wf"]["stress"]["net_pct"], "dd", s["wf"]["normal"]["dd_intrabar_pct"],
              "val net", s["val"]["normal"]["net_pct"], "val dd", s["val"]["normal"]["dd_intrabar_pct"], "monthly", s["wf"]["normal"]["monthly_geo_pct"])
    report["selected"], report["scale"] = sel, k
    (OUT / "dev_report.json").write_text(json.dumps(report, indent=1, default=str))
    (OUT / "frozen_selection.json").write_text(json.dumps({"protocol_sha256": PROTOCOL_SHA, "frozen_at": pd.Timestamp.utcnow().isoformat(),
                                                          "selected": sel, "scale": k, "columns": list(x.columns)}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["dev", "opened"])
    main(ap.parse_args().phase)
