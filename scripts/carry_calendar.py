"""Carry calendar: read-only quarterly delivery schedule (research only, no orders, public REST only).

Shows, for BTC and ETH, the listed Bybit INVERSE quarterly contracts with
delivery date/time (UTC + Vietnam time), current annualised basis
ln(F/S)*365/DTE vs the frozen 4 %/yr threshold, days to delivery, the next
roll window (<= 7 days before delivery) and the owner action list per date.

Frozen rule is imported from scripts/carry_paper.py (RULE_PARAMS,
is_quarterly_delivery, annualised_basis, fetch_dated_contracts, fetch_mid)
and never re-defined here. Venue is Bybit V5 PUBLIC endpoints only (never
signed, never POST, never an order).

Usage:
    .venv\\Scripts\\python.exe scripts/carry_calendar.py
    .venv\\Scripts\\python.exe scripts/carry_calendar.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.carry_paper import (  # noqa: E402  (frozen rule: import, do not re-define)
    MS_DAY,
    RULE_PARAMS,
    annualised_basis,
    fetch_dated_contracts,
    fetch_mid,
    is_quarterly_delivery,
)

VN_TZ = timezone(timedelta(hours=7), name="ICT")  # Vietnam time: UTC+7, no DST


def fmt_times(delivery_ms: int) -> tuple[str, str]:
    """(UTC iso, Vietnam iso) for a delivery timestamp in ms."""
    dt_utc = datetime.fromtimestamp(int(delivery_ms) / 1000, tz=timezone.utc)
    dt_vn = dt_utc.astimezone(VN_TZ)
    return dt_utc.isoformat(), dt_vn.isoformat()


def fmt_day(delivery_ms: int) -> tuple[str, str]:
    """(UTC date, Vietnam date) YYYY-MM-DD for a delivery timestamp in ms."""
    utc_iso, vn_iso = fmt_times(int(delivery_ms))
    return utc_iso[:10], vn_iso[:10]


def inverse_quarterlies(client) -> list:
    """Listed Bybit INVERSE quarterly BTC/ETH contracts, ascending delivery."""
    contracts = fetch_dated_contracts(client)
    out = [c for c in contracts
           if str(c.get("category", "")) == "inverse"
           and str(c.get("coin", "")).upper() in ("BTC", "ETH")
           and is_quarterly_delivery(int(c["delivery_ms"]))]
    out.sort(key=lambda e: int(e["delivery_ms"]))
    return out


def build_rows(client, now_ms: int | None = None) -> list:
    """One row per inverse quarterly contract. Pure read: public GETs only."""
    now_ms = int(now_ms) if now_ms is not None else int(time.time() * 1000)
    threshold = float(RULE_PARAMS["basis_threshold"])
    roll_days = int(RULE_PARAMS["roll_days"])
    rows: list = []
    for c in inverse_quarterlies(client):
        coin = str(c["coin"]).upper()
        symbol = str(c["symbol"])
        dlv = int(c["delivery_ms"])
        utc_iso, vn_iso = fmt_times(dlv)
        dte = (dlv - now_ms) / MS_DAY
        roll_start_ms = dlv - roll_days * MS_DAY
        roll_utc, roll_vn = fmt_times(roll_start_ms)
        s_mid, _ = fetch_mid(client, "spot", f"{coin}USDT")
        f_mid, _ = fetch_mid(client, "inverse", symbol)
        basis = None
        if s_mid and f_mid and dte > 0:
            try:
                basis = float(annualised_basis(float(f_mid), float(s_mid), float(dte)))
            except ValueError:
                basis = None
        above = bool(basis is not None and basis >= threshold)
        in_roll = bool(0 <= (dlv - now_ms) <= roll_days * MS_DAY)
        # Owner actions (human/bot followable, times in both zones).
        hhmm_utc = utc_iso[11:16]
        hhmm_vn = vn_iso[11:16]
        actions = [
            f"Tu {roll_utc[:10]} ({roll_vn[:10]} gio VN): mo cua so roll {symbol} "
            f"(front chi con <={roll_days} ngay); vao cap spot-long + quarterly-short "
            f"KE TIEP chi khi basis >= {threshold * 100:.0f}%/nam.",
            f"Den han {utc_iso[:10]} {hhmm_utc} UTC = {vn_iso[:10]} {hhmm_vn} gio VN: "
            f"futures tu quyet toan theo gia delivery; BAN leg spot o gia thi truong "
            f"luc {hhmm_utc} UTC (= {hhmm_vn} gio VN).",
        ]
        rows.append({
            "coin": coin,
            "symbol": symbol,
            "category": "inverse",
            "delivery_ms": dlv,
            "delivery_utc": utc_iso,
            "delivery_vn": vn_iso,
            "spot_mid": float(s_mid) if s_mid else None,
            "fut_mid": float(f_mid) if f_mid else None,
            "dte_days": round(float(dte), 2),
            "ann_basis": round(float(basis), 6) if basis is not None else None,
            "basis_threshold": threshold,
            "above_threshold": above,
            "roll_start_utc": roll_utc,
            "roll_start_vn": roll_vn,
            "in_roll_window": in_roll,
            "owner_actions": actions,
        })
    return rows


def render_text(rows: list, now_ms: int) -> str:
    now_iso = datetime.fromtimestamp(int(now_ms) / 1000, tz=timezone.utc).isoformat()
    th = float(RULE_PARAMS["basis_threshold"]) * 100
    lines = [f"carry_calendar now={now_iso} threshold={th:.0f}%/yr roll<=7d (inverse quarterly, public only)"]
    if not rows:
        lines.append("no listed inverse quarterly BTC/ETH contracts")
        return "\n".join(lines)
    by_coin: dict = {}
    for r in rows:
        by_coin.setdefault(r["coin"], []).append(r)
    for coin in ("BTC", "ETH"):
        lines.append(f"== {coin} ==")
        for r in by_coin.get(coin, []):
            b = r["ann_basis"]
            b_txt = f"{b * 100:+.2f}%/yr" if b is not None else "n/a"
            flag = "ENTER-ABLE" if r["above_threshold"] else "SKIP (<4%)"
            lines.append(
                f"{r['symbol']} delivery {r['delivery_utc'][:16]} UTC = {r['delivery_vn'][:16]} VN "
                f"| DTE {r['dte_days']:.1f}d | basis {b_txt} -> {flag}")
            lines.append(
                f"  roll window: tu {r['roll_start_utc'][:16]} UTC (= {r['roll_start_vn'][:16]} VN)"
                f"{' [IN WINDOW]' if r['in_roll_window'] else ''}")
            for a in r["owner_actions"]:
                lines.append(f"  * {a}")
        if coin not in by_coin:
            lines.append("(none listed)")
    return "\n".join(lines)


def build_client(base: str = "mainnet"):
    """Public-only Bybit client (no keys, GET /v5/market/* only)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from bot.bybit_v5 import MAINNET, TESTNET, Bybit

    return Bybit(None, None, base=MAINNET if base == "mainnet" else TESTNET)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only carry calendar for Bybit inverse quarterly contracts (public endpoints only, never places orders).")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON instead of text")
    ap.add_argument("--base", choices=("mainnet", "testnet"), default="mainnet")
    a = ap.parse_args(argv)
    client = build_client(a.base)
    now_ms = int(time.time() * 1000)
    try:
        rows = build_rows(client, now_ms=now_ms)
    except Exception as exc:  # noqa: BLE001 - public fetch flakiness, never traceback
        print(f"carry_calendar status=error note={str(exc)[:160]}")
        return 1
    if a.json:
        print(json.dumps({"now_ms": now_ms,
                          "now_utc": datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).isoformat(),
                          "basis_threshold": float(RULE_PARAMS["basis_threshold"]),
                          "roll_days": int(RULE_PARAMS["roll_days"]),
                          "rows": rows}, indent=1, default=str))
    else:
        print(render_text(rows, now_ms))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
