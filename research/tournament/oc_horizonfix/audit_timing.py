"""oc_horizonfix Task 1: code-cited timing audit of row index t.

Read-only: prints exact source lines proving what t means in
(a) preds_*.csv files, (b) member caches / blended book rows.
No outcomes computed here.
"""
from pathlib import Path

ROOT = Path(__file__).parents[3]


def show(path_rel, lo, hi):
    p = ROOT / path_rel
    lines = p.read_text().splitlines()
    print(f"\n=== {path_rel} lines {lo}-{hi} ===")
    for i in range(lo - 1, min(hi, len(lines))):
        print(f"{i+1:4d}: {lines[i]}")


def main():
    print("TASK 1(a): preds_*.csv row meaning")
    # presamplebook: bar construction on standard grid, open_time = bar OPEN
    show("research/tournament/oc_presamplebook/presamplebook.py", 65, 85)
    # TV features causal incl. bar t close
    show("research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py", 1, 6)
    show("research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py", 127, 129)
    # label + r_next use NEXT bar opens
    show("research/tournament/oc_presamplebook/presamplebook.py", 96, 108)
    show("research/tournament/oc_presamplebook/presamplebook.py", 121, 130)
    # test rows indexed by open_time (= bar open)
    show("research/tournament/oc_presamplebook/presamplebook.py", 186, 192)
    # presampleflow: same bar + flow/premium causal incl. bar t
    show("research/tournament/oc_presampleflow/presampleflow.py", 131, 144)
    show("research/parallel/rounds/parallel-20260906-r2/v236/flow_features.py", 1, 6)
    show("research/parallel/rounds/parallel-20260906-r2/v111/v111_coinbase_premium.py", 1, 6)
    # old yardstick in presampleshort: open[t+h]/open[t]
    show("research/tournament/oc_presampleshort/compute_presampleshort.py", 270, 282)

    print("\nTASK 1(b): member cache / blended book row meaning")
    show("research/parallel/rounds/parallel-20260906-r2/v103/v103_flow_short_horizon.py", 1, 13)
    show("research/parallel/rounds/parallel-20260906-r2/v103/v103_flow_short_horizon.py", 68, 84)
    show("research/parallel/rounds/parallel-20260906-r2/v144/v144_deploy_v3.py", 76, 83)
    show("scripts/forward_v205.py", 82, 90)
    show("research/tournament/oc_bookichorizon/compute_bookichorizon.py", 65, 82)

    print("\n--- CONCLUSIONS (pre-registered) ---")
    print("(a) preds open_time T = bar OPEN timestamp (00/04/08/12/16/20 UTC).")
    print("    Features at row T use bars 0..T INCLUDING close[T]")
    print("    (tv_features docstring; flow archive row known at close;")
    print("    premium known at bar close T+4h).")
    print("    Label fwd=log(o[T+1+H]/o[T+1]) and r_next=o[T+2]/o[T+1]-1 prove")
    print("    the executable base is the NEXT bar open.")
    print("    => prediction at T becomes available at T+4h (close of bar T).")
    print("(b) Member cache row at T (= v92/v103 panel t = b open_time) likewise")
    print("    uses bars closed at T; engine earns r_next=o[T+2]/o[T+1]-1")
    print("    (books.shift(2) in v144.simulate; v154_books/opens_v154 same grid).")
    print("    research_books_d2 only reindexes/fillna-blends (no time shift).")
    print("    => book row at T is the decision available at T's close,")
    print("    i.e. the decision made at the close of the bar OPENING at T.")
    print("    Old yardstick open[T+h]/open[T] from base open[T] therefore")
    print("    includes bar T's own move open[T]->open[T+1] (length 1 bar),")
    print("    already known at availability: contemporaneous leak in YARDSTICK.")
    print("    Corrected t_trade = T+4h (first bar open at/after availability).")


if __name__ == "__main__":
    main()
