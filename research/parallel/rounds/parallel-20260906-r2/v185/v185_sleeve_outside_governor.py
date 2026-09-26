"""v185: v183 with the dip sleeve sized outside the drawdown governor (registry v185).

EX POST CONTEXT: after v171-v184 on the same span; hypothesis-grade.
Why: the v110 governor g shrinks everything after drawdowns; drawdown periods are the crash-heavy periods where the
sleeve's rebounds happen, and the sleeve already has its own tail control (open notional <= 1/6 equity at every
minute, independent of g). The governor is meant for the books' drawdown. Definitional change, no new parameter:
rung notional rn = s * 0.25/4 / 1.657 (was s * g * ...). Everything else exactly v183 (books, carry and governor on the
books unchanged; the governor still reads the total equity including the sleeve). Rows normal and stress; gate DD =
max(4h, 1m-marked). Reference v183 4.284 / 19.01 (stress 3.882 / 19.13).

  python research/parallel/rounds/parallel-20260906-r2/v185/v185_sleeve_outside_governor.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v183 = _load("v183", HERE.parent / "v183/v183_tp_exit_open_budget.py")
diag, v172, v171, v170, er = v183.diag, v183.v172, v183.v171, v183.v170, v183.er


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    # sleeve outside the governor: run v183's loop with g applied to the books only
    src = Path(v183.__file__).read_text(encoding="utf-8")
    assert "rn = s[i] * g[i] * v171.SIZE / nr / v176.S_REF" in src
    ns = {"__file__": v183.__file__, "__name__": "v183_sleeve_outside_g"}
    exec(compile(src.replace("rn = s[i] * g[i] * v171.SIZE / nr / v176.S_REF", "rn = s[i] * v171.SIZE / nr / v176.S_REF")
                 .replace('if __name__ == "__main__":\n    main()', ""), v183.__file__, "exec"), ns)
    out = {"version": "v185", "reference_v183": {"normal": (4.284, 19.01), "stress": (3.882, 19.13)}}
    for key, maker, taker, extra, ex in (("primary_normal", 0.0002, 0.0005, 0.0, ex60),
                                         ("stress", 0.0004, 0.0007, 0.0005, diag.stress_exec(idx, cols))):
        t = ns["rung_table_tp"](G, cols, A, maker, taker, extra)
        r = ns["run"](books, dict(base, exec=ex), A["close"], G, *t)
        out[key] = r
        print(key, r["monthly_pct"], "4hDD", r["full_path_dd"], "1mDD", r["dd_1m_mark"], r["dd_1m_worst_bar"], "gateDD", r["gate_dd"],
              "rungs", r["rungs_taken"], "tp", r["tp_exits"], "cancelled", r["rungs_cancelled"],
              [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v185_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
