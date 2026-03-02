"""Word count enforcement helpers for export-time violation checks.

Pure functions — no UI, no async, no side effects.
Computes violation state and formats human-readable messages.

This module is intentionally only imported by export-related code
(pdf_export.py). Save, edit, and share paths must never import it.
See AC7.1-AC7.4 tests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WordCountViolation:
    """Immutable violation state from a word count check."""

    over_limit: bool = False
    under_minimum: bool = False
    over_by: int = 0
    under_by: int = 0
    count: int = 0
    word_minimum: int | None = None
    word_limit: int | None = None

    @property
    def has_violation(self) -> bool:
        """Return True if any word count limit is violated."""
        return self.over_limit or self.under_minimum


def check_word_count_violation(
    count: int,
    word_minimum: int | None,
    word_limit: int | None,
) -> WordCountViolation:
    """Check word count against configured limits.

    Args:
        count: Current word count.
        word_minimum: Minimum word count threshold, or None.
        word_limit: Maximum word count threshold, or None.

    Returns:
        WordCountViolation with computed violation state.

    Rules:
        - At limit (count == word_limit) counts as over.
        - At minimum (count == word_minimum) is acceptable (not under).
        - Both over_limit and under_minimum can be set independently,
          though validated data (word_minimum < word_limit) makes
          simultaneous True unreachable.
    """
    over_limit = False
    under_minimum = False
    over_by = 0
    under_by = 0

    if word_limit is not None and count >= word_limit:
        over_limit = True
        over_by = count - word_limit

    if word_minimum is not None and count < word_minimum:
        under_minimum = True
        under_by = word_minimum - count

    return WordCountViolation(
        over_limit=over_limit,
        under_minimum=under_minimum,
        over_by=over_by,
        under_by=under_by,
        count=count,
        word_minimum=word_minimum,
        word_limit=word_limit,
    )
