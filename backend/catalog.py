"""Product ranking/access, separate from research model selection and training."""

import json
import math

from fastapi import HTTPException

from . import db
from .config import SETTINGS

# Recorded dashboard metrics: product ranking only, explicitly requested by the user.
# g2c = deployed BOT "G2 + carry" (docs/SUMMARY_FOR_OWNER_20261007_VI.md, docs/FINAL_REPORT_VI.md):
# research 5y 5.634 %/mo, worst year 2.778 (2021), expected live ~5.2-5.4 (clock-luck adjusted),
# DD year-max 16.75 / full-path 16.66, all-trade win ~65.3% (book ~51.5%), losing years 0.
# Uses the v376 plan file (same trade_plan_v376.json); carry overlay f=0.25 in one Bybit UTA
# (bot flags --corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --carry-f 0.25).
PIPELINES = {  # product: "manual" = a human can follow it (per-pipeline locks / grants); "bot" = needs a bot (Bot tab: no locks, the 3 best,
               # visible only to admins and to accounts holding the BOT grant)
    # Deployed BOT first (explicit priority in metric_order below); older BOT entries kept as reference only.
    "g2c": {"candidate": "v376_R2_4P", "product": "bot",
            "monthly_5y": 5.634, "monthly_last_year": 4.698, "gate_dd": 16.75,
            "win_hidden": 0.515, "win_all_hidden": 0.653, "losing_years": 0},
    "v321": {"candidate": "v321_R2", "product": "bot", "monthly_last_year": 5.655, "gate_dd": 18.39, "win_hidden": 0.560},  # older/reference (single-clock R2)
    # v376 R2-4P: R2 on four 4h clocks shifted 0/1/2/3 h, 1/4 capital each (most recent year scored once: 3.902 %/month, DD 18.76 that year; gate DD = full 5-year path 23.08;
    # book win of the most recent year 0.549 from v376_mix_series; the dev years' conservative DD reaches 23.08 in 2023-24)
    "v376": {"candidate": "v376_R2_4P", "product": "bot", "monthly_last_year": 3.902, "gate_dd": 23.08, "win_hidden": 0.549},  # older/reference (book+dip plan shared with g2c, without carry overlay)
    "v301": {"candidate": "v301_G2", "product": "bot", "monthly_last_year": 5.349, "gate_dd": 17.09, "win_hidden": 0.558},  # older/reference
    "v295": {"candidate": "v295_CS", "product": "bot", "monthly_last_year": 5.266, "gate_dd": 17.2, "win_hidden": 0.558},  # older/reference
    "v367": {"candidate": "v367_M5", "product": "manual", "monthly_last_year": 5.22, "gate_dd": 18.62, "win_hidden": 0.686},
    "v362": {"candidate": "v362_M4", "product": "manual", "monthly_last_year": 5.04, "gate_dd": 16.96, "win_hidden": 0.556},
    "v342": {"candidate": "v342_M3", "product": "manual", "monthly_last_year": 4.704, "gate_dd": 17.73, "win_hidden": 0.556},
    "v340": {"candidate": "v340_M2", "product": "manual", "monthly_last_year": 3.733, "gate_dd": 13.95, "win_hidden": 0.556},
    "v315": {"candidate": "v315_M1", "product": "manual", "monthly_last_year": 3.289, "gate_dd": 18.47, "win_hidden": 0.550},
}
MANUAL = {p for p, v in PIPELINES.items() if v["product"] == "manual"}
BOT = {p for p, v in PIPELINES.items() if v["product"] == "bot"}
BOT_GRANT = "bot"  # account-level grant that opens the whole Bot tab
GRANTABLE = MANUAL | {BOT_GRANT}


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
        # g2c is the deployed BOT pipeline: rank it first among BOT pipelines (honest metrics kept above).
        return (0 if pipe == "g2c" else 1, -monthly, dd, -win, pipe)
    return sorted(PIPELINES, key=score)


POLICY_KEY = "pipeline_access_policy"
SUMMARY_FIELDS = ("monthly_5y", "monthly_dev4", "monthly_last_year", "dd_4h", "dd_1m", "gate_dd",
                  "losing_years", "yearly", "win_dev", "win_hidden", "trades_dev", "trades_hidden", "win_all_dev", "win_all_hidden",
                  "rungs_dev", "rungs_hidden")


def policy() -> dict:
    saved = db.kv_get(POLICY_KEY, {}) or {}
    automatic = saved.get("order") is None
    ranking = metric_order()
    if automatic:
        order = ranking
    else:  # a saved order from an older catalogue: drop retired pipelines, append new ones in metric order
        order = [p for p in saved["order"] if p in PIPELINES] + [p for p in ranking if p not in saved["order"]]
    # MANUAL: the two best are locked by default (premium), the rest free; BOT pipelines have no locks (access is the account's BOT grant)
    manual = [p for p in order if p in MANUAL]
    default_locks = {p: p in MANUAL and manual.index(p) < 2 for p in order}
    saved_locks = saved.get("locked")
    # a pipeline added after the locks were saved starts LOCKED (admin-only) until the admin decides
    locks = default_locks if saved_locks is None else {p: p in MANUAL and bool(saved_locks.get(p, True)) for p in order}
    return {"order": order, "locked": locks, "automatic": automatic, "revision": saved.get("revision", 0)}


def save_policy(payload: dict, email: str) -> dict:
    order, locks, revision = payload.get("order"), payload.get("locked"), payload.get("revision")
    # Backward compat: an older admin UI / saved order without display aliases (g2c reuses v376's plan)
    # appends the missing aliases in metric order instead of 400; anything else missing still 400s.
    if isinstance(order, list) and all(isinstance(p, str) for p in order) and set(order) <= set(PIPELINES) \
            and len(order) == len(set(order)) and set(order) < set(PIPELINES) \
            and set(PIPELINES) - set(order) <= set(PLAN_ALIASES):
        ranking = metric_order()
        order = list(order) + [p for p in ranking if p not in order]
        if isinstance(locks, dict):
            locks = {**locks, **{p: (p in MANUAL) for p in set(PIPELINES) - set(locks) if p in PLAN_ALIASES}}
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


# Display-only pipelines that reuse another pipeline's plan (no plan job, no replay of their own).
PLAN_ALIASES = {"g2c": "v376"}


def plan_pipes() -> list[str]:
    """ranked() without display aliases: the pipelines the scheduler builds plans / replays for."""
    return [p for p in ranked() if p not in PLAN_ALIASES]


def allowed(user: dict) -> list[str]:
    settings = policy()
    order = settings["order"]
    if user["role"] == "admin":
        return order
    grants = set(granted(user["email"])) if user["role"] == "viewer" else set()
    if user["role"] != "viewer":
        return []
    # MANUAL: unlocked or individually granted; BOT: every bot pipeline, only with the account's BOT grant
    return [p for p in order if (p in MANUAL and (not settings["locked"][p] or p in grants)) or (p in BOT and BOT_GRANT in grants)]


def granted(email: str) -> list[str]:
    """MANUAL pipeline grants and the account-level BOT grant ("bot")."""
    return [r["pipeline"] for r in db.rows("SELECT pipeline FROM user_pipeline_access WHERE email=? ORDER BY pipeline", (email,))
            if r["pipeline"] in GRANTABLE]


def bot_access(user: dict) -> bool:
    return user["role"] == "admin" or user["role"] == "viewer" and BOT_GRANT in granted(user["email"])


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
    return {**user, "allowed_pipelines": allowed(user), "bot_access": bot_access(user), "admin_contact_email": SETTINGS.admin_contact_email}
