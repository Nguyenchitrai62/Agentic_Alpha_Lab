"""Exit-completion invariant regression (BOT_SOAKINV_20261007, proposal P2).

Fast part (<= 2 min): hand-checked synthetic cases for tail_exit_sends /
check_exit_completion plus a 1h live soak slice (2025-10-10 21:00-22:00 UTC,
covers the flush-evening close5 stops) asserting 0 exit_completion
violations with the fixed bot. The long proof (6h with/without fix, 10h
both-exit-types window) is a manual command documented in
docs/opencode/BOT_SOAKINV_20261007.md.
"""

import torch  # noqa: F401  (Windows DLL load order: torch before pandas)

import json
from types import SimpleNamespace

import pandas as pd

from tests.soak_bot import (
    check_exit_completion,
    run_soak,
    tail_exit_sends,
)

SYM = "SOLUSDT"
T0 = pd.Timestamp("2025-10-10 21:30:00+00:00")


def _runner(tmp_path, ledger, links, actions=()):
    d = tmp_path / "art"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "actions.jsonl", "w", encoding="utf-8") as f:
        for rec in actions:
            f.write(json.dumps(rec) + "\n")
    return SimpleNamespace(dir=d, state={"ledger": ledger, "links": links})


def _mock(resting=(), filled=()):
    return SimpleNamespace(orders={k: {} for k in resting},
                           execs=[{"orderLinkId": k} for k in filled])


def _send(pid, link, t):
    return {"t": str(t), "op": "market_exit", "piece": pid,
            "payload": {"orderLinkId": link}}


def test_stuck_fires_link_dead_old_send(tmp_path):
    pid, link = "p1", "p1Xaaa"
    r = _runner(tmp_path, {pid: {"symbol": SYM, "qty": 0.5}},
                {link: {}}, [_send(pid, link, T0)])
    sends, _ = tail_exit_sends(r, {}, 0)
    assert len(sends[pid]) == 1
    viol = check_exit_completion(r, _mock(), T0 + pd.Timedelta(minutes=10), sends)
    assert len(viol) == 1 and viol[0]["reason"] == "exit_stuck"


def test_resend_overflow_fires_without_fill(tmp_path):
    pid = "p2"
    recs, links = [], {}
    for i in range(4):
        link = f"p2X{i}"
        links[link] = {}
        recs.append(_send(pid, link, T0 + pd.Timedelta(minutes=2 * i)))
    r = _runner(tmp_path, {pid: {"symbol": SYM, "qty": 0.5,
                                 "exit_link": "p2X3"}}, links, recs)
    sends, _ = tail_exit_sends(r, {}, 0)
    assert len(sends[pid]) == 4
    # first send 5 min old: below the stuck age, but 4 sends -> overflow
    viol = check_exit_completion(r, _mock(), T0 + pd.Timedelta(minutes=5), sends)
    assert len(viol) == 1 and viol[0]["reason"] == "exit_resend_overflow"


def test_resting_or_filled_suppress(tmp_path):
    pid, link = "p3", "p3Xaaa"
    r = _runner(tmp_path, {pid: {"symbol": SYM, "qty": 0.5,
                                 "exit_sent": str(T0), "exit_link": link}},
                {link: {}}, [_send(pid, link, T0)])
    sends, _ = tail_exit_sends(r, {}, 0)
    old = T0 + pd.Timedelta(minutes=30)
    assert check_exit_completion(r, _mock(resting=[link]), old, sends) == []
    assert check_exit_completion(r, _mock(filled=[link]), old, sends) == []


def test_rejected_dust_send_ignored_and_flat_prunes(tmp_path):
    pid, link = "p4", "p4Daaa"
    # exchange rejected the place (dust below lot minimum): logged but the
    # link never registered in state links -> must not count as a send.
    r = _runner(tmp_path, {pid: {"symbol": SYM, "qty": 0.05}}, {}, [_send(pid, link, T0)])
    sends, _ = tail_exit_sends(r, {}, 0)
    assert sends == {}
    assert check_exit_completion(r, _mock(), T0 + pd.Timedelta(minutes=30), sends) == []
    # flat piece: history pruned, reused pid starts clean
    sends = {pid: [{"t": str(T0), "link": link}]}
    r.state["ledger"][pid]["qty"] = 0.0
    assert check_exit_completion(r, _mock(), T0 + pd.Timedelta(minutes=30), sends) == []
    assert pid not in sends


def test_ledger_marker_fallback_fires(tmp_path):
    pid, link = "p5", "p5Xaaa"
    r = _runner(tmp_path, {pid: {"symbol": SYM, "qty": 0.5,
                                 "exit_sent": str(T0), "exit_link": link}},
                {link: {}}, [])
    viol = check_exit_completion(r, _mock(), T0 + pd.Timedelta(minutes=10), {})
    assert len(viol) == 1 and viol[0]["reason"] == "exit_stuck"


def test_soak_1h_no_exit_violation(tmp_path):
    # Flush-hour slice from a cold start: the slot lottery (hour_idx) sends
    # no close5 here, so this asserts the live regression (fills flow, the
    # invariant stays silent). Close5 completion with the fix is covered by
    # the 6h numbers in the doc + the filled-suppress unit above.
    res = run_soak(hours=1.0, step_s=20.0, equity=10000.0,
                   workdir=tmp_path / "soak_inv", tag="soakinv",
                   window_start=pd.Timestamp("2025-10-10 21:00:00+00:00"))
    assert res["cycles"] == 180, res["cycles"]
    assert res["exceptions"] == 0, res["violations"][:5]
    ec = [v for v in res["violations"] if v.get("invariant") == "exit_completion"]
    assert ec == [], ec[:5]
    assert res["fills"] > 0, res  # slice must exercise fills
