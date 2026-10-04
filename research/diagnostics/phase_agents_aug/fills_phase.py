"""Dev-only diagnostic (not a registered version): pooled dip-fill experience of the R2 dip agents on a 4h grid shifted by s hours.

Exactly research/diagnostics/phase_agents/build_tables.py's fill construction (v293.fills_of, 5 majors + 30 U2020 alts via v294, rungs
2.0..5.0, minute data only up to v293.END = 2025-09-25), with the grid start moved to v293.START + s h (the same shift build_tables applies to
the asset grid). The state x0..x6 is fills_of's own (sp30 / btc sp30 / dd24 at the minute before the fill, volreg / trend / sigma_4h of the
SHIFTED grid's 4h opens, hour from the shifted bar start). Adds a column `phase` = s.
Check (s = 0): the frame (without `phase`) must equal research/diagnostics/phase_agents/fills_U.parquet exactly.
Output: fills_s{s}.parquet, fills_check_s{s}.json
  python research/diagnostics/phase_agents_aug/fills_phase.py <s>
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
HERE = Path(__file__).parent
PA = ROOT / "research/diagnostics/phase_agents"


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def main(sft: int):
    bt = L("bt_aug_f", PA / "build_tables.py")
    v294 = L("v294_aug_f", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    eu = L("v221_aug_f", RD / "v221/v221_grid_hysteresis.py").eu
    v293.RUNGS = bt.U
    v293.END = bt.END                                   # 2025-09-25: no minute data after this enters any fill
    v293.START = v293.START + pd.Timedelta(hours=sft)
    t0 = time.time()
    btc = v293.Asset("BTCUSDT")
    parts, counts = [], {}
    for s in v293.MAJORS + v294.universe():
        A = btc if s == "BTCUSDT" else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
        if len(d):
            parts.append(d.assign(sym=s))
        counts[s] = len(d)
        print("phase", sft, "fills", s, len(d), round(time.time() - t0), flush=True)
        del A
    del btc
    allf = pd.concat(parts, ignore_index=True)
    chk = dict(phase=sft, start=str(v293.START), end=str(v293.END), rows=len(allf), per_sym=counts,
               t_fill_min=str(allf.t_fill.min()), t_fill_max=str(allf.t_fill.max()), t_exit_max=str(allf.t_exit.max()),
               hours_x6=sorted(int(h) for h in allf.x6.unique()))
    if sft == 0:
        ref = pd.read_parquet(PA / "fills_U.parquet")
        try:
            pd.testing.assert_frame_equal(allf.reset_index(drop=True), ref.reset_index(drop=True), check_exact=True)
            chk["equals_fills_U"] = True
        except AssertionError as e:
            chk["equals_fills_U"] = False
            chk["diff"] = str(e)[:2000]
        print("CHECK s0 equals fills_U:", chk["equals_fills_U"], flush=True)
    allf.assign(phase=sft).to_parquet(HERE / f"fills_s{sft}.parquet")
    (HERE / f"fills_check_s{sft}.json").write_text(json.dumps(chk, indent=1))
    print("done phase", sft, len(allf), round(time.time() - t0), flush=True)


if __name__ == "__main__":
    for a in sys.argv[1:]:
        main(int(a))
