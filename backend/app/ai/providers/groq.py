from app.ai.errors import AIInvalidResponseError, classify_exception
from app.ai.providers.base import AIProvider
from app.core.config import settings


class GroqProvider(AIProvider):
    name = "groq"

    def is_configured(self) -> bool:
        return bool(settings.GROQ_API_KEY)

    async def generate(self, prompt, system="", max_tokens=1024, temperature=0.7):
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.GROQ_API_KEY, timeout=settings.AI_TIMEOUT_SECONDS, max_retries=0)
            messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
            resp = await client.chat.completions.create(
                model=settings.GROQ_MODEL, messages=messages, max_tokens=max_tokens, temperature=temperature,
            )
            text = resp.choices[0].message.content
        except Exception as e:
            raise classify_exception(e, self.name) from e
        if not text:
            raise AIInvalidResponseError("Empty response", self.name)
        return text
