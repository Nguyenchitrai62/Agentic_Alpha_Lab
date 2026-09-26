"""Write a pending-audit result manifest from a version's result JSON (leader helper).

  python .../tools/write_manifest.py v100 A|B|C primary_key [secondary_key]
"""
import hashlib, json, subprocess, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
v, track, key = sys.argv[1], sys.argv[2], sys.argv[3]
sec = sys.argv[4] if len(sys.argv) > 4 else None
raw = (R / v / f"{v}_result.json").read_bytes()
res = json.loads(raw)
prim = res[key] if key != "." else res
scen = {}
for sc in ("normal", "fee_stress", "execution_stress"):
    r = prim[sc]
    scen[sc] = dict(monthly_geometric_net_percent=r["monthly_pct"], max_drawdown_percent=r["worst_year_dd"],
                    fills=sum(y["fills"] for y in r["yearly"]), months=60)
ok = all(s["monthly_geometric_net_percent"] >= 5 and s["max_drawdown_percent"] <= 20 for s in scen.values())
m = {"schema_version": 1, "experiment_id": v, "track": track, "status": "candidate" if ok else "rejected",
     "parent_commit": "1ecf947baddd5ef78444670330e9db62128dad50",
     "hashes": {"result_sha256": hashlib.sha256(raw).hexdigest()}, "scenarios": scen,
     "result": {"primary_key": key, "yearly_normal": [[y["anchor"], y["net_pct"], y["max_drawdown_percent"]] for y in prim["normal"]["yearly"]]},
     "independent_test": False, "live_approved": False, "cloud": {"submission_count": 0, "upload_attempted": False},
     "audit": {"passed": False, "replay_complete": False, "notes": "awaiting OpenCode blind audit"}}
if "ic" in prim:
    m["result"]["ic_by_anchor"] = [x.get("ic", x) if isinstance(x, dict) else x for x in prim["ic"].values()]
if sec:
    m["result"][f"secondary_{sec}_monthly"] = res[sec]["normal"]["monthly_pct"]
    m["result"][f"secondary_{sec}_worst_dd"] = res[sec]["normal"]["worst_year_dd"]
(R / v / "result_manifest.json").write_text(json.dumps(m, indent=1))
print(v, m["status"], {k: (s["monthly_geometric_net_percent"], s["max_drawdown_percent"]) for k, s in scen.items()})
