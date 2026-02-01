"""Unicode detection and LaTeX escaping for CJK and emoji."""

from __future__ import annotations

import emoji as emoji_lib


def is_cjk(char: str) -> bool:
    """Check if a single character is CJK (Chinese, Japanese, Korean).

    Detects:
    - CJK Unified Ideographs (U+4E00-U+9FFF)
    - Hiragana (U+3040-U+309F)
    - Katakana (U+30A0-U+30FF)
    - Hangul Syllables (U+AC00-U+D7AF)
    - CJK Unified Ideographs Extension A (U+3400-U+4DBF)

    Args:
        char: A single character to check.

    Returns:
        True if character is in a CJK range, False otherwise.
    """
    if len(char) != 1:
        return False

    cp = ord(char)

    return (
        # CJK Unified Ideographs
        (0x4E00 <= cp <= 0x9FFF)
        # Hiragana
        or (0x3040 <= cp <= 0x309F)
        # Katakana
        or (0x30A0 <= cp <= 0x30FF)
        # Hangul Syllables
        or (0xAC00 <= cp <= 0xD7AF)
        # CJK Unified Ideographs Extension A
        or (0x3400 <= cp <= 0x4DBF)
    )


def is_emoji(text: str) -> bool:
    """Check if text is a single emoji (including ZWJ sequences).

    Uses the emoji library to correctly handle:
    - Single codepoint emoji
    - Emoji with skin tone modifiers
    - ZWJ sequences (family, profession emoji)

    Args:
        text: Text to check.

    Returns:
        True if text is exactly one RGI emoji, False otherwise.
    """
    return emoji_lib.is_emoji(text)
