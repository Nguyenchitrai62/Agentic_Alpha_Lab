"""Dev-only diagnostic: M5 (v367) and R2 (v321) on the standard grid with the 1m cube / opens built from BYBIT linear klines instead of Binance,
everything else as history_tm (same books, agents on with the deployed tables). Both venues are run on the same index from 2021-11-15 (Bybit
SOLUSDT starts 2021-10-15) to 2025-09-23, so the comparison is like for like. Nothing is selected."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
import phase_offset_full as pof

def bybit_minutes():
    out = {}
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        m = pd.read_parquet(ROOT / f"data/raw/bybit_linear_1m_20261004/{s}_1m.parquet", columns=["open_time", "open", "high", "low", "close"])
        m["open_time"] = pd.to_datetime(m["open_time"], unit="ms", utc=True)
        out[s] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return out

def main():
    pod = pof._load("pod_bb", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load("hist_bb", ROOT / "backend/history_tm.py")
    v221 = pof._load("v221_bb", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load("fw_bb", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(), eq_max=(eq if eq_max is None else eq_max).copy()) or {}
    live0, live1 = pd.Timestamp("2021-11-15", tz="UTC"), pof.DEV1
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    std_idx = books154.index[books154.index <= pof.DEV1 + pd.Timedelta(hours=4)]
    books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[list(books154.columns)]
    res = {}
    for venue, M in (("binance", pod.minutes()), ("bybit", bybit_minutes())):
        opens, prep = pof.prep_idx(M, std_idx, 0, list(books154.columns))
        del M
        idx, cols = prep["idx"], list(prep["cols"])
        for pipe in ("v367", "v321"):
            kw, trade = pof.pipe_setup(pipe, hist, v221, v216, idx, cols, True)
            ev = []
            eu.simulate(books.reindex(idx).fillna(0.0), opens, prep, trade=trade, win_start=5, events=ev, **kw)
            m = pof.metrics(cap["idx"], cap["eq"], cap["eq_min"], cap["eq_max"], ("2022-09-24", "2023-09-24", "2024-09-24"), live0, live1)
            m.update(pof.book_win(v221, ev, live0, live1))
            res[f"{venue}_{pipe}"] = {k: m[k] for k in ("monthly_geo", "dd_1m", "book_win", "win_all")} | {"years": [y["net_pct"] for y in m["yearly"]]}
            print(venue, pipe, res[f"{venue}_{pipe}"], flush=True)
    (Path(__file__).parent / "bybit_engine.json").write_text(json.dumps(res, indent=1))

if __name__ == "__main__":
    main()
