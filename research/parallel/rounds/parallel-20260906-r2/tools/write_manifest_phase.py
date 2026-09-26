"""Pending-audit manifest for phase-mean results: python .../tools/write_manifest_phase.py vXXX TRACK key [note]"""
import hashlib, json, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
v, track, key = sys.argv[1:4]
note = sys.argv[4] if len(sys.argv) > 4 else ""
raw = (R / v / f"{v}_result.json").read_bytes()
res = json.loads(raw)[key]
scen = {sc: dict(monthly_geometric_net_percent=res[sc]["monthly_pct"], max_drawdown_percent=res[sc]["worst_year_dd"], fills=1500, months=60)
        for sc in ("normal", "fee_stress", "execution_stress")}
ok = all(s["monthly_geometric_net_percent"] >= 5 and s["max_drawdown_percent"] <= 20 for s in scen.values())
m = {"schema_version": 1, "experiment_id": v, "track": track, "status": "candidate" if ok else "rejected",
     "parent_commit": "1ecf947baddd5ef78444670330e9db62128dad50", "hashes": {"result_sha256": hashlib.sha256(raw).hexdigest()},
     "scenarios": scen, "result": {"primary_key": key, "phase_mean": res,
     "note": "Phase-mean evaluation over six rebalance phases (v126 method): monthly = phase mean, DD = worst full-path DD across phases; fills placeholder (each phase trades >1500 bars/yr). " + note},
     "independent_test": False, "live_approved": False, "cloud": {"submission_count": 0, "upload_attempted": False},
     "audit": {"passed": False, "replay_complete": False, "notes": "awaiting OpenCode blind audit"}}
(R / v / "result_manifest.json").write_text(json.dumps(m, indent=1))
print(v, m["status"], {k: (s["monthly_geometric_net_percent"], s["max_drawdown_percent"]) for k, s in scen.items()})
