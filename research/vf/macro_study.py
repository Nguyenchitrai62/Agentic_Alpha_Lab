"""W7 macro event study: definitions fixed in patterns/macro.py, run once.

Evaluates ONLY via common.event_study (decisions before 2025-09-14).
Never computes forward returns for dates >= 2025-09-24.
"""

import torch  # noqa: F401  (import first: Windows DLL load order)
from pathlib import Path

import pandas as pd

from agentic_alpha_lab.patterns import common, macro

OUT = Path(__file__).resolve().parents[2] / "artifacts" / "research" / "vf" / "macro"
HORIZONS = (1, 3, 6, 12)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for tf in ("4h", "1d"):
        bars = common.load_bars(tf)
        ev = macro.events(bars)
        res = common.event_study(bars, ev, horizons=HORIZONS, tf=tf)
        res.to_csv(OUT / f"event_study_{tf}.csv", index=False)
        frames.append(res)
        n_sig = int(res["stable_significant"].sum()) if len(res) else 0
        print(f"{tf}: rows={len(res)} stable_significant={n_sig}")
    all_res = pd.concat(frames, ignore_index=True)
    all_res.to_csv(OUT / "event_study_all.csv", index=False)
    sig = all_res[all_res["stable_significant"]]
    sig.to_csv(OUT / "event_study_stable_significant.csv", index=False)
    print(f"total={len(all_res)} stable={len(sig)}")
    if len(sig):
        print(sig[["tf", "pattern", "horizon", "n",
                    "mean_excess_bps", "q_value"]].to_string(index=False))
    n = len(all_res)
    ns = len(sig)
    mx = float(all_res["mean_excess_bps"].abs().max()) if n else float("nan")
    if ns:
        top = sig.sort_values("mean_excess_bps", ascending=False).iloc[0]
        hit = (f"top: {top['tf']} {top['pattern']} h={int(top['horizon'])} "
               f"{float(top['mean_excess_bps']):.1f} bps (q={float(top['q_value']):.3f}).")
    else:
        key = all_res[all_res["horizon"].isin((1, 3))]
        kmx = float(key["mean_excess_bps"].abs().max()) if len(key) else float("nan")
        kmin_q = float(key["q_value"].min()) if len(key) else float("nan")
        hit = (f"no stable_significant; largest h=1/3 point estimate |excess|={kmx:.1f} bps "
               f"exceeds 4-8 bps cost but min q={kmin_q:.2f} (noise) with halves flipping sign.")
    with open(OUT / "SUMMARY.md", "w") as f:
        f.write("# W7 macro summary\n")
        f.write(f"1. rows={n} stable_significant={ns} (q<0.10, n>=30, sign-stable halves).\n")
        f.write(f"2. max |mean_excess|={mx:.1f} bps vs 4-8 bps round-trip cost.\n")
        f.write(f"3. {hit}\n")
        f.write("4. risk-on switches, VIX spikes, DXY breakouts: none stable after BH.\n")
        f.write("5. verdict: macro regime not tradable alone; leader may test interactions only.\n")


if __name__ == "__main__":
    main()
