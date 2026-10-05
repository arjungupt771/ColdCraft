import pytest
from pydantic import BaseModel

from app.ai.client import AIClient
from app.ai.errors import (
    AIAllProvidersFailedError, AIAuthError, AIInvalidResponseError, AINotConfiguredError, AIProviderUnavailableError,
    AIRateLimitError, AITimeoutError, classify_exception,
)
from app.ai.json_utils import extract_json
from tests.conftest import FakeProvider, make_client


class Thing(BaseModel):
    name: str
    n: int


def seq(*outputs):
    it = iter(outputs)
    return lambda prompt, system: next(it)


async def test_primary_success():
    a, b = FakeProvider(lambda p, s: "hello", "a"), FakeProvider(lambda p, s: "other", "b")
    text, provider = await make_client(a, b).complete("hi")
    assert (text, provider) == ("hello", "a") and not b.calls


async def test_falls_back_when_primary_unavailable():
    a = FakeProvider(lambda p, s: AIProviderUnavailableError("down", "a"), "a")
    b = FakeProvider(lambda p, s: "from b", "b")
    text, provider = await make_client(a, b).complete("hi")
    assert (text, provider) == ("from b", "b")
    assert len(a.calls) == 2           # retryable: tried twice before falling back


async def test_rate_limit_is_retried_on_same_provider():
    a = FakeProvider(seq(AIRateLimitError("slow", "a"), "ok after retry"), "a")
    text, provider = await make_client(a).complete("hi")
    assert (text, provider) == ("ok after retry", "a") and len(a.calls) == 2


async def test_timeout_retried_then_fallback():
    a = FakeProvider(lambda p, s: AITimeoutError("t/o", "a"), "a")
    b = FakeProvider(lambda p, s: "b ok", "b")
    assert (await make_client(a, b).complete("x"))[1] == "b" and len(a.calls) == 2


async def test_auth_error_not_retried_but_falls_back():
    a = FakeProvider(lambda p, s: AIAuthError("bad key", "a"), "a")
    b = FakeProvider(lambda p, s: "b ok", "b")
    assert (await make_client(a, b).complete("x"))[1] == "b" and len(a.calls) == 1


async def test_all_fail_reports_each_provider():
    a = FakeProvider(lambda p, s: AIAuthError("bad key", "a"), "a")
    b = FakeProvider(lambda p, s: AIProviderUnavailableError("down", "b"), "b")
    with pytest.raises(AIAllProvidersFailedError) as ei:
        await make_client(a, b).complete("x")
    assert [name for name, _ in ei.value.failures] == ["a", "b"]
    assert ei.value.status_code == 503


async def test_all_rate_limited_maps_to_429():
    a = FakeProvider(lambda p, s: AIRateLimitError("slow", "a"), "a")
    with pytest.raises(AIAllProvidersFailedError) as ei:
        await make_client(a).complete("x")
    assert ei.value.status_code == 429


async def test_no_configured_provider():
    class Off(FakeProvider):
        def is_configured(self):
            return False
    with pytest.raises(AINotConfiguredError):
        await make_client(Off()).complete("x")


async def test_vision_skips_providers_without_vision():
    text_only = FakeProvider(lambda p, s: '{"name":"x","n":1}', "text", vision=False)
    with pytest.raises(AINotConfiguredError):
        await make_client(text_only).vision_json(b"img", "image/png", "p", Thing)


async def test_json_valid_first_try():
    p = FakeProvider(lambda pr, s: '```json\n{"name": "a", "n": 2}\n```')
    result, provider = await make_client(p).complete_json("x", Thing)
    assert result == Thing(name="a", n=2) and len(p.calls) == 1


async def test_json_repair_attempt_succeeds():
    p = FakeProvider(seq("sorry, here you go: nothing", '{"name": "fixed", "n": 1}'))
    result, _ = await make_client(p).complete_json("x", Thing)
    assert result.name == "fixed" and len(p.calls) == 2
    assert "invalid" in p.calls[1][1].lower()      # repair prompt carries the reason


async def test_json_validation_failure_repaired():
    p = FakeProvider(seq('{"name": "a", "n": "not-int"}', '{"name": "a", "n": 3}'))
    result, _ = await make_client(p).complete_json("x", Thing)
    assert result.n == 3


async def test_json_invalid_twice_falls_back_to_next_provider():
    a = FakeProvider(lambda p, s: "garbage", "a")
    b = FakeProvider(lambda p, s: '{"name": "b", "n": 1}', "b")
    result, provider = await make_client(a, b).complete_json("x", Thing)
    assert provider == "b" and len(a.calls) == 2


async def test_json_invalid_everywhere_raises_invalid_response():
    a = FakeProvider(lambda p, s: "garbage", "a")
    with pytest.raises(AIInvalidResponseError):
        await make_client(a).complete_json("x", Thing)


def test_extract_json_variants():
    assert extract_json('Here: {"a": 1} thanks') == {"a": 1}
    assert extract_json('```JSON\n{"a": 1}\n```') == {"a": 1}
    for bad in ("nope", "[1,2]", '{"a": '):
        with pytest.raises(AIInvalidResponseError):
            extract_json(bad)


class _Err(Exception):
    def __init__(self, msg="x", status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class RateLimitError(Exception):
    pass


class APITimeoutError(Exception):
    pass


@pytest.mark.parametrize("exc,expected", [
    (_Err(status_code=429), AIRateLimitError), (RateLimitError("x"), AIRateLimitError),
    (APITimeoutError("x"), AITimeoutError), (_Err(status_code=401), AIAuthError), (_Err(status_code=403), AIAuthError),
    (_Err(status_code=503), AIProviderUnavailableError), (ValueError("weird"), AIProviderUnavailableError),
])
def test_classify_exception(exc, expected):
    assert isinstance(classify_exception(exc, "p"), expected)


def test_api_keys_are_redacted_from_errors():
    from app.ai.errors import redact

    raw = "403 Permission denied: Consumer 'api_key:AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKE12345' has been suspended"
    assert "AIza" not in redact(raw)
    e = classify_exception(Exception(raw), "gemini")
    assert "AIza" not in e.message and "AIza" not in str(e)
    assert "gsk_" not in AIAuthError("bad gsk_abcdefghijklmnopqrstuvwxyz123456 key", "groq").message
    assert "sk-" not in redact("Authorization: Bearer sk-proj-abcdefghijklmnopqrstuvwxyz")
