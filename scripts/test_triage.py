"""Helper for ops_testtriage: run each untracked tests/test_*.py alone and triage.

Usage:
    .venv/Scripts/python.exe scripts/test_triage.py [--list FILE ...] [--json OUT] [--scan-only]
Discovers untracked tests via `git status --short tests/`, runs each alone with
`python -m pytest -q -x <file>` (timeout 300 s, sequential, below-normal
priority on Windows), skips when free RAM < 2 GB (retries later via 2nd pass).

Only stdlib. Machine-readable JSON goes to --json path (prefer a temp dir
outside the repo) or stdout. Tolerates files vanishing mid-run (concurrent
workspace activity) by recording status "vanished".
"""
from __future__ import annotations

import argparse
import ctypes
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 300
# ops_testtriage2 (2026-10-06): gate lowered 2.0 -> 1.5 GB to match the
# assigned heavy_slot wrapper (--min-free-gb 1.5). The wrapper itself waits
# for a free slot + RAM, so this pre-check only fast-skips when far below it.
LOW_RAM_BYTES = int(1.5 * 1024**3)
BELOW_NORMAL = 0x00004000
# Outer timeout covers heavy_slot queue wait (default timeout-h 6h) + pytest.
SLOT_WAIT_S = 6 * 3600
OUTER_TIMEOUT = TIMEOUT + SLOT_WAIT_S + 60

DEP_PATTERNS = [
    r"research/tournament/[A-Za-z0-9_]+(?:/[A-Za-z0-9_.\-]+)?",
    r"research/diagnostics/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)?",
    r"research/parallel/[A-Za-z0-9_\-./]+",
    r"research/[A-Za-z0-9_]+(?:/[A-Za-z0-9_.\-]+)?",
    r"data/raw/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)?",
    r"data/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)?",
    r"artifacts/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)?",
    r"models/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)?",
    r"reports/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)?",
]
DEP_RE = re.compile("|".join(f"({p})" for p in DEP_PATTERNS))

_CACHE_TRACKED: dict[str, bool] = {}
_CACHE_IGNORED: dict[str, bool] = {}
_CACHE_COUNT: dict[str, int] = {}


