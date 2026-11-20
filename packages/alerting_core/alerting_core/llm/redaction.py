"""Secret redaction applied to every prompt before it leaves the process."""

import re

REDACTED = "[REDACTED]"

_AUTH_HEADER = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer|basic)\s+[^\s\"',;]+")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9\-._~+/]{8,}=*")
_KEY_VALUE = re.compile(
    r"(?i)([\"']?[\w.-]*(?:password|passwd|pwd|token|secret|api[_-]?key)[\w-]*[\"']?\s*[:=]\s*)"
    r"([\"']?)([^\s\"',;&}]+)"
)
_AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_AWS_SECRET = re.compile(r"(?i)(aws[_\s-]?secret\w*\s*[:=]?\s*[\"']?)[A-Za-z0-9/+=]{40}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_CARD = re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d])")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _mask_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return REDACTED
    return match.group(0)


def redact_secrets(text: str) -> str:
    """Mask auth headers, key-value secrets, AWS keys, JWTs and Luhn-valid card numbers."""
    text = _AUTH_HEADER.sub(lambda m: m.group(1) + REDACTED, text)
    text = _BEARER.sub(lambda m: m.group(1) + REDACTED, text)
    text = _JWT.sub(REDACTED, text)
    text = _AWS_ACCESS_KEY.sub(REDACTED, text)
    text = _AWS_SECRET.sub(lambda m: m.group(1) + REDACTED, text)
    text = _KEY_VALUE.sub(lambda m: m.group(1) + m.group(2) + REDACTED, text)
    return _CARD.sub(_mask_card, text)
