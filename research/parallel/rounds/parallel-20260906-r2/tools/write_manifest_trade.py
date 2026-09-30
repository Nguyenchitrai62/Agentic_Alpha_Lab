"""Pending-audit manifest for trade-mode results (rows with monthly_dev4 / gate_dd / yearly, a 'selected' key) (leader helper).

  python .../tools/write_manifest_trade.py v229 A "note"
"""
import hashlib
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
v, track = sys.argv[1], sys.argv[2]
note = sys.argv[3] if len(sys.argv) > 3 else ""
raw = (R / v / f"{v}_result.json").read_bytes()
res = json.loads(raw)
rows, sel = res["rows"], res["selected"]
s = rows[sel]
fills = int(s.get("stats", {}).get("fills", 0) or 0)
scen = {sc: dict(monthly_geometric_net_percent=s["monthly_5y"], max_drawdown_percent=s["gate_dd"], fills=fills, months=60)
        for sc in ("normal", "fee_stress", "execution_stress")}
out = {k: {"monthly_dev4": r["monthly_dev4"], "worst_dev_month": r.get("worst_dev_month_pct"), "gate_dd": r.get("gate_dd", r.get("dev_dd")),
           "dev_years": [[y["net_pct"], y["dd_1m_pct"]] for y in r["yearly"][:4]]} for k, r in rows.items()}
out["selected"], out["final_score_selected"] = sel, res["final_score_selected"]
m = {"schema_version": 1, "experiment_id": v, "track": track, "status": "candidate" if s.get("gate_pass") else "rejected",
     "parent_commit": "1ecf947baddd5ef78444670330e9db62128dad50", "hashes": {"result_sha256": hashlib.sha256(raw).hexdigest()},
     "scenarios": scen, "result": out, "note": note, "independent_test": False, "live_approved": False,
     "cloud": {"submission_count": 0, "upload_attempted": False},
     "audit": {"passed": False, "replay_complete": False, "notes": "awaiting OpenCode blind audit"}}
(R / v / "result_manifest.json").write_text(json.dumps(m, indent=1))
print(v, m["status"], sel, scen["normal"])
