"""Backend settings, read from the repo-root .env (never committed)."""

from __future__ import annotations

import logging
import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(x.strip().lower() if "@" in x else x.strip() for x in raw.split(",") if x.strip())


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    port: int = int(os.getenv("WEB_PORT", "8724"))
    host: str = os.getenv("WEB_HOST", "127.0.0.1")
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    admin_emails: tuple[str, ...] = field(default_factory=lambda: _csv("ADMIN_EMAILS", "trainguyenchi30@gmail.com"))
    viewer_emails: tuple[str, ...] = field(default_factory=lambda: _csv("VIEWER_EMAILS"))
    allow_any_google_viewer: bool = _bool("ALLOW_ANY_GOOGLE_VIEWER", False)
    session_secret: str = os.getenv("AUTH_SESSION_SECRET", "")
    session_ttl_seconds: int = int(os.getenv("AUTH_SESSION_TTL_SECONDS", str(7 * 24 * 3600)))
    cors_origins: tuple[str, ...] = field(default_factory=lambda: _csv("CORS_ALLOW_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500"))
    cors_origin_regex: str = os.getenv("CORS_ALLOW_ORIGIN_REGEX", r"https://([a-z0-9-]+\.)*(vercel\.app|nguyenchitrai\.id\.vn)")
    db_path: Path = Path(os.getenv("WEB_DB_PATH", str(ROOT / "artifacts/web/app.db")))
    scheduler_enabled: bool = _bool("WEB_SCHEDULER_ENABLED", True)
    schedule_offset_minutes: int = int(os.getenv("WEB_SCHEDULE_OFFSET_MINUTES", "8"))
    default_equity_usdt: float = float(os.getenv("WEB_DEFAULT_EQUITY_USDT", "10000"))
    python_exe: str = os.getenv("WEB_PYTHON_EXE", str(ROOT / ".venv/Scripts/python.exe"))
    # requests made on this machine (not through the Cloudflare tunnel) are treated as the admin without Google sign-in
    local_no_auth: bool = _bool("WEB_LOCAL_NO_AUTH", True)


SETTINGS = Settings()

# console log of the pipeline jobs and the scheduler (uvicorn prints the HTTP side)
log = logging.getLogger("alphalab")
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-5s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(_h)
    log.setLevel(os.getenv("WEB_LOG_LEVEL", "INFO").upper())
    log.propagate = False
if not SETTINGS.session_secret:
    # a per-process secret still works (sessions reset on restart); set AUTH_SESSION_SECRET in .env to persist them
    object.__setattr__(SETTINGS, "session_secret", secrets.token_urlsafe(48))
