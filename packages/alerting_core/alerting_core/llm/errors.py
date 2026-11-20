"""Errors raised by the LLM client."""


class LlmError(Exception):
    """Base class for all LLM client errors."""


class LlmUnavailableError(LlmError):
    """The endpoint timed out, was unreachable or answered with a non-2xx status."""


class LlmOutputInvalidError(LlmError):
    """The model output failed schema validation after the retry."""


class LlmHostNotAllowedError(LlmError):
    """The configured base URL host is not in the allowlist."""
