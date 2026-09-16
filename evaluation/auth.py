"""Authenticates against the Node gateway (backend/src/controllers/auth.controller.js)
and hands back an httpx.AsyncClient that carries the resulting session cookie
on every subsequent request — exactly how the frontend stays logged in.

Nothing here talks to FastAPI or Mongo directly; it only ever sees what the
gateway's public HTTP surface exposes, same as your golden-set questions will.
"""

import httpx
from config import settings


async def get_authenticated_client() -> httpx.AsyncClient:
    """Log in once, return a client that will silently include the `token`
    cookie (see auth.middleware.js) on every request until it expires (7d,
    per auth.controller.js's generateToken)."""
    client = httpx.AsyncClient(base_url=settings.BASE_URL, timeout=settings.REQUEST_TIMEOUT_SEC)

    print(f"DEBUG EMAIL: '{settings.EVAL_EMAIL}'")
    print(f"DEBUG PASSWORD: '{settings.EVAL_PASSWORD}'")  
      
    resp = await client.post(
        "/auth/login",
        json={"email": settings.EVAL_EMAIL, "password": settings.EVAL_PASSWORD},
    )

    if resp.status_code == 401:
        await client.aclose()
        raise RuntimeError(
            "Login failed (401) — check EVAL_EMAIL/EVAL_PASSWORD in evaluation/.env. "
            "If this account doesn't exist yet, register it first:\n"
            "  curl -X POST http://localhost:5000/auth/register "
            '-H "Content-Type: application/json" '
            '-d \'{"email": "...", "password": "..."}\'\n'
            "...then ingest the same PDFs used to build golden_dataset.json under that account."
        )
    resp.raise_for_status()

    # httpx.AsyncClient persists Set-Cookie from the response into client.cookies
    # automatically, so `client` now carries the `token` cookie on every future
    # request without any extra wiring — this IS the auth mechanism, not a bonus.
    if "token" not in client.cookies:
        await client.aclose()
        raise RuntimeError(
            "Login succeeded (200) but no `token` cookie was set. "
            "Check NODE_ENV / cookie settings in backend/server.js if you're "
            "running the gateway over plain HTTP with secure cookies forced on."
        )

    print(f"✅ Authenticated as {settings.EVAL_EMAIL}")
    return client