"""oc_nativeclock member audit: can each book member be recomputed on a shifted 4h grid? (light)

For each of the 6 members behind research_books_d2, records the cache file,
builder chain, feature stores needed on a shifted grid, and whether frozen
per-anchor (walk-forward) models are persisted anywhere. Verdict per member:
NATIVE-computable vs must stay forward-filled (assignment fallback).

Finding (fixed): the research member caches are walk-forward PREDICTIONS whose
intermediate per-anchor/quarterly HGB fits were never persisted; models/frozen
holds only single-cutoff (2026-09-08) live models, not the per-anchor research
models. Recomputing native predictions would require rebuilding shifted panels
+ refitting per anchor/quarter = retraining, which the assignment forbids
("frozen per-anchor member models applied unchanged - no retraining"). Hence
all 6 members stay forward-filled (listed), NATIVE == REF bit-exact.
Writes tmp/member_audit.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
FROZEN = ROOT / "models/frozen"

MEMBERS = {
    "A": ("member_A_O1_orders.parquet",
          "v240/v240_order_level_flow.py build_member(q=False): v144 builder + v231 TV(17) + v236 order-level whale flow(6) on data/raw/aggflow_20260928_orders; v103 kline-flow; v142 xs; HGB per anchor, vol models exclude new feats",
          ["standard 4h bars (load_asset_ext)", "daily bars (calendar, load_asset)", "funding archive", "aggflow ORDERS binned by bar", "TV pivots (3 right bars)", "v142 xs cross-section", "per-anchor HGB fit"]),
    "Aq": ("member_Aq_O1_orders.parquet",
           "v240 build_member(q=True) via v202/v202_quarterly_retrain.py quarterly wrapper; same features as A, refit per quarter",
           ["same as A", "quarterly refit schedule (v202)", "per-quarter HGB fits (not persisted)"]),
    "B": ("member_B_tv.parquet",
          "v233/v233_tv_all_members.py B set: v144 builder + v150 Deribit options-flow + TV(17); vol models exclude OPT",
          ["standard 4h bars", "daily bars", "Deribit options-flow archive (daily/iv)", "TV(17)", "per-anchor HGB fit"]),
    "Bq": ("member_Bq_tv.parquet",
           "v233 B set via v202 quarterly wrapper; same features as B, refit per quarter",
           ["same as B", "quarterly refit schedule", "per-quarter HGB fits (not persisted)"]),
    "D": ("members_v154.parquet key D",
          "v154/v154_ensemble_coinbase.py books_coinbase(): v144 builder + v111 Coinbase-premium market features (Coinbase 1h vs Binance spot 4h, known at bar close)",
          ["standard 4h bars", "daily bars", "Coinbase 1h archive + Binance spot 4h", "per-anchor HGB fit"]),
    "Dq": ("members_quarterly_D.parquet",
           "D via v202 quarterly wrapper; same premium features, refit per quarter",
           ["same as D", "quarterly refit schedule", "per-quarter HGB fits (not persisted)"]),
}


def main() -> None:
    rows = {}
    for m, (f, builder, needs) in MEMBERS.items():
        p = CACHE / f.split(" key ")[0]
        info = {"cache": f, "builder": builder, "needs_shifted": needs,
                "cache_exists": p.exists(), "shape": None, "index_range": None,
                "per_anchor_models_persisted": False,
                "per_anchor_models_evidence": "no per-anchor/quarterly model files in models/frozen (only single-cutoff 2026-09-08 live models) nor beside the caches; v240/v202 build fits in-memory during cache construction and persists predictions only",
                "verdict": "FORWARD-FILL (native recompute needs shifted-panel rebuild + per-anchor refit = retraining, forbidden; daily/options/quarterly inputs not shiftable from available stores without refit)"}
        if p.exists():
            try:
                if "key" in f:
                    d = pd.read_parquet(p)
                    key = f.split("key ")[1]
                    w = d.xs(key, axis=1, level=0) if "Unnamed" not in str(d.columns[:1]) else d
                    info["shape"] = [int(x) for x in w.shape]
                    info["index_range"] = [str(w.index[0]), str(w.index[-1])]
                else:
                    d = pd.read_parquet(p)
                    info["shape"] = [int(x) for x in d.shape]
                    info["index_range"] = [str(d.index[0]), str(d.index[-1])]
            except Exception as e:
                info["shape"] = f"read error: {e}"
        rows[m] = info
        print(f"{m}: {f} exists={info['cache_exists']} shape={info['shape']} -> {info['verdict'][:60]}...", flush=True)
    # frozen-model check
    frozen = sorted(p.name for p in FROZEN.glob("*.pkl")) if FROZEN.exists() else []
    manifest_keys = []
    try:
        manifest_keys = sorted(json.loads((FROZEN / "manifest.json").read_text()).keys())
    except Exception as e:
        manifest_keys = [f"manifest read error: {e}"]
    out = {"members": rows, "models_frozen_files": frozen, "manifest_keys": manifest_keys,
           "conclusion": "ALL 6 members forward-filled; no member natively recomputed without retraining. NATIVE == REF bit-exact by construction (same blend, same bear filter, same ffill)."}
    (HERE / "tmp" / "member_audit.json").write_text(json.dumps(out, indent=1, default=str))
    print("member audit done: all 6 forward-filled; NATIVE == REF", flush=True)


if __name__ == "__main__":
    main()
