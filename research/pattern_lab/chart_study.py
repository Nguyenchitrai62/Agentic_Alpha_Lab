"""W2 chart-pattern event study (pattern_lab_r1).

Runs common.event_study on development bars (default loader hides the opened
year) for 1h/4h/1d. Textbook definitions were fixed in
src/agentic_alpha_lab/patterns/chart.py BEFORE this run; no tuning.
"""
import torch  # noqa: F401  (DLL load-order guard on this host)

from pathlib import Path

import pandas as pd

from agentic_alpha_lab.patterns import chart, common

OUT = Path(__file__).resolve().parents[2] / "artifacts" / "research" / "pattern_lab" / "chart"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for tf in ("1h", "4h", "1d"):
        bars = common.load_bars(tf)
        ev = chart.events(bars)
        res = common.event_study(bars, ev, tf=tf)
        res.to_csv(OUT / f"chart_event_study_{tf}.csv", index=False)
        frames.append(res)
        n_sig = int(res["stable_significant"].sum()) if len(res) else 0
        print(f"{tf}: rows={len(res)} stable_significant={n_sig}")
    allres = pd.concat(frames, ignore_index=True)
    allres.to_csv(OUT / "chart_event_study_all.csv", index=False)
    sig = allres[allres["stable_significant"]] if len(allres) else allres
    sig.to_csv(OUT / "chart_event_study_stable_significant.csv", index=False)
    print(f"TOTAL stable_significant rows: {len(sig)}")


if __name__ == "__main__":
    main()
