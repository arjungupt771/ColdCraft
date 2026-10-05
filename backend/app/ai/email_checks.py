"""Rules a generated email must satisfy beyond its JSON shape. Raise ValueError(reason): the reason
is sent back to the model for one repair attempt, then the next provider is tried."""
import re

_NUMBER = re.compile(r"\d[\d,.]*\d|\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_FILLER = ("i hope this email finds you well", "i hope this message finds you well")
MIN_WORDS, MAX_WORDS, CONCISE_MAX_WORDS = 50, 200, 120
WORD_SLACK = 1.15          # models miss word counts slightly; don't reject 205 words


def word_limits(tone: str) -> tuple[int, int]:
    return MIN_WORDS, CONCISE_MAX_WORDS if tone == "concise" else MAX_WORDS


def _digits(s: str) -> str:
    return re.sub(r"[^\d]", "", s)


def check_signature_and_greeting(body: str, greeting: str, user_name: str, user_email: str) -> None:
    if not body.startswith(greeting):
        raise ValueError(f"body must start exactly with '{greeting}' (do not invent a recipient name)")
    tail = "\n".join(body.strip().splitlines()[-4:])
    if user_name not in tail or user_email not in tail:
        raise ValueError(f"body must end with 'Best regards,', then '{user_name}', then '{user_email}'")


def check_cold_email(subject: str, body: str, *, greeting: str, user_name: str, user_email: str,
                     tone: str, sources: list[str]) -> None:
    check_signature_and_greeting(body, greeting, user_name, user_email)
    low, high = word_limits(tone)
    words = len(body.split())
    if words < low:
        raise ValueError(f"body has {words} words; write at least {low}")
    if words > high * WORD_SLACK:
        raise ValueError(f"body has {words} words; keep it under {high}")
    if len(subject) > 90 or "\n" in subject or "\r" in subject:
        raise ValueError("subject must be a single line under 90 characters")
    if any(f in body.lower() for f in _FILLER):
        raise ValueError("remove the 'I hope this email finds you well' filler")
    known = _digits(" ".join(sources))
    for token in _NUMBER.findall(_EMAIL.sub(" ", body)):
        d = _digits(token)
        if d and d not in known:
            raise ValueError(f"'{token}' does not appear in the job description, research or resume — remove invented figures")


def check_followup(subject: str, body: str, *, greeting: str, user_name: str, user_email: str) -> None:
    check_signature_and_greeting(body, greeting, user_name, user_email)
    if "\n" in subject or "\r" in subject:
        raise ValueError("subject must be a single line")
