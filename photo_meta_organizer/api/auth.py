"""Per-launch token for the desktop app (PMO-26, decision D5).

The packaged Electron shell generates a random token at every launch, hands it to the
backend in the ``PMO_API_TOKEN`` environment variable (never on the command line, where
other processes could list it) and sets it as an ``HttpOnly; SameSite=Strict`` cookie
in its own browser session before loading the UI. Every request the UI makes, including
``<img>`` thumbnails, ``/raw`` and canvas reads, carries the cookie; a web page in the
user's normal browser, or any other client, does not have it and gets 401.

Only ``/health`` is open (the shell probes it before the window exists); without the
cookie it reports status only, nothing about the library.

Without a token (plain ``uvicorn``, ``npm run desktop:dev`` through the Vite proxy) the
API stays open, protected by the Host allow-list and CORS rules (PMO-11).
"""

import hmac
import json
from collections.abc import Awaitable, Callable, MutableMapping
from http.cookies import SimpleCookie
from typing import Any

TOKEN_COOKIE = "pmo_token"
OPEN_PATHS = frozenset({"/health"})

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def cookie_token(scope: Scope) -> str | None:
    """The ``pmo_token`` cookie of an HTTP request, if any."""
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(value.decode("latin-1"))
            except Exception:  # a malformed Cookie header is simply "no token"
                return None
            morsel = jar.get(TOKEN_COOKIE)
            return morsel.value if morsel else None
    return None


def is_authenticated(scope: Scope, token: str) -> bool:
    presented = cookie_token(scope)
    return presented is not None and hmac.compare_digest(presented.encode(), token.encode())


class TokenCookieMiddleware:
    """Reject every HTTP request without the launch token cookie, except ``OPEN_PATHS``."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("path") in OPEN_PATHS
            or is_authenticated(scope, self.token)
        ):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"detail": "Not authenticated"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
