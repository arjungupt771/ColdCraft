import asyncio
from app.ai.errors import AIInvalidResponseError, AITimeoutError, classify_exception
from app.ai.providers.base import AIProvider
from app.core.config import settings


class GeminiProvider(AIProvider):
    name = "gemini"
    supports_vision = True

    def is_configured(self) -> bool:
        return bool(settings.GEMINI_API_KEY)

    async def generate(self, prompt, system="", max_tokens=1024, temperature=0.7):
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(
                model_name=settings.GEMINI_MODEL,
                system_instruction=system or None,
                generation_config=genai.GenerationConfig(max_output_tokens=max_tokens, temperature=temperature),
            )
            resp = await asyncio.wait_for(model.generate_content_async(prompt), settings.AI_TIMEOUT_SECONDS)
            text = resp.text
        except asyncio.TimeoutError as e:
            raise AITimeoutError("Gemini request timed out", self.name) from e
        except Exception as e:  # includes ValueError when the response was blocked/empty
            if isinstance(e, ValueError):
                raise AIInvalidResponseError(str(e)[:200], self.name) from e
            raise classify_exception(e, self.name) from e
        if not text:
            raise AIInvalidResponseError("Empty response", self.name)
        return text

    async def generate_vision(self, image_bytes, mime_type, prompt):
        import base64
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(settings.GEMINI_VISION_MODEL)
            part = {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}}
            resp = await asyncio.wait_for(model.generate_content_async([prompt, part]), settings.AI_TIMEOUT_SECONDS)
            return resp.text
        except asyncio.TimeoutError as e:
            raise AITimeoutError("Gemini vision timed out", self.name) from e
        except ValueError as e:
            raise AIInvalidResponseError(str(e)[:200], self.name) from e
        except Exception as e:
            raise classify_exception(e, self.name) from e
