"""Unicode detection and LaTeX escaping for CJK and emoji."""

from __future__ import annotations

import dataclasses
import functools
import re
import subprocess
from pathlib import Path

import emoji as emoji_lib

# Note: UNICODE_PREAMBLE has been removed. All static LaTeX preamble content
# (font setup, fallback chain, CJK/emoji configuration) now lives in
# promptgrimoire-export.sty. See src/promptgrimoire/export/promptgrimoire-export.sty.


# =============================================================================
# Font registry for dynamic font loading (Phase 3)
# =============================================================================


@dataclasses.dataclass(frozen=True)
class FallbackFont:
    """A font entry in the luaotfload fallback chain.

    Attributes:
        name: Font name for ``\\directlua`` (e.g. ``"Ezra SIL"``).
        script_tag: OpenType script tag (e.g. ``"hebr"``, ``"latn"`` for base fonts).
        options: luaotfload feature options after ``mode=node;``
            (e.g. ``"script=hebr"``).
    """

    name: str
    script_tag: str
    options: str = ""


FONT_REGISTRY: tuple[FallbackFont, ...] = (
    # Latin, Greek, Cyrillic -- SIL fonts with excellent coverage
    FallbackFont("Gentium Plus", "latn"),
    FallbackFont("Charis SIL", "latn"),
    FallbackFont("Noto Serif", "latn"),
    # Hebrew
    FallbackFont("Ezra SIL", "hebr", "script=hebr"),
    FallbackFont("Noto Serif Hebrew", "hebr", "script=hebr"),
    # Arabic
    FallbackFont("Scheherazade", "arab", "script=arab"),
    FallbackFont("Noto Naskh Arabic", "arab", "script=arab"),
    # Devanagari -- Hindi, Sanskrit, Marathi
    FallbackFont("Annapurna SIL", "deva", "script=deva"),
    FallbackFont("Noto Serif Devanagari", "deva", "script=deva"),
    # Bengali, Assamese
    FallbackFont("Noto Serif Bengali", "beng", "script=beng"),
    # Tamil
    FallbackFont("Noto Serif Tamil", "taml", "script=taml"),
    # Thai
    FallbackFont("Noto Serif Thai", "thai", "script=thai"),
    # Georgian
    FallbackFont("Noto Serif Georgian", "geor", "script=geor"),
    # Armenian
    FallbackFont("Noto Serif Armenian", "armn", "script=armn"),
    # Ethiopic
    FallbackFont("Abyssinica SIL", "ethi", "script=ethi"),
    FallbackFont("Noto Serif Ethiopic", "ethi", "script=ethi"),
    # Khmer
    FallbackFont("Khmer Mondulkiri", "khmr", "script=khmr"),
    FallbackFont("Noto Serif Khmer", "khmr", "script=khmr"),
    # Lao
    FallbackFont("Noto Serif Lao", "lao", "script=lao"),
    # Myanmar
    FallbackFont("Padauk", "mymr", "script=mymr"),
    FallbackFont("Noto Serif Myanmar", "mymr", "script=mymr"),
    # Sinhala (Sri Lankan)
    FallbackFont("Noto Serif Sinhala", "sinh", "script=sinh"),
    # Tai Viet
    FallbackFont("Tai Heritage Pro", "tavt"),
    # Nubian/Coptic
    FallbackFont("Sophia Nubian", "copt"),
    # Yi
    FallbackFont("Nuosu SIL", "yiii"),
    # Greek polytonic (backup)
    FallbackFont("Galatia SIL", "grek", "script=grek"),
    # Historic/rare scripts (for BLNS coverage)
    FallbackFont("Noto Sans Deseret", "dsrt"),
    FallbackFont("Noto Sans Osage", "osge"),
    FallbackFont("Noto Sans Shavian", "shaw"),
    # Symbols and math (last resort for missing glyphs)
    FallbackFont("Noto Sans Symbols", "zsym"),
    FallbackFont("Noto Sans Symbols2", "zsym"),
    FallbackFont("Noto Sans Math", "zmth"),
)

