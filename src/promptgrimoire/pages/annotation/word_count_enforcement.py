"""Re-export from canonical location for backwards compatibility.

The implementation lives in ``promptgrimoire.word_count_enforcement``.
This shim keeps existing imports (and AC7 guard tests) working.
"""

from __future__ import annotations

from promptgrimoire.word_count_enforcement import (
    WordCountViolation,
    check_word_count_violation,
    format_violation_message,
)

__all__ = [
    "WordCountViolation",
    "check_word_count_violation",
    "format_violation_message",
]
