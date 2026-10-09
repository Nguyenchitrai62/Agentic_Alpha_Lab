"""oc_b7c2pre crash risk: stack boosted stop-hit share vs base (frozen kinds, CPU-only).

Kinds REUSED read-only from oc_cboostpre/tmp/stop_kinds.npz (verbatim
build_ledger_presample.outcome_mu kind branch at mu=1.0; stop-first; 9731 fills
in ledger order; 15 unknown). No 1m recompute here (no heavy slot needed).
"Hit the stop" = kind in {stop, backstop}. Base rate = stop-hit share over known
fills in the year (copy gate vs cboostpre stop table). Stack boosted rate =
stop-hit share over known fills with stack mult > 1.0 (net-boosted); de-boosted
(mult < 1, i.e. 0.75) reported for context; TP secondary row included.
B7/C2 boosted stop rows are COPIES. Y2020p (COVID leg) highlighted separately.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PST = ROOT / "research/tournament/oc_presampletilt"
CBP = ROOT / "research/tournament/oc_cboostpre"

sys.path.insert(0, str(HERE))
from stack_rule import assign_c2, stack_mult, stack_mult_cap  # noqa: E402
from stack_rule import C2_DIRECTION, C2_Q20, C2_Q80  # noqa: E402

MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
KIND = {"backstop": 0, "tp": 1, "stop": 2, "time": 3, "unknown": -1}


def load_boost():
    d = pd.read_parquet(CBP / "boost_mult_presample.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in (0, 1, 2, 3):
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {"mult_B7": sub["mult_B7"].to_numpy(dtype=float), "t_ns": t_ns}
        for t, a in zip(pd.to_datetime(sub["T"], utc=True), sub["mult_B7"]):
            exact[(int(s), pd.Timestamp(t))] = float(a)
    return exact, per_shift


def boost_at(shift, t, exact, per_shift):
    key = (int(shift), pd.Timestamp(t))
    hit = exact.get(key)
    if hit is not None:
        return hit
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    t_ns = per_shift[int(shift)]["t_ns"]
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return 1.0
    return float(per_shift[int(shift)]["mult_B7"][pos])


def main() -> None:
    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "coin", "year"):
        led[k] = led[k].astype(np.int64)
    bt_all = np.load(PST / "tmp/bt_presample.npy", allow_pickle=True)
    n = len(led["phase"])
    assert n == 9731, n
    kinds = np.load(CBP / "tmp/stop_kinds.npz")["kind"].astype(np.int64)
    assert len(kinds) == n, (len(kinds), n)
    n_unknown = int((kinds == KIND["unknown"]).sum())
    print(f"kinds: unknown={n_unknown} (frozen; expect 15)", flush=True)
    assert n_unknown == 15, n_unknown

    # copy gate: base stop/TP rates vs frozen cboostpre stop table
    frozen = json.loads((CBP / "tmp/stop_presample.json").read_text())
    assert frozen["config"]["unknown"] == 15

    exact, per_shift = load_boost()
    ch = pd.read_parquet(PST / "chronos_features_presample.parquet",
                         columns=["sym", "shift", "T", "ch_q10"])
    ch["T"] = pd.to_datetime(ch["T"], utc=True)
    c2_lut = {(str(s), int(sh), pd.Timestamp(t)): float(q)
              for s, sh, t, q in zip(ch["sym"], ch["shift"], ch["T"], ch["ch_q10"])}
    del ch

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    m_b7 = np.array([boost_at(int(ph[i]), bt_all[i], exact, per_shift)
                     for i in range(n)], dtype=float)
    m_c2 = np.ones(n, dtype=float)
    for i in range(n):
        q = c2_lut.get((MAJORS4[int(co[i])], int(ph[i]), pd.Timestamp(bt_all[i])))
        m_c2[i] = assign_c2(-float(q), C2_DIRECTION, C2_Q20, C2_Q80) \
            if q is not None and np.isfinite(float(q)) else 1.0
    stacks = {
        "B7C2": np.array([stack_mult(a, b) for a, b in zip(m_b7, m_c2)]),
        "B7C2_cap": np.array([stack_mult_cap(a, b) for a, b in zip(m_b7, m_c2)]),
    }

    stop = (kinds == KIND["stop"]) | (kinds == KIND["backstop"])
    tp = kinds == KIND["tp"]
    known = kinds != KIND["unknown"]

    out: dict = {"config": {
        "stop": "kind in {stop, backstop} from FROZEN oc_cboostpre/tmp/stop_kinds.npz (verbatim outcome_mu mu=1.0, stop-first); reused read-only, never recomputed",
        "boosted": "stack mult > 1.0 (net-boosted); deboosted mult < 1.0 (=0.75); B7/C2 rows are copies",
        "unknown": int(n_unknown),
    }, "per_year": []}
    for y in range(4):
        my = (yr == y) & known
        row: dict = {"year": LEG_ORDER[y], "n_fills": int((yr == y).sum()),
                      "n_known": int(my.sum()),
                      "base_stop_rate": round(float(stop[my].mean()), 4),
                      "base_tp_rate": round(float(tp[my].mean()), 4)}
        fr = frozen["per_year"][y]
        assert fr["year"] == LEG_ORDER[y]
        assert row["base_stop_rate"] == fr["base_stop_rate"], (row, fr)
        assert row["base_tp_rate"] == fr["base_tp_rate"], (row, fr)
        row["B7_copy"] = {"boosted_share": fr["B7_boosted_share"],
                          "stop_rate": fr["B7_stop_rate"],
                          "stop_delta": fr["B7_stop_delta"],
                          "tp_rate": fr["B7_tp_rate"]}
        for variant in ("B7C2", "B7C2_cap"):
            idx_y = np.where(yr == y)[0]
            mv = stacks[variant][idx_y]
            is_b = mv > 1.0
            is_d = mv < 1.0
            kb = known[idx_y][is_b]
            mb = idx_y[is_b]
            kd = known[idx_y][is_d]
            md = idx_y[is_d]
            row[f"{variant}_boosted_share"] = round(float(is_b.mean()), 4)
            row[f"{variant}_deboosted_share"] = round(float(is_d.mean()), 4)
            if kb.any():
                row[f"{variant}_stop_rate"] = round(float(stop[mb][kb].mean()), 4)
                row[f"{variant}_tp_rate"] = round(float(tp[mb][kb].mean()), 4)
                row[f"{variant}_stop_delta"] = round(
                    float(stop[mb][kb].mean()) - float(stop[my].mean()), 4)
            else:
                row[f"{variant}_stop_rate"] = None
                row[f"{variant}_tp_rate"] = None
                row[f"{variant}_stop_delta"] = None
            if kd.any():
                row[f"{variant}_deboosted_stop_rate"] = round(float(stop[md][kd].mean()), 4)
            else:
                row[f"{variant}_deboosted_stop_rate"] = None
        out["per_year"].append(row)
        print(row, flush=True)
    for variant in ("B7C2", "B7C2_cap"):
        is_b = (stacks[variant] > 1.0) & known
        is_d = (stacks[variant] < 1.0) & known
        out[f"{variant}_pooled"] = {
            "boosted_share": round(float((stacks[variant] > 1.0).mean()), 4),
            "base_stop_rate": round(float(stop[known].mean()), 4),
            "boosted_stop_rate": round(float(stop[is_b].mean()), 4) if is_b.any() else None,
            "stop_delta": round(float(stop[is_b].mean()) - float(stop[known].mean()), 4)
            if is_b.any() else None,
            "deboosted_stop_rate": round(float(stop[is_d].mean()), 4) if is_d.any() else None}
        ex = (yr != 3)
        is_bx = (stacks[variant] > 1.0) & known & ex
        knx = known & ex
        out[f"{variant}_pooled_exCOVID"] = {
            "boosted_share": round(float((stacks[variant][ex] > 1.0).mean()), 4),
            "base_stop_rate": round(float(stop[knx].mean()), 4),
            "boosted_stop_rate": round(float(stop[is_bx].mean()), 4) if is_bx.any() else None,
            "stop_delta": round(float(stop[is_bx].mean()) - float(stop[knx].mean()), 4)
            if is_bx.any() else None}
        print(variant, out[f"{variant}_pooled"], out[f"{variant}_pooled_exCOVID"], flush=True)
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/stop_stack.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/stop_stack.json", flush=True)


if __name__ == "__main__":
    main()
