"""Shared fixtures for unit tests."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import emoji as emoji_lib
import pytest

from promptgrimoire.db.models import User

# Standard UUIDs for test references
SAMPLE_USER_ID = UUID("12345678-1234-5678-1234-567812345678")
SAMPLE_OWNER_ID = UUID("87654321-4321-8765-4321-876543218765")

# =============================================================================
# BLNS Corpus Parsing
# =============================================================================

type BLNSCorpus = dict[str, list[str]]


def _parse_blns_by_category(blns_path: Path) -> BLNSCorpus:
    """Parse blns.txt into {category: [strings]}.

    Category headers are lines starting with '#\\t' followed by title-case text
    after a blank line. Explanatory comments (containing 'which') are skipped.
    """
    categories: BLNSCorpus = {}
    current_category = "Uncategorized"
    prev_blank = True

    for line in blns_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        # Track blank lines
        if not stripped:
            prev_blank = True
            continue

        # Check for category header: #\t followed by title-case, after blank
        if line.startswith("#\t") and prev_blank:
            header_text = line[2:].strip()
            # Category names are Title Case, not explanations
            if (
                header_text
                and header_text[0].isupper()
                and "which" not in header_text.lower()
            ):
                current_category = header_text
                categories.setdefault(current_category, [])
        elif not line.startswith("#"):
            # Non-comment line is a test string
            categories.setdefault(current_category, []).append(line)

        prev_blank = False

    return categories


# Load BLNS corpus at module level (once per test session)
_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
BLNS_BY_CATEGORY: BLNSCorpus = _parse_blns_by_category(_FIXTURES_DIR / "blns.txt")

# Injection-related categories for always-run subset
INJECTION_CATEGORIES = [
    "Script Injection",
    "SQL Injection",
    "Server Code Injection",
    "Command Injection (Unix)",
    "Command Injection (Windows)",
    "Command Injection (Ruby)",
    "XXE Injection (XML)",
    "Unwanted Interpolation",
    "File Inclusion",
    "jinja2 injection",
]

BLNS_INJECTION_SUBSET: list[str] = [
    s for cat in INJECTION_CATEGORIES for s in BLNS_BY_CATEGORY.get(cat, [])
]

# =============================================================================
# Unicode Test Fixtures (derived from BLNS corpus)
# =============================================================================


def _is_cjk_codepoint(cp: int) -> bool:
    """Check if codepoint is in a CJK range."""
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


def _extract_cjk_chars_from_blns() -> list[str]:
    """Extract individual CJK characters from BLNS Two-Byte Characters category.

    Returns unique CJK characters for parameterized testing.
    """
    cjk_chars: set[str] = set()
    for s in BLNS_BY_CATEGORY.get("Two-Byte Characters", []):
        for char in s:
            if _is_cjk_codepoint(ord(char)):
                cjk_chars.add(char)
    return sorted(cjk_chars)


def _extract_emoji_from_blns() -> list[str]:
    """Extract individual emoji from BLNS Emoji category.

    Returns unique emoji strings (including ZWJ sequences) for parameterized testing.
    """
    emoji_set: set[str] = set()
    for s in BLNS_BY_CATEGORY.get("Emoji", []):
        # Use emoji library to find all emoji in the string
        for match in emoji_lib.emoji_list(s):
            emoji_set.add(match["emoji"])
    return sorted(emoji_set)


# Extracted test data from BLNS corpus
CJK_TEST_CHARS: list[str] = _extract_cjk_chars_from_blns()
EMOJI_TEST_STRINGS: list[str] = _extract_emoji_from_blns()

# ASCII strings for negative testing (from BLNS Reserved Strings)
ASCII_TEST_STRINGS: list[str] = [
    s
    for s in BLNS_BY_CATEGORY.get("Reserved Strings", [])
    if s.isascii() and len(s) > 0
][:10]  # Take first 10


@pytest.fixture
def make_user():
    """Factory for User instances."""

    def _make(
        email: str = "test@example.com", display_name: str = "Test User", **kwargs
    ):
        return User(email=email, display_name=display_name, **kwargs)

    return _make


@pytest.fixture
def make_workspace():
    """Factory for Workspace instances (not persisted)."""
    from promptgrimoire.db.models import Workspace

    def _make(**kwargs):
        return Workspace(**kwargs)

    return _make


@pytest.fixture
def make_workspace_document():
    """Factory for WorkspaceDocument instances (not persisted)."""
    from uuid import uuid4

    from promptgrimoire.db.models import WorkspaceDocument

    def _make(
        workspace_id: UUID | None = None,
        type: str = "source",
        content: str = "",
        source_type: str = "text",
        order_index: int = 0,
        title: str | None = None,
        **kwargs,
    ):
        return WorkspaceDocument(
            workspace_id=workspace_id or uuid4(),
            type=type,
            content=content,
            source_type=source_type,
            order_index=order_index,
            title=title,
            **kwargs,
        )

    return _make
