"""Dev-only event study (holding bars 2021-09-24 .. 2025-09-17): RE-FILLS of a dip rung after its take-profit inside the same 4h bar (BOT only).
R2 rules (v293 replica: rungs 2.5 / 3 / 3.5 / 4 / 5 sigma_4h below the 4h open from minute 16, TP 1 sigma, close5 stop 4 sigma + native 8-sigma
backstop, else exit at the next 4h open). After a TP exit at minute x, the same limit is re-placed; a refill = the next 1m trade-through after x
(before minute 239), with the same exit rules from that minute. Up to two refills per rung and bar. Majors and the 30 U2020 alts separately.
Reports per dev year: first fills and refills (n, win, mean net % per fill).
  python research/diagnostics/dip_refill/dip_refill_dev.py
"""
import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
RD = Path("research/parallel/rounds/parallel-20260906-r2")
def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
v294 = L("v294_rf2", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
MAKER, TAKER, FUND = 0.0002, 0.00055, 0.0001
ANCH = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
STOP_DEV = pd.Timestamp("2025-09-17", tz="UTC")
RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
rows = []
for s in v293.MAJORS + v294.universe():
    A = v293.Asset(s)
    for j in range(1, A.nb - 1):
        T = A.t0[j]
        if T < ANCH[0] or T >= STOP_DEV:
            continue
        sg, o1 = A.sig[j], A.o[j]
        if not (np.isfinite(sg) and np.isfinite(o1) and np.isfinite(A.o[j + 1])):
            continue
        Lw = A.L[j * 240: j * 240 + 239]
        y = max(q for q, a in enumerate(ANCH) if T >= a)
        for k in RUNGS:
            lv = o1 * (1 - k * sg)
            start, n = 16, 0
            while n < 3 and start < 239:
                hit = Lw[start:239] < lv
                if not hit.any():
                    break
                f = start + int(np.argmax(hit))
                ret, tx = v293.outcomes(A, j, lv, sg, f, (1.0,), MAKER, TAKER, FUND)[0]
                if not np.isfinite(ret):
                    break
                rows.append(dict(major=s in v293.MAJORS, y=y, refill=n > 0, ret=ret))
                x = int((tx - T).total_seconds() // 60)
                tp_exit = abs(ret - (sg / 1 * 0 + (1 + sg) - 1 - 2 * MAKER)) < 1e-12  # TP exit returns exactly sg - 2 maker
                if not tp_exit or x >= 238:
                    break
                start, n = x + 1, n + 1
    print(s, flush=True)
    del A
d = pd.DataFrame(rows)
g = d.groupby(["major", "refill", "y"]).ret.agg(n="size", win=lambda x: round(float((x > 0).mean()), 3), mean=lambda x: round(float(100 * x.mean()), 3))
print(g.unstack("y").to_string())
Path("research/diagnostics/dip_refill/dip_refill_dev.json").write_text(json.dumps(g.reset_index().to_dict("records"), indent=1))
