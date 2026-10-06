"""Tests for scripts/restart_all.sh + scripts/restart_all.ps1 (static only).

The scripts themselves are NEVER executed here (the assignment forbids running
them): these tests assert the plan content (canonical commands, order,
idempotence markers, safety rails) identically in both shells, and check plan
generation + idempotence against a fake process list with a small model that
mirrors the scripts' skip-if-running rules.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "scripts" / "restart_all.sh"
PS1 = ROOT / "scripts" / "restart_all.ps1"

BACKEND = "uvicorn backend.server:app --host 127.0.0.1 --port 8724"
LOOP = "artifacts/research/advisor_shadow/loop.sh"
CARRY = "scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry"
BOTS = [
    ("paper", "artifacts/bot/paper",
     "-m bot.run --mode paper --equity 5000 --interval 25"),
    ("d17bf", "artifacts/bot/paper_d17bf",
     "--corr-size --dip-mult 1.7 --bear-book --interval 25 --tag d17bf"),
    ("d13bf", "artifacts/bot/paper_d13bf",
     "--corr-size --dip-mult 1.3 --bear-book --interval 25 --tag d13bf"),
    ("d17bfg2", "artifacts/bot/paper_d17bfg2",
     "--corr-size --dip-mult 1.7 --dip-gross-cap 2.0 --bear-book --adopt-fresh --interval 25 --tag d17bfg2"),
    ("g2k20", "artifacts/bot/paper_g2k20",
     "--corr-size --dip-mult 2.0 --dip-gross-cap 2.0 --bear-book --adopt-fresh --interval 25 --tag g2k20"),
]


def _read(p: Path) -> str:
    assert p.exists(), f"missing {p}"
    return p.read_text(encoding="utf-8")


def test_scripts_exist():
    assert SH.exists() and PS1.exists()


def _norm(body: str) -> str:
    return body.replace("\\\\", "/")


def test_canonical_commands_in_both_shells():
    sh, ps = _read(SH), _read(PS1)
    assert BACKEND in _norm(sh), "backend uvicorn line missing (sh)"
    assert BACKEND in _norm(ps), "backend uvicorn line missing (ps1)"
    assert LOOP in _norm(sh), "advisor loop.sh line missing (sh)"
    assert LOOP in _norm(ps), "advisor loop.sh line missing (ps1)"
    assert CARRY in _norm(sh), "carry_paper line missing (sh)"
    assert CARRY in _norm(ps), "carry_paper line missing (ps1)"
    for body, name in ((sh, "sh"), (ps, "ps1")):
        norm = _norm(body)
        assert "3600" in norm, f"carry 3600s interval missing ({name})"
        for tag, _d, frag in BOTS:
            if name == "sh":
                assert frag in norm, f"bot {tag} exact args missing (sh)"
            else:
                # ps1 holds the same args as an array; every token must be present
                for tok in frag.split():
                    assert tok in norm, f"bot {tag} arg {tok!r} missing (ps1)"
        assert "bot_health.py" in norm and "daily_status.py" in norm
        assert "--mode" in norm and "paper" in norm


def test_order_backend_before_bots_before_health():
    for p in (SH, PS1):
        body = _norm(_read(p))
        # section markers (1)..(5): header comment and code sections share the order
        idx = [body.index(f"({n})") for n in ("1", "2", "3", "4", "5")]
        assert idx == sorted(idx), f"wrong order in {p.name}"
        assert "uvicorn backend.server:app" in body
        assert "paper_d17bfg2" in body and "paper_g2k20" in body


def test_idempotence_markers_in_both_shells():
    sh, ps = _read(SH), _read(PS1)
    for body in (sh, ps):
        assert "runner.lock" in body, "runner.lock guard missing"
        assert "state.json" in body and "bak_" in body, "state.json backup missing"
        assert "JSON" in body, "state.json JSON validation missing"
        assert "--dry-run" in body or "DryRun" in body, "dry-run flag missing"
        assert "--only" in body or "-Only" in body, "only flag missing"
        for scope in ("bots", "backend", "carry"):
            assert scope in body, f"--only scope {scope} missing"
        assert "already running" in body, "skip-if-running branch missing"


def test_safety_rails_no_live_no_tunnel():
    for p in (SH, PS1):
        body = _read(p)
        assert "BOT_ALLOW_LIVE" in body, "must mention it never sets BOT_ALLOW_LIVE"
        assert "--mode testnet" not in body, f"must never start testnet ({p.name})"
        assert "--mode live" not in body, f"must never start live ({p.name})"
        # "never the public tunnel" must be stated; no tunnel invocation may exist
        assert "never the public tunnel" in body.lower(), f"missing no-tunnel rule ({p.name})"
        assert "cloudflared.exe" not in body.lower(), f"must never start the tunnel binary ({p.name})"
        assert "start-tunnel" not in body.lower(), f"must never start the tunnel ({p.name})"
        assert "Stop-Process" not in body and "kill " not in body, "must never stop processes"


# --- plan generation + idempotence with a fake process list ---
# Mirrors the scripts' rules: start a component only if no matching live
# process; backend also needs /health; dry-run starts nothing.

def plan(fake_procs, backend_healthy=True, only="all", dry_run=False):
    """Return the ordered list of actions the scripts would take.

    fake_procs: list of command-line strings (fakes, no live processes read).
    Each action is (kind, name); kind is 'start', 'skip' or 'would'.
    """
    assert only in ("all", "bots", "backend", "carry")
    acts = []

    def running(*needles, exclude=()):
        for c in fake_procs:
            if all(n in c for n in needles) and not any(e in c for e in exclude):
                return True
        return False

    if only in ("all", "backend"):
        acts.append(("skip" if backend_healthy else ("would" if dry_run else "start"), "backend"))
        loop_run = running("loop.sh")
        acts.append(("skip" if loop_run else ("would" if dry_run else "start"), "loop"))
    if only in ("all", "bots"):
        for tag, _d, _a in BOTS:
            if tag == "paper":
                hit = running("bot.run", "--mode paper", exclude=("--tag",))
            else:
                hit = running("bot.run", f"--tag {tag}")
            acts.append(("skip" if hit else ("would" if dry_run else "start"), f"bot:{tag}"))
    if only in ("all", "carry"):
        hit = running("carry_paper", "--tag carry")
        acts.append(("skip" if hit else ("would" if dry_run else "start"), "carry"))
    acts.append(("would" if dry_run else "check", "health"))
    return acts


def _all_cmdlines():
    out = ["uvicorn backend.server:app --host 127.0.0.1",
           "bash artifacts/research/advisor_shadow/loop.sh"]
    for tag, _d, a in BOTS:
        if tag == "paper":
            out.append(f".venv/Scripts/python.exe {a}")
        else:
            out.append(f".venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 {a}")
    out.append(".venv/Scripts/python.exe scripts/carry_paper.py --once --equity 5000 --f 0.5 --tag carry")
    return out


def test_plan_empty_world_starts_everything_once():
    acts = plan([], backend_healthy=False, only="all")
    starts = [a for k, a in acts if k == "start"]
    assert starts == ["backend", "loop", "bot:paper", "bot:d17bf", "bot:d13bf",
                      "bot:d17bfg2", "bot:g2k20", "carry"]


def test_plan_full_world_idempotent_second_run_starts_nothing():
    first = plan([], backend_healthy=False, only="all")
    # apply: every 'start' becomes a live fake process
    live = list(_all_cmdlines())
    second = plan(live, backend_healthy=True, only="all")
    assert [k for k, _ in second if k == "start"] == []
    assert all(k in ("skip", "check") for k, _ in second)
    # first run was all starts (idempotence base)
    assert all(k == "start" for k, _ in first if _ != "health")


def test_plan_dry_run_starts_nothing():
    acts = plan([], backend_healthy=False, only="all", dry_run=True)
    assert [k for k, _ in acts if k == "start"] == []
    assert any(a == "backend" for k, a in acts if k == "would")


def test_plan_only_scopes():
    assert {a for _, a in plan([], False, "backend") if a != "health"} == {"backend", "loop"}
    assert {a for _, a in plan([], False, "bots") if a != "health"} == \
        {"bot:paper", "bot:d17bf", "bot:d13bf", "bot:d17bfg2", "bot:g2k20"}
    assert [a for _, a in plan([], False, "carry") if a != "health"] == ["carry"]


def test_plan_partial_world_skips_only_runners_present():
    live = [".venv/Scripts/python.exe -m bot.run --mode paper --equity 5000 --corr-size --dip-mult 1.7 --bear-book --interval 25 --tag d17bf"]
    acts = dict((a, k) for k, a in plan(live, backend_healthy=True, only="bots"))
    assert acts["bot:d17bf"] == "skip"
    assert acts["bot:paper"] == "start"
    assert acts["bot:g2k20"] == "start"
