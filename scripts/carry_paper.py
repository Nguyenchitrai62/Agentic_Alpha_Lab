"""Prospective PAPER ledger for the frozen cash-and-carry sleeve (research only, no orders, public REST only).

Pre-registered rule (research/tournament/oc_cashcarry/PLAN.md, frozen before outcomes):
per coin (BTC, ETH) sort quarterly delivery expiries ascending; enter the NEXT
quarterly when <= 7 days remain on the current (front) one, or the front at
first availability; ENTER only if annualised basis ln(F/S)*365/DTE >= 4 %/yr;
equal-notional spot long + quarterly short, each leg = f x equity at entry;
hold to delivery; fees spot taker 0.1 %/side, futures taker 0.055 % entry,
0.02 % delivery (drag 0.275 % of allocated). Delivery futures pay NO funding.

Live venue is Bybit V5 PUBLIC endpoints only (never signed, never POST, never
an order): instruments-info (linear + inverse, dated futures, status Trading),
tickers (spot + futures mid prices), delivery-price (settlement). Nothing is
bought or sold; the ledger only tracks what the rule WOULD hold.

Usage (idempotent; meant to run hourly from the existing loop or by hand):

    .venv\\Scripts\\python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry

State in artifacts/bot/paper_<tag>/state.json, every decision appended to
artifacts/bot/paper_<tag>/actions.jsonl. Prints the frozen rule sha256 at
start plus a one-line status. API errors use retry/backoff and never crash
the loop (logged as error actions, exit 0).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- frozen rule

RULE_PARAMS = {
    "coins": ["BTC", "ETH"],
    "roll_days": 7,
    "basis_threshold": 0.04,
    "hold_to_delivery": True,
    "fee_spot_taker": 0.001,
    "fee_fut_entry": 0.00055,
    "fee_fut_delivery": 0.0002,
    "fee_drag_total": 0.00275,
    "entry_fee_frac": 0.00155,
    "sizing": "equal-notional spot long + quarterly short, each leg = f x equity at entry",
    "settlement": "Bybit V5 public delivery-price endpoint; fallback spot mid (labelled)",
    "venue": "Bybit V5 public market endpoints only (no orders)",
}

MS_DAY = 86_400_000


def rule_sha256() -> str:
    canon = json.dumps(RULE_PARAMS, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


# ---------------------------------------------------------------- paths

ROOT = Path(__file__).resolve().parents[1]


def state_dir_for(tag: str) -> Path:
    safe = "".join(c for c in str(tag) if c.isalnum() or c in ("-", "_")) or "carry"
    return ROOT / "artifacts" / "bot" / f"paper_{safe}"


# ---------------------------------------------------------------- maths

def annualised_basis(fut: float, spot: float, dte_days: float) -> float:
    if not (fut > 0 and spot > 0 and dte_days > 0):
        raise ValueError("need positive F, S and DTE")
    return math.log(fut / spot) * 365.0 / dte_days


def pick_candidate(expiries: list, now_ms: int, has_history: bool):
    """Return the candidate contract dict or None.

    expiries: [{symbol, category, delivery_ms}] sorted ascending internally.
    Rule: front = earliest expiry with delivery > now. If the front expires
    within roll_days, the candidate is the NEXT quarterly (C1). Otherwise the
    candidate is the front only at first availability (no history for the
    coin); if we already traded this coin, waiting is the position (None).
    """
    live = sorted(
        (e for e in expiries if int(e["delivery_ms"]) > int(now_ms)),
        key=lambda e: int(e["delivery_ms"]),
    )
    if not live:
        return None
    front = live[0]
    left_ms = int(front["delivery_ms"]) - int(now_ms)
    if left_ms <= int(RULE_PARAMS["roll_days"]) * MS_DAY:
        return live[1] if len(live) > 1 else None
    return front if not has_history else None


def mid_from_ticker(t: dict) -> float | None:
    try:
        bid = float(t.get("bid1Price") or 0) if t.get("bid1Price") not in (None, "") else 0.0
        ask = float(t.get("ask1Price") or 0) if t.get("ask1Price") not in (None, "") else 0.0
        if bid > 0 and ask > 0:
            return (bid + ask) / 2.0
        for k in ("lastPrice", "markPrice", "indexPrice"):
            v = t.get(k)
            if v not in (None, "") and float(v) > 0:
                return float(v)
    except (TypeError, ValueError):
        return None
    return None


# ---------------------------------------------------------------- public I/O

def _call_public(client, path: str, tries: int = 3, **params):
    """GET a public endpoint with backoff; reraise after `tries` attempts."""
    last: Exception | None = None
    for attempt in range(int(tries)):
        try:
            return client.public(path, **params)
        except Exception as exc:  # noqa: BLE001 - network flakiness, never crash the loop
            last = exc
            msg = repr(exc)
            rate = any(c in msg for c in ("10006", "429", "418"))
            if attempt + 1 >= int(tries):
                break
            time.sleep((1.5 if rate else 0.8) * (attempt + 1))
    assert last is not None
    raise last


def is_quarterly_delivery(delivery_ms: int) -> bool:
    """Quarterly cycle only (as researched in oc_cashcarry): delivery on the last Friday of Mar/Jun/Sep/Dec (UTC)."""
    import datetime as _dt
    d = _dt.datetime.fromtimestamp(int(delivery_ms) / 1000, tz=_dt.timezone.utc)
    return d.month in (3, 6, 9, 12) and d.weekday() == 4 and (d + _dt.timedelta(days=7)).month != d.month


def fetch_dated_contracts(client) -> list:
    """Dated BTC/ETH futures with status Trading (linear + inverse)."""
    out = []
    for cat in ("linear", "inverse"):
        cursor = None
        for _ in range(10):  # pagination guard; dated lists are tiny
            kw: dict = {"category": cat, "limit": 1000}
            if cursor:
                kw["cursor"] = cursor
            res = _call_public(client, "/v5/market/instruments-info", **kw)
            items = (res or {}).get("list", []) if isinstance(res, dict) else []
            for it in items:
                if not isinstance(it, dict):
                    continue
                if str(it.get("status", "")) != "Trading":
                    continue
                base = str(it.get("baseCoin", "")).upper()
                if base not in ("BTC", "ETH"):
                    continue
                ctype = str(it.get("contractType", ""))
                if "Perpetual" in ctype or "Futures" not in ctype:
                    continue  # dated delivery futures only; perps are a different sleeve
                try:
                    dlv = int(float(it.get("deliveryTime") or 0))
                except (TypeError, ValueError):
                    continue
                if dlv <= 0:
                    continue
                if not is_quarterly_delivery(dlv):
                    continue  # weekly / monthly / bi-weekly dated contracts are NOT part of the pre-registered quarterly rule
                out.append({
                    "symbol": str(it.get("symbol")),
                    "category": cat,
                    "coin": base,
                    "delivery_ms": dlv,
                    "deliveryFeeRate": str(it.get("deliveryFeeRate", "")),
                })
            cursor = (res or {}).get("nextPageCursor") if isinstance(res, dict) else None
            if not cursor:
                break
    out.sort(key=lambda e: int(e["delivery_ms"]))
    return out


def fetch_mid(client, category: str, symbol: str) -> tuple[float | None, dict | None]:
    res = _call_public(client, "/v5/market/tickers", category=category, symbol=symbol)
    rows = (res or {}).get("list", []) if isinstance(res, dict) else []
    row = rows[0] if rows and isinstance(rows[0], dict) else None
    if row is None:
        return None, None
    return mid_from_ticker(row), row


def fetch_delivery_price(client, category: str, symbol: str):
    """(price, delivery_ms) or (None, None) when not yet published."""
    try:
        res = _call_public(client, "/v5/market/delivery-price", category=category, symbol=symbol)
    except Exception:
        return None, None
    rows = (res or {}).get("list", []) if isinstance(res, dict) else []
    for row in rows:
        if isinstance(row, dict) and str(row.get("symbol", "")) == symbol:
            try:
                px = float(row.get("deliveryPrice") or 0)
                if px > 0:
                    dm = row.get("deliveryTime")
                    return px, int(float(dm)) if dm not in (None, "") else None
            except (TypeError, ValueError):
                continue
    return None, None


# ---------------------------------------------------------------- ledger

def blank_state(tag: str, equity: float, f: float) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "tag": tag, "equity_arg": float(equity), "f": float(f),
        "rule": dict(RULE_PARAMS), "rule_sha256": rule_sha256(),
        "created_at": now, "updated_at": now,
        "positions": {}, "history": [], "entered_symbols": [],
        "totals": {"n_entered": 0, "n_skipped": 0, "realised_pnl": 0.0, "fees_paid": 0.0},
    }


def load_state(path: Path, tag: str, equity: float, f: float) -> dict:
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(st, dict) and isinstance(st.get("positions"), dict):
            st.setdefault("history", [])
            st.setdefault("entered_symbols", [])
            tot = st.setdefault("totals", {})
            for k, v in (("n_entered", 0), ("n_skipped", 0), ("realised_pnl", 0.0), ("fees_paid", 0.0)):
                tot.setdefault(k, v)
            st["rule"] = dict(RULE_PARAMS)
            st["rule_sha256"] = rule_sha256()
            return st
    except (OSError, ValueError):
        pass
    return blank_state(tag, equity, f)


def save_state(path: Path, st: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    st["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")
    import os

    os.replace(tmp, path)


def log_action(actions_path: Path, rec: dict) -> None:
    actions_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"t": datetime.now(timezone.utc).isoformat(), **rec}
    with actions_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def realised_pnl_pair(f: float, eq_entry: float, s_entry: float,
                       fut_entry: float, s_del: float) -> tuple[float, float]:
    """(net P&L in USDT, ret on allocated) per oc_cashcarry PLAN §Position/fees."""
    drag = float(RULE_PARAMS["fee_drag_total"])
    gross_alloc = (s_del - s_entry) / s_entry + (fut_entry - s_del) / fut_entry
    ret_alloc = gross_alloc - drag
    return float(f) * float(eq_entry) * ret_alloc, ret_alloc


# ---------------------------------------------------------------- one pass

def run_once(client, sdir: Path, equity: float, f: float, tag: str,
             now_ms: int | None = None) -> dict:
    """One idempotent hourly pass. Never raises on API errors (logs + status)."""
    now_ms = int(now_ms) if now_ms is not None else int(time.time() * 1000)
    now_iso = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).isoformat()
    state_path = Path(sdir) / "state.json"
    actions_path = Path(sdir) / "actions.jsonl"
    st = load_state(state_path, tag, equity, f)
    st["equity_arg"] = float(equity)
    st["f"] = float(f)
    counts = {"entered": 0, "settled": 0, "skipped": 0, "errors": 0, "holding": 0}

    try:
        contracts = fetch_dated_contracts(client)
    except Exception as exc:  # noqa: BLE001
        log_action(actions_path, {"op": "error", "tag": tag, "call": "instruments-info",
                                  "note": str(exc)[:300]})
        save_state(state_path, st)
        return {"status": "error", "note": f"instruments-info failed: {exc}"[:160], **counts}

    trading = {c["symbol"] for c in contracts}
    by_coin: dict = {}
    for c in contracts:
        by_coin.setdefault(c["coin"], []).append(c)

    for coin in RULE_PARAMS["coins"]:
        expiries = by_coin.get(coin, [])
        pos = (st["positions"] or {}).get(coin)

        # ---- settle an open position that reached delivery
        if pos:
            dlv = int(pos["delivery_ms"])
            if now_ms >= dlv:
                s_del, src = None, "spot-fallback"
                try:
                    px, _ = fetch_delivery_price(client, pos["category"], pos["symbol"])
                    if px:
                        s_del, src = float(px), "delivery-price"
                except Exception as exc:  # noqa: BLE001
                    log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                              "call": "delivery-price", "note": str(exc)[:300]})
                if s_del is None:
                    try:
                        m, _ = fetch_mid(client, "spot", pos["spot_symbol"])
                        if m:
                            s_del = float(m)
                    except Exception as exc:  # noqa: BLE001
                        log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                                  "call": "spot-ticker-settle", "note": str(exc)[:300]})
                if s_del is None:
                    counts["errors"] += 1
                    log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                              "symbol": pos["symbol"],
                                              "note": "delivery due but no settlement price; retry next run"})
                    continue
                pnl, ret_alloc = realised_pnl_pair(float(pos["f"]), float(pos["equity_entry"]),
                                                   float(pos["S_entry"]), float(pos["F_entry"]),
                                                   float(s_del))
                fees = float(pos["f"]) * float(pos["equity_entry"]) * float(RULE_PARAMS["fee_drag_total"])
                st["history"].append({**pos, "status": "delivered", "S_del": float(s_del),
                                     "delivery_source": src, "settled_at": now_iso,
                                     "realised_pnl": round(pnl, 6),
                                     "realised_ret_alloc": round(ret_alloc, 6)})
                st["positions"].pop(coin, None)
                st["totals"]["realised_pnl"] = round(float(st["totals"]["realised_pnl"]) + pnl, 6)
                st["totals"]["fees_paid"] = round(float(st["totals"]["fees_paid"]) + fees, 6)
                counts["settled"] += 1
                log_action(actions_path, {"op": "settle", "tag": tag, "coin": coin,
                                          "symbol": pos["symbol"], "S_del": float(s_del),
                                          "source": src, "realised_pnl": round(pnl, 4),
                                          "ret_alloc": round(ret_alloc, 6)})
                pos = None
            else:
                # ---- hold: refresh mark-to-market from mid prices (info only)
                if pos["symbol"] not in trading:
                    log_action(actions_path, {"op": "delisted", "tag": tag, "coin": coin,
                                              "symbol": pos["symbol"],
                                              "note": "contract no longer Trading; holding to delivery on last marks"})
                try:
                    s_mid, _ = fetch_mid(client, "spot", pos["spot_symbol"])
                    f_mid, _ = fetch_mid(client, pos["category"], pos["symbol"])
                except Exception as exc:  # noqa: BLE001
                    counts["errors"] += 1
                    log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                              "symbol": pos.get("symbol"),
                                              "call": "tickers-hold", "note": str(exc)[:300]})
                    continue
                if s_mid and f_mid:
                    mtm = (s_mid / pos["S_entry"] - 1) + ((pos["F_entry"] - f_mid) / pos["F_entry"]) \
                        - float(RULE_PARAMS["entry_fee_frac"])
                    pos["last_spot"] = float(s_mid)
                    pos["last_fut"] = float(f_mid)
                    pos["mtm_alloc"] = round(float(mtm), 6)
                    pos["unrealised"] = round(float(pos["f"]) * float(pos["equity_entry"]) * float(mtm), 4)
                counts["holding"] += 1
                log_action(actions_path, {"op": "hold", "tag": tag, "coin": coin,
                                          "symbol": pos["symbol"],
                                          "mtm_alloc": pos.get("mtm_alloc"),
                                          "unrealised": pos.get("unrealised")})
        if pos:
            continue  # still open: no entry while holding (never overlap by construction)

        # ---- flat: apply the frozen roll/entry rule
        if not expiries:
            log_action(actions_path, {"op": "no_eligible", "tag": tag, "coin": coin,
                                      "note": "no Trading dated BTC/ETH futures listed"})
            continue
        has_hist = bool(st["positions"].get(coin)) or \
            any(h.get("coin") == coin for h in st["history"]) or \
            any(str(s).startswith(coin) for s in st.get("entered_symbols", []))
        cand = pick_candidate(expiries, now_ms, has_hist)
        if cand is None:
            log_action(actions_path, {"op": "wait", "tag": tag, "coin": coin,
                                      "note": "front has >7d to delivery and coin already traded; no entry"})
            continue
        try:
            spot_sym = f"{coin}USDT"
            s_mid, _ = fetch_mid(client, "spot", spot_sym)
            f_mid, _ = fetch_mid(client, cand["category"], cand["symbol"])
        except Exception as exc:  # noqa: BLE001
            counts["errors"] += 1
            log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                      "symbol": cand["symbol"], "call": "tickers-entry",
                                      "note": str(exc)[:300]})
            continue
        if not (s_mid and f_mid):
            counts["errors"] += 1
            log_action(actions_path, {"op": "error", "tag": tag, "coin": coin,
                                      "symbol": cand["symbol"],
                                      "note": "empty ticker mid; retry next run"})
            continue
        dte = (int(cand["delivery_ms"]) - now_ms) / MS_DAY
        try:
            basis = annualised_basis(float(f_mid), float(s_mid), float(dte))
        except ValueError:
            counts["errors"] += 1
            continue
        if basis < float(RULE_PARAMS["basis_threshold"]):
            st["totals"]["n_skipped"] = int(st["totals"].get("n_skipped", 0)) + 1
            counts["skipped"] += 1
            log_action(actions_path, {"op": "skip", "tag": tag, "coin": coin,
                                      "symbol": cand["symbol"],
                                      "ann_basis": round(basis, 6),
                                      "note": f"basis {basis * 100:.2f}%/yr < 4%/yr threshold"})
            continue
        # ENTER the pair (paper only: no orders are placed anywhere).
        eq = float(equity)
        notion = float(f) * eq
        entry_fees = notion * (float(RULE_PARAMS["fee_spot_taker"]) + float(RULE_PARAMS["fee_fut_entry"]))
        st["positions"][coin] = {
            "coin": coin, "symbol": cand["symbol"], "category": cand["category"],
            "spot_symbol": spot_sym, "status": "open",
            "entry_time": now_iso, "delivery_ms": int(cand["delivery_ms"]),
            "S_entry": float(s_mid), "F_entry": float(f_mid),
            "ann_basis": round(float(basis), 6), "dte_days": round(float(dte), 2),
            "equity_entry": eq, "f": float(f),
            "spot_qty": notion / float(s_mid), "fut_qty": notion / float(f_mid),
            "entry_fees": round(entry_fees, 6),
            "last_spot": float(s_mid), "last_fut": float(f_mid),
            "mtm_alloc": round(-float(RULE_PARAMS["entry_fee_frac"]), 6),
            "unrealised": round(-entry_fees, 4),
        }
        st["entered_symbols"].append(f"{coin}:{cand['symbol']}")
        st["totals"]["n_entered"] = int(st["totals"].get("n_entered", 0)) + 1
        st["totals"]["fees_paid"] = round(float(st["totals"]["fees_paid"]) + 0.0, 6)
        counts["entered"] += 1
        log_action(actions_path, {"op": "entry", "tag": tag, "coin": coin,
                                  "symbol": cand["symbol"], "category": cand["category"],
                                  "S_entry": float(s_mid), "F_entry": float(f_mid),
                                  "ann_basis": round(float(basis), 6),
                                  "dte_days": round(float(dte), 2),
                                  "notional_each_leg": round(notion, 2)})

    save_state(state_path, st)
    open_n = len(st.get("positions") or {})
    status = (f"carry_paper tag={tag} open={open_n} entered={counts['entered']} "
              f"settled={counts['settled']} skipped={counts['skipped']} "
              f"errors={counts['errors']} realised={float(st['totals']['realised_pnl']):+.2f}")
    return {"status": "ok", "summary": status, **counts}


def build_client(base: str = "mainnet"):
    """Public-only Bybit client (no keys, GET /v5/market/* only)."""
    sys.path.insert(0, str(ROOT))
    from bot.bybit_v5 import MAINNET, TESTNET, Bybit

    return Bybit(None, None, base=MAINNET if base == "mainnet" else TESTNET)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prospective paper ledger for the frozen cash-and-carry sleeve (public endpoints only, never places orders).")
    ap.add_argument("--once", action="store_true", help="single pass then exit (hourly loop/CRON mode)")
    ap.add_argument("--equity", type=float, default=5000.0)
    ap.add_argument("--f", type=float, default=0.5, help="fraction of equity per leg per coin")
    ap.add_argument("--tag", default="carry")
    ap.add_argument("--base", choices=("mainnet", "testnet"), default="mainnet")
    ap.add_argument("--interval", type=float, default=3600.0, help="loop interval seconds when --once is off")
    ap.add_argument("--state-dir", default=None, help="override state dir (tests)")
    a = ap.parse_args(argv)
    print(f"carry_paper rule_sha256={rule_sha256()} rule={json.dumps(RULE_PARAMS, sort_keys=True)}", flush=True)
    if not (a.f > 0 and a.f <= 1):
        print("carry_paper: --f must be in (0, 1]", flush=True)
        return 2
    sdir = Path(a.state_dir) if a.state_dir else state_dir_for(a.tag)
    client = build_client(a.base)
    if a.once:
        try:
            res = run_once(client, sdir, float(a.equity), float(a.f), a.tag)
        except Exception as exc:  # noqa: BLE001 - never crash the loop
            print(f"carry_paper tag={a.tag} status=error note={str(exc)[:160]}", flush=True)
            return 0
        print(res.get("summary", res.get("status")), flush=True)
        return 0
    while True:
        try:
            res = run_once(client, sdir, float(a.equity), float(a.f), a.tag)
            print(res.get("summary", res.get("status")), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"carry_paper tag={a.tag} status=error note={str(exc)[:160]}", flush=True)
        time.sleep(float(a.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
