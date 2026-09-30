"""Dev-only: v289's 12h dip account at a smaller risk per rung (not registered; no data after 2025-09-24 is loaded).

Runs v289.simulate_account on 2021-06-01 .. 2025-09-24 with R_RISK in (0.0025, 0.005, 0.01, 0.03) and reports per dev year the
account's net, its 1m-low-marked DD and the daily correlation with CB's total PnL is left to the registered run.
"""
import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
R = "research/parallel/rounds/parallel-20260906-r2"
s = importlib.util.spec_from_file_location("v289d", R + "/v289/v289_dip12h_account.py"); v = importlib.util.module_from_spec(s); s.loader.exec_module(v)
v.END = pd.Timestamp("2025-09-24", tz="UTC")
data = {x: v.load_1m(x) for x in v.SYMS}
ANCH = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
out = {}
for r in (0.0025, 0.005, 0.01, 0.03):
    v.R_RISK = r
    acc = v.simulate_account(data)
    g = acc["grid"]; eq = acc["cash"] + acc["u_close"]; lo = np.minimum(acc["cash"] + acc["u_low"], eq)
    rows = []
    for a0 in ANCH:
        mk = np.asarray((g >= a0) & (g < a0 + pd.Timedelta(days=365)))
        i0 = int(np.argmax(mk)); base = eq[i0 - 1]
        e, l = eq[mk] / base, lo[mk] / base
        dd = float(np.max(1 - l / np.maximum.accumulate(np.r_[1.0, e])[1:]))
        tr = acc["trades"]; t = tr[(tr.t >= a0) & (tr.t < a0 + pd.Timedelta(days=365))]
        rows.append((a0.year, round(100 * (e[-1] - 1), 1), round(100 * dd, 1), len(t), round(float((t.ret > 0).mean()), 3), round(100 * float(t.ret.mean()), 3)))
    out[str(r)] = rows
    print("R", r, "(year, net %, DD %, trades, win, mean ret per notional %)", rows, flush=True)
Path("research/diagnostics/daily_dip/sizing_dev.json").write_text(json.dumps(out, indent=1))
