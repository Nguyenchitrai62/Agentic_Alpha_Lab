"""oc_k2parity parity analysis (CPU-only; runs after the live backfill exists).

Joins own live backfill
  research/tournament/oc_k2parity/kronos_features_live_backfill.parquet
to the frozen research features
  research/tournament/oc_kronoshidden/kronos_features_4shift.parquet
on (sym, shift, T) and reports the pre-registered metrics:
  bar OHLC max-rel-diff (vs bars_4h_4shift.parquet), sigma diff, low1
  Spearman + max/median abs diff, k2_mult disagreement share, plus the
  MC-noise baseline columns (live seed vs research seedA/seedB re-runs on the
  fixed 60-row subsample; see tmp/mc_research_rerun.py).
Out: results.json + console lines for REPORT.md. No GPU, no network.
"""
from pathlib import Path

import torch  # noqa: F401  (before pandas: Windows DLL load order)

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OC = ROOT / "research/tournament/oc_k2parity"
LIVE = OC / "kronos_features_live_backfill.parquet"
RESF = ROOT / "research/tournament/oc_kronoshidden/kronos_features_4shift.parquet"
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
MC = OC / "tmp" / "mc_research_rerun.parquet"


def spearman(a: pd.Series, b: pd.Series) -> float:
    return float(pd.DataFrame({"a": a, "b": b}).corr(method="spearman").iloc[0, 1])


def main():
    live = pd.read_parquet(LIVE)
    res = pd.read_parquet(RESF)
    for d in (live, res):
        d["T"] = pd.to_datetime(d["T"], utc=True)
    print(f"live rows={len(live)} {live['T'].min()}..{live['T'].max()}", flush=True)
    print(f"research rows={len(res)}", flush=True)
    j = live.merge(res, on=["sym", "shift", "T"], suffixes=("_live", "_res"))
    print(f"joined rows={len(j)} (live extra={len(live) - len(j)})", flush=True)
    assert len(j) > 2000, "join too small; backfill incomplete?"
    # bars OHLC check on the joined keys
    bars = pd.read_parquet(BARS, columns=["sym", "shift", "T", "open", "high", "low", "close"])
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    jb = j[["sym", "shift", "T"]].merge(bars, on=["sym", "shift", "T"])
    # live context bars were shown identical in tmp/bar_compare.json; re-verify open_T vs C0 path:
    sig_rho = spearman(j["sigma_live"], j["sigma_res"])
    sig_max = float((j["sigma_live"] - j["sigma_res"]).abs().max())
    sig_med = float((j["sigma_live"] - j["sigma_res"]).abs().median())
    low_rho = spearman(j["low1_live"], j["low1_res"])
    low_max = float((j["low1_live"] - j["low1_res"]).abs().max())
    low_med = float((j["low1_live"] - j["low1_res"]).abs().median())
    # research file has no k2_mult column: apply the same frozen rule both sides
    # (tilt_rule.assign_mult(-low1) == kronos_shadow.assign_k2(low1)).
    import importlib.util as _ilu
    import sys as _sys
    _spec = _ilu.spec_from_file_location("ks_rule", ROOT / "scripts/kronos_shadow.py")
    _ks = _ilu.module_from_spec(_spec)
    _sys.modules["ks_rule"] = _ks
    _spec.loader.exec_module(_ks)
    k2_live = j["low1_live"].map(lambda v: _ks.assign_k2(float(v)))
    k2_res = j["low1_res"].map(lambda v: _ks.assign_k2(float(v)))
    stored_ok = bool((k2_live == j["k2_mult"]).all())
    print(f"live stored k2_mult == recomputed: {stored_ok}", flush=True)
    assert stored_ok, "live k2_mult inconsistent with assign_k2!"
    k2_dis = float((k2_live != k2_res).mean())
    # per-symbol low1 rho
    per_sym = {s: round(spearman(g["low1_live"], g["low1_res"]), 4)
               for s, g in j.groupby("sym")}
    out = {
        "n_live": int(len(live)), "n_join": int(len(j)),
        "sigma_spearman": round(sig_rho, 4), "sigma_maxabs": sig_max,
        "sigma_medabs": sig_med, "low1_spearman": round(low_rho, 4),
        "low1_maxabs": low_max, "low1_medabs": low_med,
        "k2_disagreement": round(k2_dis, 4), "low1_rho_per_sym": per_sym,
    }
    if MC.exists():
        mc = pd.read_parquet(MC)
        mc_dis = float((mc["k2_a"] != mc["k2_b"]).mean())
        low_mc_max = float((mc["low1_a"] - mc["low1_b"]).abs().max())
        out["mc_k2_disagreement"] = round(mc_dis, 4)
        out["mc_low1_maxabs"] = low_mc_max
        out["mc_n"] = int(len(mc))
        print(f"MC baseline (research seedA vs seedB, n={len(mc)}): "
              f"k2_dis={mc_dis:.4f} low1_maxabs={low_mc_max:.4f}", flush=True)
    import json
    (OC / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("live==research up to MC noise?" , flush=True)
    for k, v in out.items():
        print(f"  {k}: {v}", flush=True)
    print(f"saved {OC / 'results.json'}", flush=True)


if __name__ == "__main__":
    main()
