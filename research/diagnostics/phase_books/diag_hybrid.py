"""s = 0 source attribution: member A, anchor 2021 only, with one input family native and the other aggregated."""
import json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase_books as pb, verify_s0 as v

class KlinesNative(pb.Sources):   # native 4h klines + spot prefix, flow from the 1m store
    tag = "_hyb_klines_native"
    def perp_4h(self, sym): self.native = True; r = super().perp_4h(sym); self.native = False; return r
    def spot_prefix_4h(self, sym): self.native = True; r = super().spot_prefix_4h(sym); self.native = False; return r

class FlowNative(pb.Sources):     # 1h-aggregated klines, native 4h flow table
    tag = "_hyb_flow_native"
    def flow_table(self, sym): self.native = True; r = super().flow_table(sym); self.native = False; return r

class AllAgg(pb.Sources):
    tag = "_hyb_all_agg"

res = {}
lo, hi = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2022-09-24", tz="UTC")
for cls in (KlinesNative, FlowNative, AllAgg):
    bk, _ = pb.build_member("A", "annual", cls(0), print, anchors=["2021-09-24"])
    r = v.diff(bk, v.cached("A"), lo, hi)
    res[cls.tag] = {"max_abs": r["max_abs"], "rows_gt_1e-12": r["rows_gt_1e-12"], "corr": r["yearly"]["2021"]["corr"], "mean_abs": r["mean_abs"]}
    print(cls.tag, res[cls.tag], flush=True)
(pb.OUT / "diag_hybrid_s0.json").write_text(json.dumps(res, indent=1))
