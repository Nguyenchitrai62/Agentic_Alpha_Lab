"""oc_nativeclock book construction: REF (forward-filled) + NATIVE frames (light, no 1m).

REF per shift s = v421 worker replica: standard research_books_d2 blend after
the v421 x0.5 bear filter, ffill'd onto the shifted decision index
(books154.index + s hours). NATIVE per shift: phase 0 = REF phase 0; phases
1..3 = native-blended frames where computable, else the forward-filled member
(see audit_members.py: ALL 6 members forward-filled -> NATIVE == REF bit-exact).

Also reports, per shift: staleness share (decision bars whose ffill'd book row
is 1..3 bars old), and book turnover proxy per dev year + recent year
(mean |dW| per decision bar, summed over coins). Writes
tmp/native_books_check.json. Causality: ffill uses only standard rows r <= t_s
(never future); at s=0 identity.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    eu = _load("eu_nb", RD / "engine_user/engine_user.py")
    fw = _load("fw_nb", ROOT / "scripts/forward_v205.py")
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    std = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    audit = json.loads((HERE / "tmp" / "member_audit.json").read_text())
    assert all(v["verdict"].startswith("FORWARD-FILL") for v in audit["members"].values()), audit
    out_shifts = {}
    for s in range(4):
        sh = pd.Timedelta(hours=s)
        idx = books154.index + sh
        ref = sb.reindex(idx, method="ffill").fillna(0.0)
        # NATIVE: all members forward-filled -> identical construction
        native = sb.reindex(idx, method="ffill").fillna(0.0)
        assert native.shape == ref.shape and (native.index == ref.index).all()
        maxdiff = float(np.max(np.abs(native.to_numpy() - ref.to_numpy())))
        assert maxdiff == 0.0, maxdiff
        # staleness: age (in standard bars) of the ffill'd row at each decision bar
        pos = sb.index.searchsorted(idx, side="right") - 1
        age_bars = np.arange(len(idx)) - pos * 0 + 0  # placeholder, replaced below
        # exact: for decision idx[i], source row = sb.index[pos[i]]; age in hours:
        src = sb.index[pos.clip(0, len(sb) - 1)]
        age_h = ((idx - src).total_seconds() / 3600).to_numpy()
        stale_share = round(float(np.mean(age_h > 0.5)), 4)
        # turnover proxy per year: mean |dW| per bar summed over coins
        dW = native.diff().abs().sum(axis=1)
        yrs = []
        for y, a0 in enumerate(ANCH):
            a0s = a0 + sh
            seg = (native.index >= a0s) & (native.index < a0s + YEAR)
            yrs.append({"year": str(a0.date()), "bars": int(seg.sum()),
                        "turnover_per_bar": round(float(dW[seg].mean()), 6),
                        "turnover_total": round(float(dW[seg].sum()), 4)})
        out_shifts[s] = {"bars": len(idx), "max_abs_diff_native_vs_ref": maxdiff,
                         "stale_share": stale_share, "mean_age_h": round(float(age_h.mean()), 3),
                         "phase0_unchanged": True, "years": yrs}
        print(f"shift {s}: NATIVE==REF maxdiff={maxdiff} stale={stale_share} mean_age_h={age_h.mean():.2f}", flush=True)
    out = {"note": "ALL members forward-filled per member_audit.json; NATIVE frames bit-identical to REF ffill frames; phase 0 unchanged by construction.",
           "shifts": out_shifts}
    (HERE / "tmp" / "native_books_check.json").write_text(json.dumps(out, indent=1, default=str))
    print("native books check done: NATIVE == REF bit-exact on all 4 shifts", flush=True)


if __name__ == "__main__":
    main()
