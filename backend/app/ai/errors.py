"""Typed AI failures so the client can retry, fall back or surface the right message."""
import re

# Provider SDK errors often echo the request's API key. Never let one reach logs or the UI.
_SECRET_RE = re.compile(
    r"(AIza[0-9A-Za-z_\-]{20,}|gsk_[0-9A-Za-z]{20,}|sk-[0-9A-Za-z_\-]{20,}"
    r"|Bearer\s+[0-9A-Za-z._\-]{20,}|api_key:[^\s'\"]+)"
)


def redact(text: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", text or "")

class AIError(Exception):
    status_code = 502
    retryable = False        # worth retrying on the SAME provider
    fallback = True          # worth trying the NEXT provider

    def __init__(self, message: str = "", provider: str = ""):
        message = redact(message)
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.detail = message or self.__class__.__name__


class AITimeoutError(AIError):
    status_code = 504
    retryable = True


class AIRateLimitError(AIError):
    status_code = 429
    retryable = True


class AIAuthError(AIError):
    status_code = 502
    fallback = True          # a bad key on one provider shouldn't block the others


class AIInvalidResponseError(AIError):
    status_code = 502
    retryable = False


class AIProviderUnavailableError(AIError):
    status_code = 503
    retryable = True


class AINotConfiguredError(AIError):
    status_code = 503
    fallback = False


class AIAllProvidersFailedError(AIError):
    """Raised when every configured provider failed. `failures` lists (provider, error)."""
    status_code = 503

    def __init__(self, failures: list[tuple[str, AIError]]):
                # For invalid-output failures the reason is useful (and contains no secrets); show it.
        summary = "; ".join(
            f"{p}: {type(e).__name__}" + (f" — {e.message}" if isinstance(e, AIInvalidResponseError) and e.message else "")
            for p, e in failures)
        super().__init__(f"All AI providers failed ({summary})")
        self.failures = failures
        # Surface the most actionable status: rate limits/timeouts keep their own code
        kinds = {type(e) for _, e in failures}
        if kinds == {AIRateLimitError}:
            self.status_code = 429
        elif kinds == {AIAuthError}:
            self.status_code = 502


def classify_exception(exc: Exception, provider: str) -> AIError:
    """Map any SDK/HTTP exception to a typed AIError without importing the SDKs."""
    if isinstance(exc, AIError):
        return exc
    name = type(exc).__name__.lower()
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    code = getattr(exc, "code", None)
    msg = redact(str(exc))[:300]

    if "timeout" in name or "deadline" in name or status in (408, 504):
        return AITimeoutError(msg, provider)
    if "ratelimit" in name or "resourceexhausted" in name or "toomanyrequests" in name or status == 429:
        return AIRateLimitError(msg, provider)
    if ("auth" in name or "permission" in name or "unauthenticated" in name or "invalidargument" in name and "api key" in msg.lower()
            or status in (401, 403)):
        return AIAuthError(msg, provider)
    if "connection" in name or "unavailable" in name or "internalserver" in name or "serviceunavailable" in name \
            or (isinstance(status, int) and status >= 500) or code in (500, 502, 503):
        return AIProviderUnavailableError(msg, provider)
    return AIProviderUnavailableError(f"{type(exc).__name__}: {msg}", provider)
