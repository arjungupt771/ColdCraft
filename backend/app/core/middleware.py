"""Security headers, request-size cap and a small in-memory rate limiter."""
import time
from collections import defaultdict, deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings

AI_PATH_PREFIXES = ("/api/v1/process-", "/api/v1/generate-email", "/api/v1/followups/schedule", "/api/v1/tasks")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Rejects requests whose declared Content-Length exceeds MAX_REQUEST_BYTES."""
    async def dispatch(self, request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.MAX_REQUEST_BYTES:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window limiter per client IP. Single-process only (fine for a local app)."""
    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        is_ai = request.url.path.startswith(AI_PATH_PREFIXES)
        limit = settings.RATE_LIMIT_AI_PER_MINUTE if is_ai else settings.RATE_LIMIT_PER_MINUTE
        key = (request.client.host if request.client else "unknown", "ai" if is_ai else "general")
        now = time.monotonic()
        window = self.hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            return JSONResponse({"detail": "Rate limit exceeded. Slow down."}, status_code=429,
                                headers={"Retry-After": "60"})
        window.append(now)
        return await call_next(request)
