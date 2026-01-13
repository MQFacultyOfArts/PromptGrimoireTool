"""Shared pytest fixtures for PromptGrimoire tests."""

import pytest


@pytest.fixture
def sample_claude_conversation() -> str:
    """A sample Claude conversation for testing parsers."""
    return (
        "Human: What is the capital of France?\n\n"
        "Assistant: The capital of France is Paris.\n\n"
        "Human: What about Germany?\n\n"
        "Assistant: The capital of Germany is Berlin."
    )


@pytest.fixture
def sample_chatgpt_conversation() -> str:
    """A sample ChatGPT conversation for testing parsers."""
    return (
        "User: What is the capital of France?\n\n"
        "ChatGPT: The capital of France is Paris.\n\n"
        "User: What about Germany?\n\n"
        "ChatGPT: The capital of Germany is Berlin."
    )
