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

import jieba  # noqa: F401 — used by word_count() in later tasks

try:
    import MeCab
except ImportError as exc:
    msg = (
        "MeCab is required for Japanese word counting. "
        "Install: apt install mecab libmecab-dev && uv add mecab-python3 unidic-lite"
    )
    raise ImportError(msg) from exc

from uniseg.wordbreak import words as uniseg_words  # noqa: F401 — used by word_count()

logger = logging.getLogger(__name__)

_MECAB_TAGGER = MeCab.Tagger("-Owakati")

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
    # NFKC normalisation: full-width -> ASCII, compatibility decomposition
    text = unicodedata.normalize("NFKC", text)

    # Strip Unicode format characters (zero-width spaces, joiners, etc.)
    text = _FORMAT_CHARS_RE.sub("", text)

    # Strip markdown image markers: ![alt](url) -> [alt](url)
    text = _MARKDOWN_IMAGE_RE.sub("[", text)

    # Strip markdown link URLs: [text](url) -> [text]
    text = _MARKDOWN_LINK_URL_RE.sub("]", text)

    return text
