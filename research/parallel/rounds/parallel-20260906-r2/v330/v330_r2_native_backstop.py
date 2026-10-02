"""v330: BOT R2 - a closer exchange-native backstop to make R2 robust to a bot outage (registry v330; robustness design, dev years only).

R2 robustness (research/diagnostics/r2_robustness): R2 beats G2 on return in every stress row but its drawdown breaches 20% when the bot is down
(only the native 8-sigma touch stop protects the dip rungs: dev DD 22.15) - the 5-sigma rung makes the outage tail worse. The native backstop is the
one protection that works without the bot. Rows (fixed before running; R2 otherwise unchanged, bar-open lookup hooks):
  backstop 8 (R2) / 6 sigma below the rung level (the v306 gene values), each in NORMAL operation (close5 stop 4 sigma + backstop) and in OUTAGE (native touch stop only
  at the backstop level: sleeve_stop_mode touch, m_sleeve_sl = backstop).
CHOICE (dev years only): the closest backstop whose NORMAL dev4 >= R2's - 0.15 and NORMAL worst dev year >= R2's - 0.15; among those the lowest OUTAGE
dev DD. Adopted only if its outage dev DD <= 20. The most recent year is computed once for the adopted row (R2's 5.655 known).

  python research/parallel/rounds/parallel-20260906-r2/v330/v330_r2_native_backstop.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v306 = _load("v306_bs", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    eu = v306.W["eu"]
    sim0 = eu.simulate
    rows = {}
    for bs in (8.0, 6.0):
        for mode in ("normal", "outage"):
            def sim(*a, **kw):
                if mode == "outage":
                    kw["sleeve_stop_mode"], kw["m_sleeve_sl"], kw["sleeve_backstop"] = "touch", bs, None
                return sim0(*a, **kw)
            eu.simulate = sim
            try:
                d = dict(v306.SEEDS["R2"], backstop=bs) if bs != 8.0 else v306.SEEDS["R2"]
                r = v306.run_genome(v306.encode(d))
            finally:
                eu.simulate = sim0
            m = v306.metrics(r, [0, 1, 2, 3])
            rows[(bs, mode)] = dict(dev4=m, worst=m["W"], dd=m["DD"], F=round(v306.fitness(r, [0, 1, 2, 3]), 4))
            print(bs, mode, rows[(bs, mode)], flush=True)
    assert abs(rows[(8.0, "normal")]["dev4"]["R"] - 7.079) < 0.003
    ref = rows[(8.0, "normal")]
    ok = [bs for bs in (8.0, 6.0) if rows[(bs, "normal")]["dev4"]["R"] >= ref["dev4"]["R"] - 0.15 and rows[(bs, "normal")]["worst"] >= ref["worst"] - 0.15]
    ch = min(ok, key=lambda bs: rows[(bs, "outage")]["dd"])
    adopted = ch if rows[(ch, "outage")]["dd"] <= 20 else None
    out = {"version": "v330", "rows": {f"{k[0]}:{k[1]}": v for k, v in rows.items()}, "eligible": ok, "choice": ch, "adopted": adopted}
    if adopted is not None:
        r = v306.run_genome(v306.encode(dict(v306.SEEDS["R2"], backstop=adopted)), True)
        out["final"] = dict(last_year=v306.metrics(r, [4]), five_years=v306.metrics(r, [0, 1, 2, 3, 4]),
                            full={q: r[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("CHOICE", ch, "ADOPTED", adopted, out.get("final"), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v330_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
