"""Regenerate docs/RESEARCH_INDEX.md (assignment ops_reindex).

Deterministic, read-only scan (no network) of:
  - research/tournament/*/REPORT.md
  - research/diagnostics/*/REPORT.md (+ ROBUST.md / COMPARISON.md where present)
  - research/parallel/rounds/parallel-20260906-r2/v3*/v4* result_manifest.json

One table row per file with: family, folder, file, date (file mtime), verdict.
Sorted by (family, mtime, path). Runs in well under 10 s.

Usage:
    .venv/Scripts/python.exe scripts/research_index.py [--out docs/RESEARCH_INDEX.md]
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re

VERDICT_MAX_LEN = 220

# ---------------------------------------------------------------- verdict ---

_HEADING_VERDICT = re.compile(r"(?im)^##\s*verdict\b(.*)$")
_HEADING_ONELINE = re.compile(r"(?im)^##\s*one-line verdict\b(.*)$")
_INLINE_ONELINE = re.compile(r"(?im)^.*one-line verdict\s*[:\-–—]\s*(.+?)\s*$")
_INLINE_VERDICT = re.compile(r"(?im)^.*\bVERDICT\s*:\s*(.+?)\s*$")
_INLINE_VERDICT2 = re.compile(r"(?im)^.*\bVerdict\s*:\s*(.+?)\s*$")
_TITLE = re.compile(r"(?m)^#\s+(.+?)\s*$")


def _clean(s: str, limit: int = VERDICT_MAX_LEN) -> str:
    s = re.sub(r"\s+", " ", s.strip())
    s = s.replace("|", "\\|")
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def _next_lines(text: str, pos: int, n: int = 2) -> str:
    out: list[str] = []
    for line in text[pos:].splitlines():
        t = line.strip().lstrip("#>* ").strip().strip("*").strip()
        if not t:
            continue
        # stop at the next heading
        if line.lstrip().startswith("#"):
            break
        out.append(t)
        if len(out) >= n:
            break
    return " | ".join(out)


def extract_verdict_md(text: str) -> str:
    """Single-line verdict from a REPORT/ROBUST/COMPARISON markdown file."""
    m = _HEADING_ONELINE.search(text)
    if m:
        rest_inline = m.group(1).strip(" :–—-")
        if rest_inline:
            return _clean(rest_inline)
        nxt = _next_lines(text, m.end())
        if nxt:
            return _clean(nxt)
    m = _INLINE_ONELINE.search(text)
    if m:
        v = m.group(1).strip()
        # heading-only form "## One-line verdict" has empty capture; fall through
        if v and v.lower() not in ("line",):
            return _clean(v)
    m = _HEADING_VERDICT.search(text)
    if m:
        rest_inline = m.group(1).strip(" :–—-()")
        # headings like "## Verdict (one line)" carry no verdict themselves
        if rest_inline and "one line" not in rest_inline.lower():
            return _clean(rest_inline)
        nxt = _next_lines(text, m.end())
        if nxt:
            return _clean(nxt)
    m = _INLINE_VERDICT.search(text) or _INLINE_VERDICT2.search(text)
    if m:
        v = m.group(1).strip()
        return _clean(v)
    m = _TITLE.search(text)
    if m:
        return _clean(m.group(1))
    for line in text.splitlines():
        if line.strip():
            return _clean(line.strip("#>* "))
    return "(empty)"


def extract_verdict_manifest(data: dict) -> str:
    status = str(data.get("status", "unknown"))
    audit = data.get("audit", {}) if isinstance(data.get("audit"), dict) else {}
    audit_str = "PASS" if audit.get("passed") is True else ("FAIL" if audit.get("passed") is False else "n/a")
    note = data.get("note")
    if not note:
        res = data.get("result", {}) if isinstance(data.get("result"), dict) else {}
        note = res.get("note") or res.get("final_score_selected") or res.get("final") or res.get("selected")
    note = str(note) if note is not None else "-"
    return _clean(f"status={status}; audit={audit_str}; {note}")


# ---------------------------------------------------------------- family ----

def infer_family(rel_posix: str, text: str = "") -> str:
    """Family tag from folder name (primary) and text (fallback).

    Families: dip ladder / book / sleeve / MANUAL / execution / ops /
    diagnostic / engine version.
    """
    p = rel_posix.lower()
    parent = os.path.basename(os.path.dirname(rel_posix)).lower()
    fname = os.path.basename(rel_posix).lower()
    if fname == "result_manifest.json" or re.fullmatch(r"v\d+", parent):
        return "engine version"
    if "manual" in parent:
        return "MANUAL"
    if parent.startswith("ops_"):
        return "ops"
    if parent.startswith("bot_") or "parity" in parent or "capfix" in parent or parent == "bot_bookgap":
        return "execution"
    if "book" in parent:
        return "book"
    if any(k in parent for k in ("dip", "ladder", "rung", "kelly", "dca", "crashrisk", "context", "breadth", "flush")):
        return "dip ladder"
    if any(k in parent for k in ("sleeve", "carry", "hedge", "funding", "second_", "basis")):
        return "sleeve"
    t = text.lower()[:4000]
    if "dip ladder" in t or "dip sleeve" in t or "dip-sleeve" in t:
        return "dip ladder"
    if "research/diagnostics" in p:
        return "diagnostic"
    if any(k in parent for k in ("exec", "fill", "tp", "exit", "slip", "fee", "venue", "bybit", "latency", "liq", "stress", "gap", "robust")):
        return "execution"
    return "diagnostic"


# ----------------------------------------------------------------- scan ----

def collect(root: str) -> list[str]:
    pats = [
        "research/tournament/*/REPORT.md",
        "research/diagnostics/*/REPORT.md",
        "research/diagnostics/*/ROBUST.md",
        "research/diagnostics/*/COMPARISON.md",
        "research/parallel/rounds/parallel-20260906-r2/v3*/result_manifest.json",
        "research/parallel/rounds/parallel-20260906-r2/v4*/result_manifest.json",
    ]
    found: list[str] = []
    for pat in pats:
        found.extend(glob.glob(os.path.join(root, pat.replace("/", os.sep))))
    # deterministic, de-duplicated
    return sorted({os.path.relpath(f, root).replace(os.sep, "/") for f in found})


def build_rows(root: str) -> list[dict]:
    rows: list[dict] = []
    for rel in collect(root):
        abs_path = os.path.join(root, rel.replace("/", os.sep))
        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            continue
        date = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
        folder = os.path.dirname(rel)
        fname = os.path.basename(rel)
        try:
            if rel.endswith(".json"):
                with open(abs_path, encoding="utf-8", errors="replace") as fh:
                    data = json.load(fh)
                verdict = extract_verdict_manifest(data)
                family = infer_family(rel)
            else:
                with open(abs_path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                verdict = extract_verdict_md(text)
                family = infer_family(rel, text)
        except Exception as exc:  # never fail the whole index on one file
            verdict = _clean(f"(unreadable: {exc})")
            family = infer_family(rel)
        rows.append({"family": family, "folder": folder, "file": fname, "date": date, "mtime": mtime, "path": rel, "verdict": verdict})
    rows.sort(key=lambda r: (r["family"], r["mtime"], r["path"]))
    return rows


def render(rows: list[dict]) -> str:
    from collections import Counter

    counts = Counter(r["family"] for r in rows)
    fam_summary = ", ".join(f"{fam}={counts[fam]}" for fam in sorted(counts))
    lines = [
        "# Research index",
        "",
        "Regenerated by `scripts/research_index.py` (deterministic, read-only scan, no network).",
        "",
        f"Items: {len(rows)} ({fam_summary}).",
        "One table row per file: `research/tournament/*/REPORT.md`,",
        "`research/diagnostics/*/REPORT.md` (+ `ROBUST.md` / `COMPARISON.md` where present),",
        "and `research/parallel/rounds/parallel-20260906-r2/v3*` / `v4*` `result_manifest.json`",
        "(verdict = status + audit + result/top-level note).",
        "Columns: family (dip ladder / book / sleeve / MANUAL / execution / ops / diagnostic / engine version,",
        "inferred from folder name with text fallback), folder, file, date (file mtime, UTC), one-line verdict",
        "(REPORTs: the `## Verdict` / `One-line verdict` / `VERDICT:` line; manifests: status + audit + note).",
        "Sorted by family then date (mtime), ties by path.",
        "",
        "| Family | Folder | File | Date | Verdict |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['family']} | `{r['folder']}` | `{r['file']}` | {r['date']} | {r['verdict']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/RESEARCH_INDEX.md")
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rows = build_rows(root)
    out = args.out if os.path.isabs(args.out) else os.path.join(root, args.out.replace("/", os.sep))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(rows))
    print(f"wrote {out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
