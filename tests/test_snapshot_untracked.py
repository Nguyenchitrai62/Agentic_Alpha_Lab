"""Tests for scripts/snapshot_untracked.py (temp git repo only, never the real tree)."""
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "snapshot_untracked.py"


def _load():
    spec = importlib.util.spec_from_file_location("snapshot_untracked", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["snapshot_untracked"] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"
    return r


def _mk_repo(tmp_path: Path):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "t@t.t", cwd=tmp_path)
    _git("config", "user.name", "t", cwd=tmp_path)
    (tmp_path / ".gitignore").write_text("*.ign\n", encoding="utf-8")
    return tmp_path


def _write(p: Path, text: str = "x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_scope_manifest_and_sources_untouched(tmp_path):
    mod = _load()
    root = _mk_repo(tmp_path)
    wanted = {
        "research/a.txt": "aaa",
        "docs/opencode/b.md": "bbb",
        "tests/c.py": "ccc",
        "artifacts/bot/paper/state.json": "{}",
        "artifacts/bot/paper/actions.jsonl": "{}\n",
        "artifacts/bot/paper/exchange.json": "{}",
        "research/x.ign": "ignored-but-in-scope",
    }
    for rel, text in wanted.items():
        _write(root / Path(*rel.split("/")), text)
    # Out of scope / excluded.
    _write(root / "artifacts/bot/paper/stdout.log", "no")
    _write(root / "research/__pycache__/q.pyc", "no")
    _write(root / "data/raw/big.csv", "no")
    _write(root / "models/m.bin", "no")
    _write(root / "other/n.txt", "no")
    # Tracked file must NOT be snapshotted.
    _write(root / "research/tracked.txt", "tracked")
    _git("add", "research/tracked.txt", cwd=root)
    _git("commit", "-m", "t", cwd=root)

    before = {rel: hashlib.sha256((root / Path(*rel.split("/"))).read_bytes()).hexdigest() for rel in wanted}
    files, skipped, total = mod.collect_candidates(root, mod.MAX_BYTES_DEFAULT)
    got = sorted(f.relative_to(root).as_posix() for f in files)
    assert got == sorted(wanted), f"scope mismatch: {got}"
    assert total == sum((root / r).stat().st_size for r in wanted)
    assert any("__pycache__" in s for s in skipped)

    dest = root / "artifacts" / "backups" / "untracked_TEST.zip"
    entries = mod.write_snapshot(root, files, dest)
    assert dest.is_file()
    with zipfile.ZipFile(dest) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        for rel in wanted:
            assert rel in names, f"missing in zip: {rel}"
            assert zf.read(rel) == (root / Path(*rel.split("/"))).read_bytes()
        man = json.loads(zf.read("manifest.json").decode())
    assert sorted(e["path"] for e in man["files"]) == sorted(wanted)
    for e in man["files"]:
        assert set(e) >= {"path", "size", "sha256"}
        assert e["sha256"] == before[e["path"]]
        assert e["size"] == (root / Path(*e["path"].split("/"))).stat().st_size
    # Sources never modified/deleted.
    for rel, h in before.items():
        p = root / Path(*rel.split("/"))
        assert p.is_file()
        assert hashlib.sha256(p.read_bytes()).hexdigest() == h


def test_ignored_files_included_and_large_excluded(tmp_path):
    mod = _load()
    root = _mk_repo(tmp_path)
    _write(root / "research/small.txt", "s")
    big = root / "research/big.bin"
    big.parent.mkdir(parents=True, exist_ok=True)
    big.write_bytes(b"0" * 2048)
    files, _sk, _t = mod.collect_candidates(root, 1024)
    got = [f.relative_to(root).as_posix() for f in files]
    assert "research/small.txt" in got
    assert "research/big.bin" not in got  # > max-bytes
    # *.ign is gitignored yet still in scope.
    _write(root / "research/y.ign", "y")
    files2, _, _ = mod.collect_candidates(root, 1024 * 1024)
    got2 = [f.relative_to(root).as_posix() for f in files2]
    assert "research/y.ign" in got2


def test_dry_run_writes_nothing(tmp_path, capsys):
    mod = _load()
    root = _mk_repo(tmp_path)
    _write(root / "research/a.txt", "aaa")
    rc = mod.main(["--root", str(root), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out and "research/a.txt" in out
    assert not (root / "artifacts" / "backups").exists() or not list((root / "artifacts" / "backups").glob("*.zip"))


def test_retention_keeps_newest_14_only(tmp_path):
    mod = _load()
    bdir = tmp_path / "artifacts" / "backups"
    bdir.mkdir(parents=True)
    for i in range(16):
        (bdir / f"untracked_202601{i:02d}T000000Z.zip").write_bytes(b"z")
    keep = bdir / "keep.txt"
    keep.write_text("do not delete", encoding="utf-8")
    doomed = mod.prune_snapshots(bdir, 14)
    assert len(doomed) == 2
    assert len(list(bdir.glob("untracked_*.zip"))) == 14
    assert keep.is_file()  # only own snapshot zips are ever deleted
    assert not (bdir / "untracked_20260100T000000Z.zip").exists()
    assert (bdir / "untracked_20260115T000000Z.zip").exists()


def test_restore_list_no_writes(tmp_path, capsys):
    mod = _load()
    root = _mk_repo(tmp_path)
    _write(root / "research/a.txt", "aaa")
    files, _, _ = mod.collect_candidates(root, mod.MAX_BYTES_DEFAULT)
    dest = root / "artifacts" / "backups" / "untracked_R.zip"
    mod.write_snapshot(root, files, dest)
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--root", str(root), "--restore-list", str(dest)])
    assert rc == 0
    assert "research/a.txt" in buf.getvalue()
    after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert before == after  # restore-list writes nothing
