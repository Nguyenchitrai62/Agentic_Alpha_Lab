"""W5 positioning event study: definitions fixed in patterns/positioning.py, run once.

Evaluates ONLY via common.event_study (decisions before 2025-09-14).
Never computes forward returns for dates >= 2025-09-24.
"""

from pathlib import Path

import pandas as pd

from agentic_alpha_lab.patterns import common, positioning

OUT = Path(__file__).resolve().parents[2] / "artifacts" / "research" / "vf" / "positioning"
HORIZONS = (1, 3, 6, 12)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for tf in ("1h", "4h", "1d"):
        bars = common.load_bars(tf)
        ev = positioning.events(bars)
        res = common.event_study(bars, ev, horizons=HORIZONS, tf=tf)
        res.to_csv(OUT / f"event_study_{tf}.csv", index=False)
        frames.append(res)
        n_sig = int(res["stable_significant"].sum()) if len(res) else 0
        print(f"{tf}: rows={len(res)} stable_significant={n_sig}", flush=True)
    all_res = pd.concat(frames, ignore_index=True)
    all_res.to_csv(OUT / "event_study_all.csv", index=False)
    sig = all_res[all_res["stable_significant"]]
    print(f"total={len(all_res)} stable={len(sig)}", flush=True)
    if len(sig):
        print(sig[["tf", "pattern", "horizon", "n", "mean_excess_bps",
                    "q_value"]].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
