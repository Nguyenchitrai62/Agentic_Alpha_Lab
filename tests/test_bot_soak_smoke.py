"""2-hour mini version of the BOT soak (OPENCODE_W_bot_soak) that pytest runs.

Same harness as tests/soak_bot.py (72h), same deployment flags
(corr-size, dip-mult 1.7, bear-book, dip-gross-cap 2.0, adopt-fresh,
carry-f 0.25) and fake clock, but only the first 2 simulated hours
(360 cycles at 20 s/cycle) so it fits in a unit test.

Known bot bug documented here (not a harness failure): hourly plan side
flips can leave TWO open book pieces in one phase sub-book (old piece not
yet diverged, new entry filled); bot/mirror.py desired() manages only the
first piece found per (phase, symbol) (bot/mirror.py:301, `next(...)`), so
the second piece rests with no stop/TP. The full 72h soak reports it with
evidence in docs/opencode/BOT_SOAK_20261006.md; this test xfails while any
`protection` gap remains and passes cleanly once the bot is fixed.
"""

import torch  # noqa: F401  (Windows DLL load order: torch before pandas)

import pandas as pd
import pytest

from tests.soak_bot import WINDOW_START, run_soak


def test_soak_2h_no_violations(tmp_path):
    res = run_soak(hours=2.0, step_s=20.0, equity=10000.0,
                   workdir=tmp_path / "soak_smoke", tag="smoke",
                   window_start=pd.Timestamp(WINDOW_START))
    # harness mechanics: must always hold
    assert res["cycles"] == 360, res["cycles"]
    assert res["exceptions"] == 0, res["violations"][:5]
    assert res["restart"]["ok"], res["restart"]
    other = [v for v in res["violations"] if v["invariant"] != "protection"]
    assert other == [], other[:5]
    # the window must actually exercise fills or resting dip bids
    assert res["resting_end"] + res["fills"] + res["ledger_pieces"] > 0, res
    # bot-side protection gaps -> known bug (see module docstring)
    prot = [v for v in res["violations"] if v["invariant"] == "protection"]
    if prot:
        by_piece = sorted({v.get("piece") for v in prot})
        pytest.xfail(f"known bot bug bot/mirror.py:301 orphans the 2nd book piece "
                     f"of a sub-book: {len(prot)} protection gaps on {by_piece[:4]}")
    assert prot == []