def free_ram_bytes() -> int | None:
    try:

        class MEM(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = MEM()
        st.dwLength = ctypes.sizeof(MEM)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return int(st.ullAvailPhys)
        return None
    except Exception:
        return None


def git(cmd: list[str]) -> str:
    r = subprocess.run(["git"] + cmd, cwd=ROOT, capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def discover_untracked() -> list[str]:
    out = git(["status", "--short", "tests/"])
    files = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("??"):
            p = line[2:].strip().strip('"')
            if p.endswith(".py") and "/test_" in p.replace("\\", "/"):
                files.append(p.replace("\\", "/"))
    return sorted(files)


def git_tracked(path: str) -> bool:
    # tracked if `git ls-files <path>` non-empty (works for files and dirs)
    if path not in _CACHE_TRACKED:
        _CACHE_TRACKED[path] = bool(git(["ls-files", path]))
    return _CACHE_TRACKED[path]


def git_ignored(path: str) -> bool:
    if path not in _CACHE_IGNORED:
        r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
        _CACHE_IGNORED[path] = (r.returncode == 0)
    return _CACHE_IGNORED[path]


def tracked_count(path: str) -> int:
    if path not in _CACHE_COUNT:
        out = git(["ls-files", path])
        _CACHE_COUNT[path] = len([l for l in out.splitlines() if l.strip()])
    return _CACHE_COUNT[path]


def path_status(path: str) -> str:
    p = ROOT / path
    exists = p.exists()
    tracked = git_tracked(path)
    ignored = git_ignored(path)
    if tracked:
        return "tracked" + (",exists" if exists else ",missing-wd")
    if ignored:
        return "gitignored" + (",exists" if exists else ",missing")
    if exists:
        return "untracked-exists"
    return "missing"


def scan_deps(test_file: str) -> list[str]:
    try:
        text = (ROOT / test_file).read_text(errors="replace")
    except FileNotFoundError:
        return []
    hits: list[str] = []
    for m in DEP_RE.finditer(text):
        hits.append(m.group(0))
    short: list[str] = []
    seen = set()
    for h in hits:
        parts = h.split("/")
        if h.startswith("research/tournament/") and len(parts) >= 3:
            h = "/".join(parts[:3])
        elif h.startswith("research/diagnostics/") and len(parts) >= 3:
            h = "/".join(parts[:2])
        if h not in seen:
            seen.add(h)
            short.append(h)
    return sorted(short)[:8]


def run_one(test_file: str) -> dict:
    if not (ROOT / test_file).exists():
        return {"file": test_file, "status": "vanished", "deps": {},
                "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
                "runtime_s": 0, "tail": "file absent at run time"}
    deps = scan_deps(test_file)
    depinfo = {d: path_status(d) for d in deps}
    # RAM gate (assignment): skip when free < 2 GB, retry later (second pass in
    # main). Single check per attempt so a full pass stays fast under load.
    free = free_ram_bytes()
    if free is not None and free < LOW_RAM_BYTES:
        return {"file": test_file, "status": "deferred-low-ram", "deps": depinfo,
                "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
                "runtime_s": 0, "free_gb": round(free / 2**30, 2)}
    # NOTE: pyproject sets addopts="-q", so a bare `-q -x` run is really `-q -q -x`
    # and pytest suppresses the "N passed" summary. We keep the assigned flags
    # and add `-v` so per-test lines stay countable; verdict semantics unchanged.
    # ops_testtriage2: wrap each pytest with the shared heavy_slot semaphore so
    # the sweep queues behind heavy jobs (assigned wrapper, min-free 1.5 GB).
    # BELOW_NORMAL is set on the outer heavy_slot process; the inner pytest
    # inherits the priority class on Windows.
    inner = [sys.executable, "-m", "pytest", "-q", "-x", "-v", test_file]
    cmd = [sys.executable, str(ROOT / "scripts" / "heavy_slot.py"), "run",
           "--tag", "triage", "--min-free-gb", "1.5", "--"] + inner
    kwargs: dict = {"cwd": ROOT, "capture_output": True, "text": True, "timeout": OUTER_TIMEOUT}
    if sys.platform == "win32":
        kwargs["creationflags"] = BELOW_NORMAL  # low priority per assignment
    t0 = time.time()
    try:
        r = subprocess.run(cmd, **kwargs)
        out = (r.stdout or "") + "\n" + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        raw = e.stdout
        out = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
        return {"file": test_file, "status": "timeout", "deps": depinfo,
                "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
                "runtime_s": round(time.time() - t0, 1), "tail": out[-800:]}
    dt = round(time.time() - t0, 1)
    passed = len(re.findall(r"PASSED", out))
    failed = len(re.findall(r"FAILED", out))
    errors = len(re.findall(r"ERROR", out))
    skipped = len(re.findall(r"SKIPPED", out))
    if not (passed or failed or errors or skipped):
        # fallback to summary line (e.g. non-verbose runs)
        m = re.search(r"(\d+)\s+passed", out)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+)\s+failed", out)
        if m:
            failed = int(m.group(1))
        m = re.search(r"(\d+)\s+error", out)
        if m:
            errors = int(m.group(1))
        m = re.search(r"(\d+)\s+skipped", out)
        if m:
            skipped = int(m.group(1))
    tail = "\n".join(out.strip().splitlines()[-4:])
    if r.returncode == 0 and failed == 0 and errors == 0:
        status = "pass" if passed else "no-tests"
    elif "SKIP" in out.upper() and passed == 0 and failed == 0 and errors == 0:
        status = "skip"
    elif failed or errors:
        # collection error vs assertion failure
        status = "error" if errors and not failed else "fail"
        if "ModuleNotFoundError" in out or "ImportError" in out or "ERROR collecting" in out:
            status = "error"
    elif r.returncode == 5:
        status = "no-tests"
    else:
        status = f"rc{r.returncode}"
    return {"file": test_file, "status": status, "deps": depinfo,
            "passed": passed, "failed": failed, "errors": errors,
            "skipped": skipped, "runtime_s": dt, "tail": tail[-400:]}


def classify(row: dict) -> str:
    if row.get("status") == "vanished":
        return "VANISHED"
    deps = row.get("deps", {})
    depvals = list(deps.values())
    has_missing = any("missing" in v for v in depvals)
    tail = row.get("tail", "")
    missing_hint = bool(re.search(r"FileNotFoundError|No such file|does not exist|not found|missing", tail, re.I))
    st = row["status"]
    if st == "pass":
        return "COMMIT"
    if st in ("fail", "error"):
        if has_missing or missing_hint:
            return "COMMIT-WITH-SKIP"
        # closed screen: every tournament dep folder has zero tracked files
        tdeps = [d for d in deps if d.startswith("research/tournament/")]
        if tdeps and all(tracked_count(d) == 0 for d in tdeps):
            return "DROP-CANDIDATE"
        if tdeps and any("untracked-exists" in deps[d] for d in tdeps):
            return "DROP-CANDIDATE"
        return "STALE"
    if st == "deferred-low-ram":
        return "DEFERRED"
    if st in ("skip", "no-tests", "timeout", "not-run"):
        return "COMMIT-WITH-SKIP" if (has_missing or missing_hint) else "STALE"
    return "STALE"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", nargs="*", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--scan-only", action="store_true",
                    help="skip pytest/RAM gate; record only static dep scan")
    ap.add_argument("--retry-wait", type=int, default=600,
                    help="seconds to wait before the deferred retry pass")
    args = ap.parse_args()
    files = args.list if args.list else discover_untracked()
    print(f"# triage snapshot: {len(files)} files", flush=True)
    rows = []
    if args.scan_only:
        for f in files:
            if not (ROOT / f).exists():
                rows.append({"file": f, "status": "vanished", "deps": {},
                             "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
                             "runtime_s": 0, "tail": "", "class": "VANISHED"})
                print(f"{f}: VANISHED (deleted mid-run)", flush=True)
                continue
            deps = scan_deps(f)
            depinfo = {d: path_status(d) for d in deps}
            tdeps = [d for d in depinfo if d.startswith("research/tournament/")]
            if tdeps and all(tracked_count(d) == 0 for d in tdeps):
                cls = "DROP-CANDIDATE?"
            elif any("missing" in v for v in depinfo.values()):
                cls = "COMMIT-WITH-SKIP?"
            else:
                cls = "COMMIT?"
            rows.append({"file": f, "status": "not-run", "deps": depinfo,
                         "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
                         "runtime_s": 0, "tail": "", "class": cls})
            print(f"{f}: {cls} deps={json.dumps(depinfo)}", flush=True)
        blob = {"rows": rows, "mode": "scan-only"}
        if args.json:
            Path(args.json).write_text(json.dumps(blob, indent=1))
        return
    for f in files:
        row = run_one(f)
        row["class"] = classify(row)
        rows.append(row)
        print(f"{row['file']}: {row['status']} "
              f"(p={row['passed']} f={row['failed']} e={row['errors']} s={row['skipped']}) "
              f"{row['runtime_s']}s -> {row['class']}", flush=True)
    # second pass: retry files deferred for low RAM ("retry later")
    deferred = [r["file"] for r in rows if r["status"] == "deferred-low-ram"]
    if deferred:
        print(f"# retrying {len(deferred)} deferred files after {args.retry_wait}s", flush=True)
        time.sleep(args.retry_wait)
        for f in deferred:
            row = run_one(f)
            row["class"] = classify(row)
            for i, r in enumerate(rows):
                if r["file"] == f:
                    rows[i] = row
                    break
            print(f"{row['file']}: {row['status']} "
                  f"(p={row['passed']} f={row['failed']} e={row['errors']} s={row['skipped']}) "
                  f"{row['runtime_s']}s -> {row['class']} (retry)", flush=True)
    blob = {"rows": rows}
    if args.json:
        Path(args.json).write_text(json.dumps(blob, indent=1))
    else:
        print("JSON-BEGIN")
        print(json.dumps(blob))
        print("JSON-END")


if __name__ == "__main__":
    main()
