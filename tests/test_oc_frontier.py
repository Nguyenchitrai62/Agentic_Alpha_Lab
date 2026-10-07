"""oc_frontier tests: table fidelity vs vNNN sources, Pareto correctness, artifacts."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research" / "tournament" / "oc_frontier"
R2 = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
VERSIONS = [f"v{n}" for n in range(399, 424)]
FULLPATH_RE = re.compile(r"^(\S+)\s+full-path DD\s+([0-9.]+)", re.M)


def load_results():
    return json.loads((OC / "results.json").read_text())


def pareto(keys, r, dd):
    out = []
    for a in keys:
        dom = any(b != a and r[b] >= r[a] and dd[b] <= dd[a]
                  and (r[b] > r[a] or dd[b] < dd[a]) for b in keys)
        if not dom:
            out.append(a)
    return sorted(out, key=lambda k: (-r[k], dd[k]))


def test_row_count_and_versions():
    res = load_results()
    assert res["meta"]["versions"] == VERSIONS
    assert len(res["rows"]) == 80
    got = sorted({r["version"] for r in res["rows"]})
    assert got == VERSIONS


def test_rows_match_sources():
    res = load_results()
    by_key = {(r["version"], r["row"]): r for r in res["rows"]}
    for v in VERSIONS:
        src = json.loads((R2 / v / f"{v}_result.json").read_text())
        man = json.loads((R2 / v / "result_manifest.json").read_text())
        log = (R2 / v / "run.log").read_text(errors="replace")
        logged = {m.group(1): float(m.group(2)) for m in FULLPATH_RE.finditer(log)}
        audited = bool(man.get("audit", {}).get("passed", False))
        assert set(src.get("rows", {})) == {k[1] for k in by_key if k[0] == v}, v
        for row, d in src["rows"].items():
            r = by_key[(v, row)]
            assert r["R"] == d["R"], (v, row)
            assert r["W"] == d["W"], (v, row)
            assert r["dd_yearly"] == d["DD"], (v, row)
            assert r["years"] == [[float(a), float(b)] for a, b in d["years"]], (v, row)
            assert r["recent_r"] == float(d["years"][4][0]), (v, row)
            assert r["audited"] == audited, (v, row)
            jf = d.get("full_path_dd")
            lf = logged.get(row)
            exp = lf if lf is not None else (None if jf is None else float(jf))
            assert r["full_path_dd"] == exp, (v, row, lf, jf)
            # DD_yearly is the max of yearly DDs
            assert abs(r["dd_yearly"] - max(y[1] for y in r["years"])) < 1e-9, (v, row)


def test_null_fullpath_only_v399_v400():
    res = load_results()
    nulls = sorted(f"{r['version']}/{r['row']}" for r in res["rows"] if r["full_path_dd"] is None)
    assert len(nulls) == 7
    assert all(k.startswith(("v399/", "v400/")) for k in nulls)
    assert res["meta"]["log_json_mismatches"] == []


def test_frontiers_recomputed():
    res = load_results()
    rmap = {f"{r['version']}/{r['row']}": r["R"] for r in res["rows"]}
    ymap = {f"{r['version']}/{r['row']}": r["dd_yearly"] for r in res["rows"]}
    fmap = {f"{r['version']}/{r['row']}": r["full_path_dd"] for r in res["rows"]
            if r["full_path_dd"] is not None}
    assert res["frontier_yearly"] == pareto(list(ymap), rmap, ymap)
    assert res["frontier_fullpath"] == pareto(list(fmap), rmap, fmap)
    assert len(res["frontier_yearly"]) == 9
    assert len(res["frontier_fullpath"]) == 9
    # deploy pick present in table but on neither frontier
    assert "v411/R2B1D17BF" not in res["frontier_yearly"]
    assert "v411/R2B1D17BF" not in res["frontier_fullpath"]
    # stretch flags recomputed
    assert res["dd15_yearly"] == sorted(k for k in ymap if ymap[k] < 15.0) == ["v399/R2B1"]
    assert res["dd15_fullpath"] == sorted(k for k in fmap if fmap[k] < 15.0)
    assert res["dd15_fullpath"] == ["v409/R2B1D15B08"]


def test_artifacts_exist():
    for f in ("PLAN.md", "build_frontier.py", "results.json", "REPORT.md", "frontier.png"):
        p = OC / f
        assert p.exists() and p.stat().st_size > 0, f
    raw = (OC / "frontier.png").read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "frontier.png is not a PNG"
    rep = (OC / "REPORT.md").read_text()
    assert "v411/R2B1D17BF" in rep and "Verdict" in rep
