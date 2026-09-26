"""MJ W15 pairs event study on the SPREAD return.

Definitions fixed in patterns/pairs.py; run once. Evaluates ONLY decisions
before 2025-09-14 and never computes forward returns for dates >= 2025-09-24
(load_bars default hides the opened year).

Spread return for pair (A,B) with beta fixed as of the decision bar t, entered
at the next open and held h bars (mirrors common.forward_log_return):
    s_h[t] = log(Ao[t+1+h]/Ao[t+1]) - beta[t]*log(Bo[t+1+h]/Bo[t+1]),
where Ao/Bo are the as-of aligned opens. Signed excess for an event at t with
direction d: d * (s_h[t] - mean(s_h)). Newey-West lag = h, BH-FDR, half
stability split at common.DEV_SPLIT -- identical to common.event_study except
the evaluated return is the beta-hedged spread instead of outright BTC.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from agentic_alpha_lab.patterns import common, pairs

OUT = Path(__file__).resolve().parents[2] / "artifacts" / "research" / "mj" / "pairs"
HORIZONS = {"4h": (1, 3, 6, 12), "1d": (1, 3, 7, 14)}


def spread_event_study(bars: pd.DataFrame, events: pd.DataFrame,
                       horizons: tuple[int, ...], tf: str) -> pd.DataFrame:
    feats = pairs.compute(bars)
    legs = pairs._ratio_frame(bars)
    decide = (bars["open_time"] < common.DEV_DECISION_END).to_numpy()
    first_half = (bars["open_time"] < common.DEV_SPLIT).to_numpy()
    rows = []
    for col in events.columns:
        code = col.split("_")[2]
        beta = feats[f"pr_{code}_beta60"].to_numpy(float)
        ao = legs[f"{code}_a_open"].to_numpy(float)
        bo = legs[f"{code}_b_open"].to_numpy(float)
        d = events[col].to_numpy()
        for h in horizons:
            with np.errstate(divide="ignore", invalid="ignore"):
                ra_h = np.full(len(bars), np.nan)
                rb_h = np.full(len(bars), np.nan)
                num = len(bars) - (1 + h)
                if num > 0:
                    ra_h[:num] = np.log(ao[1 + h:1 + h + num] / ao[1:1 + num])
                    rb_h[:num] = np.log(bo[1 + h:1 + h + num] / bo[1:1 + num])
                s = ra_h - beta * rb_h
            valid = decide & ~np.isnan(s) & ~np.isnan(beta)
            base = np.nanmean(s[valid])
            m = valid & (d != 0)
            if m.sum() == 0:
                continue
            ex = d[m] * (s[m] - base)
            t = common.newey_west_t(ex, h)
            halves = [ex[first_half[m]], ex[~first_half[m]]]
            rows.append(dict(
                tf=tf, pattern=col, horizon=h, n=int(m.sum()),
                n_long=int((d[m] > 0).sum()), n_short=int((d[m] < 0).sum()),
                mean_excess_bps=1e4 * ex.mean(),
                hit_rate=float(np.mean(d[m] * s[m] > 0)), nw_t=t,
                p_value=float(2 * stats.norm.sf(abs(t))) if np.isfinite(t) else np.nan,
                first_half_bps=1e4 * halves[0].mean() if len(halves[0]) else np.nan,
                second_half_bps=1e4 * halves[1].mean() if len(halves[1]) else np.nan,
            ))
    out = pd.DataFrame(rows)
    if len(out):
        out["q_value"] = common.benjamini_hochberg(out["p_value"].to_numpy())
        out["stable_significant"] = (
            (out["q_value"] < 0.10) & (out["n"] >= 30)
            & (np.sign(out["first_half_bps"]) == np.sign(out["second_half_bps"]))
            & (np.sign(out["first_half_bps"]) == np.sign(out["mean_excess_bps"]))
        )
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for tf in ("4h", "1d"):
        bars = common.load_bars(tf)
        ev = pairs.events(bars)
        res = spread_event_study(bars, ev, horizons=HORIZONS[tf], tf=tf)
        res.to_csv(OUT / f"event_study_{tf}.csv", index=False)
        frames.append(res)
        n_sig = int(res["stable_significant"].sum()) if len(res) else 0
        print(f"{tf}: rows={len(res)} stable_significant={n_sig}")
    all_res = pd.concat(frames, ignore_index=True)
    all_res.to_csv(OUT / "event_study_all.csv", index=False)
    sig = all_res[all_res["stable_significant"]]
    print(f"total={len(all_res)} stable={len(sig)}")
    if len(sig):
        print(sig[["tf", "pattern", "horizon", "n", "mean_excess_bps",
                    "q_value"]].to_string(index=False))


if __name__ == "__main__":
    main()
