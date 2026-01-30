"""Speaker detection and label injection for chatbot HTML exports.

Detects the source platform (Claude, OpenAI, Gemini, ScienceOS) from HTML
structure and injects User:/Assistant: labels at turn boundaries.

This is a pre-processor that runs before Pandoc conversion.
"""

from __future__ import annotations

import re
from typing import Literal

# Platform type
Platform = Literal["claude", "openai", "gemini", "scienceos"]

# Detection patterns for each platform
_PLATFORM_PATTERNS: dict[Platform, re.Pattern[str]] = {
    "claude": re.compile(r'class="[^"]*font-user-message[^"]*"', re.IGNORECASE),
    "openai": re.compile(r'class="[^"]*agent-turn[^"]*"', re.IGNORECASE),
    "gemini": re.compile(r'class="[^"]*chat-turn-container[^"]*"', re.IGNORECASE),
    "scienceos": re.compile(r'class="[^"]*tabler-icon-robot-face[^"]*"', re.IGNORECASE),
}

# Turn boundary patterns for label injection
_TURN_PATTERNS: dict[Platform, dict[str, re.Pattern[str]]] = {
    "claude": {
        "user": re.compile(
            r'(<[^>]*class="[^"]*font-user-message[^"]*"[^>]*>)', re.IGNORECASE
        ),
        "assistant": re.compile(
            r'(<[^>]*class="[^"]*font-claude-response[^"]*"[^>]*>)', re.IGNORECASE
        ),
    },
    "openai": {
        # OpenAI: user turns have items-end, assistant turns have agent-turn
        "user": re.compile(r'(<[^>]*class="[^"]*items-end[^"]*"[^>]*>)', re.IGNORECASE),
        "assistant": re.compile(
            r'(<[^>]*class="[^"]*agent-turn[^"]*"[^>]*>)', re.IGNORECASE
        ),
    },
    "gemini": {
        "user": re.compile(
            r'(<[^>]*class="[^"]*chat-turn-container[^"]*\buser\b[^"]*"[^>]*>)',
            re.IGNORECASE,
        ),
        "assistant": re.compile(
            r'(<[^>]*class="[^"]*chat-turn-container[^"]*\bmodel\b[^"]*"[^>]*>)',
            re.IGNORECASE,
        ),
    },
    "scienceos": {
        # ScienceOS uses tabler icons: medal for user, robot-face for assistant
        "user": re.compile(
            r'(<[^>]*class="[^"]*tabler-icon-medal[^"]*"[^>]*>)', re.IGNORECASE
        ),
        "assistant": re.compile(
            r'(<[^>]*class="[^"]*tabler-icon-robot-face[^"]*"[^>]*>)', re.IGNORECASE
        ),
    },
}


def detect_platform(html: str) -> Platform | None:
    """Detect which chatbot platform generated the HTML.

    Args:
        html: Raw HTML content.

    Returns:
        Platform identifier ('claude', 'openai', 'gemini', 'scienceos')
        or None if platform cannot be detected.
    """
    for platform, pattern in _PLATFORM_PATTERNS.items():
        if pattern.search(html):
            return platform
    return None


def inject_speaker_labels(html: str) -> str:
    """Inject User:/Assistant: labels at conversation turn boundaries.

    Detects the platform and inserts appropriate labels based on
    platform-specific turn markers.

    Args:
        html: Raw HTML content from a chatbot export.

    Returns:
        HTML with speaker labels injected before each turn.
    """
    platform = detect_platform(html)
    if platform is None:
        return html

    patterns = _TURN_PATTERNS.get(platform)
    if patterns is None:
        return html

    # Inject user labels
    user_pattern = patterns.get("user")
    if user_pattern:
        html = user_pattern.sub(r"<strong>User:</strong> \1", html)

    # Inject assistant labels
    assistant_pattern = patterns.get("assistant")
    if assistant_pattern:
        html = assistant_pattern.sub(r"<strong>Assistant:</strong> \1", html)

    return html
