"""Unicode detection and LaTeX escaping for CJK and emoji."""

from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path

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

% Fallback for emoji not in LaTeX emoji package
\newfontfamily\emojifallback{Noto Color Emoji}
\newcommand{\emojifallbackchar}[1]{{\emojifallback #1}}
"""


@functools.cache
def _load_latex_emoji_names() -> frozenset[str]:
    """Load valid emoji names from LaTeX emoji package.

    Parses emoji-table.def to extract all valid emoji names and aliases.
    Returns empty set if the file cannot be found or parsed.
    """
    try:
        result = subprocess.run(
            ["kpsewhich", "emoji-table.def"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        table_path = result.stdout.strip()
        if not table_path:
            return frozenset()

        # Parse emoji definitions: \__emoji_def:nnnnn {unicode} {name} {aliases} ...
        # Field 2 = primary name, Field 3 = comma-separated aliases
        pattern = re.compile(
            r"\\__emoji_def:nnnnn\s*\{[^}]*\}\s*\{([^}]*)\}\s*\{([^}]*)\}"
        )

        names: set[str] = set()
        with Path(table_path).open(encoding="utf-8") as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    primary = match.group(1).strip()
                    aliases = match.group(2).strip()
                    if primary:
                        names.add(primary)
                    for alias in aliases.split(","):
                        stripped = alias.strip()
                        if stripped:
                            names.add(stripped)

        return frozenset(names)
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return frozenset()
    except OSError:
        return frozenset()


def _format_emoji_for_latex(emoji_char: str, emoji_name: str) -> str:
    """Format emoji for LaTeX, with fallback for unknown names.

    If the emoji name is valid in LaTeX emoji package, uses \\emoji{name}.
    Otherwise falls back to raw emoji with font wrapper.
    """
    valid_names = _load_latex_emoji_names()

    if emoji_name in valid_names:
        return f"\\emoji{{{emoji_name}}}"

    # Fallback: render raw emoji with emoji font
    return f"\\emojifallbackchar{{{emoji_char}}}"


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


def _is_latex_safe_char(c: str) -> bool:
    """Check if a character is safe for LaTeX input.

    LaTeX cannot handle certain Unicode categories:
    - C0 controls (0x00-0x1F) except tab, newline, CR
    - DEL (0x7F)
    - C1 controls (0x80-0x9F)
    - Surrogates (0xD800-0xDFFF) - invalid in UTF-8 anyway
    - Noncharacters (0xFFFE, 0xFFFF, and last 2 codepoints of each plane)

    Returns True if the character can be safely included in LaTeX source.
    """
    cp = ord(c)

    # C0 controls - allow only tab, newline, CR
    if cp < 0x20:
        return c in "\t\n\r"

    # DEL, C1 controls, surrogates, or noncharacters
    is_del = cp == 0x7F
    is_c1 = 0x80 <= cp <= 0x9F
    is_surrogate = 0xD800 <= cp <= 0xDFFF
    is_nonchar = (cp & 0xFFFF) >= 0xFFFE

    return not (is_del or is_c1 or is_surrogate or is_nonchar)


def _strip_control_chars(text: str) -> str:
    """Strip characters that are invalid in LaTeX.

    Removes control characters and other problematic Unicode that cause
    'Text line contains an invalid character' LaTeX errors.

    See _is_latex_safe_char() for the complete list of filtered characters.
    """
    return "".join(c for c in text if _is_latex_safe_char(c))


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
            emoji_name = emoji_name.strip(":").replace("_", "-").lower()
            result.append(_format_emoji_for_latex(emoji_char, emoji_name))
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
