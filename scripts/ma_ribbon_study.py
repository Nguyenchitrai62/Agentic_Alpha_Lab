"""Protocol ma_ribbon_r1: MA-ribbon rules and gated ML on development and hidden holdout year."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from agentic_alpha_lab.backtest.ma_ribbon import (
    ACTUAL_FUNDING, NORMAL, STRESS, backtest, block_bootstrap_mean, daily_returns,
    funding_per_bar, ribbon_target, summarize,
)
from agentic_alpha_lab.models.ma_ribbon_ml import daily_features, labels, ml_target, walk_forward, fit_predict

PROTOCOL = Path("configs/ma_ribbon_r1_protocol.json")
PROTOCOL_SHA = "f5642fdbc5843966fcf71162805d7c29d2565b9aa23bdfb86150fe25f119ce7c"
DATA = Path("data/raw/ma_ribbon_20260924")
SCENARIOS = {"normal": NORMAL, "stress": STRESS, "actual_funding": ACTUAL_FUNDING}
PRIMARY = {
    "H1_cross_long": ("cross", "long"),
    "H2_cross_long_short": ("cross", "long_short"),
    "H3_ribbon_long": ("ribbon", "long"),
    "H4_ribbon_long_short": ("ribbon", "long_short"),
}


def index_range(bars: pd.DataFrame, first: str, last: str) -> tuple[int, int]:
    day = bars["open_time"].dt.tz_convert(None).dt.normalize()
    ok = np.flatnonzero((day >= pd.Timestamp(first)) & (day <= pd.Timestamp(last)))
    return int(ok[0]), int(ok[-1])


def evaluate(bars, target, rng, fr, fc, scenarios=SCENARIOS):
    rows = {}
    for name, costs in scenarios.items():
        res = backtest(bars, target, rng[0], rng[1], costs, fr, fc)
        rows[name] = summarize(res)
        if name == "normal":
            rows["_result"] = res
    return rows


def yearly(curve: pd.DataFrame) -> dict:
    eq = curve["equity"]
    out, prev = {}, 100.0
    for year, grp in eq.groupby(eq.index.year):
        out[int(year)] = round(100 * (grp.iloc[-1] / prev - 1), 2)
        prev = grp.iloc[-1]
    return out


def strip(rows: dict) -> dict:
    return {k: {m: round(v, 4) if isinstance(v, float) else v for m, v in r.items()} for k, r in rows.items() if not k.startswith("_")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/research/ma_ribbon_r1")
    args = ap.parse_args()
    got = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    if got != PROTOCOL_SHA:
        raise SystemExit(f"protocol changed after registration: {got}")
    proto = json.loads(PROTOCOL.read_text())
    dev_first, dev_last = proto["splits"]["development_decisions"]
    ho_first, ho_last = proto["splits"]["holdout_decisions"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    funding = pd.read_parquet(DATA / "funding.parquet").sort_values("fundingTime").reset_index(drop=True)
    tf_bars = {tf: pd.read_parquet(DATA / f"klines_{tf}.parquet") for tf in ("1d", "4h")}
    tf_fund = {tf: funding_per_bar(b, funding) for tf, b in tf_bars.items()}
    report: dict = {"protocol_sha256": got, "data_manifest": json.loads((DATA / "manifest.json").read_text())}

    d1 = tf_bars["1d"]
    fr, fc = tf_fund["1d"]
    dev = index_range(d1, dev_first, dev_last)
    ho = index_range(d1, ho_first, ho_last)
    ml_dev = index_range(d1, "2021-01-01", dev_last)
    report["windows"] = {
        "dev": [str(d1.open_time[dev[0]].date()), str(d1.open_time[dev[1]].date())],
        "ml_dev": [str(d1.open_time[ml_dev[0]].date()), str(d1.open_time[ml_dev[1]].date())],
        "holdout": [str(d1.open_time[ho[0]].date()), str(d1.open_time[ho[1]].date())],
    }

    # ---- primary rules + benchmark
    targets = {"buy_hold": np.ones(len(d1), dtype=int)}
    for name, (rule, direction) in PRIMARY.items():
        targets[name] = ribbon_target(d1["close"], 50, 200, rule, direction)

    # ---- ML (development walk-forward; holdout frozen + walk-forward)
    feats = daily_features(d1, funding)
    y = labels(d1)
    gate = feats["sma50_gt_200"].to_numpy()
    ml_diag = {}
    for model in ("HGB", "LR"):
        p_dev = walk_forward(feats, y, model, ml_dev[0], ml_dev[1])
        p_frozen = np.full(len(d1), np.nan)
        hidx = np.arange(ho[0], ho[1] + 1)
        p_frozen[hidx] = fit_predict(feats, y, model, ho[0], hidx)
        p_wf = walk_forward(feats, y, model, ho[0], ho[1])
        for tag, p, rng_ in (("dev", p_dev, ml_dev), ("holdout_frozen", p_frozen, ho), ("holdout_wf", p_wf, ho)):
            ii = np.arange(rng_[0], rng_[1] + 1)
            m = ~np.isnan(p[ii]) & y.iloc[ii].notna().to_numpy()
            yy, pp = y.iloc[ii].to_numpy()[m], p[ii][m]
            ml_diag[f"{model}_{tag}"] = dict(
                n=int(m.sum()), auc=float(roc_auc_score(yy, pp)) if len(set(yy)) > 1 else None,
                acc=float(np.mean((pp > 0.5) == yy)), base_rate=float(yy.mean()),
                frac_long=float(np.mean(pp > 0.55)), frac_short=float(np.mean(pp < 0.45)),
            )
        combined_dev = p_dev.copy()
        combined_frozen = np.where(np.isnan(p_frozen), p_dev, p_frozen)
        combined_wf = np.where(np.isnan(p_wf), p_dev, p_wf)
        for gated in (True, False):
            g = gate if gated else None
            suffix = "gated" if gated else "ungated"
            targets[f"ML_{model}_{suffix}_dev"] = ml_target(combined_dev, g)
            targets[f"ML_{model}_{suffix}_frozen"] = ml_target(combined_frozen, g)
            targets[f"ML_{model}_{suffix}_wf"] = ml_target(combined_wf, g)
    report["ml_diagnostics"] = ml_diag

    primary_rows: dict = {}
    for name, tgt in targets.items():
        if name.startswith("ML_"):
            if name.endswith("_dev"):
                base = name[: -len("_dev")]
                primary_rows.setdefault(base, {})["dev_ml_window"] = evaluate(d1, tgt, ml_dev, fr, fc)
            else:
                base, variant = name.rsplit("_", 1)
                primary_rows.setdefault(base, {})[f"holdout_{variant}"] = evaluate(d1, tgt, ho, fr, fc)
            continue
        primary_rows[name] = {
            "dev": evaluate(d1, tgt, dev, fr, fc),
            "dev_ml_window": evaluate(d1, tgt, ml_dev, fr, fc),
            "holdout": evaluate(d1, tgt, ho, fr, fc),
        }

    bh_ho = daily_returns(primary_rows["buy_hold"]["holdout"]["_result"])
    table = {}
    for name, blocks in primary_rows.items():
        table[name] = {}
        for block, rows in blocks.items():
            entry = strip(rows)
            res = rows["_result"]
            if block == "dev":
                entry["yearly_normal_pct"] = yearly(res["curve"])
            if block.startswith("holdout"):
                r = daily_returns(res)
                lo, hi = block_bootstrap_mean(r.to_numpy())
                ex = (r - bh_ho.reindex(r.index).fillna(0)).to_numpy()
                elo, ehi = block_bootstrap_mean(ex)
                entry["bootstrap90_ann_mean_pct"] = [round(36500 * lo, 1), round(36500 * hi, 1)]
                entry["bootstrap90_ann_excess_vs_bh_pct"] = [round(36500 * elo, 1), round(36500 * ehi, 1)]
                entry["trade_log"] = [
                    dict(side=t["side"], entry=str(d1.open_time[t["entry_index"]].date()),
                         exit=str(d1.open_time[t["exit_index"]].date()), entry_px=round(t["entry_price"], 1),
                         exit_px=round(t["exit_price"], 1), pnl=round(t["pnl"], 2))
                    for t in res["trades"]
                ]
            table[name][block] = entry
    report["primary"] = table

    # ---- secondary grid: select on development only, then evaluate once on holdout
    g = proto["secondary_grid"]
    grid_rows = []
    for kind, fast, slow, rule, direction, tf in itertools.product(
        g["ma_type"], g["fast"], g["slow"], g["rule"], g["direction"], g["timeframe"]
    ):
        if fast >= slow:
            continue
        bars = tf_bars[tf]
        fr_, fc_ = tf_fund[tf]
        tgt = ribbon_target(bars["close"], fast, slow, rule, direction, kind)
        dv = summarize(backtest(bars, tgt, *index_range(bars, dev_first, dev_last), NORMAL, fr_, fc_))
        hn = summarize(backtest(bars, tgt, *index_range(bars, ho_first, ho_last), NORMAL, fr_, fc_))
        hs = summarize(backtest(bars, tgt, *index_range(bars, ho_first, ho_last), STRESS, fr_, fc_))
        grid_rows.append(dict(
            config=f"{tf}_{kind}{fast}/{slow}_{rule}_{direction}",
            dev_sharpe=dv["sharpe"], dev_net=dv["net_pct"], dev_cagr=dv["cagr_pct"], dev_dd=dv["dd_intrabar_pct"],
            dev_trades=dv["trades"], ho_net=hn["net_pct"], ho_net_stress=hs["net_pct"], ho_dd=hn["dd_intrabar_pct"],
            ho_trades=hn["trades"], ho_sharpe=hn["sharpe"],
        ))
    grid = pd.DataFrame(grid_rows)
    eligible = grid[(grid.dev_trades >= 8) & (grid.dev_dd <= 45)]
    selected = eligible.sort_values("dev_sharpe", ascending=False).iloc[0].to_dict()
    grid.round(3).to_csv(out / "grid.csv", index=False)
    report["grid_selected_on_dev"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in selected.items()}
    report["grid_holdout_context"] = {
        "configs": len(grid), "ho_net_positive_frac": float((grid.ho_net > 0).mean()),
        "ho_net_median": float(grid.ho_net.median()),
        "dev_rank_vs_ho_rank_spearman": float(grid.dev_sharpe.rank().corr(grid.ho_sharpe.rank())),
    }

    # ---- current state
    c = d1["close"]
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    above = s50 > s200
    flips = np.flatnonzero(above.to_numpy()[1:] != above.to_numpy()[:-1]) + 1
    report["current_state"] = dict(
        last_closed_day=str(d1.open_time.iloc[-1].date()), close=float(c.iloc[-1]),
        sma50=round(float(s50.iloc[-1]), 1), sma200=round(float(s200.iloc[-1]), 1),
        regime="SMA50>SMA200" if above.iloc[-1] else "SMA50<SMA200",
        last_cross=str(d1.open_time[flips[-1]].date()),
        close_vs_sma50_pct=round(100 * (c.iloc[-1] / s50.iloc[-1] - 1), 2),
        close_vs_sma200_pct=round(100 * (c.iloc[-1] / s200.iloc[-1] - 1), 2),
        crosses_in_history=[(str(d1.open_time[i].date()), "golden" if above.iloc[i] else "death") for i in flips],
        ml_latest_p_up={m: None for m in ("HGB", "LR")},
    )
    last = len(d1) - 1
    for m in ("HGB", "LR"):
        report["current_state"]["ml_latest_p_up"][m] = round(float(fit_predict(feats, y, m, ho[0], np.array([last]))[0]), 3)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: report[k] for k in ("windows", "grid_selected_on_dev", "grid_holdout_context", "current_state")}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
