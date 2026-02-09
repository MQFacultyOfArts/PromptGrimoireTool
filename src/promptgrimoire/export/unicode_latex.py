"""Unicode detection and LaTeX escaping for CJK and emoji."""

from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path

import emoji as emoji_lib

UNICODE_PREAMBLE = r"""
% Unicode support for CJK and Emoji (added by unicode_latex.py)
% Note: [match] option removed - caused font identifier errors in sectioning
\usepackage{luatexja-fontspec}
\usepackage{emoji}

% luatexja range 2 (U+0370-U+04FF: Greek + basic Cyrillic) defaults to +2 (JAchar),
% routing these characters to the CJK font which lacks accented Greek (ά U+03AC)
% and extended Cyrillic (ї U+0457). Set -2 to route through main font fallback.
\ltjsetparameter{jacharrange={-2}}

% Define comprehensive font fallback chain BEFORE loading fonts
% Fonts are tried in order until one has the glyph
% SIL fonts first (higher quality for their target scripts), then Noto as backup
\directlua{
  luaotfload.add_fallback("mainfallback", {
    % Latin, Greek, Cyrillic — SIL fonts with excellent coverage
    "Gentium Plus:mode=node;",
    "Charis SIL:mode=node;",
    "Noto Serif:mode=node;",
    % Hebrew
    "Ezra SIL:mode=node;script=hebr;",
    "Noto Serif Hebrew:mode=node;script=hebr;",
    % Arabic
    "Scheherazade:mode=node;script=arab;",
    "Noto Naskh Arabic:mode=node;script=arab;",
    % Devanagari (Hindi, Sanskrit, Marathi)
    "Annapurna SIL:mode=node;script=deva;",
    "Noto Serif Devanagari:mode=node;script=deva;",
    % Bengali, Assamese
    "Noto Serif Bengali:mode=node;script=beng;",
    % Tamil
    "Noto Serif Tamil:mode=node;script=taml;",
    % Thai
    "Noto Serif Thai:mode=node;script=thai;",
    % Georgian
    "Noto Serif Georgian:mode=node;script=geor;",
    % Armenian
    "Noto Serif Armenian:mode=node;script=armn;",
    % Ethiopic
    "Abyssinica SIL:mode=node;script=ethi;",
    "Noto Serif Ethiopic:mode=node;script=ethi;",
    % Khmer (Cambodian)
    "Khmer Mondulkiri:mode=node;script=khmr;",
    "Noto Serif Khmer:mode=node;script=khmr;",
    % Lao
    "Noto Serif Lao:mode=node;script=lao;",
    % Myanmar (Burmese)
    "Padauk:mode=node;script=mymr;",
    "Noto Serif Myanmar:mode=node;script=mymr;",
    % Sinhala (Sri Lankan)
    "Noto Serif Sinhala:mode=node;script=sinh;",
    % Tai Viet
    "Tai Heritage Pro:mode=node;",
    % Nubian/Coptic
    "Sophia Nubian:mode=node;",
    % Yi
    "Nuosu SIL:mode=node;",
    % Greek polytonic (backup)
    "Galatia SIL:mode=node;script=grek;",
    % Historic/rare scripts (for BLNS coverage)
    "Noto Sans Deseret:mode=node;",
    "Noto Sans Osage:mode=node;",
    "Noto Sans Shavian:mode=node;",
    % Symbols and math (last resort for missing glyphs)
    "Noto Sans Symbols:mode=node;",
    "Noto Sans Symbols2:mode=node;",
    "Noto Sans Math:mode=node;",
  })
}

% CJK font setup - Noto Serif CJK for serif consistency with TNR
% Set as default Japanese fonts so [match] option uses them for all CJK
% SC variant has broadest coverage (Simplified Chinese + JP/KR compatibility)
% Must specify all font faces explicitly for luatexja compatibility
\setmainjfont{Noto Serif CJK SC}[
  UprightFont = *,
  BoldFont = * Bold,
  ItalicFont = *,        % CJK has no italic - use upright
  BoldItalicFont = * Bold,
]
\setsansjfont{Noto Sans CJK SC}[
  UprightFont = *,
  BoldFont = * Bold,
  ItalicFont = *,        % CJK has no italic - use upright
  BoldItalicFont = * Bold,
]

% Also define as command for explicit wrapping if needed
\newjfontfamily\notocjk{Noto Serif CJK SC}

% Command for wrapping CJK text (used by escape_unicode_latex)
\newcommand{\cjktext}[1]{{\notocjk #1}}

% Emoji font setup
\setemojifont{Noto Color Emoji}

% Main font: TeX Gyre Termes (TNR equivalent) with fallback chain
\setmainfont{TeX Gyre Termes}[RawFeature={fallback=mainfallback}]

% Fallback for emoji not in LaTeX emoji package
% Can't use Noto Color Emoji directly (CBDT format not supported by LuaLaTeX)
% Just show placeholder text for unknown emoji
\newcommand{\emojifallbackchar}[1]{[#1]}

% Stub for \includegraphics - Pandoc converts <img> tags to this
% Make it a no-op to handle BLNS XSS test strings like <img src=x>
% We don't actually want to include external images from user content
\newcommand{\includegraphics}[2][]{[image: #2]}
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


def _format_emoji_for_latex(emoji_name: str) -> str:
    """Format emoji for LaTeX, with fallback for unknown names.

    If the emoji name is valid in LaTeX emoji package, uses \\emoji{name}.
    Otherwise shows placeholder with emoji name (raw emoji can't be rendered).
    """
    valid_names = _load_latex_emoji_names()

    if emoji_name in valid_names:
        return f"\\emoji{{{emoji_name}}}"

    # Fallback: show name as placeholder (raw emoji can't render in PDF)
    return f"\\emojifallbackchar{{{emoji_name}}}"


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
    - Line/paragraph separators (U+2028, U+2029) - break LaTeX parsing

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
    # Line/paragraph separators break LaTeX
    is_line_sep = cp in (0x2028, 0x2029)

    return not (is_del or is_c1 or is_surrogate or is_nonchar or is_line_sep)


# Unicode spaces to normalize to ASCII space
_UNICODE_SPACES = frozenset(
    [
        "\u1680",  # Ogham Space Mark
        "\u2000",  # En Quad
        "\u2001",  # Em Quad
        "\u2002",  # En Space
        "\u2003",  # Em Space
        "\u2004",  # Three-Per-Em Space
        "\u2005",  # Four-Per-Em Space
        "\u2006",  # Six-Per-Em Space
        "\u2007",  # Figure Space
        "\u2008",  # Punctuation Space
        "\u2009",  # Thin Space
        "\u200a",  # Hair Space
        "\u202f",  # Narrow No-Break Space
        "\u205f",  # Medium Mathematical Space
        "\u3000",  # Ideographic Space
    ]
)


def _strip_control_chars(text: str) -> str:
    """Strip/normalize characters that are problematic for LaTeX.

    - Removes control characters that cause 'invalid character' errors
    - Normalizes exotic Unicode spaces to ASCII space

    See _is_latex_safe_char() for the complete list of filtered characters.
    """
    result = []
    for c in text:
        if c in _UNICODE_SPACES:
            result.append(" ")  # Normalize to ASCII space
        elif _is_latex_safe_char(c):
            result.append(c)
        # else: drop the character
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
            emoji_name = emoji_name.strip(":").replace("_", "-").lower()
            result.append(_format_emoji_for_latex(emoji_name))
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
