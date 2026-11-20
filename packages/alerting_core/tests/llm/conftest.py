"""Fixtures for LLM client tests."""

import pytest
from alerting_core.llm import LlmConfig
from pydantic import BaseModel


class Answer(BaseModel):
    value: int


@pytest.fixture
def config() -> LlmConfig:
    return LlmConfig(base_url="http://localhost:11434/v1", api_key="sk-test-key-123456", model="m")


def chat(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}
