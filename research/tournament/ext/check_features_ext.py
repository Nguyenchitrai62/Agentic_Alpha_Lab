"""Overlap check: ext/bar_open_ext.parquet vs data/bar_open.parquet (rows keyed by sym / j / r) and ext/hourly_ext vs data/hourly (sym / t).
Plus causality: 20 random bar_open_ext rows recomputed from 1m arrays truncated at the bar's minute-0 close (kk = 240 j) are identical."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = HERE / "features_check.json"


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def logret(C, k, n):
    return np.log(C[k] / C[k - n]) if k - n >= 0 and C[k] > 0 and C[k - n] > 0 else np.nan
out = {}
o, n = pd.read_parquet(ROOT / "research/tournament/data/bar_open.parquet"), pd.read_parquet(HERE / "bar_open_ext.parquet")
fo, fn = pd.read_parquet(ROOT / "research/diagnostics/phase_agents/fills_U.parquet"), pd.read_parquet(HERE / "fills_U_ext.parquet")
out["bar_open_index_matches_fills_ext"] = bool(n.index.equals(fn.index) and (n.j.to_numpy() == fn.j.to_numpy()).all() and (n.sym.to_numpy() == fn.sym.to_numpy()).all())
m = o.merge(n, on=["sym", "j", "r"], how="left", suffixes=("_old", ""), indicator=True)
out["bar_open_rows_old"], out["bar_open_rows_ext"], out["old_rows_missing_in_ext"] = len(o), len(n), int((m._merge == "left_only").sum())
cols = [c for c in o.columns if c not in ("sym", "j", "r")]
d = {}
for c in cols:
    x, y = m[c + "_old"].to_numpy(float), m[c].to_numpy(float)
    d[c] = dict(max_abs=float(np.nanmax(np.abs(x - y))) if np.isfinite(x - y).any() else 0.0, nan_mismatch=int((np.isnan(x) != np.isnan(y)).sum()))
out["bar_open_diff"] = d
out["bar_open_identical_first_rows"] = bool(n.iloc[: len(o)].reset_index(drop=True).equals(o.reset_index(drop=True)))
ho, hn = pd.read_parquet(ROOT / "research/tournament/data/hourly.parquet"), pd.read_parquet(HERE / "hourly_ext.parquet")
mh = ho.merge(hn, on=["sym", "t"], how="left", suffixes=("_old", ""), indicator=True)
out["hourly_rows_old"], out["hourly_rows_ext"], out["hourly_old_missing_in_ext"] = len(ho), len(hn), int((mh._merge == "left_only").sum())
out["hourly_maxdiff"] = {c: float(np.nanmax(np.abs(mh[c + "_old"].to_numpy(float) - mh[c].to_numpy(float)))) for c in ("open", "high", "low", "close")}
out["hourly_t_max_ext"], out["hourly_t_max_old"] = str(hn.t.max()), str(ho.t.max())
out["hourly_columns_ext"] = list(hn.columns)
last = hn.groupby("sym").t.max()
out["hourly_syms_ending_early"] = {s: str(t) for s, t in last.items() if t < pd.Timestamp("2026-09-23 23:00", tz="UTC")}
out["hourly_rows_after_cut"] = int((hn.t >= pd.Timestamp("2026-09-24", tz="UTC")).sum())

# ---- causality: 20 random bar_open_ext rows recomputed from truncated 1m arrays ----
v294 = L("v294_chk", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
v293.END = pd.Timestamp("2026-09-24", tz="UTC")
rng = np.random.default_rng(7)
idx = rng.choice(len(n), 20, replace=False)
assets, btc_holder = {}, {}
btc = v293.Asset("BTCUSDT")
worst = 0.0
rows_checked = []
for i in sorted(idx):
    r = n.iloc[i]
    s, j = r.sym, int(r.j)
    kk = j * 240
    A = assets.get(s)
    if A is None:
        A = btc if s == "BTCUSDT" else v293.Asset(s)
        assets[s] = A
    sg = A.sig[j]
    C, Hh, Ll = A.C[: kk + 1], A.H[: kk + 1], A.L[: kk + 1]  # truncated at minute-0 close
    assert len(C) == kk + 1
    exp = {}
    for nn, name in ((60, "r1h"), (240, "r4h"), (1440, "r24h"), (4320, "r72h")):
        exp[name] = logret(C, kk, nn) / sg
    lo24 = np.nanmin(Ll[max(0, kk - 1439): kk + 1]); hi24 = np.nanmax(Hh[max(0, kk - 1439): kk + 1])
    hi7 = np.nanmax(Hh[max(0, kk - 10079): kk + 1]); lo7 = np.nanmin(Ll[max(0, kk - 10079): kk + 1])
    exp["rng24"] = (hi24 - lo24) / C[kk] / sg
    exp["dd7"], exp["du7"] = np.log(C[kk] / hi7) / sg, np.log(C[kk] / lo7) / sg
    h1 = C[max(0, kk - 1440): kk + 1: 60]
    exp["rv24"] = np.nanstd(np.diff(np.log(h1))) / (sg / 2) if len(h1) > 3 else np.nan
    dmax = 0.0
    for c, v in exp.items():
        a, b = float(r[c]), float(v)
        same_nan = (np.isnan(a) and np.isnan(b))
        dd = 0.0 if same_nan else abs(a - b)
        assert same_nan or dd < 1e-9, (i, s, j, c, a, b)
        dmax = max(dmax, dd)
    worst = max(worst, dmax)
    rows_checked.append(dict(i=int(i), sym=s, j=j, max_abs_diff=float(dmax)))
del assets
del btc
out["causality_rows"] = rows_checked
out["causality_max_abs_diff"] = float(worst)
out["causality_passed"] = bool(worst < 1e-9)
(HERE / "features_check.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
