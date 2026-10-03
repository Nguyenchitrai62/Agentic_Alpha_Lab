"""Part 1: dynamic correlation checks. Writes replication.json FIRST, then CSVs. Cap: no returns after 2026-09-23."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from leak_checks import (ANCHORS, CACHE, OPEN_CAP, PRICE_CAP, SYMS, build_opens_4h_from_1m, leak_flags, load_members,
                         return_triples, spearman)

HERE = Path(__file__).parent


def fileinfo(p: Path):
    return {"path": p.as_posix(), "bytes": p.stat().st_size, "mtime": p.stat().st_mtime,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16]}


def main():
    members = load_members()
    opens = build_opens_4h_from_1m()
    r_dec, r_hold, r_next = return_triples(opens)
    # replication.json FIRST (before any correlation is inspected)
    try:
        rev = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        rev = "unknown"
    rep = {
        "git_rev": rev,
        "price_cap": str(PRICE_CAP), "open_cap": str(OPEN_CAP),
        "price_source": "data/raw/btc_intraday_20260924/klines_1m_20*.parquet + data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet (open at 4h boundaries)",
        "opens_rows": len(opens), "opens_range": [str(opens.index.min()), str(opens.index.max())],
        "anchors": ANCHORS, "year_window": "[anchor, anchor+365d)",
        "returns": {"r_dec": "open(t+4h)/open(t)-1", "r_hold": "open(t+8h)/open(t+4h)-1", "r_next": "open(t+12h)/open(t+8h)-1"},
        "convention": "book row t = decision at close of bar starting at t (holding bar t+4h..t+8h); engine_user.prepare cube row i = holding bar T = idx[i]+4h",
        "members": {k: {"rows": len(v), "range": [str(v.index.min()), str(v.index.max())]} for k, v in members.items()},
        "weights": "O1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2; D2 = 0.8*O1 + 0.2*(D+Dq)/2 (scripts/forward_v205.py research_books_d2)",
        "flags": "|corr(book,r_hold)|>0.10; or corr_hold>3*corr_next AND corr_hold>0.06; plus shifted (book[t+4h] vs r_hold[t]) jump check",
    }
    (HERE / "replication.json").write_text(json.dumps(rep, indent=1))
    print("replication.json saved")

    rows, summary = [], []
    for mem, books in members.items():
        for Y in ANCHORS:
            a0 = pd.Timestamp(Y, tz="UTC")
            a1 = a0 + pd.Timedelta(days=365)
            idx = books.index[(books.index >= a0) & (books.index < a1)]
            idx = idx[idx <= pd.Timestamp("2026-09-23T08:00:00Z")]  # need +12h opens within cap
            m_dec, m_hold, m_next, m_shift = [], [], [], []
            for s in SYMS:
                b = books[s].reindex(opens.index).reindex(idx)
                cd = spearman(b, r_dec[s].reindex(idx))
                ch = spearman(b, r_hold[s].reindex(idx))
                cn = spearman(b, r_next[s].reindex(idx))
                cs = spearman(b.shift(-1).reindex(idx), r_hold[s].reindex(idx))
                fl = leak_flags(ch, cn)
                rows.append({"member": mem, "year": Y[:4], "symbol": s, "n": int(b.dropna().__len__()),
                             "corr_dec": round(cd, 4) if cd == cd else "", "corr_hold": round(ch, 4) if ch == ch else "",
                             "corr_next": round(cn, 4) if cn == cn else "",
                             "corr_shifted": round(cs, 4) if cs == cs else "",
                             "flag_abs": int(fl["flag_abs"]), "flag_3x": int(fl["flag_3x"])})
                for v, acc in ((cd, m_dec), (ch, m_hold), (cn, m_next), (cs, m_shift)):
                    if v == v:
                        acc.append(v)
            import numpy as np
            mean = lambda a: round(float(np.mean(a)), 4) if a else ""
            summary.append({"member": mem, "year": Y[:4], "mean_corr_dec": mean(m_dec),
                            "mean_corr_hold": mean(m_hold), "mean_corr_next": mean(m_next),
                            "mean_corr_shifted": mean(m_shift),
                            "max_abs_hold": round(max(abs(r["corr_hold"]) for r in rows if r["member"] == mem and r["year"] == Y[:4] and r["corr_hold"] != ""), 4) if any(r["corr_hold"] != "" for r in rows if r["member"] == mem and r["year"] == Y[:4]) else "",
                            "n_flags": sum(r["flag_abs"] or r["flag_3x"] for r in rows if r["member"] == mem and r["year"] == Y[:4])})
    pd.DataFrame(rows).to_csv(HERE / "part1_correlations.csv", index=False)
    pd.DataFrame(summary).to_csv(HERE / "part1_summary.csv", index=False)
    nflag = sum(r["flag_abs"] or r["flag_3x"] for r in rows)
    print(f"part1 done: {len(rows)} cells, {nflag} leak flags")
    for r in rows:
        if r["flag_abs"] or r["flag_3x"]:
            print("FLAG", r)


if __name__ == "__main__":
    main()
