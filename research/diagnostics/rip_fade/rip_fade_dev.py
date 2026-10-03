"""Dev-only event study (holding bars 2021-09-24 .. 2025-09-17; no most-recent-year number is computed): bracket SELL limits above the 4h open.
Mirror of the M3 dip limit: short limit at lv = o1 * (1 + k sigma_4h), filled on a 1m trade-through from minute 16, TP limit lv * (1 - 1 sigma),
exchange-native touch stop lv * (1 + 8 sigma), else market exit at the next 4h open; maker entry / maker TP / taker stop or exit; shorts receive no
funding (gate). Regime split by the v293 trend feature at the bar (42-bar log return / (sigma sqrt 42)): down (< 0) vs up (>= 0).
Universe: the 5 majors and, separately, the 30 U2020 alts (experience only). Reports per dev year: fills, win, mean net per fill (%).
  python research/diagnostics/rip_fade/rip_fade_dev.py
"""
import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
RD = Path("research/parallel/rounds/parallel-20260906-r2")
def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
v294 = L("v294_rf", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
MAKER, TAKER = 0.0002, 0.00055
ANCH = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
STOP_DEV = pd.Timestamp("2025-09-17", tz="UTC")
rows = []
for s in v293.MAJORS + v294.universe():
    A = v293.Asset(s)
    for j in range(1, A.nb - 1):
        T = A.t0[j]
        if T < ANCH[0] or T >= STOP_DEV:
            continue
        sg, o1, o2 = A.sig[j], A.o[j], A.o[j + 1]
        if not (np.isfinite(sg) and np.isfinite(o1) and np.isfinite(o2)):
            continue
        H = A.H[j * 240: j * 240 + 240]; Lw = A.L[j * 240: j * 240 + 240]; O = A.O[j * 240: j * 240 + 240]
        for k in (3.0, 4.0):
            lv = o1 * (1 + k * sg)
            hit = H[16:239] > lv
            if not hit.any():
                continue
            f = 16 + int(np.argmax(hit))
            tp, st = lv * (1 - sg), lv * (1 + 8 * sg)
            hs = H[f + 1:240] >= st; ht = Lw[f + 1:240] < tp
            ks = int(np.argmax(hs)) if hs.any() else None; kt = int(np.argmax(ht)) if ht.any() else None
            if ks is not None and (kt is None or ks <= kt):
                ret = 1 - max(st, O[f + 1 + ks]) / lv - MAKER - TAKER
            elif kt is not None:
                ret = 1 - tp / lv - 2 * MAKER
            else:
                ret = 1 - o2 / lv - MAKER - TAKER
            y = max(q for q, a in enumerate(ANCH) if T >= a)
            rows.append(dict(sym=s, major=s in v293.MAJORS, k=k, y=y, down=bool(A.trend[j] < 0), ret=ret))
    print(s, flush=True)
    del A
d = pd.DataFrame(rows)
g = d.groupby(["major", "down", "k", "y"]).ret.agg(n="size", win=lambda x: round(float((x > 0).mean()), 3), mean=lambda x: round(float(100 * x.mean()), 3))
print(g.unstack("y").to_string())
Path("research/diagnostics/rip_fade/rip_fade_dev.json").write_text(json.dumps(g.reset_index().to_dict("records"), indent=1))
