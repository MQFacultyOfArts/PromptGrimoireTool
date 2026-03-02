"""Word count enforcement helpers for export-time violation checks.

Pure functions -- no UI, no async, no side effects.
Computes violation state and formats human-readable messages.

Lives at the package root (alongside ``word_count.py``) so both
``export/pdf_export.py`` and ``pages/annotation/pdf_export.py`` can
import it without cross-boundary dependencies.

Only export-related code should import this module.  Save, edit, and
share paths must never import it.  See AC7.1-AC7.4 tests.
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


def format_violation_message(violation: WordCountViolation) -> str:
    """Format a human-readable violation message for dialog display.

    Args:
        violation: The violation state to describe.

    Returns:
        A sentence describing what limit(s) are violated.

    Message patterns:
        - No violation: returns empty string.
        - Both violated: mentions over and under in one sentence.
        - Over only: includes word limit and current count.
        - Under only: includes word minimum and current count.
    """
    if not violation.has_violation:
        return ""
    if violation.over_limit and violation.under_minimum:
        return (
            f"Your response is {violation.over_by} words over the limit"
            f" and {violation.under_by} words under the minimum."
        )
    if violation.over_limit:
        return (
            f"Your response is {violation.over_by} words over the"
            f" {violation.word_limit}-word limit"
            f" (current count: {violation.count:,})."
        )
    return (
        f"Your response is {violation.under_by} words under the"
        f" {violation.word_minimum}-word minimum"
        f" (current count: {violation.count:,})."
    )
