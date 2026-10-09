"""oc_netting analyze (LIGHT): selection + tables + fee/funding + win rates.

Reads tmp/engine_dev.pkl, tmp/engine_dev_events.pkl, tmp/engine_dev_rowstats.json,
tmp/n2overlay_dev.json and the stored G2 reference. No 1m. No fits.

  .venv/Scripts/python.exe research/tournament/oc_netting/analyze.py --stage dev
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "full"], default="dev")
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof
    v221 = pof._load("v221_netan", pof.RD / "v221/v221_grid_hysteresis.py")

    runs = pickle.loads((HERE / "tmp" / f"engine_{args.stage}.pkl").read_bytes())
    evs = pickle.loads((HERE / "tmp" / f"engine_{args.stage}_events.pkl").read_bytes())
    rowstats = json.loads((HERE / "tmp" / f"engine_{args.stage}_rowstats.json").read_text())
    n2 = json.loads((HERE / "tmp" / f"n2overlay_{args.stage}.json").read_text())
    stat = json.loads((HERE / "tmp" / f"engine_{args.stage}_stats.json").read_text())
    stored = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]

    anchors = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
    ysel = [0, 1, 2, 3] if args.stage == "dev" else [4]
    rows = [r for r in ("G2REF", "N1") if r in stat and isinstance(stat[r], dict)]

    print(f"=== oc_netting {args.stage}: per-year R %/mo / DD % ===", flush=True)
    for r in rows:
        print(r, stat[r]["years"], "=>", {k: stat[r][k] for k in ("R", "W", "DD", "losing")}, flush=True)
    print("N2 overlay:", n2["years"], "=>", {k: n2[k] for k in ("R", "W", "DD", "losing")}, flush=True)
    print("stored G2 5y:", [(a, b) for a, b in stored["years"]], stored["R"], stored["W"], stored["DD"], flush=True)

    print(f"=== fee/funding split (sum over 4 sub-accounts, fractions of sub-account equity) ===", flush=True)
    for r in rows:
        fees = sum(rowstats[str(s)][r].get("fees", 0) for s in range(4))
        fund = sum(rowstats[str(s)][r].get("funding", 0) for s in range(4))
        fills = sum(rowstats[str(s)][r].get("fills", 0) for s in range(4))
        rungs = sum(rowstats[str(s)][r].get("rungs", 0) for s in range(4))
        print(f"{r}: fills={fills} rungs={rungs} fees={fees:.4f} funding={fund:.4f}", flush=True)

    print("=== win rates (live window per shift, aggregated) ===", flush=True)
    for r in rows:
        nb_all, wb_num, rr_all = 0, 0.0, []
        for s in range(4):
            sh = pd.Timedelta(hours=s)
            live0 = pof.DEV0 + sh
            live1 = (pd.Timestamp("2026-09-23", tz="UTC") if args.stage == "full" else pof.DEV1) + sh
            bw = pof.book_win(v221, evs[s][r], live0, live1)
            nb = bw.get("book_trades") or 0
            nb_all += nb
            wb_num += (bw.get("book_win") or 0.0) * nb
            rr_all += [float(e["ret"]) for e in evs[s][r]
                       if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout")
                       and live0 <= pd.Timestamp(e["t"]) < live1 + pd.Timedelta(hours=8)]
        rr = np.array(rr_all, float)
        print(f"{r}: book_trades={nb_all} book_win={wb_num / nb_all if nb_all else None} "
              f"rungs={len(rr)} rung_win={round(float((rr > 0).mean()), 4) if len(rr) else None} "
              f"all_win={round((wb_num + float((rr > 0).sum())) / (nb_all + len(rr)), 4) if nb_all + len(rr) else None}",
              flush=True)

    print("=== per-year trade census (summed over shifts) ===", flush=True)
    for r in rows:
        per = {}
        for y, a0 in enumerate(anchors):
            if y not in ysel:
                continue
            a = pd.Timestamp(a0, tz="UTC")
            b = a + pd.Timedelta(days=365)
            nb = sum(1 for s in range(4) for e in evs[s][r]
                     if e["kind"] in ("book_stop", "book_tp", "book_close", "book_reduce", "book_partial")
                     and a <= pd.Timestamp(e["t"]) < b)
            nr = [float(e["ret"]) for s in range(4) for e in evs[s][r]
                  if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and a <= pd.Timestamp(e["t"]) < b]
            per[y] = dict(book_exits=nb, rungs=len(nr),
                          rung_win=round(float(np.mean(np.array(nr) > 0)), 4) if nr else None)
        print(r, per, flush=True)

    if args.stage == "dev":
        cand = {}
        for r, src in (("N1", stat["N1"]), ("N2", n2)):
            cand[r] = dict(R=src["R"], W=src["W"], DD=src["DD"], losing=src["losing"])
        elig = {r: m for r, m in cand.items() if m["DD"] <= 20 and m["losing"] == 0}
        ge5 = {r: m for r, m in elig.items() if m["R"] >= 5}
        pool = ge5 if ge5 else elig
        pick = max(pool, key=lambda r: (pool[r]["W"], pool[r]["R"])) if pool else None
        print(f"dev4 robust pick: {pick} {cand.get(pick)} (eligible={sorted(elig)})", flush=True)


if __name__ == "__main__":
    main()
