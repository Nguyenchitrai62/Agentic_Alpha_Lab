from bot import mirror
from bot.risk_guard import check

EQ = 10000.0
PX = {"BTCUSDT": 80000.0, "ETHUSDT": 3000.0, "SOLUSDT": 150.0, "BNBUSDT": 600.0, "XRPUSDT": 2.0}


def entry(sym="BTCUSDT", qty=0.02, price=None, meta=None, **kw):
    px = PX[sym] if price is None else price
    m = dict(kind="book") if meta is None else dict(meta)
    m.update(kw.pop("meta_extra", {}))
    return mirror.Order(f"e-{sym}-{qty}-{px}", sym, "Buy", qty, "entry", price=px, meta=m, **kw)


def dip_entry(sym="BTCUSDT", qty=0.02, price=None):
    return entry(sym, qty, price, meta=dict(kind="dip", phase=0))


def reasons(rej):
    return [r["reason"] for r in rej]


def test_normal_book_entry_passes():
    ok, rej = check([entry()], None, EQ, PX)
    assert len(ok) == 1 and rej == []


def test_rejects_non_reduce_only_market():
    o = mirror.Order("m1", "BTCUSDT", "Buy", 0.02, "entry")  # no price/trigger = Market
    ok, rej = check([o], None, EQ, PX)
    assert ok == [] and reasons(rej) == ["market_not_reduce_only"]
    o2 = mirror.Order("m2", "BTCUSDT", "Buy", 0.02, "stop", trigger=80000.0)  # non-R/O stop = Market
    ok2, rej2 = check([o2], None, EQ, PX)
    assert ok2 == [] and reasons(rej2) == ["market_not_reduce_only"]


def test_reduce_only_market_exit_always_allowed():
    o = mirror.Order("x1", "BTCUSDT", "Sell", 5.0, "reduce", reduce_only=True, position_idx=1, piece="p")
    ok, rej = check([o], None, 0.0, {})  # even with zero equity / no prices
    assert ok == [o] and rej == []


def test_protection_never_blocked():
    tp = mirror.Order("t", "BTCUSDT", "Sell", 5.0, "tp", price=1.0, reduce_only=True, piece="p")
    st = mirror.Order("s", "BTCUSDT", "Sell", 5.0, "stop", trigger=1.0, reduce_only=True, piece="p")
    ok, rej = check([tp, st, entry()], None, 1.0, PX)  # tiny equity: entry fails, protection passes
    assert tp in ok and st in ok and rej and all(r["link"] != "t" and r["link"] != "s" for r in rej)


def test_symbol_allowlist():
    bad = entry("DOGEUSDT", 1.0, 0.2)
    ok, rej = check([bad], None, EQ, {"DOGEUSDT": 0.2, **PX})
    assert ok == [] and reasons(rej) == ["symbol_not_allowed"]
    # ... but a reduce-only exit on any symbol is never blocked
    out = mirror.Order("x", "DOGEUSDT", "Sell", 1.0, "reduce", reduce_only=True, piece="p")
    ok2, rej2 = check([out], None, EQ, {})
    assert ok2 == [out] and rej2 == []


def test_fat_finger():
    far = entry("BTCUSDT", 0.02, PX["BTCUSDT"] * 1.20)
    near = entry("BTCUSDT", 0.02, PX["BTCUSDT"] * 1.05)
    ok, rej = check([far, near], None, EQ, PX)
    assert [o.link for o in ok] == [near.link] and reasons(rej) == ["fat_finger"]


def test_fat_finger_boundary():
    at = entry("BTCUSDT", 0.02, PX["BTCUSDT"] * 1.15)
    over = entry("BTCUSDT", 0.02, PX["BTCUSDT"] * 1.1501)
    ok, rej = check([at, over], None, EQ, PX)
    assert [o.link for o in ok] == [at.link] and reasons(rej) == ["fat_finger"]


def test_single_order_cap():
    big = entry("BTCUSDT", 0.2, PX["BTCUSDT"])  # 16000 > 1x equity
    ok, rej = check([big], None, EQ, PX)
    assert ok == [] and reasons(rej) == ["single_order_too_big"]


