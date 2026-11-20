"""Tests for redact_secrets."""

import pytest
from alerting_core.llm import redact_secrets


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("Authorization: Bearer abcdef1234567890", "abcdef1234567890"),
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("login password=hunter2 now", "hunter2"),
        ("token: abc123xyz", "abc123xyz"),
        ("client_secret=s3cr3t!", "s3cr3t!"),
        ("api_key = KEY-999", "KEY-999"),
        ('{"password": "p@ss w0rd"}', "p@ss"),
        ("key AKIAIOSFODNN7EXAMPLE used", "AKIAIOSFODNN7EXAMPLE"),
        (
            "aws_secret_access_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "wJalrXUtnFEMI",
        ),
        ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc_def-123 end", "eyJhbGci"),
        ("card 4111 1111 1111 1111 paid", "4111"),
        ("card 4111-1111-1111-1111 paid", "4111"),
        ("card 4111111111111111", "4111111111111111"),
    ],
)
def test_masks_secret(text: str, secret: str) -> None:
    out = redact_secrets(text)
    assert secret not in out
    assert "[REDACTED]" in out


def test_non_luhn_digits_kept() -> None:
    text = "workflow 1234567890123456 and 20240101123456789"
    assert redact_secrets(text) == text


def test_plain_text_untouched() -> None:
    text = "Restart the pricing adapter for feed {{feed}} after basic checks."
    assert redact_secrets(text) == text
