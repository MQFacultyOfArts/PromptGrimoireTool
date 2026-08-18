"""Tests for scripts/jsonl_to_md.py transcript conversion.

Covers ``convert_jsonl_to_md`` after decomposing it into ``_parse_jsonl_line``
and ``_record_to_markdown_section`` (see
``docs/design-plans/2026-04-23-ty-sa-typing-cleanup.md``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts.jsonl_to_md import convert_jsonl_to_md

if TYPE_CHECKING:
    from pathlib import Path


def test_convert_jsonl_to_md_synthetic_transcript(tmp_path: Path) -> None:
    """Synthetic input -> markdown shape: heading, roles, and skip rules."""
    records = [
        # Blank line and malformed JSON are both skipped, not errors.
        "",
        "{not valid json",
        # Non-message record type is skipped.
        json.dumps({"type": "progress", "message": {"role": "user"}}),
        # Simple string-content user turn.
        json.dumps(
            {"type": "user", "message": {"role": "user", "content": "hello there"}}
        ),
        # List-content assistant turn with a text block and a tool_use block.
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "checking the file"},
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "foo.py"},
                        },
                    ],
                },
            }
        ),
        # Content that renders to empty text is skipped.
        json.dumps({"type": "user", "message": {"role": "user", "content": "   "}}),
    ]
    jsonl_path = tmp_path / "transcript.jsonl"
    jsonl_path.write_text("\n".join(records) + "\n", encoding="utf-8")

    md = convert_jsonl_to_md(jsonl_path)

    assert md.startswith("# Conversation: transcript\n")
    assert "## User\n\nhello there\n" in md
    assert "## Assistant\n\nchecking the file" in md
    assert "**Tool: Read** `foo.py`" in md
    assert md.count("## User") == 1
    assert md.count("## Assistant") == 1
