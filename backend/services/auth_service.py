"""
Auth service — GitHub OAuth + Tailscale bypass.

Tailscale IPs (10.1.10.x and 100.x.x.x) are trusted and bypass auth.
All other requests require a valid GitHub OAuth session cookie.
Only ALLOWED_GITHUB_USERS can authenticate.
"""

import hashlib
import os
import time
from typing import Optional

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Configuration from environment
GITHUB_CLIENT_ID = os.environ.get("GITHUB_OAUTH_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "")
ALLOWED_GITHUB_USERS = {"PaladinEng"}
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
COOKIE_NAME = "paladin_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days in seconds

# Generate a stable session secret if not set
# (derives from client secret so it survives restarts)
if not SESSION_SECRET and GITHUB_CLIENT_SECRET:
    SESSION_SECRET = hashlib.sha256(
        f"paladin-session-{GITHUB_CLIENT_SECRET}".encode()
    ).hexdigest()

_serializer = URLSafeTimedSerializer(SESSION_SECRET) if SESSION_SECRET else None

TAILSCALE_PREFIXES = ("100.", "10.1.10.")


def is_tailscale_request(request) -> bool:
    """Return True if the request originates from a trusted internal IP.

    Only checks the TCP peer address (request.client.host) — never trust
    headers like X-Forwarded-For or CF-Connecting-IP which can be spoofed.
    Localhost (127.0.0.1) is trusted only when no Cloudflare headers are
    present, so tunnel traffic is not mistaken for local service calls.
    """
    client_ip = request.client.host if request.client else ""

    # Tailscale IPs — always trusted
    for prefix in TAILSCALE_PREFIXES:
        if client_ip.startswith(prefix):
            return True

    # Localhost — trusted only if NOT coming through Cloudflare Tunnel
    if client_ip == "127.0.0.1":
        has_cf = (request.headers.get("CF-Connecting-IP")
                  or request.headers.get("CF-Ray"))
        return not has_cf

    return False


def get_github_auth_url(state: str) -> str:
    """Return the GitHub OAuth authorization URL."""
    return (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&scope=read:user"
        f"&state={state}"
    )


async def exchange_code_for_token(code: str) -> Optional[str]:
    """Exchange OAuth code for access token. Returns token or None."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data.get("access_token")


async def get_github_username(token: str) -> Optional[str]:
    """Fetch the authenticated GitHub username."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
    if resp.status_code != 200:
        return None
    return resp.json().get("login")


def create_session_cookie(username: str) -> str:
    """Create a signed session cookie value."""
    if not _serializer:
        raise RuntimeError("SESSION_SECRET not configured")
    payload = {"user": username, "ts": int(time.time())}
    return _serializer.dumps(payload)


def verify_session_cookie(cookie_value: str) -> Optional[str]:
    """Verify a session cookie and return the GitHub username, or None if invalid."""
    if not _serializer or not cookie_value:
        return None
    try:
        payload = _serializer.loads(cookie_value, max_age=SESSION_MAX_AGE)
        username = payload.get("user")
        if username in ALLOWED_GITHUB_USERS:
            return username
        return None
    except (BadSignature, SignatureExpired):
        return None


def get_session_user(request) -> Optional[str]:
    """Extract and verify the session user from request cookies."""
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    return verify_session_cookie(cookie)


def is_authenticated(request) -> bool:
    """Return True if the request is authenticated (Tailscale or valid session)."""
    if is_tailscale_request(request):
        return True
    return get_session_user(request) is not None
