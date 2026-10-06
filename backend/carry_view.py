"""Read-only view over the carry paper ledger (scripts/carry_paper.py).

Reads artifacts/bot/paper_carry/state.json only; never writes, never touches
the network, never places orders. Used by the GET /api/carry endpoint and the
'Carry quý (paper)' frontend panel.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STALE_SECONDS = 2 * 3600  # the assignment's stale flag: no ledger run for > 2 h
MS_DAY = 86_400_000


def default_state_path() -> Path:
    from .config import ROOT

    return ROOT / "artifacts" / "bot" / "paper_carry" / "state.json"


def _parse_time(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _num(value, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if out == out else default  # NaN -> default


def load_raw(state_path: Path | str | None = None) -> dict | None:
    """Return the parsed ledger dict, or None when missing/corrupt (read-only)."""
    path = Path(state_path) if state_path is not None else default_state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def summarize(state: dict | None, now: datetime | None = None) -> dict:
    """Build the JSON-serializable carry view from a ledger dict (pure function)."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    now_ms = int(moment.timestamp() * 1000)
    st = state if isinstance(state, dict) else {}

    positions = st.get("positions")
    if not isinstance(positions, dict):
        positions = {}
    history = st.get("history")
    if not isinstance(history, list):
        history = []
    totals = st.get("totals")
    if not isinstance(totals, dict):
        totals = {}

    open_pairs = []
    for coin in sorted(positions):
        pos = positions[coin]
        if not isinstance(pos, dict):
            continue
        delivery_ms = pos.get("delivery_ms")
        try:
            delivery_ms = int(delivery_ms)
        except (TypeError, ValueError):
            delivery_ms = None
        days_left = (delivery_ms - now_ms) / MS_DAY if delivery_ms else None
        basis = pos.get("ann_basis")
        mtm = pos.get("mtm_alloc")
        open_pairs.append({
            "coin": pos.get("coin", coin),
            "contract": pos.get("symbol"),
            "category": pos.get("category"),
            "entry_time": pos.get("entry_time"),
            "entry_basis": _num(basis, 0.0),  # annualised ln(F/S)*365/DTE, fraction/yr
            "entry_basis_pct_yr": round(_num(basis, 0.0) * 100.0, 2),
            "dte_days_entry": pos.get("dte_days"),
            "delivery_ms": delivery_ms,
            "days_to_delivery": round(days_left, 2) if days_left is not None else None,
            "mtm_alloc": _num(mtm, 0.0),  # ledger's last mark, fraction of allocated
            "mtm_pct_alloc": round(_num(mtm, 0.0) * 100.0, 2),
            "unrealised_usdt": pos.get("unrealised"),
            "entry_fees_usdt": pos.get("entry_fees"),
            "equity_entry": pos.get("equity_entry"),
            "f": pos.get("f"),
        })

    settled_pairs = []
    for rec in history:
        if not isinstance(rec, dict):
            continue
        settled_pairs.append({
            "coin": rec.get("coin"),
            "contract": rec.get("symbol"),
            "entry_time": rec.get("entry_time"),
            "settled_at": rec.get("settled_at"),
            "status": rec.get("status"),
            "s_entry": rec.get("S_entry"),
            "f_entry": rec.get("F_entry"),
            "s_del": rec.get("S_del"),
            "delivery_source": rec.get("delivery_source"),
            "realised_pnl_usdt": rec.get("realised_pnl"),
            "realised_ret_alloc": rec.get("realised_ret_alloc"),
        })

    updated_at = st.get("updated_at") if isinstance(st.get("updated_at"), str) else None
    seen = _parse_time(updated_at)
    stale = True if seen is None else (moment - seen).total_seconds() > STALE_SECONDS

    rule = st.get("rule") if isinstance(st.get("rule"), dict) else None
    sha = st.get("rule_sha256") if isinstance(st.get("rule_sha256"), str) else None
    return {
        "tag": st.get("tag", "carry"),
        "rule": rule,
        "rule_sha256": sha,
        "open_pairs": open_pairs,
        "n_open": len(open_pairs),
        "settled_pairs": settled_pairs,
        "n_settled": len(settled_pairs),
        "totals": {
            "n_entered": totals.get("n_entered", 0),
            "n_skipped": totals.get("n_skipped", 0),
            "realised_pnl_usdt": _num(totals.get("realised_pnl", 0.0)),
            "fees_paid_usdt": _num(totals.get("fees_paid", 0.0)),
        },
        "updated_at": updated_at,
        "stale": stale,
        "has_data": bool(open_pairs or settled_pairs),
    }


def get_carry_view(state_path: Path | str | None = None, now: datetime | None = None) -> dict:
    """Read the ledger file and return the endpoint payload (read-only)."""
    return summarize(load_raw(state_path), now=now)
