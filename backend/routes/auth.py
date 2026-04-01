"""
Auth routes — GitHub OAuth flow.

GET  /auth/login     -> show login page or redirect to GitHub OAuth
GET  /auth/callback  -> handle OAuth callback, set session cookie
GET  /auth/logout    -> clear session cookie
GET  /auth/status    -> return current auth status (for frontend)
"""

import html
import secrets
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from backend.services.auth_service import (
    ALLOWED_GITHUB_USERS,
    COOKIE_NAME,
    SESSION_MAX_AGE,
    create_session_cookie,
    exchange_code_for_token,
    get_github_auth_url,
    get_github_username,
    get_session_user,
    is_tailscale_request,
)

router = APIRouter(prefix="/auth")

# Simple in-memory state store (prevents CSRF)
# State tokens expire after 10 minutes
_pending_states: dict[str, float] = {}


def _clean_states():
    now = time.time()
    expired = [k for k, v in _pending_states.items() if now - v > 600]
    for k in expired:
        del _pending_states[k]


def _safe_next_url(url: str) -> str:
    """Validate redirect target to prevent open redirects."""
    if not url or not url.startswith("/") or url.startswith("//"):
        return "/"
    return url


@router.get("/login")
async def login(request: Request):
    """Show login page or redirect to GitHub OAuth."""
    # If 'go' param is set, redirect to GitHub
    if request.query_params.get("go"):
        _clean_states()
        state = secrets.token_urlsafe(32)
        _pending_states[state] = time.time()
        next_url = _safe_next_url(request.query_params.get("next", "/"))
        auth_url = get_github_auth_url(state)
        response = RedirectResponse(url=auth_url)
        response.set_cookie("paladin_next", next_url, max_age=600, httponly=True)
        return response

    # Show login page
    next_url = html.escape(_safe_next_url(request.query_params.get("next", "/")))
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paladin Control Plane — Sign In</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f172a; color: #e2e8f0;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh;
  }}
  .card {{
    background: #1e293b; border: 1px solid #334155;
    border-radius: 12px; padding: 2.5rem 2rem; width: 100%;
    max-width: 360px; text-align: center;
  }}
  .logo {{ font-size: 2rem; margin-bottom: 0.5rem; }}
  h1 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 0.25rem; }}
  p {{ font-size: 0.875rem; color: #94a3b8; margin-bottom: 2rem; }}
  .btn {{
    display: inline-flex; align-items: center; gap: 10px;
    background: #238636; color: #fff; border: none;
    border-radius: 8px; padding: 0.75rem 1.5rem;
    font-size: 0.9375rem; font-weight: 500;
    text-decoration: none; cursor: pointer;
    transition: background 0.15s;
  }}
  .btn:hover {{ background: #2ea043; }}
  .btn svg {{ width: 20px; height: 20px; fill: currentColor; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">&#9881;</div>
  <h1>Paladin Control Plane</h1>
  <p>Sign in to manage your homelab projects</p>
  <a class="btn" href="/auth/login?go=1&next={next_url}">
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57
               0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41
               -1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815
               2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925
               0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23
               .96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65
               .24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925
               .435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57
               A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
    </svg>
    Sign in with GitHub
  </a>
</div>
</body>
</html>""")


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """Handle GitHub OAuth callback."""
    if error:
        return HTMLResponse(
            f"<h1>Login failed</h1><p>{html.escape(error)}</p><a href='/'>Back</a>",
            status_code=400,
        )

    if state not in _pending_states:
        return HTMLResponse(
            "<h1>Login failed</h1><p>Invalid state. Please try again.</p>"
            "<a href='/auth/login'>Login</a>",
            status_code=400,
        )
    del _pending_states[state]

    if not code:
        return HTMLResponse(
            "<h1>Login failed</h1><p>No code received.</p>"
            "<a href='/auth/login'>Login</a>",
            status_code=400,
        )

    token = await exchange_code_for_token(code)
    if not token:
        return HTMLResponse(
            "<h1>Login failed</h1><p>Could not exchange code for token.</p>"
            "<a href='/auth/login'>Login</a>",
            status_code=400,
        )

    username = await get_github_username(token)
    if not username:
        return HTMLResponse(
            "<h1>Login failed</h1><p>Could not fetch GitHub user.</p>"
            "<a href='/auth/login'>Login</a>",
            status_code=400,
        )

    if username not in ALLOWED_GITHUB_USERS:
        return HTMLResponse(
            f"<h1>Access denied</h1><p>{html.escape(username)} is not authorised.</p>",
            status_code=403,
        )

    session_value = create_session_cookie(username)
    next_url = _safe_next_url(request.cookies.get("paladin_next", "/"))

    response = RedirectResponse(url=next_url, status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        session_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    response.delete_cookie("paladin_next")
    return response


@router.get("/logout")
async def logout():
    """Clear session cookie and redirect to login."""
    response = RedirectResponse(url="/auth/login")
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/status")
async def auth_status(request: Request):
    """Return current auth status. Used by frontend to show user info."""
    if is_tailscale_request(request):
        return JSONResponse({
            "authenticated": True,
            "method": "tailscale",
            "user": "local",
        })
    user = get_session_user(request)
    if user:
        return JSONResponse({
            "authenticated": True,
            "method": "github",
            "user": user,
        })
    return JSONResponse({
        "authenticated": False,
        "method": None,
        "user": None,
    })
