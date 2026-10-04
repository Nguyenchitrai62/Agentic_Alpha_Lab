"""Summary of the phase-book build: leakage records per (phase, member, anchor), timings, output coverage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase_books as pb  # noqa: E402


def main():
    out = {}
    for sfx in ("0_native", "0", "1", "2", "3"):
        lp = pb.OUT / f"leakage_s{sfx}.json"
        if not lp.exists():
            continue
        leak = json.loads(lp.read_text())
        rows = []
        for member, d in leak.items():
            for key, fits in d.items():
                kind, anchor = key.split("|")
                for f in fits:
                    le, cut = pd.Timestamp(f["label_end"]), pd.Timestamp(f["cutoff"])
                    rows.append({"member": member, "kind": kind, "anchor": anchor, "target": f["target"], "n": f["n"],
                                 "max_label_end": le, "anchor_minus_embargo": cut, "margin_h": (cut - le) / pd.Timedelta(hours=1), "ok": f["ok"]})
        df = pd.DataFrame(rows)
        per = df.groupby(["member", "anchor"]).agg(fits=("ok", "size"), all_ok=("ok", "all"), max_label_end=("max_label_end", "max"),
                                                   min_margin_h=("margin_h", "min")).reset_index()
        out[f"s{sfx}"] = {"fits": int(len(df)), "all_ok": bool(df["ok"].all()), "min_margin_h": float(df["margin_h"].min()),
                          "per_member_anchor": json.loads(per.to_json(orient="records", date_format="iso"))}
        per.to_csv(pb.OUT / f"leakage_summary_s{sfx}.csv", index=False)
        print(f"s{sfx}: fits {len(df)} all label ends < anchor - embargo: {bool(df['ok'].all())}, min margin {df['margin_h'].min():.0f} h", flush=True)
        tp = pb.OUT / f"timing_s{sfx}.json"
        if tp.exists():
            out[f"s{sfx}"]["timing_s"] = json.loads(tp.read_text())
        bp = pb.OUT / f"books_s{sfx.replace('_native', '')}{'_native' if 'native' in sfx else ''}.parquet"
        if bp.exists():
            b = pd.read_parquet(bp)
            out[f"s{sfx}"]["books"] = {"rows": len(b), "first": str(b.index.min()), "last": str(b.index.max()),
                                       "hours": sorted({int(h) for h in b.index.hour})}
    (pb.OUT / "summary.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
