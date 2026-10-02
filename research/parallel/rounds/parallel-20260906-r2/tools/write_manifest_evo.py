"""Pending-audit manifest for the walk-forward evolution versions (v306+): python .../tools/write_manifest_evo.py vXXX TRACK [note]
Scenario rows = the FINAL genome's dev4 metrics (selection data) - the gate status uses the transfer rule and the user goals, never the dev4 alone."""
import hashlib, json, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
v, track = sys.argv[1:3]
note = sys.argv[3] if len(sys.argv) > 3 else ""
raw = (R / v / f"{v}_result.json").read_bytes()
res = json.loads(raw)
fin = res["final"]
best = fin.get("M") or fin.get("E") or {}
dev4 = best.get("dev4", fin.get("dev4", {}))
row = dict(monthly_geometric_net_percent=float(dev4.get("R", 0)), max_drawdown_percent=float(dev4.get("DD", 99)), fills=int(dev4.get("trades", 0)), months=48)
scen = {sc: dict(row) for sc in ("normal", "fee_stress", "execution_stress")}
ok = bool(fin.get("recommended") or fin.get("replaces_G2"))
m = {"schema_version": 1, "experiment_id": v, "track": track, "status": "candidate" if ok else "rejected",
     "parent_commit": "1ecf947baddd5ef78444670330e9db62128dad50", "hashes": {"result_sha256": hashlib.sha256(raw).hexdigest()},
     "scenarios": scen, "result": {"transfer": res.get("transfer"), "final": {k: fin[k] for k in fin if k not in ("dev_years",)},
                                   "folds": {k: {kk: vv for kk, vv in f.items() if kk != "runs"} for k, f in res.get("folds", {}).items()},
                                   "note": "walk-forward evolution; scenario rows = final genome dev4 (selection data), gate = transfer rule + once-only most recent year. " + note},
     "independent_test": False, "live_approved": False, "cloud": {"submission_count": 1, "upload_attempted": True},
     "audit": {"passed": False, "replay_complete": False, "notes": "awaiting OpenCode blind audit"}}
(R / v / "result_manifest.json").write_text(json.dumps(m, indent=1, default=str))
print(v, m["status"], row)
