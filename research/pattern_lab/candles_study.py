"""W1 candle event study: textbook definitions fixed first, run once on dev bars."""

import torch  # noqa: F401  (import first: Windows DLL load order)
from pathlib import Path

import pandas as pd

from agentic_alpha_lab.patterns import candles, common

OUT = Path(__file__).resolve().parents[2] / "artifacts" / "research" / "pattern_lab" / "candles"
HORIZONS = (1, 3, 6, 12)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for tf in ("1h", "4h", "1d"):
        bars = common.load_bars(tf)
        ev = candles.events(bars)
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
        print(sig[["tf", "pattern", "horizon", "n", "mean_excess_bps"]].to_string(index=False))


if __name__ == "__main__":
    main()
