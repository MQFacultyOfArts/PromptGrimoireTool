#!/usr/bin/env python3
"""Save clipboard content as a test fixture.

Usage:
    # Copy HTML from browser, then:
    uv run python scripts/save_clipboard_fixture.py claude
    uv run python scripts/save_clipboard_fixture.py chatgpt --lipsum
    uv run python scripts/save_clipboard_fixture.py gemini
    uv run python scripts/save_clipboard_fixture.py copilot

    --lipsum: Replace text content with lorem ipsum (preserves HTML structure)

Saves to: tests/fixtures/conversations/{name}.html
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "conversations"

LOREM_WORDS = [
    "lorem",
    "ipsum",
    "dolor",
    "sit",
    "amet",
    "consectetur",
    "adipiscing",
    "elit",
    "sed",
    "do",
    "eiusmod",
    "tempor",
    "incididunt",
    "ut",
    "labore",
    "et",
    "dolore",
    "magna",
    "aliqua",
    "enim",
    "ad",
    "minim",
    "veniam",
    "quis",
    "nostrud",
    "exercitation",
    "ullamco",
    "laboris",
    "nisi",
    "aliquip",
    "ex",
    "ea",
    "commodo",
    "consequat",
    "duis",
    "aute",
    "irure",
    "in",
    "reprehenderit",
    "voluptate",
    "velit",
    "esse",
    "cillum",
    "fugiat",
    "nulla",
    "pariatur",
    "excepteur",
    "sint",
    "occaecat",
    "cupidatat",
    "non",
    "proident",
    "sunt",
    "culpa",
    "qui",
    "officia",
    "deserunt",
    "mollit",
    "anim",
    "id",
    "est",
]


def lipsum_text(text: str) -> str:
    """Replace text with lorem ipsum, preserving word count and punctuation."""

    def replace_word(match: re.Match) -> str:
        word = match.group(0)
        replacement = random.choice(LOREM_WORDS)
        # Preserve capitalization
        if word[0].isupper():
            replacement = replacement.capitalize()
        if word.isupper():
            replacement = replacement.upper()
        return replacement

    # Replace words but keep punctuation, numbers, whitespace
    return re.sub(r"\b[a-zA-Z]+\b", replace_word, text)


def lipsum_html(html: str) -> str:
    """Replace text content in HTML with lorem ipsum, preserving tags."""
    # Split on HTML tags, lipsum only the text parts
    parts = re.split(r"(<[^>]+>)", html)
    result = []
    for part in parts:
        if part.startswith("<"):
            # Keep tags as-is
            result.append(part)
        else:
            # Lipsum text content
            result.append(lipsum_text(part))
    return "".join(result)


def get_clipboard() -> str:
    """Get clipboard content using xclip."""
    # Try HTML content first (preserves formatting from browser copy)
    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "text/html", "-o"],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            return result.stdout
    except subprocess.CalledProcessError:
        pass

    # Fall back to plain text
    result = subprocess.run(
        ["xclip", "-selection", "clipboard", "-o"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: save_clipboard_fixture.py <name> [--lipsum]")
        print("  e.g., save_clipboard_fixture.py claude --lipsum")
        sys.exit(1)

    args = sys.argv[1:]
    do_lipsum = "--lipsum" in args
    name = next(a for a in args if not a.startswith("-")).lower()

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    content = get_clipboard()
    if not content.strip():
        print("ERROR: Clipboard is empty")
        sys.exit(1)

    if do_lipsum:
        content = lipsum_html(content)
        print("Applied lorem ipsum replacement")

    output_path = FIXTURES_DIR / f"{name}.html"
    output_path.write_text(content, encoding="utf-8")
    print(f"Saved {len(content)} bytes to {output_path}")


if __name__ == "__main__":
    main()
