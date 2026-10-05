from abc import ABC, abstractmethod


class AIProvider(ABC):
    name: str = "base"
    supports_vision: bool = False

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def generate(self, prompt: str, system: str = "", max_tokens: int = 1024, temperature: float = 0.7) -> str:
        """Return model text. Must raise only typed AIError subclasses."""

    async def generate_vision(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        raise NotImplementedError(f"{self.name} does not support vision")
