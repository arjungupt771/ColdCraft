import json
import re

from app.ai.errors import AIInvalidResponseError

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(raw: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences and surrounding prose."""
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise AIInvalidResponseError("Model did not return JSON")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            raise AIInvalidResponseError(f"Model returned malformed JSON: {e}") from e
    if not isinstance(data, dict):
        raise AIInvalidResponseError("Model returned JSON that is not an object")
    return data
