"""Year metric with the four sub-accounts reset to 1/4 of the capital at each anchor (what a user starting that year gets)."""
import importlib.util, pickle, numpy as np, pandas as pd
from pathlib import Path
RD = Path(__file__).resolve().parents[3] / "research/parallel/rounds/parallel-20260906-r2"
spec = importlib.util.spec_from_file_location("v388_rm", RD / "v388/v388_bot_stop_distance.py"); v388 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v388)


def year_reset(runs, strat, y, g1=None):
    g1 = g1 or v388.Y1 + pd.Timedelta(hours=12)
    a0 = pd.Timestamp(v388.ANCH[y], tz="UTC")
    E, MN = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][strat], pd.Timestamp("2021-09-24 04:00", tz="UTC"), g1)
        b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
        seg = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
        E.append(e1[seg] / b); MN.append(m1[seg] / b)
    es, ms = sum(E) / 4, sum(MN) / 4
    pk = np.maximum.accumulate(es.to_numpy())
    return dict(R=round(100 * float(es.iloc[-1] ** (1 / 12) - 1), 3), DD=round(100 * float(np.max(1 - ms.to_numpy() / pk)), 2))


if __name__ == "__main__":
    runs = pickle.loads((Path(__file__).parent / "runs.pkl").read_bytes())
    for strat in ("R2", "R2_book", "R2_dip"):
        print(strat, [tuple(year_reset(runs, strat, y).values()) for y in range(5)])
