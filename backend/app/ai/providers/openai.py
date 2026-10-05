"""OpenAI via plain HTTPS (no SDK dependency). Also works with any OpenAI-compatible base URL."""
import base64
import httpx

from app.ai.errors import AIInvalidResponseError, AITimeoutError, classify_exception
from app.ai.providers.base import AIProvider
from app.core.config import settings


class OpenAIProvider(AIProvider):
    name = "openai"
    supports_vision = True

    def is_configured(self) -> bool:
        return bool(settings.OPENAI_API_KEY)

    async def _chat(self, messages: list, max_tokens: int, temperature: float) -> str:
        try:
            async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as c:
                r = await c.post(
                    f"{settings.OPENAI_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={"model": settings.OPENAI_MODEL, "messages": messages,
                          "max_tokens": max_tokens, "temperature": temperature},
                )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException as e:
            raise AITimeoutError("OpenAI request timed out", self.name) from e
        except (KeyError, IndexError, ValueError) as e:
            raise AIInvalidResponseError("Malformed OpenAI response", self.name) from e
        except Exception as e:
            raise classify_exception(e, self.name) from e
        if not text:
            raise AIInvalidResponseError("Empty response", self.name)
        return text

    async def generate(self, prompt, system="", max_tokens=1024, temperature=0.7):
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        return await self._chat(messages, max_tokens, temperature)

    async def generate_vision(self, image_bytes, mime_type, prompt):
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}]
        return await self._chat(messages, 2048, 0.1)
