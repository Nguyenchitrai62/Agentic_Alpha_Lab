"""Dev-only: how much does a 12h dip ladder overlap with CB's own PnL (book and 4h dip sleeve)? (not registered)

CB (v285 D2) is simulated with the audited engine and `attrib` (per-bar book / sleeve PnL as fractions of bar-start equity); only rows
before 2025-09-24 are analysed. 12h dip events = daily_dip_dev.study at 720 minutes, rungs k 3.0 / 3.5 / 4.0, exit B (TP +1 sigma or the
next 12h open), one unit per fill, PnL booked on the exit day. Reported per dev year: daily correlation with CB sleeve / book / total, the
12h ladder's own daily-PnL stats, the share of 12h fills on days when the CB sleeve lost, and a naive sub-account blend: daily return =
(1 - x) CB + x (u x 12h ladder units) for x in (0.1, 0.2), u = 0.5 (half the sub-account per fill) - worst year monthly and max DD on
daily closes (indicative only; the real test is an engine run).

  python research/diagnostics/daily_dip/overlap_dev.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = Path("research/parallel/rounds/parallel-20260906-r2")
END = pd.Timestamp("2025-09-24", tz="UTC")
C4R = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    dd = _load("daily_dip_dev", HERE / "daily_dip_dev.py")
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216 = v221.eu, v221.v216
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    D = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    Dq = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (D + Dq) / 2
    att = []
    eu.simulate(cb, opens, eu.prepare(books154, opens), trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)),
                win_start=5, attrib=att, **dict(v221.KW, **C4R))
    a = pd.DataFrame({"t": [x[0] for x in att], "book": [float(np.sum(x[1])) for x in att], "sleeve": [float(x[2]) for x in att]})
    a["t"] = pd.to_datetime(a["t"], utc=True)
    a = a[a.t < END]
    day = a.set_index("t").resample("1D").apply(lambda s: np.prod(1 + s) - 1)
    day["total"] = (1 + day["book"]) * (1 + day["sleeve"]) - 1
    evs = []
    for s in dd.SYMS:
        ev, _ = dd.study(dd.load_1m(s), 720)
        evs.append(ev[ev.k >= 3.0].assign(sym=s))
    ev = pd.concat(evs)
    ev["day"] = (ev["t"] + pd.Timedelta(hours=12)).dt.floor("1D")  # exit at the next 12h open or earlier (TP) -> booked on that day
    lad = ev.groupby("day")["net_b"].sum().reindex(day.index).fillna(0.0)
    out = {}
    for a0 in dd.ANCHORS:
        a1 = a0 + pd.Timedelta(days=365)
        mk = (day.index >= a0) & (day.index < a1)
        d, l = day[mk], lad[mk]
        e = ev[(ev.t >= a0) & (ev.t < a1)]
        lose_days = set(d.index[d["sleeve"] < 0])
        row = dict(corr_sleeve=round(float(np.corrcoef(l, d["sleeve"])[0, 1]), 3), corr_book=round(float(np.corrcoef(l, d["book"])[0, 1]), 3),
                   corr_total=round(float(np.corrcoef(l, d["total"])[0, 1]), 3), fills=int(len(e)),
                   share_fills_on_cb_sleeve_loss_days=round(float(e["t"].dt.floor("1D").isin(lose_days).mean()), 3),
                   cb_year_pct=round(100 * float(np.prod(1 + d["total"]) - 1), 1))
        for x in (0.1, 0.2):
            r = (1 - x) * d["total"] + x * 0.5 * l
            eq = np.cumprod(1 + r.to_numpy())
            row[f"blend_x{x}_year_pct"] = round(100 * float(eq[-1] - 1), 1)
            row[f"blend_x{x}_dd_daily"] = round(100 * float(np.max(1 - eq / np.maximum.accumulate(eq))), 1)
        eqc = np.cumprod(1 + d["total"].to_numpy())
        row["cb_dd_daily"] = round(100 * float(np.max(1 - eqc / np.maximum.accumulate(eqc))), 1)
        out[str(a0.year)] = row
        print(a0.year, row, flush=True)
    (HERE / "overlap_dev.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
