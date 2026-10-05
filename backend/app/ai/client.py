"""Provider-agnostic AI client: ordered fallback, per-error retry policy, validated JSON output."""
import asyncio
import logging
from typing import Awaitable, Callable, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.errors import (
    AIAllProvidersFailedError, AIError, AIInvalidResponseError, AINotConfiguredError,
)
from app.ai.json_utils import extract_json
from app.ai.providers import REGISTRY, AIProvider
from app.core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def _summarise(err: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors()[:6])


class AIClient:
    def __init__(self, providers: Optional[list[AIProvider]] = None, sleep: Callable[[float], Awaitable] = asyncio.sleep):
        self._providers = providers
        self._sleep = sleep

    # ── provider selection ─────────────────────────
    def providers(self, need_vision: bool = False) -> list[AIProvider]:
        if self._providers is not None:
            candidates = self._providers
        else:
            candidates = [REGISTRY[n]() for n in settings.AI_PROVIDER_ORDER if n in REGISTRY]
        ready = [p for p in candidates if p.is_configured() and (p.supports_vision or not need_vision)]
        if not ready:
            what = "vision-capable AI provider (set GEMINI_API_KEY or OPENAI_API_KEY)" if need_vision \
                else "AI provider (set GROQ_API_KEY, GEMINI_API_KEY or OPENAI_API_KEY)"
            raise AINotConfiguredError(f"No {what} configured")
        return ready

    # ── retry policy ───────────────────────────────
    async def _with_retry(self, call: Callable[[], Awaitable[str]]) -> str:
        attempts = 1 + max(settings.AI_MAX_RETRIES, 0)
        for i in range(attempts):
            try:
                return await call()
            except AIError as e:
                if not e.retryable or i == attempts - 1:
                    raise
                delay = settings.AI_RETRY_BASE_DELAY * (2 ** i)
                logger.info("Retrying %s after %s in %.1fs", e.provider, type(e).__name__, delay)
                await self._sleep(delay)
        raise AssertionError("unreachable")

    # ── plain text ─────────────────────────────────
    async def complete(self, prompt: str, system: str = "", max_tokens: int = 1024,
                       temperature: float = 0.7) -> tuple[str, str]:
        """Returns (text, provider_name)."""
        failures: list[tuple[str, AIError]] = []
        for p in self.providers():
            try:
                text = await self._with_retry(lambda p=p: p.generate(prompt, system, max_tokens, temperature))
                return text, p.name
            except AIError as e:
                e.provider = e.provider or p.name
                failures.append((p.name, e))
                logger.warning("%s failed (%s: %s)", p.name, type(e).__name__, e.message)
                if not e.fallback:
                    raise
        raise AIAllProvidersFailedError(failures)

    # ── validated JSON ─────────────────────────────
    async def _json_loop(self, providers: list[AIProvider], first_call: Callable[[AIProvider], Awaitable[str]],
                         model: Type[T], system: str, max_tokens: int,
                         check: Optional[Callable[[T], None]] = None) -> tuple[T, str]:
        def parse(raw: str) -> T:
            obj = model.model_validate(extract_json(raw))
            if check:
                try:
                    check(obj)
                except ValueError as e:          # semantic rule failed → same repair path as bad JSON
                    raise AIInvalidResponseError(str(e)) from e
            return obj

        failures: list[tuple[str, AIError]] = []
        for p in providers:
            try:
                raw = await self._with_retry(lambda p=p: first_call(p))
                try:
                    return parse(raw), p.name
                except (AIInvalidResponseError, ValidationError) as first_err:
                    reason = first_err.message if isinstance(first_err, AIInvalidResponseError) else _summarise(first_err)
                    logger.info("%s returned invalid output (%s) — asking for a repair", p.name, reason)
                    repair = (f"Your previous reply was invalid: {reason}\n\nPrevious reply:\n{raw[:4000]}\n\n"
                              "Return ONLY a corrected JSON object that satisfies every rule. No commentary.")
                    raw2 = await self._with_retry(lambda p=p: p.generate(repair, system, max_tokens, 0.1))
                    try:
                        return parse(raw2), p.name
                    except (AIInvalidResponseError, ValidationError) as second_err:
                        msg = second_err.message if isinstance(second_err, AIInvalidResponseError) else _summarise(second_err)
                        raise AIInvalidResponseError(msg, p.name) from second_err
            except AIError as e:
                e.provider = e.provider or p.name
                failures.append((p.name, e))
                logger.warning("%s failed (%s: %s)", p.name, type(e).__name__, e.message)
                if not e.fallback:
                    raise
        if failures and all(isinstance(e, AIInvalidResponseError) for _, e in failures):
            raise AIInvalidResponseError("; ".join(f"{p}: {e.message}" for p, e in failures))
        raise AIAllProvidersFailedError(failures)

    async def complete_json(self, prompt: str, model: Type[T], system: str = "", max_tokens: int = 1024,
                            temperature: float = 0.4, check: Optional[Callable[[T], None]] = None) -> tuple[T, str]:
        """Generate, parse and Pydantic-validate. One repair attempt per provider, then falls back."""
        return await self._json_loop(
            self.providers(), lambda p: p.generate(prompt, system, max_tokens, temperature), model, system, max_tokens, check)

    async def vision_json(self, image_bytes: bytes, mime_type: str, prompt: str, model: Type[T],
                          system: str = "", max_tokens: int = 2048) -> tuple[T, str]:
        return await self._json_loop(
            self.providers(need_vision=True), lambda p: p.generate_vision(image_bytes, mime_type, prompt),
            model, system, max_tokens)


_client: Optional[AIClient] = None


def get_client() -> AIClient:
    global _client
    if _client is None:
        _client = AIClient()
    return _client


def set_client(client: Optional[AIClient]) -> None:
    """Swap the process-wide client (used by tests)."""
    global _client
    _client = client
