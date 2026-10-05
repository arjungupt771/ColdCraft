"""Versioned prompt loader. Prompts live in app/prompts/<name>/vN.txt so every generated
email can be traced back to the exact prompt text that produced it."""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

from app.core.config import settings

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_VERSION_RE = re.compile(r"^v(\d+)\.txt$")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    user: str

    @property
    def tag(self) -> str:
        return f"{self.name}@{self.version}"

    def render(self, **variables) -> tuple[str, str]:
        """Returns (system, user). Raises KeyError if a template variable is missing."""
        values = {k: ("" if v is None else str(v)) for k, v in variables.items()}
        return Template(self.system).substitute(values), Template(self.user).substitute(values)


def available_versions(name: str) -> list[str]:
    folder = PROMPTS_DIR / name
    found = sorted(
        (int(m.group(1)), f.stem) for f in folder.glob("v*.txt") if (m := _VERSION_RE.match(f.name))
    )
    return [v for _, v in found]


@lru_cache(maxsize=64)
def _load(name: str, version: str) -> Prompt:
    path = PROMPTS_DIR / name / f"{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt {name}@{version} not found at {path}")
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^### (SYSTEM|USER)\s*$", text, flags=re.MULTILINE)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    if "USER" not in sections:
        raise ValueError(f"Prompt {name}@{version} has no '### USER' section")
    return Prompt(name, version, sections.get("SYSTEM", ""), sections["USER"])


def load_prompt(name: str, version: str | None = None) -> Prompt:
    version = version or settings.prompt_version(name) or (available_versions(name) or [""])[-1]
    if not version:
        raise FileNotFoundError(f"No versions found for prompt '{name}'")
    return _load(name, version)
