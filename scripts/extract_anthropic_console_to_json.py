"""Extract Anthropic console API call exports from .docx to .json.

Each docx contains a single `client.messages.create(...)` call with the full
conversation as a messages array. This script parses the Python source out of
the docx paragraphs, extracts the messages list and model parameters, and
writes one JSON file per run.

Note: the original runs also had a system prompt which is not captured in these
console exports. The system prompt exists separately.

Usage::

    uvx --from python-docx python scripts/extract_anthropic_console_to_json.py <dir>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from docx import Document  # type: ignore[import-untyped]


def extract_source(docx_path: Path) -> str:
    """Join all paragraphs from a docx into one Python source string."""
    doc = Document(str(docx_path))
    return "\n".join(p.text for p in doc.paragraphs)


def extract_messages_and_params(source: str) -> dict[str, Any]:
    """Extract the messages array and call parameters from the source."""
    msg_start = source.find("messages=[")
    if msg_start == -1:
        msg = "Could not find messages=[ in source"
        raise ValueError(msg)

    bracket_start = source.index("[", msg_start)
    depth = 0
    i = bracket_start
    while i < len(source):
        if source[i] == "[":
            depth += 1
        elif source[i] == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1

    messages_str = source[bracket_start : i + 1]
    cleaned = re.sub(r",\s*([}\]])", r"\1", messages_str)
    messages = json.loads(cleaned)

    model_match = re.search(r'model="([^"]+)"', source)
    max_tokens_match = re.search(r"max_tokens=(\d+)", source)
    temperature_match = re.search(r"temperature=([\d.]+)", source)

    note = (
        "Extracted from Anthropic console export."
        " System prompt not included in these exports"
        " but exists separately."
    )
    return {
        "_note": note,
        "model": model_match.group(1) if model_match else "unknown",
        "max_tokens": (int(max_tokens_match.group(1)) if max_tokens_match else None),
        "temperature": (
            float(temperature_match.group(1)) if temperature_match else None
        ),
        "message_count": len(messages),
        "messages": messages,
    }


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(f"Usage: {sys.argv[0]} <input_dir>")

    input_dir = Path(sys.argv[1])
    if not input_dir.is_dir():
        sys.exit(f"Not a directory: {input_dir}")

    for docx_path in sorted(input_dir.iterdir()):
        if docx_path.suffix != ".docx":
            continue

        json_path = docx_path.with_suffix(".json")
        print(f"Processing: {docx_path.name}")
        try:
            source = extract_source(docx_path)
            data = extract_messages_and_params(source)
            json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"  -> {json_path.name} ({data['message_count']} messages)")
        except Exception as e:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
