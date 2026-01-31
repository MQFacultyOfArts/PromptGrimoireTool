"""Speaker detection and label injection for chatbot HTML exports.

Detects the source platform (Claude, OpenAI, Gemini, ScienceOS) from HTML
structure and injects User:/Assistant: labels at turn boundaries.

Also detects Claude's "Thought process" summaries and marks them for
special styling (smaller font).

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
        # User turns have data-testid="user-message" - most reliable marker
        "user": re.compile(r'(<[^>]*data-testid="user-message"[^>]*>)', re.IGNORECASE),
        # Assistant turns: match main response container with leading-[1.65rem]
        # This distinguishes from thinking summaries which have text-sm
        "assistant": re.compile(
            r'(<[^>]*class="font-claude-response relative leading-\[1\.65rem\]'
            r'[^"]*"[^>]*>)',
            re.IGNORECASE,
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

    # Inject user labels with data attribute for Lua filter to detect
    user_pattern = patterns.get("user")
    if user_pattern:
        html = user_pattern.sub(
            r'<div data-speaker="user" class="speaker-turn"></div>\1', html
        )

    # Inject assistant labels with data attribute for Lua filter to detect
    assistant_pattern = patterns.get("assistant")
    if assistant_pattern:
        html = assistant_pattern.sub(
            r'<div data-speaker="assistant" class="speaker-turn"></div>\1', html
        )

    # Mark Claude thinking sections for special styling
    if platform == "claude":
        html = _mark_thinking_sections(html)

    return html


# Pattern to find Claude's "Thought process" header div
_THINKING_HEADER_PATTERN = re.compile(
    r"(<div[^>]*>)\s*Thought process\s*(</div>)",
    re.IGNORECASE,
)

# Pattern for thinking summary content (text-sm with font-claude-response)
# This captures the div that contains the thinking summary text
# We inject data-thinking="summary" into the existing div
_THINKING_SUMMARY_PATTERN = re.compile(
    r'<div([^>]*class="[^"]*text-sm[^"]*font-claude-response[^"]*"[^>]*)>',
    re.IGNORECASE,
)


def _mark_thinking_sections(html: str) -> str:
    """Mark Claude thinking sections with data-thinking attribute.

    Claude's extended thinking appears as:
    1. "Thought process" header
    2. Time indicator (e.g., "18s")
    3. Thinking summary text (in text-sm font-claude-response div)

    This marks these sections for special styling in the Lua filter.

    Args:
        html: HTML content with Claude conversation.

    Returns:
        HTML with thinking sections marked.
    """
    # Mark "Thought process" header
    html = _THINKING_HEADER_PATTERN.sub(
        r'<div data-thinking="header" class="thinking-header">'
        r"\1Thought process\2</div>",
        html,
    )

    # Mark thinking summary content - inject attribute into existing div
    html = _THINKING_SUMMARY_PATTERN.sub(
        r'<div data-thinking="summary" \1>',
        html,
    )

    return html
