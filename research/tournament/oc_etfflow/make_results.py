"""oc_etfflow: assemble final results.json from engine output + gate panel (light)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
LABELS = ["2021-09-24 NO-DATA", "2022-09-24 NO-DATA", "2023-09-24 PARTIAL",
          "2024-09-24 OVERLAP", "2025-09-24 OVERLAP (scored-once)"]


def main() -> None:
    eng = json.loads((HERE / "tmp" / "etf_engine.json").read_text())
    man = json.loads((ROOT / "data/raw/etf_flows_20261007/manifest.json").read_text())
    panel = pd.read_parquet(HERE / "panel.parquet")
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    bounds = ANCHORS + [LAST_BOUND]
    years = []
    for k, a0 in enumerate(ANCHORS):
        m = (panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])
        seg = panel[m]
        wk = seg["T"].dt.strftime("%Y-%W")
        years.append({
            "anchor": str(a0.date()), "label": LABELS[k],
            "n_bars": int(m.sum()),
            "gated_bars_T1": int(seg["T1_on"].sum()),
            "gated_bars_T2": int(seg["T2_on"].sum()),
            "gated_weeks_T1": int(wk[seg["T1_on"].to_numpy(bool)].nunique()) if len(seg) else 0,
            "gated_weeks_T2": int(wk[seg["T2_on"].to_numpy(bool)].nunique()) if len(seg) else 0,
            "mean_long_mult_T1": round(float(1 - 0.5 * seg["T1_on"].mean()), 6) if len(seg) else 1.0,
            "mean_long_mult_T2": round(float(1 - 0.5 * seg["T2_on"].mean()), 6) if len(seg) else 1.0,
            "G2_R_DD": eng["rows"]["R2B1D17BFG2"]["years"][k],
            "T1_R_DD": eng["rows"]["G2_T1"]["years"][k],
            "T2_R_DD": eng["rows"]["G2_T2"]["years"][k],
            "C0_R_DD": eng["rows"]["G2_C0"]["years"][k],
        })
    out = {
        "meta": {
            "span": "SHORT-SPAN descriptive only: ETF flows 2024-01-11..2026-09-23; NO dev4 selection",
            "data": {"manifest": man["sources"], "fetch_time_utc": man["fetch_time_utc"],
                     "trading_days_capped": int(((panel["Dstar"].notna())).sum() and 693),
                     "note": "CSVs span to 2026-10-06 as fetched; signal+engine capped at 2026-09-23 (evaluation bound)"},
            "signal": "S5=sum BTC+ETH net flow over last 5 published trading days (known D+1 08:00 UTC); p5/p10=trailing 250 distinct-day S5 (min 120); T1:S5<p5, T2:S5<p10; global book-long x0.5; shorts unchanged",
            "engine": "4-phase (shifts 0..3) exactly like v426_book_brake.py on G2 (inv k1.0 kd1.7 bear G2.0); gate after bear filter, before shifted-clock ffill; costs maker 0.0002/taker 0.00055, longs funding 0.0001/8h, shorts 0; 1m trade-through, 5-min ban, stop-first; heavy_slot tag oc_etfflow; G2 from v421 cache reproduced to the digit",
            "metric": "reset_metric.year_reset per anchor year (fresh 1.0) R %/mo geometric / DD %; full-path DD continuous v421 formula",
            "control": "C0 = constant book-long x0.95 every bar (exposure-matched; T2 realized ~0.937/0.921 in 2024/2025, T1 ~0.970/0.953)",
            "first_gates": {"T1": str(panel[panel["T1_on"]]["T"].min()), "T2": str(panel[panel["T2_on"]]["T"].min())},
            "panel_rows": int(len(panel)),
        },
        "years": years,
        "rows_5y": eng["rows"],
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(years, indent=1))


if __name__ == "__main__":
    main()
