"""Word count with multilingual support and anti-gaming measures.

Pipeline: normalise -> segment by script -> tokenise per segment -> filter -> count.

External tokenisers:
- uniseg: UAX #29 word boundaries (Latin, Korean)
- jieba: Chinese word segmentation
- MeCab: Japanese morphological analysis
"""

from __future__ import annotations

import logging
import re
import unicodedata
import warnings

# Suppress jieba SyntaxWarning before importing
warnings.filterwarnings("ignore", category=SyntaxWarning, module="jieba")

import jieba  # noqa: E402

try:
    import MeCab
except ImportError as exc:
    msg = (
        "MeCab is required for Japanese word counting. "
        "Install: apt install mecab libmecab-dev && uv add mecab-python3 unidic-lite"
    )
    raise ImportError(msg) from exc

from uniseg.wordbreak import words as uniseg_words  # noqa: E402

logger = logging.getLogger(__name__)

try:
    _MECAB_TAGGER = MeCab.Tagger("-Owakati")
except RuntimeError as exc:
    msg = (
        "MeCab is installed but could not be initialised. "
        "Check that a dictionary is installed and MECABRC is configured correctly. "
        "Fix: apt install mecab mecab-ipadic-utf8 && uv add unidic-lite"
    )
    raise RuntimeError(msg) from exc

# Regex to strip Unicode format characters (category Cf)
_FORMAT_CHARS_RE = re.compile(r"[\u200b-\u200f\u2028-\u202f\u2060-\u2069\ufeff]")

# Regex to strip markdown link/image URLs: [text](url) -> [text]
_MARKDOWN_IMAGE_RE = re.compile(r"!\[")
_MARKDOWN_LINK_URL_RE = re.compile(r"\]\([^)]*\)")


def normalise_text(text: str) -> str:
    """Normalise text for word counting.

    Applies:
    1. NFKC Unicode normalisation (AC1.9)
    2. Strip zero-width / format characters (AC1.8)
    3. Strip markdown link/image URLs (AC1.6)
    """
    text = unicodedata.normalize("NFKC", text)
    text = _FORMAT_CHARS_RE.sub("", text)
    text = _MARKDOWN_IMAGE_RE.sub("[", text)
    text = _MARKDOWN_LINK_URL_RE.sub("]", text)

    return text


def _classify_codepoint(cp: int) -> str:
    """Classify a Unicode codepoint into a script category.

    Returns one of: "zh", "ja", "ko", "latin".

    CJK Unified Ideographs are initially classified as "zh"; the caller
    (segment_by_script) applies neighbour resolution to reclassify kanji
    adjacent to hiragana/katakana as "ja".
    """
    # Hiragana
    if 0x3040 <= cp <= 0x309F:
        return "ja"
    # Katakana (main block + extension + half-width)
    if 0x30A0 <= cp <= 0x30FF or 0x31F0 <= cp <= 0x31FF or 0xFF65 <= cp <= 0xFF9F:
        return "ja"
    # Hangul: Syllables, Jamo, Compatibility Jamo
    if 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F:
        return "ko"
    # CJK Unified Ideographs (all blocks)
    if (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0x2B740 <= cp <= 0x2B81F
        or 0x2B820 <= cp <= 0x2CEAF
        or 0x2CEB0 <= cp <= 0x2EBEF
        or 0x30000 <= cp <= 0x3134F
        or 0x31350 <= cp <= 0x323AF
    ):
        return "zh"
    # Everything else: Latin, punctuation, whitespace, numbers, emoji
    return "latin"


def segment_by_script(text: str) -> list[tuple[str, str]]:
    """Segment text into runs of consecutive characters with the same script.

    Returns a list of (script, text) tuples where script is one of:
    "zh", "ja", "ko", "latin".

    After initial per-codepoint classification, applies neighbour resolution:
    any "zh" segment immediately adjacent to a "ja" segment is reclassified
    as "ja" (kanji used in Japanese context).
    """
    if not text:
        return []

    # Phase 1: group consecutive codepoints by script
    segments: list[tuple[str, str]] = []
    current_script = _classify_codepoint(ord(text[0]))
    current_chars: list[str] = [text[0]]

    for ch in text[1:]:
        script = _classify_codepoint(ord(ch))
        if script == current_script:
            current_chars.append(ch)
        else:
            segments.append((current_script, "".join(current_chars)))
            current_script = script
            current_chars = [ch]

    segments.append((current_script, "".join(current_chars)))

    # Phase 2: neighbour resolution — reclassify "zh" adjacent to "ja" as "ja"
    scripts = [s for s, _ in segments]
    for i, (script, seg_text) in enumerate(segments):
        if script != "zh":
            continue
        prev_ja = i > 0 and scripts[i - 1] == "ja"
        next_ja = i < len(scripts) - 1 and scripts[i + 1] == "ja"
        if prev_ja or next_ja:
            segments[i] = ("ja", seg_text)
            scripts[i] = "ja"

    # Phase 3: merge adjacent segments of the same script
    merged: list[tuple[str, str]] = [segments[0]]
    for script, seg_text in segments[1:]:
        if script == merged[-1][0]:
            merged[-1] = (script, merged[-1][1] + seg_text)
        else:
            merged.append((script, seg_text))

    return merged


def word_count(text: str) -> int:
    """Count words in text with multilingual support and anti-gaming measures.

    Pipeline:
    1. Normalise (NFKC, strip zero-width chars, strip markdown URLs)
    2. Segment by script (Latin, Chinese, Japanese, Korean)
    3. Tokenise each segment with appropriate tokeniser
    4. Split tokens on hyphens (anti-gaming)
    5. Filter to tokens containing at least one Unicode letter
    6. Return count

    CJK tokenisation uses dictionary-based segmentation (jieba for Chinese,
    MeCab for Japanese), so exact counts may vary slightly across dictionary
    versions.
    """
    text = normalise_text(text)
    segments = segment_by_script(text)

    tokens: list[str] = []
    for script, segment_text in segments:
        if script == "zh":
            tokens.extend(jieba.lcut(segment_text, cut_all=False))
        elif script == "ja":
            parsed = _MECAB_TAGGER.parse(segment_text).strip()
            if parsed:
                tokens.extend(parsed.split())
        else:  # ko, latin — both use UAX #29
            tokens.extend(uniseg_words(segment_text))

    # Split on hyphens (anti-gaming: AC1.7), then keep only tokens
    # containing at least one Unicode letter
    def _has_letter(s: str) -> bool:
        return any(unicodedata.category(c).startswith("L") for c in s)

    return sum(1 for token in tokens for sub in token.split("-") if _has_letter(sub))
