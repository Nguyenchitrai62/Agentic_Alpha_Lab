"""SYSTEM AUDIT 2 tests: synthetic leak-flag check + truncation helper on a synthetic series."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/diagnostics/system_audit/leak_opencode"))
from leak_checks import leak_flags, spearman, truncate_compare


def test_leaky_book_flagged():
    n = 500
    r_hold = pd.Series([0.001 * ((i % 7) - 3) for i in range(n)])
    r_next = pd.Series([0.001 * (((i * 13) % 11) - 5) for i in range(n)])
    book = r_hold.copy()  # equals the holding-bar return -> must be flagged
    ch = spearman(book, r_hold)
    cn = spearman(book, r_next)
    fl = leak_flags(ch, cn)
    assert ch > 0.99
    assert fl["flag_any"]


def test_random_book_not_flagged():
    import numpy as np
    rng = np.random.default_rng(0)
    n = 2000
    book = pd.Series(rng.normal(size=n))
    r_hold = pd.Series(rng.normal(size=n))
    r_next = pd.Series(rng.normal(size=n))
    ch = spearman(book, r_hold)
    cn = spearman(book, r_next)
    fl = leak_flags(ch, cn)
    assert abs(ch) < 0.10
    assert not fl["flag_any"]


def test_truncate_helper_synthetic():
    # causal rolling mean: full vs truncated-at-T must match at row T
    s = pd.Series(range(100), dtype=float)
    full = s.rolling(6).mean().to_frame("a")
    trunc = s.iloc[:50].rolling(6).mean().to_frame("a")
    ok, bad, _ = truncate_compare(full.iloc[[49]], trunc.iloc[[-1]])
    assert ok and bad == []
    # leaky future mean must mismatch
    leaky_full = s.shift(-1).rolling(6).mean().to_frame("a")
    ok2, bad2, _ = truncate_compare(leaky_full.iloc[[49]], trunc.iloc[[-1]])
    assert not ok2 and bad2 == ["a"]
