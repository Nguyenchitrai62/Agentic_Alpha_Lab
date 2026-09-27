"""Google sign-in -> signed session tokens; roles: admin (ADMIN_EMAILS in .env), viewer (approved), pending."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

from fastapi import Depends, HTTPException, Request

from . import db
from .config import SETTINGS

try:
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token as g_id_token
except ImportError:  # pragma: no cover
    g_requests = g_id_token = None

ISS = "agentic-alpha-lab"
log = logging.getLogger("uvicorn.error")
_google_req = g_requests.Request() if g_requests else None


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(msg: bytes) -> str:
    return _b64e(hmac.new(SETTINGS.session_secret.encode(), msg, hashlib.sha256).digest())


def issue_session(email: str) -> tuple[str, int]:
    exp = int(time.time()) + SETTINGS.session_ttl_seconds
    head = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64e(json.dumps({"iss": ISS, "sub": email, "exp": exp}).encode())
    return f"{head}.{body}.{_sign(f'{head}.{body}'.encode())}", exp


def _read_session(token: str) -> str:
    try:
        head, body, sig = token.split(".")
    except ValueError as exc:
        raise HTTPException(401, "Invalid session.") from exc
    if not hmac.compare_digest(sig, _sign(f"{head}.{body}".encode())):
        raise HTTPException(401, "Invalid session.")
    payload = json.loads(_b64d(body))
    if payload.get("iss") != ISS or int(payload.get("exp", 0)) < time.time():
        raise HTTPException(401, "Session expired. Sign in again.")
    return str(payload["sub"]).lower()


def role_for(email: str) -> str:
    email = email.lower()
    if email in SETTINGS.admin_emails:
        return "admin"
    if email in SETTINGS.viewer_emails or SETTINGS.allow_any_google_viewer:
        return "viewer"
    u = db.one("SELECT role, approved FROM users WHERE email = ?", (email,))
    if u and u["approved"]:
        return "viewer"  # admin comes only from ADMIN_EMAILS in .env, never from the database
    return "pending"


def verify_google(credential: str) -> dict:
    if not SETTINGS.google_client_id:
        raise HTTPException(500, "GOOGLE_CLIENT_ID is not configured on the backend (.env).")
    if g_id_token is None:
        raise HTTPException(500, "google-auth is not installed on the backend.")
    try:
        info = g_id_token.verify_oauth2_token(credential, _google_req, SETTINGS.google_client_id, clock_skew_in_seconds=60)
    except ValueError as exc:
        log.warning("Google token rejected: %s", exc)
        raise HTTPException(401, f"Google sign-in token is invalid or expired ({exc}).") from exc
    if not info.get("email_verified"):
        raise HTTPException(401, "Google account email is not verified.")
    return info


def login(credential: str) -> dict:
    info = verify_google(credential)
    email = info["email"].lower()
    now = db.now_ms()
    role = role_for(email)
    with db.write() as c:
        c.execute(
            "INSERT INTO users(email, name, picture, role, approved, first_seen, last_seen) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(email) DO UPDATE SET name=excluded.name, picture=excluded.picture, last_seen=excluded.last_seen",
            (email, info.get("name"), info.get("picture"), "admin" if role == "admin" else "viewer",
             1 if role in ("admin", "viewer") else 0, now, now))
    token, exp = issue_session(email)
    return {"token": token, "expires_at": exp, "user": {"email": email, "name": info.get("name"),
                                                         "picture": info.get("picture"), "role": role}}


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def is_local_request(request: Request) -> bool:
    """True only for a request made on this machine directly to uvicorn.

    Tunnelled requests also arrive from 127.0.0.1 (cloudflared), but Cloudflare always adds CF-Connecting-IP / CF-Ray and
    keeps the public Host header, so they never qualify. The Host check also blocks DNS-rebinding pages.
    """
    client = request.client.host if request.client else ""
    if client not in _LOOPBACK:
        return False
    if any(h in request.headers for h in ("cf-connecting-ip", "cf-ray", "cf-visitor", "x-forwarded-for")):
        return False
    host = request.headers.get("host", "").lower()
    host = host.rsplit(":", 1)[0] if not host.endswith("]") else host
    return host in _LOCAL_HOSTS


def current_user(request: Request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        if SETTINGS.local_no_auth and SETTINGS.admin_emails and is_local_request(request):
            return {"email": SETTINGS.admin_emails[0], "role": "admin", "name": "Local admin", "picture": None, "local": True}
        return None
    email = _read_session(auth[7:].strip())
    u = db.one("SELECT name, picture FROM users WHERE email = ?", (email,)) or {}
    return {"email": email, "role": role_for(email), "name": u.get("name"), "picture": u.get("picture")}


def require_viewer(user: dict | None = Depends(current_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Sign in with Google.")
    if user["role"] not in ("viewer", "admin"):
        raise HTTPException(403, "Your account is waiting for admin approval.")
    return user


def require_admin(user: dict | None = Depends(current_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Sign in with Google.")
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only.")
    return user
