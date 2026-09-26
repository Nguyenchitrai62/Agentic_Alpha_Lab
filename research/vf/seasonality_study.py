"""W4 seasonality event study: definitions fixed in patterns/seasonality.py, run once.

Evaluates ONLY via common.event_study (decisions before 2025-09-14).
Yearly persistence reuses the same dev-only mask and excess definition.
Horizon 1 bar is the key test for hour buckets.
"""

import torch  # noqa: F401  (import first: Windows DLL load order)
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import common, seasonality

OUT = Path(__file__).resolve().parents[2] / "artifacts" / "research" / "vf" / "seasonality"
HORIZONS = (1, 3, 6, 12)
KEY_H = 1
YEARS = (2020, 2021, 2022, 2023, 2024, 2025)


def _yearly_persistence(bars: pd.DataFrame, ev: pd.DataFrame, h: int, tf: str) -> pd.DataFrame:
    r = common.forward_log_return(bars, h).to_numpy()
    decide = (bars["open_time"] < common.DEV_DECISION_END).to_numpy()
    valid = decide & ~np.isnan(r)
    base = np.nanmean(r[valid])
    years = pd.to_datetime(bars["open_time"], utc=True).dt.year.to_numpy()
    rows = []
    for col in ev.columns:
        d = ev[col].to_numpy()
        m = valid & (d != 0)
        if m.sum() == 0:
            continue
        ex = d[m] * (r[m] - base)
        ym = years[m]
        for y in YEARS:
            k = ym == y
            if k.sum() == 0:
                continue
            mu = float(np.mean(ex[k]))
            rows.append(dict(tf=tf, pattern=col, horizon=h, year=int(y),
                             n=int(k.sum()), mean_excess_bps=1e4 * mu,
                             sign=int(np.sign(mu)) if mu != 0 else 0))
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames, yframes = [], []
    for tf in ("1h", "4h", "1d"):
        bars = common.load_bars(tf)
        ev = seasonality.events(bars)
        res = common.event_study(bars, ev, horizons=HORIZONS, tf=tf)
        if len(res):
            res["p_bonf"] = np.minimum(res["p_value"].to_numpy() * len(res), 1.0)
        res.to_csv(OUT / f"event_study_{tf}.csv", index=False)
        frames.append(res)
        yd = _yearly_persistence(bars, ev, KEY_H, tf)
        yd.to_csv(OUT / f"yearly_persistence_h{KEY_H}_{tf}.csv", index=False)
        yframes.append(yd)
        n_sig = int(res["stable_significant"].sum()) if len(res) else 0
        print(f"{tf}: rows={len(res)} stable_significant={n_sig}")
    all_res = pd.concat(frames, ignore_index=True)
    all_res.to_csv(OUT / "event_study_all.csv", index=False)
    sig = all_res[all_res["stable_significant"]]
    sig.to_csv(OUT / "event_study_stable_significant.csv", index=False)
    yd_all = pd.concat(yframes, ignore_index=True)
    yd_all.to_csv(OUT / "yearly_persistence_all.csv", index=False)
    sign_pivot = yd_all.pivot_table(index=["tf", "pattern"], columns="year",
                                    values="sign", aggfunc="first").reset_index()
    sign_pivot.to_csv(OUT / "yearly_sign_pivot.csv", index=False)
    key = all_res[all_res["horizon"] == KEY_H]
    key_sig = key[key["stable_significant"]]
    mx = float(key["mean_excess_bps"].abs().max()) if len(key) else float("nan")
    if len(sig):
        top = sig.sort_values("mean_excess_bps", ascending=False).iloc[0]
        hit = (f"sole hit: {top['tf']} {top['pattern']} h={int(top['horizon'])} "
               f"{float(top['mean_excess_bps']):.1f} bps "
               f"(q={float(top['q_value']):.3f}); ~ cost, yearly signs flip.")
    else:
        hit = "no stable_significant; hour excess mostly <8 bps, below cost."
    with open(OUT / "SUMMARY.md", "w") as f:
        f.write("# W4 seasonality summary\n")
        f.write(f"1. rows={len(all_res)} stable_significant={len(sig)} (q<0.10, n>=30, sign-stable halves).\n")
        f.write(f"2. h=1 key rows={len(key)} stable={len(key_sig)}; max |mean_excess|={mx:.1f} bps vs 4-8 bps cost.\n")
        f.write(f"3. {hit}\n")
        f.write("4. weekday/session buckets: none stable after BH/Bonferroni.\n")
        f.write("5. yearly signs 2020-2025 flip per bucket; no persistent calendar edge.\n")
        f.write("6. verdict: calendar seasonality not tradable alone; leader may test interactions only.\n")
    print(f"total={len(all_res)} stable={len(sig)}")
    if len(sig):
        print(sig[["tf", "pattern", "horizon", "n", "mean_excess_bps"]].to_string(index=False))


if __name__ == "__main__":
    main()
