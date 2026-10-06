"""tests for oc_idea1_kellyrung (light; uses cached tmp/results, no engine reruns)."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "research/tournament/oc_idea1_kellyrung"
TMP = T / "tmp"


def load_results():
    return json.loads((T / "results.json").read_text())


def test_prereg_frozen_first():
    txt = (T / "REPORT.md").read_text()
    head = "\n".join(txt.splitlines()[:40])
    assert "K1" in head and "0.25" in head
    assert "K2" in head and "0.50" in head or "0.5" in head
    assert "2021-2024" in head or "dev4" in head.lower()
    assert ("winner" in head.lower() or "chosen" in head.lower()) and "2025" in head


def test_baseline_exact():
    r = load_results()["baseline"]
    assert r["G2_R"] == 5.41 and r["G2_W"] == 2.588 and r["G2_DD"] == 16.91
    assert r["G2_full"] == 16.82
    assert r["GC_R"] == 5.634 and r["GC_DD"] == 16.75 and r["GC_full"] == 16.66
    assert r["carry_add"] == 0.224
    assert r["status"] == "reproduced exactly"


def test_fit_leakage_free_and_bounded():
    fit = json.loads((TMP / "fit_tables.json").read_text())
    assert set(fit) >= {"2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"}
    for key, t in fit.items():
        assert t["C0"] > 0 and 0 < t["meanB1"] < 1
        for k, b in t["base"].items():
            assert 0.0 <= b <= 2.0, (key, k, b)
    # embargo spot check: 2024 train max t_exit < anchor - 7d (light recompute)
    import sys
    sys.path.insert(0, str(ROOT / "research/tournament/ext"))
    import harness5 as H5
    import pandas as pd
    d = H5.load()
    y, a0, tr, te = H5.folds(d)[3]
    assert d.t_exit[tr].max() < a0 - pd.Timedelta(days=7)
    assert int(tr.sum()) == fit["2024-09-24"]["n_train_all"]


def test_dev_selection_never_touched_2025():
    rep4 = json.loads((TMP / "replica_dev4.json").read_text())
    for v, rr in rep4["variants"].items():
        yrs = [r["year"] for r in rr["raw"]]
        assert yrs == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"], (v, yrs)
    assert set(json.loads((TMP / "replica_last.json").read_text())["variants"]) == {"K2"}
    import pickle
    dev = pickle.loads((TMP / "engine_dev.pkl").read_bytes())
    assert set(dev[0]) == {"K1", "K2"}
    last = pickle.loads((TMP / "engine_last.pkl").read_bytes())
    assert set(last[0]) == {"K2"}


def test_robust_choice_is_k2():
    r = load_results()
    assert r["choice"]["winner"] == "K2"
    e = r["engine_dev4"]
    for v in ("K1", "K2"):
        assert e[v]["DD"] <= 20 and e[v]["losing"] == 0
    assert e["K2"]["R"] >= 5 > e["K1"]["R"] or e["K2"]["W"] > e["K1"]["W"]
    assert e["K2"]["W"] > e["K1"]["W"]


def test_gate_and_verdict_consistent():
    r = load_results()
    g = r["gate_K2"]
    assert g["(a) 5y>=5"] is True and g["(b) last>=5"] is False
    assert g["(c) no losing"] is True and g["(d) fullDD<=20"] is False
    f = r["five_year_K2"]
    assert f["R"] == 5.353 and f["full_path_dd"]["full"] == 21.79
    assert r["last_year_POSTHOC_winner_only"]["engine"] == {"R": 4.641, "DD": 14.69}
    assert "REJECT" in r["verdict"]
    txt = (T / "REPORT.md").read_text()
    assert "Khong ap dung" in txt or "reject" in txt.lower()


def test_costs_and_artifacts():
    r = load_results()
    assert "0.0002" in r["meta"]["costs"] and "0.00055" in r["meta"]["costs"]
    for p in ("REPORT.md", "results.json", "run_kellyrung.py", "engine_kelly.py",
              "tmp/baseline.json", "tmp/fit_tables.json", "tmp/replica_dev4.json",
              "tmp/replica_last.json", "tmp/engine_dev_choice.json"):
        assert (T / p).exists(), p
