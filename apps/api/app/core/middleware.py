import json

from fastapi import Request
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=()"
        # CSP: API only serves JSON — no scripts, no images, no frames needed.
        # This stops a CORS misconfiguration or XSS in error pages from doing anything.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response


class RequestBodyTooLarge(Exception):
    """Raised by RequestSizeLimitMiddleware when a streamed body exceeds the cap.

    main.py registers an exception handler that turns this into a clean 413 so the
    body is bounded even for chunked / Content-Length-omitted uploads.
    """


class RequestSizeLimitMiddleware:
    """Pure-ASGI request body-size guard.

    Trusts a valid ``Content-Length`` for a fast up-front reject, but ALSO counts
    bytes as the body streams in, so a request that omits Content-Length / uses
    ``Transfer-Encoding: chunked`` cannot bypass the cap. (The previous
    BaseHTTPMiddleware version checked only the header — bypassable — and raised an
    unhandled ValueError, hence a noisy 500, on a malformed header value.)
    """

    def __init__(self, app: ASGIApp, max_bytes: int = 10 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await self._send_error(send, 400, "bad_request", "Invalid Content-Length header")
                return
            if declared > self.max_bytes:
                await self._send_error(send, 413, "payload_too_large", "Request body exceeds size limit")
                return

        seen = 0

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b"") or b"")
                if seen > self.max_bytes:
                    raise RequestBodyTooLarge()
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _send_error(send: Send, status_code: int, code: str, message: str) -> None:
        body = json.dumps(
            {"ok": False, "data": None, "error": {"code": code, "message": message, "details": None}}
        ).encode()
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
