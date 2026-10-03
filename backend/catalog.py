"""Product ranking/access, separate from research model selection and training."""

import json
import math

from fastapi import HTTPException

from . import db
from .config import SETTINGS

# Recorded dashboard metrics: product ranking only, explicitly requested by the user.
PIPELINES = {
    "v301": {"candidate": "v301_G2", "monthly_last_year": 5.349, "gate_dd": 17.09, "win_hidden": 0.558},
    "v295": {"candidate": "v295_CS", "monthly_last_year": 5.266, "gate_dd": 17.2, "win_hidden": 0.558},
    "v266": {"candidate": "v266_B1", "monthly_last_year": 4.464, "gate_dd": 19.7, "win_hidden": 0.541},
    "v269": {"candidate": "v269_M1", "monthly_last_year": 4.645, "gate_dd": 18.27, "win_hidden": 0.546},
    "v285": {"candidate": "v285_D2", "monthly_last_year": 5.167, "gate_dd": 18.39, "win_hidden": 0.558},
    "v321": {"candidate": "v321_R2", "monthly_last_year": 5.655, "gate_dd": 18.39, "win_hidden": 0.560},
    "v315": {"candidate": "v315_M1", "monthly_last_year": 3.289, "gate_dd": 18.47, "win_hidden": 0.550},
    "v342": {"candidate": "v342_M3", "monthly_last_year": 4.704, "gate_dd": 17.73, "win_hidden": 0.556},
    "v362": {"candidate": "v362_M4", "monthly_last_year": 5.04, "gate_dd": 16.96, "win_hidden": 0.556},
}


def metric_order() -> list[str]:
    def score(pipe):
        summary = db.kv_get(f"summary_tm_{pipe}", {}) or {}
        values = []
        for key in ("monthly_last_year", "gate_dd", "win_hidden"):
            value = summary.get(key)
            if (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
                    or key == "gate_dd" and not 0 <= value <= 100
                    or key == "win_hidden" and not 0 <= value <= 1):
                value = PIPELINES[pipe][key]
            values.append(value)
        monthly, dd, win = values
        return -monthly, dd, -win, pipe
    return sorted(PIPELINES, key=score)


NEW_LOCKED = {"v321", "v315", "v342", "v362"}  # paper pipelines added 2026-10-03: admin-only until the admin unlocks them
POLICY_KEY = "pipeline_access_policy"
SUMMARY_FIELDS = ("monthly_5y", "monthly_dev4", "monthly_last_year", "dd_4h", "dd_1m", "gate_dd",
                  "losing_years", "yearly", "win_dev", "win_hidden", "trades_dev", "trades_hidden")


def policy() -> dict:
    saved = db.kv_get(POLICY_KEY, {}) or {}
    automatic = saved.get("order") is None
    ranking = metric_order()
    if automatic:
        order = ranking
    else:  # a saved order from an older catalogue: drop retired pipelines, append new ones in metric order
        order = [p for p in saved["order"] if p in PIPELINES] + [p for p in ranking if p not in saved["order"]]
    # pipelines added after the access rules were set start LOCKED (admin-only); the top-two-locked default applies to the others
    older = [p for p in order if p not in NEW_LOCKED]
    default_locks = {p: p in NEW_LOCKED or older.index(p) < 2 for p in order}
    saved_locks = saved.get("locked")
    # a pipeline added after the locks were saved starts LOCKED (admin-only) until the admin decides
    locks = default_locks if saved_locks is None else {p: bool(saved_locks.get(p, True)) for p in order}
    return {"order": order, "locked": locks, "automatic": automatic, "revision": saved.get("revision", 0)}


def save_policy(payload: dict, email: str) -> dict:
    order, locks, revision = payload.get("order"), payload.get("locked"), payload.get("revision")
    if "order" not in payload or order is not None and (
            not isinstance(order, list) or len(order) != len(PIPELINES)
            or any(not isinstance(p, str) for p in order) or set(order) != set(PIPELINES)):
        raise HTTPException(400, "order must contain every pipeline exactly once, or null for automatic ranking.")
    if not isinstance(locks, dict) or set(locks) != set(PIPELINES) or any(type(v) is not bool for v in locks.values()):
        raise HTTPException(400, "locked must specify a boolean for every pipeline.")
    if type(revision) is not int or revision < 0:
        raise HTTPException(400, "revision must be a non-negative integer.")
    # Compare and save in one transaction: a second admin tab cannot silently overwrite newer changes.
    with db.write() as c:
        row = c.execute("SELECT v FROM kv WHERE k=?", (POLICY_KEY,)).fetchone()
        saved = json.loads(row["v"]) if row else {}
        if saved.get("revision", 0) != revision:
            raise HTTPException(409, "Pipeline settings changed. Reload the settings before saving.")
        value = {"order": order, "locked": locks, "revision": revision + 1,
                 "updated_by": email, "updated_at": db.now_ms()}
        c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                  (POLICY_KEY, json.dumps(value)))
    return policy()


def ranked() -> list[str]:
    return policy()["order"]


def allowed(user: dict) -> list[str]:
    settings = policy()
    order = settings["order"]
    if user["role"] == "admin":
        return order
    grants = set(granted(user["email"])) if user["role"] == "viewer" else set()
    return [p for p in order if not settings["locked"][p] or p in grants] if user["role"] == "viewer" else []


def granted(email: str) -> list[str]:
    return [r["pipeline"] for r in db.rows("SELECT pipeline FROM user_pipeline_access WHERE email=? ORDER BY pipeline", (email,))
            if r["pipeline"] in PIPELINES]


def default_pipeline(user: dict) -> str:
    permitted = allowed(user)
    if not permitted:
        raise HTTPException(403, "All pipelines are locked. Contact the admin to request access.")
    return permitted[0]


def require_pipeline(user: dict, pipe: str) -> str:
    if user["role"] != "admin" and pipe not in allowed(user):
        raise HTTPException(403, "This pipeline requires an admin access grant.")
    return pipe


def require_source(user: dict, source: str) -> None:
    if user["role"] == "admin":
        return
    if source.startswith(("tm_", "paper_")):
        require_pipeline(user, source.split("_", 1)[1])
    else:
        raise HTTPException(403, "Legacy pipeline data is available to admins only.")


def with_permissions(user: dict) -> dict:
    return {**user, "allowed_pipelines": allowed(user), "admin_contact_email": SETTINGS.admin_contact_email}
