"""Snapshot untracked + gitignored research files (read-only backup).

Context: on 2026-10-06 a worker ran `git stash -u`, which removed ~860
untracked research files from the working tree until the leader restored
them. Untracked files (reports, scripts, results) are not in git by design
(AGENTS.md: results stay local). This script snapshots them into a
timestamped zip so a future stash/clean incident is recoverable.

Scope (relative to the repo root):
  - research/
  - docs/opencode/
  - tests/
  - artifacts/bot/*/{state.json,actions.jsonl,exchange.json}

Both untracked (``git ls-files --others --exclude-standard``) and ignored
(``git ls-files --others --ignored --exclude-standard``) files in that scope
are included. Tracked files are NEVER included (git already protects them).

Exclusions (never snapshotted, never deleted):
  - data/raw, models (any path under those top-level dirs, or any segment
    equal to them inside research/ scope)
  - large binaries > 50 MB
  - __pycache__ (any segment)

Output: artifacts/backups/untracked_<UTC>.zip containing the files (relative
paths, forward slashes) plus manifest.json at the zip root. Each manifest
entry is {"path": ..., "size": ..., "sha256": ...}. Keeps the newest 14
snapshots; only snapshot zips this script created (untracked_*.zip) are ever
deleted, and only older ones. Snapshotted source files are never modified or
deleted.

Usage:
  .venv/Scripts/python.exe scripts/snapshot_untracked.py [--dry-run]
  .venv/Scripts/python.exe scripts/snapshot_untracked.py --restore-list <zip>

--dry-run prints the plan (files + total size) and writes nothing.
--restore-list prints what would be restored from <zip> and writes nothing.
GIT IS READ-ONLY for this script: it never runs stash/reset/checkout/clean/
commit; it only READS via `git ls-files`.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIRNAME = Path("artifacts") / "backups"
SNAP_PREFIX = "untracked_"
MANIFEST_NAME = "manifest.json"
KEEP_DEFAULT = 14
MAX_BYTES_DEFAULT = 50 * 1024 * 1024  # 50 MB
BOT_FILES = {"state.json", "actions.jsonl", "exchange.json"}


def repo_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except OSError:
        pass
    return REPO_ROOT


def git_others(root: Path, ignored: bool) -> list[str]:
    """List untracked (ignored=False) or ignored (ignored=True) files via git.

    Returns repo-relative posix paths. Empty list when git is unavailable.
    """
    cmd = ["git", "ls-files", "--others", "--exclude-standard", "-z"]
    if ignored:
        cmd.insert(3, "--ignored")
    try:
        out = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if out.returncode != 0:
        return []
    raw = out.stdout.split(b"\0")
    paths: list[str] = []
    for b in raw:
        if not b:
            continue
        try:
            paths.append(b.decode("utf-8", errors="replace"))
        except ValueError:
            continue
    return paths


def in_scope(rel_posix: str) -> bool:
    """True if a repo-relative posix path is inside the snapshot scope."""
    p = rel_posix.strip().lstrip("./")
    if not p or p.startswith(".git/"):
        return False
    parts = p.split("/")
    if p == "research" or parts[0] == "research":
        # research/ scope (files under it; the dir entry itself is skipped later)
        if len(parts) >= 1 and parts[0] == "research":
            return True
    if p.startswith("docs/opencode/"):
        return True
    if p == "tests" or p.startswith("tests/"):
        return True
    # artifacts/bot/*/{state.json,actions.jsonl,exchange.json}
    if (
        len(parts) == 4
        and parts[0] == "artifacts"
        and parts[1] == "bot"
        and parts[3] in BOT_FILES
    ):
        return True
    return False


def excluded(rel_posix: str, size: int | None, max_bytes: int) -> str | None:
    """Return the exclusion reason, or None when the file is eligible."""
    parts = rel_posix.split("/")
    if "__pycache__" in parts:
        return "__pycache__"
    if parts[0] == "models":
        return "models/"
    if parts[:2] == ["data", "raw"]:
        return "data/raw/"
    if "data" in parts and "raw" in parts:
        # e.g. research/.../data/raw/... safety net
        try:
            i = parts.index("data")
            if parts[i + 1] == "raw":
                return "data/raw/"
        except (ValueError, IndexError):
            pass
    if size is not None and size > max_bytes:
        return f"> {max_bytes} bytes"
    return None


def collect_candidates(root: Path, max_bytes: int) -> tuple[list[Path], list[str], int]:
    """Return (files, skipped_reasons, total_bytes) for the snapshot scope."""
    seen: dict[str, None] = {}
    for ignored in (False, True):
        for rel in git_others(root, ignored=ignored):
            rel_posix = rel.replace("\\", "/")
            seen[rel_posix] = None
    files: list[Path] = []
    skipped: list[str] = []
    total = 0
    for rel_posix in sorted(seen):
        if not in_scope(rel_posix):
            continue
        # Never snapshot our own outputs.
        if rel_posix.startswith("artifacts/backups/"):
            continue
        f = root / Path(*rel_posix.split("/"))
        try:
            if not f.is_file() or f.is_symlink():
                continue
            size = f.stat().st_size
        except OSError:
            skipped.append(f"{rel_posix}: unreadable")
            continue
        reason = excluded(rel_posix, size, max_bytes)
        if reason:
            skipped.append(f"{rel_posix}: excluded ({reason}, {size} bytes)")
            continue
        files.append(f)
        total += size
    return files, skipped, total


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_name(now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return f"{SNAP_PREFIX}{now.strftime('%Y%m%dT%H%M%SZ')}.zip"


def write_snapshot(root: Path, files: list[Path], dest: Path) -> list[dict]:
    """Write zip with relative paths + manifest.json. Returns manifest entries."""
    entries: list[dict] = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        entries.append({"path": rel, "size": f.stat().st_size, "sha256": sha256_of(f)})
    entries.sort(key=lambda e: e["path"])
    manifest = {"created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "files": entries}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for e in entries:
            zf.write(str(root / Path(*e["path"].split("/"))), arcname=e["path"])
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
    return entries


def prune_snapshots(backup_dir: Path, keep: int) -> list[Path]:
    """Delete oldest untracked_*.zip beyond `keep` newest. Returns deleted paths."""
    snaps = sorted(backup_dir.glob(f"{SNAP_PREFIX}*.zip"))
    if len(snaps) <= keep:
        return []
    doomed = snaps[: len(snaps) - keep]
    for d in doomed:
        try:
            d.unlink()
        except OSError:
            pass
    return doomed


def read_manifest_entries(zippath: Path) -> list[dict]:
    with zipfile.ZipFile(zippath, "r") as zf:
        try:
            raw = zf.read(MANIFEST_NAME)
            man = json.loads(raw.decode("utf-8"))
            if isinstance(man, dict) and isinstance(man.get("files"), list):
                return man["files"]
        except KeyError:
            pass
        # Fallback: zip listing minus the manifest itself.
        return [{"path": n, "size": None, "sha256": None} for n in zf.namelist() if n != MANIFEST_NAME]


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Snapshot untracked + gitignored research files (read-only w.r.t. git).")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and total size; write nothing")
    ap.add_argument("--restore-list", metavar="ZIP", default=None, help="print what would be restored from ZIP; write nothing")
    ap.add_argument("--keep", type=int, default=KEEP_DEFAULT, help="snapshots to keep (default 14)")
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES_DEFAULT, help="skip files larger than this (default 50MB)")
    ap.add_argument("--root", default=None, help="repo root (default: git toplevel)")
    args = ap.parse_args(argv)

    if args.restore_list:
        zippath = Path(args.restore_list)
        if not zippath.is_absolute():
            zippath = (repo_root(args.root) / zippath).resolve()
        if not zippath.is_file():
            print(f"restore-list: not found: {zippath}", file=sys.stderr)
            return 2
        entries = read_manifest_entries(zippath)
        total = sum(e.get("size") or 0 for e in entries if isinstance(e.get("size"), int))
        print(f"restore-list: {zippath} ({len(entries)} files, {total} bytes; no writes)")
        for e in sorted(entries, key=lambda d: str(d.get("path"))):
            print(f"  {e.get('path')}  size={e.get('size')}  sha256={e.get('sha256')}")
        return 0

    root = repo_root(args.root)
    files, skipped, total = collect_candidates(root, args.max_bytes)
    backup_dir = root / BACKUP_DIRNAME

    if args.dry_run:
        print(f"dry-run: {len(files)} files, {total} bytes -> {backup_dir.as_posix()}/ (no writes)")
        for f in files:
            rel = f.relative_to(root).as_posix()
            print(f"  + {rel}  ({f.stat().st_size} bytes)")
        for s in skipped:
            print(f"  skip {s}")
        existing = sorted(backup_dir.glob(f"{SNAP_PREFIX}*.zip"))
        print(f"existing snapshots: {len(existing)} (keep {args.keep}; dry-run prunes nothing)")
        return 0

    dest = backup_dir / snapshot_name()
    # Avoid clobbering when two runs share a second: append a counter.
    n = 1
    while dest.exists():
        stem = dest.stem
        dest = backup_dir / f"{stem}_{n}.zip"
        n += 1
    entries = write_snapshot(root, files, dest)
    pruned = prune_snapshots(backup_dir, args.keep)
    print(f"snapshot: {len(entries)} files, {total} bytes -> {dest}")
    if pruned:
        print(f"pruned {len(pruned)} old snapshot(s), keeping newest {args.keep}:")
        for d in pruned:
            print(f"  - {d.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
