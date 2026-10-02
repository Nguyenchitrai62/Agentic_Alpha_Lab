"""Google sign-in, short access JWTs and rotating, revocable refresh sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

from fastapi import Depends, HTTPException, Request

from . import catalog, db
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


def issue_session(email: str, session_id: str | None = None) -> tuple[str, int]:
    exp = int(time.time()) + SETTINGS.access_ttl_seconds
    head = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64e(json.dumps({"iss": ISS, "sub": email.lower(), "exp": exp,
                           "iat": int(time.time()), "kind": "access", "sid": session_id}).encode())
    return f"{head}.{body}.{_sign(f'{head}.{body}'.encode())}", exp


def _session_payload(token: str) -> dict:
    try:
        head, body, sig = token.split(".")
        signature_valid = hmac.compare_digest(sig, _sign(f"{head}.{body}".encode()))
    except (ValueError, TypeError) as exc:
        raise HTTPException(401, "Invalid session.") from exc
    if not signature_valid:
        raise HTTPException(401, "Invalid session.")
    try:
        header, payload = json.loads(_b64d(head)), json.loads(_b64d(body))
        valid = (header.get("alg") == "HS256" and header.get("typ") == "JWT"
                 and payload.get("iss") == ISS and payload.get("kind") == "access"
                 and int(payload.get("exp", 0)) > time.time()
                 and isinstance(payload.get("sub"), str) and bool(payload["sub"]))
    except (ValueError, TypeError, AttributeError, UnicodeError, OverflowError) as exc:
        raise HTTPException(401, "Invalid session.") from exc
    if not valid:
        raise HTTPException(401, "Session expired. Sign in again.")
    return payload


def _read_session(token: str) -> str:
    return _session_payload(token)["sub"].lower()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_refresh(c, sid: str, expires: int) -> str:
    token = secrets.token_urlsafe(48)
    c.execute("INSERT INTO auth_refresh_tokens(token_hash, session_id, expires_at) VALUES(?,?,?)",
              (_token_hash(token), sid, expires))
    return token


def _user(email: str) -> dict:
    u = db.one("SELECT name, picture, access_revoked FROM users WHERE email = ?", (email,)) or {}
    return catalog.with_permissions({"email": email, "role": role_for(email),
                                     "access_revoked": bool(u.get("access_revoked")) and email not in SETTINGS.admin_emails,
                                     "name": u.get("name"), "picture": u.get("picture")})


def _tokens(email: str, sid: str, refresh: str, expires: int) -> dict:
    token, exp = issue_session(email, sid)
    return {"access_token": token, "token": token, "token_type": "bearer", "expires_at": exp,
            "refresh_token": refresh, "refresh_expires_at": expires, "user": _user(email)}


def create_session(email: str) -> dict:
    email = email.lower()
    sid = secrets.token_urlsafe(32)
    expires = int(time.time()) + SETTINGS.refresh_ttl_seconds
    with db.write() as c:
        c.execute("INSERT INTO auth_sessions(id, email, expires_at) VALUES(?,?,?)", (sid, email, expires))
        refresh = _new_refresh(c, sid, expires)
    return _tokens(email, sid, refresh, expires)


def refresh_session(token: str) -> dict:
    now = int(time.time())
    invalid = False
    with db.write() as c:
        row = c.execute("SELECT r.*, s.email, s.revoked, s.expires_at AS session_exp "
                        "FROM auth_refresh_tokens r JOIN auth_sessions s ON s.id=r.session_id "
                        "WHERE token_hash=?", (_token_hash(token),)).fetchone()
        if row is None or row["revoked"] or min(row["expires_at"], row["session_exp"]) <= now:
            invalid = True
        elif row["used_at"] is not None:
            # Commit revocation even though the request will fail.
            c.execute("UPDATE auth_sessions SET revoked=1 WHERE id=?", (row["session_id"],))
            invalid = True
        else:
            c.execute("UPDATE auth_refresh_tokens SET used_at=? WHERE token_hash=?", (now, _token_hash(token)))
            refresh = _new_refresh(c, row["session_id"], row["session_exp"])
    if invalid:
        raise HTTPException(401, "Refresh token expired or revoked. Sign in again.")
    return _tokens(row["email"], row["session_id"], refresh, row["session_exp"])


def revoke_session(token: str) -> None:
    with db.write() as c:
        c.execute("UPDATE auth_sessions SET revoked=1 WHERE id IN "
                  "(SELECT session_id FROM auth_refresh_tokens WHERE token_hash=?)", (_token_hash(token),))


def role_for(email: str) -> str:
    email = email.lower()
    if email in SETTINGS.admin_emails:
        return "admin"
    u = db.one("SELECT approved, access_revoked FROM users WHERE email = ?", (email,))
    if u and u["access_revoked"]:
        return "pending"
    if email in SETTINGS.viewer_emails or SETTINGS.allow_any_google_viewer:
        return "viewer"
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
        raise HTTPException(401, "Google sign-in token is invalid or expired.") from exc
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
    return create_session(email)


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
    if request.headers.get("sec-fetch-site") == "cross-site":
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
            return catalog.with_permissions({"email": SETTINGS.admin_emails[0], "role": "admin", "name": "Local admin", "picture": None, "local": True})
        return None
    payload = _session_payload(auth[7:].strip())
    if not isinstance(payload.get("sid"), str) or len(payload["sid"]) > 128:
        raise HTTPException(401, "Invalid session.")
    session = db.one("SELECT email, revoked, expires_at FROM auth_sessions WHERE id=?", (payload.get("sid"),))
    if not session or session["revoked"] or session["expires_at"] <= time.time() or session["email"] != payload["sub"]:
        raise HTTPException(401, "Session revoked. Sign in again.")
    return _user(payload["sub"])


def require_viewer(user: dict | None = Depends(current_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Sign in with Google.")
    if user["role"] not in ("viewer", "admin"):
        if user.get("access_revoked"):
            raise HTTPException(403, "Your account access has been revoked by the admin.")
        raise HTTPException(403, "Your account is waiting for admin approval.")
    return user


def require_admin(user: dict | None = Depends(current_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Sign in with Google.")
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only.")
    return user
