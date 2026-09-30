"""Dev-only (no data after 2025-09-24): stop design of the 12h dip account - mean return per notional, win, stops, net and DD per dev year."""
import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
s = importlib.util.spec_from_file_location("acc2", "research/diagnostics/daily_dip/account2.py"); a2 = importlib.util.module_from_spec(s); s.loader.exec_module(a2)
a2.v289.END = pd.Timestamp("2025-09-24", tz="UTC")
data = {x: a2.v289.load_1m(x) for x in a2.SYMS}
ANCH = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
CFG = {"touch3": dict(stop_mode="touch", m_stop=3.0, backstop=None, risk_at=3.0),
       "close5_4_b8": dict(stop_mode="close5", m_stop=4.0, backstop=8.0, risk_at=4.0),
       "close5_3_b8": dict(stop_mode="close5", m_stop=3.0, backstop=8.0, risk_at=3.0),
       "touch8_only": dict(stop_mode="touch", m_stop=8.0, backstop=None, risk_at=8.0)}
out = {}
for name, c in CFG.items():
    acc = a2.simulate_account(data, r_risk=0.01, **c)
    g = acc["grid"]; eq = acc["cash"] + acc["u_close"]; lo = np.minimum(acc["cash"] + acc["u_low"], eq)
    rows = []
    for a0 in ANCH:
        mk = np.asarray((g >= a0) & (g < a0 + pd.Timedelta(days=365))); i0 = int(np.argmax(mk)); base = eq[i0 - 1]
        e, l = eq[mk] / base, lo[mk] / base
        dd = float(np.max(1 - l / np.maximum.accumulate(np.r_[1.0, e])[1:]))
        t = acc["trades"]; t = t[(t.t >= a0) & (t.t < a0 + pd.Timedelta(days=365))]
        rows.append(dict(y=a0.year, net=round(100 * (e[-1] - 1), 1), dd=round(100 * dd, 1), n=len(t), win=round(float((t.ret > 0).mean()), 3),
                         mean_ret_pct=round(100 * float(t.ret.mean()), 3), stops=int((t.kind == "stop").sum())))
    out[name] = rows
    print(name, rows, flush=True)
Path("research/diagnostics/daily_dip/stops_dev.json").write_text(json.dumps(out, indent=1))