SCRIPT_TAG_RANGES: dict[str, list[tuple[int, int]]] = {
    "hebr": [(0x0590, 0x05FF), (0xFB1D, 0xFB4F)],
    "arab": [
        (0x0600, 0x06FF),
        (0x0750, 0x077F),
        (0x08A0, 0x08FF),
        (0xFB50, 0xFDFF),
        (0xFE70, 0xFEFF),
    ],
    "deva": [(0x0900, 0x097F), (0xA8E0, 0xA8FF)],
    "beng": [(0x0980, 0x09FF)],
    "taml": [(0x0B80, 0x0BFF)],
    "thai": [(0x0E00, 0x0E7F)],
    "geor": [(0x10A0, 0x10FF), (0x2D00, 0x2D2F)],
    "armn": [(0x0530, 0x058F), (0xFB00, 0xFB06)],
    "ethi": [(0x1200, 0x137F), (0x1380, 0x139F), (0x2D80, 0x2DDF), (0xAB00, 0xAB2F)],
    "khmr": [(0x1780, 0x17FF), (0x19E0, 0x19FF)],
    "lao": [(0x0E80, 0x0EFF)],
    "mymr": [(0x1000, 0x109F), (0xAA60, 0xAA7F)],
    "sinh": [(0x0D80, 0x0DFF)],
    "cjk": [
        (0x2E80, 0x2EFF),
        (0x3000, 0x303F),
        (0x3040, 0x309F),
        (0x30A0, 0x30FF),
        (0x31F0, 0x31FF),
        (0x3400, 0x4DBF),
        (0x4E00, 0x9FFF),
        (0xAC00, 0xD7AF),
        (0xF900, 0xFAFF),
        (0x20000, 0x2A6DF),
    ],
    "grek": [(0x0370, 0x03FF), (0x1F00, 0x1FFF)],
    "cyrl": [(0x0400, 0x04FF), (0x0500, 0x052F), (0x2DE0, 0x2DFF), (0xA640, 0xA69F)],
    "tavt": [(0xAA80, 0xAADF)],
    "copt": [(0x2C80, 0x2CFF)],
    "yiii": [(0xA000, 0xA48F), (0xA490, 0xA4CF)],
    "dsrt": [(0x10400, 0x1044F)],
    "osge": [(0x104B0, 0x104FF)],
    "shaw": [(0x10450, 0x1047F)],
    "zsym": [
        (0x2600, 0x26FF),
        (0x2700, 0x27BF),
        (0x1F300, 0x1F5FF),
        (0x1F680, 0x1F6FF),
    ],
    "zmth": [(0x2200, 0x22FF), (0x27C0, 0x27EF), (0x2980, 0x29FF), (0x1D400, 0x1D7FF)],
}

_REQUIRED_SCRIPTS: frozenset[str] = frozenset(
    f.script_tag for f in FONT_REGISTRY if f.script_tag != "latn"
)


def detect_scripts(text: str) -> frozenset[str]:
    """Scan text and return OpenType script tags for detected non-Latin scripts.

    Latin/ASCII is always assumed present and not included in the result.
    An empty frozenset means only Latin base fonts are needed.
    """
    found: set[str] = set()
    for ch in text:
        cp = ord(ch)
        if cp < 0x0370:  # ASCII + Latin Extended -- fast skip
            continue
        for tag, ranges in SCRIPT_TAG_RANGES.items():
            if tag in found:
                continue  # Already detected this script
            for start, end in ranges:
                if start <= cp <= end:
                    found.add(tag)
                    break
        if found >= _REQUIRED_SCRIPTS:
            break  # All possible scripts found, stop scanning
    return frozenset(found)


def build_font_preamble(scripts: frozenset[str]) -> str:
    """Build LaTeX font preamble with only fonts needed for detected scripts.

    Args:
        scripts: Script tags from ``detect_scripts()``. Empty = Latin-only.

    Returns:
        LaTeX string for insertion between ``\\usepackage{promptgrimoire-export}``
        and colour definitions in the document preamble.
    """
    lines: list[str] = []

    # Step 1: CJK package loading (must come before \directlua)
    has_cjk = "cjk" in scripts
    if has_cjk:
        lines.append(r"\usepackage{luatexja-fontspec}")
        lines.append(r"\ltjsetparameter{jacharrange={-2}}")
        lines.append("")

    # Step 2: Filter fonts -- always include latn, plus matched script tags
    selected = [
        f for f in FONT_REGISTRY if f.script_tag == "latn" or f.script_tag in scripts
    ]

    # Step 3: Build \directlua fallback chain
    entries: list[str] = []
    for font in selected:
        if font.options:
            entry = f'    "{font.name}:mode=node;{font.options};",'
        else:
            entry = f'    "{font.name}:mode=node;",'
        entries.append(entry)

    lines.append(r"\directlua{")
    lines.append(r'  luaotfload.add_fallback("mainfallback", {')
    lines.extend(entries)
    lines.append("  })")
    lines.append("}")
    lines.append("")

    # Step 4: CJK font setup (after \directlua, before \setmainfont)
    if has_cjk:
        lines.append(r"\setmainjfont{Noto Serif CJK SC}[")
        lines.append("  UprightFont = *,")
        lines.append("  BoldFont = * Bold,")
        lines.append("  ItalicFont = *,")
        lines.append("  BoldItalicFont = * Bold,")
        lines.append("]")
        lines.append(r"\setsansjfont{Noto Sans CJK SC}[")
        lines.append("  UprightFont = *,")
        lines.append("  BoldFont = * Bold,")
        lines.append("  ItalicFont = *,")
        lines.append("  BoldItalicFont = * Bold,")
        lines.append("]")
        lines.append(r"\newjfontfamily\notocjk{Noto Serif CJK SC}")
        lines.append("")

    # Step 5: Main font with fallback (always)
    lines.append(r"\setmainfont{TeX Gyre Termes}[RawFeature={fallback=mainfallback}]")

    # Step 6: CJK text command override (after \notocjk is defined)
    if has_cjk:
        lines.append(r"\renewcommand{\cjktext}[1]{{\notocjk #1}}")

    return "\n".join(lines)


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
