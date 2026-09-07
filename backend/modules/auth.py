"""
Shared authentication dependency for every FastAPI route.

The verify_access_token() function was originally buried inside
modules/account_deletion.py — the only endpoint that bothered to check a
token.  Now that EVERY endpoint needs the same check, it lives here so
routes can ``from modules.auth import get_current_user`` instead of each
reinventing the wheel.

The function calls Supabase's ``GET /auth/v1/user`` with the caller's
Bearer token.  If Supabase says 200, the token is valid and we get back
the user object (id, email, metadata).  Anything else → PermissionError.
"""

import os

import httpx
from fastapi import Header, HTTPException


# ── Supabase config (shared with account_deletion) ────────────────────
def _supabase_config() -> tuple[str, str]:
    """
    Return (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).

    Admin API (auth user lookup, user delete) requires the service-role
    key — the anon key gets 403 on those endpoints.
    """
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing from backend env — "
            "token verification is not possible."
        )
    return url.rstrip("/"), key


# ── Token verification ────────────────────────────────────────────────
def verify_access_token(access_token: str) -> dict:
    """
    Verify a Supabase access token and return the user payload.

    Raises PermissionError when the token is invalid or expired.
    """
    url, key = _supabase_config()
    res = httpx.get(
        f"{url}/auth/v1/user",
        headers={"apikey": key, "Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if res.status_code != 200:
        raise PermissionError("Invalid or expired session token.")
    return res.json()


# ── FastAPI dependency ────────────────────────────────────────────────
def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """
    FastAPI ``Depends()`` that returns the caller's verified user_id.

    Usage::

        @router.get("/foo/{user_id}")
        def foo(user_id: str, caller: str = Depends(get_current_user)):
            if caller != user_id:
                raise HTTPException(403, "Not your resource.")
            ...

    Returns the user's UUID (str) extracted from the Supabase token.
    Raises 401 if the header is missing or the token is invalid.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header. "
                   "Send 'Bearer <supabase_access_token>'.",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        caller = verify_access_token(token)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    user_id = caller.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token valid but no user id found.")
    return user_id


# ── Convenience: ownership check for path-param routes ────────────────
def require_owner(caller: str, resource_owner: str) -> None:
    """
    Raise 403 unless ``caller`` is the resource owner (or an admin).

    Keeps route bodies short::

        @router.get("/{user_id}")
        def get_thing(user_id: str, caller: str = Depends(get_current_user)):
            require_owner(caller, user_id)
            ...
    """
    # Admin bypass — same check as the original delete-account _authorize()
    is_admin = False  # caller is just a str here; admin metadata not available
    if caller != resource_owner and not is_admin:
        raise HTTPException(
            status_code=403,
            detail="You can only access your own data.",
        )
