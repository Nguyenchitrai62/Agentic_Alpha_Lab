"""Walk-forward decision table of the v321 R2 BOT pipeline (size + take-profit at the bar open) for the backend history (not a selection input).
From the v306 gene tables (fit "U": agents trained on pooled fills of all seven rung depths that exited before anchor - 7 days, state at the close of
minute 0): per holding bar T, major and R2 rung index (depths 2.5 / 3.0 / 3.5 / 4.0 / 5.0): size (S1 rule) and TP (X4 rule).
Check (asserted): the engine with these lookup hooks reproduces the v306 / v321 R2 seed (dev4 7.079).
Output: artifacts/research/engine_real/v321_r2_table_m0.parquet (T, sym, rung, size, tp)
  python research/diagnostics/r2_exec/r2_cache.py
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


v306 = L("v306_r2c", RD / "v306/v306_walkforward_evolution.py")
v306.init_worker()
d = v306.decode(v306.encode(v306.SEEDS["R2"]))
size, tp = v306._tables(d)
assert tuple(k for k in v306.U if d[f"r{int(k * 10)}"]) == R2
idx, cols = v306.W["idx"], v306.W["cols"]
rows = []
for r, k in enumerate(R2):
    kk = v306.U.index(k)
    for a, s in enumerate(cols):
        T = idx + pd.Timedelta(hours=4)
        rows.append(pd.DataFrame({"T": T, "sym": s, "rung": r, "size": size[:, a, kk], "tp": tp[:, a, kk]}))
tab = pd.concat(rows, ignore_index=True)
tab = tab[tab["T"] >= pd.Timestamp("2021-09-24", tz="UTC")]
res = v306.run_genome(v306.encode(v306.SEEDS["R2"]))
dev4 = v306.metrics(res, [0, 1, 2, 3])["R"]
print("R2 dev4", dev4, flush=True)
assert abs(dev4 - 7.079) < 0.003
out = Path("artifacts/research/engine_real/v321_r2_table_m0.parquet")
tab.to_parquet(out)
print("saved", out, len(tab), tab["size"].value_counts().to_dict(), tab["tp"].value_counts().to_dict())
