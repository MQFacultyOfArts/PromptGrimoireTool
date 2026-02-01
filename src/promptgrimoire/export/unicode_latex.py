"""Unicode detection and LaTeX escaping for CJK and emoji."""

from __future__ import annotations

import emoji as emoji_lib

UNICODE_PREAMBLE = r"""
% Unicode support for CJK and Emoji (added by unicode_latex.py)
\usepackage[match]{luatexja-fontspec}
\usepackage{emoji}

% CJK font setup - Noto fonts for broad unicode coverage
\newjfontfamily\notocjk{Noto Sans CJK SC}

% Command for wrapping CJK text (used by escape_unicode_latex)
\newcommand{\cjktext}[1]{{\notocjk #1}}

% Emoji font setup
\setemojifont{Noto Color Emoji}
"""


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


def get_emoji_spans(text: str) -> list[tuple[int, int, str]]:
    """Get positions of all emoji in text.

    Args:
        text: Text to scan for emoji.

    Returns:
        List of (start, end, emoji) tuples for each emoji found.
        Positions are character indices (not byte offsets).
    """
    matches = emoji_lib.emoji_list(text)
    return [(m["match_start"], m["match_end"], m["emoji"]) for m in matches]


# ASCII special characters for LaTeX escaping
_LATEX_SPECIAL_CHARS = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]


def _strip_control_chars(text: str) -> str:
    """Strip control characters that are invalid in LaTeX.

    Removes:
    - C0 controls: 0x00-0x08, 0x0B-0x0C, 0x0E-0x1F (preserves tab, newline, CR)
    - DEL: 0x7F
    - C1 controls: 0x80-0x9F (often misinterpreted as extended ASCII)

    These appear in BLNS test corpus and cause LaTeX compilation failures.
    """
    result = []
    for c in text:
        cp = ord(c)
        # Skip C0 controls except whitespace (tab, newline, CR)
        if cp < 0x20 and c not in "\t\n\r":
            continue
        # Skip DEL (0x7F)
        if cp == 0x7F:
            continue
        # Skip C1 controls (0x80-0x9F)
        if 0x80 <= cp <= 0x9F:
            continue
        result.append(c)
    return "".join(result)


def _escape_ascii_special(text: str) -> str:
    """Escape ASCII special characters for LaTeX."""
    for char, replacement in _LATEX_SPECIAL_CHARS:
        text = text.replace(char, replacement)
    return text


def escape_unicode_latex(text: str) -> str:
    """Escape text for LaTeX with unicode handling.

    - ASCII control characters (0x00-0x1F except whitespace) are stripped
    - ASCII special characters (& % $ # _ { } ~ ^) are escaped
    - CJK text is wrapped in \\cjktext{} command
    - Emoji are wrapped in \\emoji{} command with name format

    Args:
        text: Input text potentially containing unicode.

    Returns:
        LaTeX-safe string with appropriate wrapping.
    """
    if not text:
        return text

    # Strip control characters that are invalid in LaTeX
    text = _strip_control_chars(text)

    # First, identify emoji spans (must do before any modifications)
    emoji_spans = get_emoji_spans(text)

    # Build result by processing character by character
    result: list[str] = []
    i = 0
    cjk_buffer: list[str] = []

    def flush_cjk() -> None:
        """Flush accumulated CJK characters as wrapped command."""
        if cjk_buffer:
            escaped = _escape_ascii_special("".join(cjk_buffer))
            result.append(f"\\cjktext{{{escaped}}}")
            cjk_buffer.clear()

    while i < len(text):
        # Check if we're at an emoji span
        emoji_match = None
        for start, end, emoji_char in emoji_spans:
            if i == start:
                emoji_match = (end, emoji_char)
                break

        if emoji_match:
            flush_cjk()
            end, emoji_char = emoji_match
            # Convert emoji to name using emoji library
            emoji_name = emoji_lib.demojize(emoji_char, delimiters=("", ""))
            # Remove colons if present and convert to LaTeX emoji format
            emoji_name = emoji_name.strip(":").replace("_", "-")
            result.append(f"\\emoji{{{emoji_name}}}")
            i = end
        elif is_cjk(text[i]):
            cjk_buffer.append(text[i])
            i += 1
        else:
            flush_cjk()
            # Escape ASCII special chars
            result.append(_escape_ascii_special(text[i]))
            i += 1

    flush_cjk()
    return "".join(result)