def test_per_coin_cap():
    pos = {"p1": dict(symbol="BTCUSDT", side=1, qty=0.28, entry=80000.0, kind="book", phase=0)}  # 22400 open
    small = entry("BTCUSDT", 0.02, PX["BTCUSDT"])  # +1600 -> 24000 <= 25000 ok
    big = entry("BTCUSDT", 0.05, PX["BTCUSDT"])  # +4000 -> over 25000
    ok, rej = check([small, big], pos, EQ, PX)
    assert [o.link for o in ok] == [small.link] and reasons(rej) == ["per_coin_cap"]


def test_total_cap():
    pos = {f"p{i}": dict(symbol=s, side=1, qty=10000.0 / PX[s], entry=PX[s], kind="book", phase=0)
           for i, s in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"])}  # 30000 open of 40000 cap
    a = entry("XRPUSDT", 3000.0, PX["XRPUSDT"])  # +6000 -> 36000 ok
    b = entry("BNBUSDT", 10.0, PX["BNBUSDT"])  # +6000 -> 42000 over
    ok, rej = check([a, b], pos, EQ, PX)
    assert [o.link for o in ok] == [a.link] and reasons(rej) == ["total_cap"]


def test_dip_cap_only_counts_dips():
    pos = {"d1": dict(symbol="BTCUSDT", side=1, qty=0.22, entry=80000.0, kind="dip", phase=0)}  # 17600 dip open
    dip = dip_entry("BTCUSDT", 0.02, PX["BTCUSDT"])  # +1600 -> 19200 <= 20000 ok
    dip2 = dip_entry("ETHUSDT", 1.0, PX["ETHUSDT"])  # +3000 -> 22200 over dip cap
    book = entry("ETHUSDT", 1.0, PX["ETHUSDT"])  # same size but book: dip cap must not touch it
    ok, rej = check([dip, dip2, book], pos, EQ, PX)
    assert [o.link for o in ok] == [dip.link, book.link] and reasons(rej) == ["dip_cap"]


def test_sequential_admission():
    a = entry("BTCUSDT", 0.1, PX["BTCUSDT"])  # 8000
    b = entry("BTCUSDT", 0.1, PX["BTCUSDT"])  # +8000 -> 16000 ok
    c = entry("BTCUSDT", 0.12, PX["BTCUSDT"])  # +9600 -> 25600 over per-coin 25000
    ok, rej = check([a, b, c], None, EQ, PX)
    assert [o.link for o in ok] == [a.link, b.link] and reasons(rej) == ["per_coin_cap"]


def test_custom_limits_relax_caps():
    big = entry("BTCUSDT", 0.2, PX["BTCUSDT"])  # 16000 notional
    ok, _ = check([big], None, EQ, PX, limits=dict(single_order=2.0, per_coin_gross=2.5, total_gross=4.0))
    assert len(ok) == 1
    ok2, _ = check([big], None, EQ, PX, limits="nope-im-invalid")  # invalid limits must never raise
    assert ok2 == []


def test_dict_inputs_and_pure():
    orders = {"k1": entry(), "k2": entry("ETHUSDT", 1.0)}
    pos = {"p": dict(symbol="BTCUSDT", side=1, qty=0.01, entry=80000.0, kind="book", phase=0)}
    before = (len(orders), len(pos))
    ok, rej = check(orders, pos, EQ, PX)
    assert len(ok) == 2 and rej == [] and (len(orders), len(pos)) == before


def test_zero_equity_blocks_new_but_not_exits():
    new = entry()
    out = mirror.Order("x", "BTCUSDT", "Sell", 0.01, "reduce", reduce_only=True, piece="p")
    ok, rej = check([new, out], None, 0.0, PX)
    assert ok == [out] and reasons(rej) == ["single_order_too_big"]


def test_bad_order_on_missing_symbol_or_qty():
    o = mirror.Order("z", "BTCUSDT", "Buy", 0.0, "entry", price=80000.0)
    ok, rej = check([o], None, EQ, PX)
    assert ok == [] and reasons(rej) == ["bad_order"]
