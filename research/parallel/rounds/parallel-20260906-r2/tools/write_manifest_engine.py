"""Pending-audit manifest for results in the v144-engine row format (leader helper).

The engine is a single realistic execution model (no fee scenarios), so all three scenario slots carry the primary row.

  python .../tools/write_manifest_engine.py v165 A primary_ensemble [primary_t25_governed] ["note"]
"""
import hashlib
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
v, track, block = sys.argv[1], sys.argv[2], sys.argv[3]
row = sys.argv[4] if len(sys.argv) > 4 else "primary_t25_governed"
note = sys.argv[5] if len(sys.argv) > 5 else ""
raw = (R / v / f"{v}_result.json").read_bytes()
res = json.loads(raw)
rows = res[block] if block != "." else res
p = rows[row]
fills = sum(y.get("fills", 0) for y in p["yearly"])
sc = dict(monthly_geometric_net_percent=p["monthly_pct"], max_drawdown_percent=p["full_path_dd"], fills=fills, months=60)
ok = p["monthly_pct"] >= 5 and p["full_path_dd"] <= 20
m = {"schema_version": 1, "experiment_id": v, "track": track, "status": "candidate" if ok else "rejected",
     "parent_commit": "1ecf947baddd5ef78444670330e9db62128dad50",
     "hashes": {"result_sha256": hashlib.sha256(raw).hexdigest()},
     "scenarios": {k: dict(sc) for k in ("normal", "fee_stress", "execution_stress")},
     "result": {k: {"monthly": r["monthly_pct"], "full_path_dd": r["full_path_dd"], "yearly": [y["net_pct"] for y in r["yearly"]]}
                for k, r in rows.items() if isinstance(r, dict) and "yearly" in r},
     "note": note, "independent_test": False, "live_approved": False,
     "cloud": {"submission_count": 0, "upload_attempted": False},
     "audit": {"passed": False, "replay_complete": False, "notes": "awaiting OpenCode blind audit"}}
cs = R / v / "cloud_submission.json"
if cs.exists():
    m["cloud"] = {"submission_count": 1, "upload_attempted": True, "record": json.loads(cs.read_text())}
(R / v / "result_manifest.json").write_text(json.dumps(m, indent=1))
print(v, m["status"], p["monthly_pct"], p["full_path_dd"])
