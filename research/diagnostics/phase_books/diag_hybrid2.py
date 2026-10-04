"""s = 0 attribution 2: 1h-aggregated klines with (a) only the listing-edge rows set to the native rows, (b) also the ~5 glitch bars per symbol."""
import json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase_books as pb, verify_s0 as v

def native_perp(sym):
    return pb.Sources(0, native=True).perp_4h(sym)

class EdgesFixed(pb.Sources):
    tag = "_hyb_edges_fixed"
    fix_glitch = False
    def perp_4h(self, sym):
        a, n = super().perp_4h(sym), native_perp(sym)
        a = a[a.open_time.isin(n.open_time)]
        a = pd.concat([n[~n.open_time.isin(a.open_time)], a]).sort_values("open_time").reset_index(drop=True)
        if self.fix_glitch:
            return n.copy()
        return a[n.columns]
    def spot_prefix_4h(self, sym):
        self.native = True; r = super().spot_prefix_4h(sym); self.native = False; return r

class GlitchFixed(EdgesFixed):
    tag = "_hyb_glitch_fixed"
    fix_glitch = True

res = {}
lo, hi = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2022-09-24", tz="UTC")
for cls in (EdgesFixed,):
    bk, _ = pb.build_member("A", "annual", cls(0), print, anchors=["2021-09-24"])
    r = v.diff(bk, v.cached("A"), lo, hi)
    res[cls.tag] = {"max_abs": r["max_abs"], "rows_gt_1e-12": r["rows_gt_1e-12"], "corr": r["yearly"]["2021"]["corr"], "mean_abs": r["mean_abs"]}
    print(cls.tag, res[cls.tag], flush=True)
(pb.OUT / "diag_hybrid2_s0.json").write_text(json.dumps(res, indent=1))
