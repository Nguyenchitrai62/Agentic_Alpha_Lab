# M4 (v362 S5T10 = M3 with book SL 5 / TP 10 sigma_d) vs M3 robustness (kpack inputs; 5y / most recent year / gate DD; no losing year anywhere)
- base:           M3 5.925 / 4.704 / 17.73   M4 6.120 / 5.040 / 16.96
- cost stress (maker 0.0004, taker 0.0012; engine globals patched): M3 5.242 / 4.105 / 18.74   M4 5.422 / 4.461 / 17.86
- latency 30 min: M3 5.208 / 4.498 / 19.44   M4 5.356 / 4.903 / 18.55
- skip the 03:00 VN bar (15-min latency elsewhere): M4 5.279 / 5.039 / 16.64
Reading: M4 >= M3 on every row with lower DD; the gain is small and v362's fold transfer was not confirmed -> extra paper pipeline, not a replacement.
Note: earlier kpack runs that set eu.MAKER / eu.TAKER on the fake namespace did not change the packed engine's fees (only its module globals do).
