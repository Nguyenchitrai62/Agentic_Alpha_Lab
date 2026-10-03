"""Diagnostic: which panel columns differ between the real REST as-of live_panel and the cached-REST emulation (one as-of bar)."""
import importlib.util, os, sys
from pathlib import Path
import numpy as np, pandas as pd, requests
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[3]; os.chdir(ROOT); sys.path.insert(0, str(HERE))
import rest_cache as rc
def _load(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
v104 = _load("emu_v104", ROOT / "scripts/v104_advisor.py")
T = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else "2026-09-10 11:59:59.999", tz="UTC")
os.environ["ADVISOR_ASOF"] = str(T)
real = v104.live_panel(requests.Session(), T.to_pydatetime())
rf = {s: v104.funding_asof(requests.Session(), s) for s in v104.v92.SYMS}
K4, K1D, FR = rc.market_data(pd.Timestamp("2026-10-03 12:00", tz="UTC"))
import agentic_alpha_lab.data.binance_usdm as bu
bu.fetch_klines = lambda symbol, interval, start, end=None, session=None: (K4 if interval == "4h" else K1D)[symbol].pipe(lambda d: d[(d.open_time >= pd.Timestamp(start)) & (d.open_time <= pd.Timestamp(end))].reset_index(drop=True).copy())
v104.funding_asof = lambda session, sym: FR[sym][FR[sym].fundingTime <= T].tail(1000).reset_index(drop=True)
em = v104.live_panel(None, T.to_pydatetime())
j = real.merge(em, on=["t", "sym"], suffixes=("_r", "_e"))
for c in [c for c in em.columns if c not in ("t", "sym", "bar")]:
    d = (j[c + "_r"].astype(float) - j[c + "_e"].astype(float)).abs()
    if d.max() > 1e-9:
        k = d.idxmax(); print(c, "max", d.max(), "n>1e-9", int((d > 1e-9).sum()), j.loc[k, ["t", "sym"]].tolist(), "last differing t", j.loc[d > 1e-9, "t"].max(), "recent-window start", T - pd.Timedelta(days=120))
for s in v104.v92.SYMS:
    a, b = rf[s], FR[s][FR[s].fundingTime <= T].tail(1000).reset_index(drop=True)
    print(s, "real funding", len(a), a.fundingTime.min(), a.fundingTime.max(), "| cached", len(b), b.fundingTime.min(), b.fundingTime.max())
