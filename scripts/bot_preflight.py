"""Read-only preflight the account owner runs before testnet/live (`TESTNET_REVIEW_20261006.md` V1-V2).

Usage:
    .venv\\Scripts\\python.exe scripts/bot_preflight.py --mode testnet
    .venv\\Scripts\\python.exe scripts/bot_preflight.py --mode live

Loads keys the same way bot/run.py does (never prints them), then checks via
READ-ONLY V5 endpoints only (signed GET + public; never POST, so it can never
place, amend or cancel orders, nor change hedge/leverage/margin settings):

  1. API key + permissions .... GET /v5/user/query-api (fallback: wallet-balance proves signing works)
  2. Unified account .......... GET /v5/account/wallet-balance?accountType=UNIFIED (same call the bot uses)
  3. Hedge Mode per coin ...... GET /v5/position/list (positionIdx 1/2 = hedge, 0 = one-way)
  4. Cross margin .............. GET /v5/position/list (tradeMode 0 = cross, 1 = isolated)
  5. Leverage 5x per coin ..... GET /v5/position/list (leverage field)
  6. Equity .................... 5000 USDT minimum (warn), 10000 comfortable
  7. Foreign orders/positions . GET /v5/order/realtime + positions (bot links match ^[bd]<phase><BTC|ETH|SOL|BNB|XRP>)
  8. Server time skew < 1 s ... GET /v5/market/time (public)
  9. Instruments minima ........ GET /v5/market/instruments-info + deployment sizes (dip_mult 1.7, runbook R2B1D17BF)

Prints a Vietnamese PASS/WARN/FAIL checklist with the exact Bybit UI step for
each FAIL. Exit code 0 only if no FAIL (WARNs still exit 0).

Safety: this module never imports or calls any POST endpoint. Tests assert no
POST /v5/order/* or /v5/position/switch-mode call is ever made (mock calls log).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.bybit_v5 import Bybit, BybitError, MAINNET, TESTNET  # noqa: E402
from bot.run import PLAN as DEFAULT_PLAN, SYMS, env  # noqa: E402

MIN_EQUITY = 5000.0      # runbook: minimum (below -> BTC rungs skip)
COMFORT_EQUITY = 10000.0  # runbook: comfortable level
EXPECTED_LEVERAGE = 5.0  # runbook: 5x on each of the five majors
SKEW_LIMIT_S = 1.0       # signing breaks when local clock drifts
DEPLOY_DIP_MULT = 1.7    # recommended pipeline flag --dip-mult 1.7 (runbook R2B1D17BF)

# Bot-owned orderLinkIds: book_pid b<phase><ROOT><t36>, dip_pid d<phase><ROOT><rung10><t36>
# (mirror.book_pid/dip_pid); exits reuse the pid (...+T/S/E, pid+X../U..).
BOT_LINK_RE = re.compile(r"^[bd]\d(BTC|ETH|SOL|BNB|XRP)")

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _short(msg: object, n: int = 160) -> str:
    try:
        s = str(msg)
    except Exception:
        s = "unknown error"
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "..."


def _is_auth_error(e: Exception) -> bool:
    m = _short(e)
    return any(c in m for c in ("10003", "10004", "10005", "401", "auth", "api key", "API key", "invalid"))


# ---- read-only probes (signed GET / public only; no POST anywhere) -----------------


def fetch_api_info(client: Bybit) -> dict:
    """GET /v5/user/query-api (read-only): key metadata + permission list."""
    res = client.get("/v5/user/query-api")
    if not isinstance(res, dict):
        raise BybitError("10001: unexpected query-api response")
    return res


def fetch_positions(client: Bybit, symbol: str) -> list:
    """GET /v5/position/list (read-only) for one symbol; client-side filtered."""
    res = client.get("/v5/position/list", category="linear", symbol=symbol)
    rows = res.get("list", []) if isinstance(res, dict) else []
    return [p for p in rows if isinstance(p, dict) and p.get("symbol") == symbol]


def fetch_server_time_ms(client: Bybit) -> int:
    """GET /v5/market/time (public): Bybit server time in ms."""
    res = client.public("/v5/market/time")
    if not isinstance(res, dict):
        raise BybitError("10001: unexpected server-time response")
    if res.get("timeNano") is not None:
        return int(float(res["timeNano"]) // 1_000_000)
    if res.get("timeSecond") is not None:
        return int(float(res["timeSecond"]) * 1000)
    raise BybitError("10001: server-time fields missing")


def _leverage_of(pos: dict):
    for k in ("leverage", "buyLeverage", "sellLeverage"):
        try:
            v = pos.get(k)
            if v is not None and float(v) > 0:
                return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _check_leverage_row(positions: dict) -> tuple:
    """(status, detail, fix) for the 5x-per-coin expectation from position/list rows."""
    per_coin: dict = {}
    for sym in SYMS:
        levs = [_leverage_of(p) for p in positions.get(sym, [])]
        levs = [v for v in levs if v is not None]
        per_coin[sym] = levs
    if not any(per_coin.values()):
        return (WARN, "không đọc được đòn bẩy hiện tại qua API (tài khoản chưa có vị thế hoặc API không trả trường leverage) — "
                "tự kiểm tra trên UI: mỗi coin BTC/ETH/SOL/BNB/XRP phải là 5x.", None)
    bad = {s: v[0] for s, v in per_coin.items() if v and abs(v[0] - EXPECTED_LEVERAGE) > 1e-9}
    if bad:
        txt = ", ".join(f"{s}={v:g}x" for s, v in sorted(bad.items()))
        return (FAIL, f"đòn bẩy sai kỳ vọng 5x: {txt}. Đòn bẩy thấp làm bot thiếu margin chặn lệnh.",
                "Trên Bybit (testnet.bybit.com hoặc bybit.com): mở lệnh BTCUSDT Perps → ô Cross/đòn bẩy "
                "(cạnh nút Cross) → bấm vào số đòn bẩy → nhập 5 → Confirm; lặp lại cho ETH, SOL, BNB, XRP. "
                "KHÔNG hạ đòn bẩy khi đang có vị thế.")
    unknown = sorted(s for s, v in per_coin.items() if not v)
    extra = f" (chưa rõ {','.join(unknown)} — kiểm tra tay)" if unknown else ""
    return (PASS, f"đòn bẩy 5x đúng trên các coin có vị thế{extra}.", None)


def _check_margin_row(positions: dict) -> tuple:
    """(status, detail, fix) for Cross (tradeMode 0) from position/list rows."""
    modes = {}
    for sym in SYMS:
        for p in positions.get(sym, []):
            try:
                if float(p.get("size", 0) or 0) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
            tm = p.get("tradeMode")
            if tm is not None:
                try:
                    modes[sym] = int(float(tm))
                except (TypeError, ValueError):
                    continue
    if not modes:
        return (WARN, "không đọc được margin mode qua API (chưa có vị thế hoặc API không trả trường tradeMode) — "
                "tự kiểm tra trên UI: tài khoản phải là Cross margin (không dùng Isolated cho bot).", None)
    bad = sorted(s for s, m in modes.items() if m != 0)
    if bad:
        return (FAIL, f"các coin đang Isolated (cần Cross): {','.join(bad)}.",
                "Trên Bybit: mở cửa sổ đặt lệnh từng coin → chuyển Isolated sang Cross "
                "(ô Cross/Isolated cạnh đòn bẩy). Lưu ý Bybit không cho đổi margin khi đang có vị thế — "
                "đóng vị thế testnet trước rồi đổi.")
    return (PASS, "margin mode Cross đúng trên các coin có vị thế.", None)


def _check_hedge_row(positions: dict) -> tuple:
    """(status, detail, fix) for Hedge Mode from positionIdx (0 = one-way -> FAIL)."""
    have_any = any(positions.get(s) for s in SYMS)
    oneway = sorted({s for s in SYMS for p in positions.get(s, [])
                     if str(p.get("positionIdx")) == "0"})
    if oneway:
        return (FAIL, f"tài khoản đang One-Way (positionIdx=0) trên {','.join(oneway)} — bot gửi positionIdx 1/2 nên lệnh sẽ bị từ chối.",
                "Trên Bybit: mở chart BTCUSDT Perps → góc trên gần ô Cross/đòn bẩy → Position Mode "
                "→ chọn Hedge Mode / Both long & short positions → Confirm (áp dụng cho USDT Perps).")
    if not have_any:
        return (WARN, "chưa có vị thế nên không xác minh được Hedge qua API — "
                "tự kiểm tra trên UI: Position Mode phải là Hedge Mode (bot chỉ tự gọi một lần và bỏ qua lỗi).", None)
    return (PASS, "Hedge Mode (positionIdx 1/2, không có vị thế One-Way).", None)


def _deployment_sizes(plan: dict, equity: float) -> dict:
    """Per-coin candidate new-order qtys at current equity (deployment sizing, window-independent).

    book: weight x equity / price (pending orders; fallback: open position weight/avg_entry as proxy).
    dip: size_frac x equity x DEPLOY_DIP_MULT / buy_limit (shallowest-first, corr only shrinks -> use 1.0).
    Returns {symbol: [(kind, qty, price)]}.
    """
    from bot.mirror import Order  # local import: mirror is pure logic, no I/O

    out: dict = {}
    for sym, c in (plan.get("coins") or {}).items():
        if sym not in SYMS:
            continue
        cands = []
        for sub in c.get("subs", []) or []:
            o = sub.get("order") or {}
            pos = sub.get("position") or {}
            if sub.get("state") == "pending" and o.get("kind") == "open":
                try:
                    w, px = float(o["weight"]), float(o["price"])
                    side = "Buy" if str(o.get("side", "BUY")).upper() == "BUY" else "Sell"
                    if w > 0 and px > 0:
                        cands.append(("book", Order("tmp", sym, side, w * equity / px, "entry", price=px)))
                except (TypeError, ValueError):
                    continue
            elif sub.get("state") == "position" and pos:
                try:
                    w, px = float(pos.get("weight", 0) or 0), float(pos.get("avg_entry", 0) or 0)
                    if w > 0 and px > 0:
                        cands.append(("book", Order("tmp", sym, "Buy", w * equity / px, "entry", price=px)))
                except (TypeError, ValueError):
                    continue
        for d in c.get("dips", []) or []:
            try:
                frac, lv = float(d.get("size_frac", 0) or 0), float(d.get("buy_limit", 0) or 0)
                if frac > 0 and lv > 0:
                    cands.append(("dip", Order("tmp", sym, "Buy", frac * equity * DEPLOY_DIP_MULT / lv,
                                              "entry", price=lv, meta=dict(kind="dip"))))
            except (TypeError, ValueError):
                continue
        if cands:
            out[sym] = cands
    return out


def _check_minima_row(client: Bybit, plan: dict | None, equity: float) -> tuple:
    """Instruments minima vs deployment sizes at current equity (WARN-only row)."""
    from bot.run import to_exchange  # same rounding/minimum rule the runner uses

    try:
        inst = client.instruments(SYMS)
    except (BybitError, OSError) as e:
        return (WARN, f"không đọc được instruments-info ({_short(e)}) — kiểm tra tay minima.", None)
    if plan is None:
        return (WARN, "không đọc được trade plan nên chưa đối chiếu minima — kiểm tra tay khi vốn < 5000.", None)
    sizes = _deployment_sizes(plan, equity)
    if not sizes:
        return (WARN, "plan không có lệnh book/dip nào để đối chiếu minima.", None)
    below: dict = {}
    for sym, cands in sizes.items():
        if sym not in inst:
            continue
        for kind, o in cands:
            if to_exchange(o, inst) is None:
                below.setdefault(sym, set()).add(kind)
    if below:
        txt = ", ".join(f"{s} ({'/'.join(sorted(k))})" for s, k in sorted(below.items()))
        return (WARN, f"vốn hiện tại làm lệnh dưới minima Bybit (bot sẽ skip, không phải lỗi): {txt}. "
                f"Nạp thêm về ~10000 USDT hoặc bỏ qua các rung nhỏ.", None)
    return (PASS, "mọi cỡ lệnh book/dip ước tính đều trên minima Bybit ở vốn hiện tại.", None)


def run_preflight(client: Bybit, plan: dict | None) -> tuple[list, int]:
    """Run all read-only checks. Returns (rows, exit_code); rows are (name, status, detail, fix)."""
    rows: list = []

    # 0. network sanity (public, no keys involved)
    try:
        client.public("/v5/market/instruments-info", category="linear", symbol="BTCUSDT")
    except OSError as e:
        rows.append(("Mạng", FAIL, f"không kết nối được Bybit ({_short(e)}) — kiểm tra mạng/VPN rồi chạy lại.", None))
        return rows, 1
    except BybitError:
        pass  # public validation error still proves the network path works

    # 1. API key + permissions (read-only info endpoint; fallback proves signing works)
    equity: float | None = None
    try:
        info = fetch_api_info(client)
        ro = info.get("readOnly", 0)
        try:
            ro = int(ro)
        except (TypeError, ValueError):
            ro = 1 if ro else 0
        perms = info.get("permissions") or {}
        ct = perms.get("ContractTrade") or []
        if ro:
            rows.append(("API key", FAIL, "key đang ở chế độ Read-Only — bot cần key Read-Write để đặt/hủy lệnh.",
                         _fix_key()))
        elif perms and "Order" not in [str(x) for x in ct]:
            rows.append(("API key", FAIL, f"key thiếu quyền đặt lệnh Contracts (ContractTrade={ct}).", _fix_key()))
        else:
            extra = f" ContractTrade={ct}" if perms else ""
            rows.append(("API key", PASS, f"key hợp lệ, đủ quyền trade.{extra}", None))
    except BybitError as e:
        if _is_auth_error(e):
            rows.append(("API key", FAIL, f"key không hợp lệ/hết hạn ({_short(e)}).", _fix_key()))
            return rows, 1
        try:
            client.get("/v5/account/wallet-balance", accountType="UNIFIED")
            rows.append(("API key", WARN, "key ký được nhưng không đọc được quyền qua query-api — "
                         "tự kiểm tra trên UI: key phải là Read-Write + có quyền Contracts.", None))
        except BybitError as e2:
            if _is_auth_error(e2):
                rows.append(("API key", FAIL, f"key không hợp lệ/hết hạn ({_short(e2)}).", _fix_key()))
                return rows, 1
            rows.append(("API key", WARN, f"không xác minh được key/quyền ({_short(e2)}) — kiểm tra tay.", None))
        except OSError as e2:
            rows.append(("API key", FAIL, f"mất kết nối khi xác minh key ({_short(e2)}).", None))
            return rows, 1
    except OSError as e:
        rows.append(("API key", FAIL, f"mất kết nối khi xác minh key ({_short(e)}).", None))
        return rows, 1

    # 2. unified account + equity (same call the bot uses)
    try:
        acc = client.get("/v5/account/wallet-balance", accountType="UNIFIED")
        lst = acc.get("list", [{}]) if isinstance(acc, dict) else [{}]
        equity = float((lst[0] if lst else {}).get("totalEquity", 0) or 0)
        rows.append(("Tài khoản", PASS, "tài khoản Unified (đọc được wallet-balance UNIFIED).", None))
    except BybitError as e:
        rows.append(("Tài khoản", FAIL, f"không đọc được số dư UNIFIED ({_short(e)}) — "
                     "có thể tài khoản còn là Classic.",
                     "Trên Bybit: avatar → ... → Upgrade to Unified Trading Account "
                     "(bot chỉ chạy trên Unified; xem lại mục Vốn/margin trong runbook)."))
        equity = 0.0
    except OSError as e:
        rows.append(("Tài khoản", FAIL, f"mất kết nối khi đọc số dư ({_short(e)}).", None))
        equity = 0.0

    # 3-5. position mode / margin mode / leverage (one read-only endpoint)
    positions: dict = {s: [] for s in SYMS}
    try:
        for s in SYMS:
            positions[s] = fetch_positions(client, s)
    except (BybitError, OSError) as e:
        rows.append(("Vị thế/mode", WARN, f"không đọc được position/list ({_short(e)}) — kiểm tra Hedge/Cross/5x tay.", None))
        positions = {s: [] for s in SYMS}
    st, dt, fx = _check_hedge_row(positions)
    rows.append(("Hedge Mode", st, dt, fx))
    st, dt, fx = _check_margin_row(positions)
    rows.append(("Cross margin", st, dt, fx))
    st, dt, fx = _check_leverage_row(positions)
    rows.append(("Đòn bẩy 5x", st, dt, fx))

    # 6. equity thresholds (WARN only)
    eq = equity or 0.0
    if eq >= COMFORT_EQUITY:
        rows.append(("Vốn", PASS, f"equity {eq:,.0f} USDT (>= {COMFORT_EQUITY:,.0f} thoải mái).", None))
    elif eq >= MIN_EQUITY:
        rows.append(("Vốn", WARN, f"equity {eq:,.0f} USDT dưới mức thoải mái {COMFORT_EQUITY:,.0f} "
                     "(vẫn trên tối thiểu 5000; theo dõi skipped_below_minimum).", None))
    else:
        rows.append(("Vốn", WARN, f"equity {eq:,.0f} USDT dưới tối thiểu {MIN_EQUITY:,.0f} — "
                     "các rung BTC sẽ bị skip (bình thường, không phải lỗi); nạp thêm trước khi đánh giá.", None))

    # 7. foreign orders / open positions (WARN only)
    try:
        orders = client.open_orders()
        foreign = [o for o in orders if isinstance(o, dict) and o.get("symbol") in SYMS
                   and not BOT_LINK_RE.match(str(o.get("orderLinkId") or ""))]
        held = sorted({s for s in SYMS for p in positions.get(s, [])
                       if _pos_size(p) > 0})
        if not foreign and not held:
            rows.append(("Lệnh/vị thế lạ", PASS, "không có lệnh chờ hay vị thế mở trên 5 coin majors.", None))
        else:
            bits = []
            if foreign:
                bits.append("lệnh lạ: " + ", ".join(
                    f"{o.get('symbol')}:{o.get('orderLinkId')}" for o in foreign[:10]))
            if held:
                bits.append("vị thế đang mở (chưa rõ của bot hay tay): " + ",".join(held)
                            + " — đối chiếu state.json/actions.jsonl trước khi chạy")
            rows.append(("Lệnh/vị thế lạ", WARN, "; ".join(bits)
                         + " — bot sẽ nhận nhầm nếu trùng symbol; dọn hoặc xác nhận chủ trước.", None))
    except (BybitError, OSError) as e:
        rows.append(("Lệnh/vị thế lạ", WARN, f"không đọc được open orders ({_short(e)}) — kiểm tra tay.", None))

    # 8. server time skew (FAIL at >= 1 s: ký request sẽ lệch, lệnh dễ bị từ chối)
    try:
        server_ms = fetch_server_time_ms(client)
        skew = abs(time.time() * 1000 - server_ms) / 1000.0
        if skew < SKEW_LIMIT_S:
            rows.append(("Giờ server", PASS, f"chênh lệch {skew:.2f}s (< 1s).", None))
        else:
            rows.append(("Giờ server", FAIL, f"chênh lệch {skew:.2f}s (>= 1s) — request ký sẽ lệch giờ, dễ bị từ chối.",
                         "Trên Windows: Settings → Time & language → Date & time → bật Set time automatically "
                         "và bấm Sync now (đồng bộ NTP); chạy lại preflight."))
    except (BybitError, OSError, ValueError, TypeError) as e:
        rows.append(("Giờ server", WARN, f"không xác minh được giờ server ({_short(e)}) — đồng bộ NTP tay.", None))

    # 9. instruments minima at current equity (WARN only)
    st, dt, fx = _check_minima_row(client, plan, eq)
    rows.append(("Minima sàn", st, dt, fx))

    code = 0 if all(r[1] != FAIL for r in rows) else 1
    return rows, code


def _pos_size(p: dict) -> float:
    try:
        return float(p.get("size", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _fix_key() -> str:
    return ("Tạo key mới: testnet.bybit.com (testnet) hoặc bybit.com (live) → API Management → Create New Key "
            "(quyền Read-Write, bật Contracts/Derivatives) → chỉ điền BYBIT_TESTNET_API_KEY/_SECRET (testnet) "
            "hoặc BYBIT_API_KEY/_SECRET (live) vào file .env local, không commit/không dán chat.")


def _load_plan(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _build_client(mode: str) -> Bybit:
    if mode == "testnet":
        key, sec = env("BYBIT_TESTNET_API_KEY"), env("BYBIT_TESTNET_API_SECRET")
        if not (key and sec):
            sys.exit("thiếu BYBIT_TESTNET_API_KEY/_SECRET trong .env (xem runbook mục V2).")
        return Bybit(key, sec, base=TESTNET)
    key, sec = env("BYBIT_API_KEY"), env("BYBIT_API_SECRET")
    if not (key and sec):
        sys.exit("thiếu BYBIT_API_KEY/_SECRET trong .env (chỉ chủ tài khoản chạy live).")
    return Bybit(key, sec, base=MAINNET)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only preflight cho bot Bybit (không đặt/hủy lệnh, không đổi settings).")
    ap.add_argument("--mode", choices=("testnet", "live"), required=True)
    ap.add_argument("--plan", default=str(DEFAULT_PLAN), help="trade plan dùng để ước tính minima")
    a = ap.parse_args(argv)
    client = _build_client(a.mode)
    plan = _load_plan(Path(a.plan))
    if plan is None:
        print(f"WARN: không đọc được plan {a.plan} — bỏ qua đối chiếu minima.", flush=True)
    rows, code = run_preflight(client, plan)
    print(f"BOT PREFLIGHT -- mode={a.mode}", flush=True)
    for name, st, detail, fix in rows:
        print(f"[{st}] {name}: {detail}", flush=True)
        if st == FAIL and fix:
            print(f"  Sửa (Bybit UI): {fix}", flush=True)
    print(("KẾT QUẢ: PASS — đủ điều kiện chạy thử." if code == 0
           else "KẾT QUẢ: FAIL — sửa các mục FAIL ở trên rồi chạy lại. Không khởi động bot."), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
