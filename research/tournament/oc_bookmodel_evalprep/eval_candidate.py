"""oc_bookmodel_evalprep: evaluate a book-model candidate on the deployment harness.

Design: docs/opencode/BOOKMODEL_PLAN_20261006.md (evaluation: 4-phase reset-metric
harness with the deployed sleeve fixed, selection only on 2021-2024, 2025-09-24
scored once for the finalist), scripts/forward_v205.py (research_books_d2),
research/parallel/rounds/parallel-20260906-r2/v421/v421_gross_cap.py (deployment
wiring R2B1D17BFG2 = G2).

Given a Kaggle output folder of member parquets in deployed member format
(index ``t`` tz-aware 4h, columns BNBUSDT,BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT),
builds the candidate book = 0.8 x new O1 blend + 0.2 x D (D byte-identical to
deployed) exactly like research_books_d2, then runs the deployment harness
(v421 wiring, G2, bear filter applied to the candidate book) for the 4 phases
and prints the per-year reset metric for dev years 2021-2024 only. The 2025
year is computed but written to a SEPARATE sealed file final_year.json that
the script refuses to print unless --final is passed.

Kaggle folder layout: any set of *.parquet files in deployed member format.
Files are bucketed into A / B / Aq / Bq by filename (case-insensitive):
``aq`` -> Aq, ``bq`` -> Bq, else ``_a_`` / member_a -> A, ``_b_`` / member_b
-> B. This accepts both the deployed O1 names (member_A_O1_orders.parquet,
member_Aq_O1_orders.parquet, member_B_tv.parquet, member_Bq_tv.parquet) and
the C1/C2 per-year names (member_C1_A_2021.parquet, ...). Each bucket's files
are concatenated (dedup index, sort); per-year splits and full-history files
both work. D files in the folder are IGNORED: D is always the deployed
members_v154 key D + members_quarterly_D (byte-identical by construction).

Harness (verbatim v421 R2B1D17BFG2 wiring): 4 clock-shifted phases (0/1/2/3h),
books on the shifted grid by forward-fill, bear filter (BTC 4h open < mean of
last 1200 opens halves positive book weights) applied to the CANDIDATE book,
v321 pipe_setup with the v376 hidden R2 tables, B1 inv rule (kd 1.7), risk
budget 0.26*k*kd, sleeve_gross_cap G=2.0, trade=G2 grid policy, win_start=5,
gate costs. Per-year reset metric via
research/diagnostics/r2_decompose5/reset_metric.py year_reset (same function
v421 uses).

Usage:
  .venv/Scripts/python.exe research/tournament/oc_bookmodel_evalprep/eval_candidate.py --members <kaggle_out_dir> [--out <dir>] [--final]
  # reproduction check with the current deployed O1 members:
  #   copy artifacts/research/engine_real/{member_A_O1_orders,member_Aq_O1_orders,member_B_tv,member_Bq_tv}.parquet
  #   into an empty folder, then run the command above. Dev years must equal
  #   v421 R2B1D17BFG2 dev years exactly: 2021 (2.588, 10.86), 2022 (3.282, 16.91),
  #   2023 (6.045, 15.81), 2024 (10.677, 8.27); sealed 2025 = (4.648, 12.9).

No training, no Kaggle upload, no commits. No statistic from 2025-09-24+
feeds any choice here (2025 is sealed; selection uses dev years only).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
# v421 deployment pick R2B1D17BFG2 (registry v421): B1 inv, k=1.0, kd=1.7, bear, G=2.0
G2_CFG = dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0)
ROW = "CAND"
DEV_ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")
FINAL_ANCHOR = "2025-09-24"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _is_deployed_d_file(stem_lower: str) -> bool:
    s = stem_lower
    if "members_v154" in s or "members_quarterly_d" in s:
        return True
    if s.startswith("member_d") or s.startswith("member_sat") or "_dc" in s:
        return True
    if "_d_" in s or s.endswith("_d") or "_dq" in s:
        # member_D_tv / member_Dq_tv style names; Aq/Bq already handled before this check
        # by the caller (aq/bq take priority), so reaching here means a D file.
        return True
    return False


def bucket_member_files(members_dir: Path) -> dict:
    files = sorted(members_dir.glob("*.parquet"))
    buckets: dict = {"A": [], "B": [], "Aq": [], "Bq": []}
    for f in files:
        s = f.stem.lower()
        if "aq" in s:
            buckets["Aq"].append(f)
            continue
        if "bq" in s:
            buckets["Bq"].append(f)
            continue
        if _is_deployed_d_file(s):
            continue  # D stays byte-identical deployed; never from the candidate folder
        if "_a_" in s or s.endswith("_a") or s.startswith("member_a") or s.startswith("a_"):
            buckets["A"].append(f)
        elif "_b_" in s or s.endswith("_b") or s.startswith("member_b") or s.startswith("b_"):
            buckets["B"].append(f)
        # unknown files (e.g. other satellites) are ignored
    return buckets


def _load_bucket(paths: list) -> pd.DataFrame:
    frames = []
    for p in paths:
        w = pd.read_parquet(p)
        if isinstance(w.columns, pd.MultiIndex):
            # deployed members_v154 style (A/B/D level): caller should have split already;
            # refuse ambiguous multiindex frames here.
            raise ValueError(f"{p.name}: unexpected MultiIndex columns; expected deployed member format")
        missing = [c for c in SYMS if c not in w.columns]
        if missing:
            raise ValueError(f"{p.name}: missing columns {missing}; expected {SYMS}")
        w = w[SYMS]
        w.index = pd.to_datetime(w.index, utc=True)
        w.index.name = "t"
        frames.append(w.astype(float))
    full = pd.concat(frames, axis=0) if len(frames) > 1 else frames[0].copy()
    full = full[~full.index.duplicated(keep="last")].sort_index()
    return full


def load_candidate_o1(members_dir: Path) -> dict:
    """Load candidate A/B/Aq/Bq frames from the Kaggle folder."""
    buckets = bucket_member_files(members_dir)
    for k in ("A", "B", "Aq", "Bq"):
        if not buckets[k]:
            raise FileNotFoundError(
                f"no *{k}* member parquet in {members_dir} "
                f"(found: {sum(len(v) for v in buckets.values())} bucketed files). "
                "Expected A/B/Aq/Bq files in deployed member format."
            )
    return {k: _load_bucket(v) for k, v in buckets.items()}


def candidate_books_d2(members_dir: Path) -> pd.DataFrame:
    """Candidate book = 0.8 x new O1 + 0.2 x D, exactly like forward_v205.research_books_d2.

    O1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2 with idx = A.index.union(Aq.index);
    D2 = 0.8*O1 + 0.2*(D+Dq)/2 with D/Dq from the deployed cache (byte-identical).
    """
    m = load_candidate_o1(members_dir)
    A, B, Aq, Bq = m["A"], m["B"], m["Aq"], m["Bq"]
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731 -- same form as forward_v205
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    return 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2


def run_phase(shift: int, cand_std: pd.DataFrame, books154: pd.DataFrame,
              opens_std: pd.DataFrame) -> dict:
    """One v421 phase with the candidate book (verbatim R2B1D17BFG2 wiring)."""
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof

    pod = _load(f"pod_evalprep_{shift}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = _load(f"hist_evalprep_{shift}", ROOT / "backend/history_tm.py")
    v221 = _load(f"v221_evalprep_{shift}", pof.RD / "v221/v221_grid_hysteresis.py")
    eu, v216 = v221.eu, v221.v216
    v388 = _load(f"v388_evalprep_{shift}", pof.RD / "v388/v388_bot_stop_distance.py")
    Y1 = v388.Y1
    cap: dict = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy()) or {}
    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = cand_std.reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)
    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    cfg = G2_CFG
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    O, C, sg = prep["O"], prep["C"], prep["sig4"]
    base_size, rule = kw["sleeve_fill_size"], cfg["rule"]
    kd = cfg.get("kd", 1.0)
    ev, stops, ptr = [], {}, [0]
    cool = cfg.get("cool", False)
    COOL = pd.Timedelta(hours=24)

    def cooled(i, a):
        while ptr[0] < len(ev):
            e = ev[ptr[0]]
            ptr[0] += 1
            if e["kind"] == "rung_sl":
                stops.setdefault(e["symbol"], []).append(e["t"])
        B = idx[i] + pd.Timedelta(hours=4)
        return any(s_ < B <= s_ + COOL for s_ in stops.get(cols[a], [])[-20:])

    def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd, cool=cool):
        if cool and cooled(i, a):
            return 0.0
        m_ = f - 1
        n = 0
        for b in range(len(cols)):
            if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m_, b]) and np.isfinite(sg[i][b])):
                continue
            n += float(C[i, m_, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
        mult = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
        return mult * kd * base_size(i, a, r, f)

    kw["sleeve_fill_size"] = corr_size
    k = cfg["k"]
    kw["risk_mult"] = lambda i, e, k=k: k
    kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * k * kd
    if "G" in cfg:
        kw["sleeve_gross_cap"] = cfg["G"]
    eu.simulate(books_bear if cfg.get("bear") else books, opens, prep,
                trade=trade, win_start=5, events=ev, **kw)
    lv = np.asarray((cap["idx"] >= live0) & (cap["idx"] < live1))
    first = int(np.argmax(lv))
    base = cap["eq"][first - 1] if first > 0 else 1.0
    return dict(t=[str(x) for x in cap["idx"][lv] + pd.Timedelta(hours=8)],
                eq=(cap["eq"][lv] / base).tolist(),
                eq_min=(cap["eq_min"][lv] / base).tolist())


def evaluate(members_dir: Path) -> tuple:
    """Run all 4 phases; return (runs, per_year[5], dev_summary)."""
    cand = candidate_books_d2(members_dir)
    eru = _load("er_evalprep", RD / "engine_real/engine_real.py")
    books154, opens_std = eru.v154_books()
    cols = list(books154.columns)
    cand_std = cand.reindex(cand.index.union(books154.index)).fillna(0.0)
    cand_std = cand_std.reindex(books154.index).fillna(0.0)[cols]
    runs: dict = {}
    for shift in range(4):
        out = run_phase(shift, cand_std, books154, opens_std)
        runs[shift] = {ROW: out}
        print(f"phase {shift} done eq_end={round(out['eq'][-1], 3)}", flush=True)
    rm = _load("reset_evalprep", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    per_year = [rm.year_reset(runs, ROW, y) for y in range(5)]
    dev = per_year[:4]
    geo = float(np.prod([1 + y["R"] / 100 for y in dev]) ** (1 / len(dev)) - 1)
    summary = dict(R=round(100 * geo, 3), W=min(y["R"] for y in dev),
                   DD=max(y["DD"] for y in dev),
                   losing=sum(y["R"] < 0 for y in dev))
    return runs, per_year, summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--members", required=True, help="Kaggle output folder of member parquets (deployed member format)")
    ap.add_argument("--out", default=None, help="output dir for final_year.json (default <repo>/research/tournament/oc_bookmodel_evalprep/output)")
    ap.add_argument("--sealed", default=None, help="sealed file path (default <out>/final_year.json)")
    ap.add_argument("--final", action="store_true", help="also print the sealed 2025 year (default: refuse)")
    a = ap.parse_args()
    members = Path(a.members)
    out_dir = Path(a.out) if a.out else (HERE / "output")
    out_dir.mkdir(parents=True, exist_ok=True)
    sealed = Path(a.sealed) if a.sealed else (out_dir / "final_year.json")
    _, per_year, summary = evaluate(members)
    dev_rows = [dict(anchor=an, R=y["R"], DD=y["DD"]) for an, y in zip(DEV_ANCHORS, per_year[:4])]
    print(json.dumps(dict(row="R2B1D17BFG2 wiring (G2) with candidate book",
                          candidate_members=str(members),
                          dev_years=dev_rows, dev_summary=summary), indent=1))
    sealed_payload = dict(row="R2B1D17BFG2 wiring (G2) with candidate book",
                          candidate_members=str(members),
                          final_year=dict(anchor=FINAL_ANCHOR, R=per_year[4]["R"], DD=per_year[4]["DD"]),
                          note="sealed: 2025-09-24 scored once for the frozen finalist; never used for selection")
    sealed.write_text(json.dumps(sealed_payload, indent=1))
    print(f"sealed 2025 year written to {sealed} (use --final to display it)", flush=True)
    if a.final:
        print(json.dumps(dict(final_year=sealed_payload["final_year"]), indent=1))
    # without --final the 2025 R/DD never appears on stdout (only in the sealed file)


if __name__ == "__main__":
    main()
