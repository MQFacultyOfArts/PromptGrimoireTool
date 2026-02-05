#!/usr/bin/env python3
"""Analyse HTML fixture files for debugging the annotation pipeline.

Loads plain or gzipped HTML fixtures and runs common analysis queries,
eliminating the need for shell-level zcat/grep/perl.

Usage:
    uv run python scripts/analyse_fixture.py list
    uv run python scripts/analyse_fixture.py tags google_gemini_debug user-query
    uv run python scripts/analyse_fixture.py search claude_cooking "Thought process"
    uv run python scripts/analyse_fixture.py context claude_cooking \
        "Assistant:" --chars 200
    uv run python scripts/analyse_fixture.py structure google_aistudio_image
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "conversations"


def _load_fixture(name_or_path: str) -> tuple[str, str]:
    """Load a fixture by name or path, handling .html and .html.gz transparently.

    Returns (display_name, html_content).
    """
    # Try as direct path first
    path = Path(name_or_path)
    if path.exists():
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return path.stem.replace(".html", ""), f.read()
        return path.stem, path.read_text(encoding="utf-8")

    # Try as fixture name (without extension)
    name = name_or_path.lower()
    for ext in [".html", ".html.gz"]:
        candidate = FIXTURES_DIR / f"{name}{ext}"
        if candidate.exists():
            if ext == ".html.gz":
                with gzip.open(candidate, "rt", encoding="utf-8") as f:
                    return name, f.read()
            return name, candidate.read_text(encoding="utf-8")

    # Try matching as substring
    matches = []
    for f in sorted(FIXTURES_DIR.iterdir()):
        if f.name == "clean" or f.is_dir():
            continue
        stem = f.name.replace(".html.gz", "").replace(".html", "")
        if name in stem:
            matches.append(f)

    if len(matches) == 1:
        f = matches[0]
        stem = f.name.replace(".html.gz", "").replace(".html", "")
        if f.name.endswith(".gz"):
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                return stem, fh.read()
        return stem, f.read_text(encoding="utf-8")
    if len(matches) > 1:
        names = [m.name for m in matches]
        print(
            f"Ambiguous fixture name '{name}'. Matches: {', '.join(names)}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Fixture not found: {name_or_path}", file=sys.stderr)
    print("Available fixtures (use 'list' command):", file=sys.stderr)
    sys.exit(1)


def _strip_style_attrs(html: str) -> str:
    """Strip style='...' attributes for readability."""
    return re.sub(r'\s*style="[^"]*"', "", html)


def cmd_list(_args: argparse.Namespace) -> None:
    """List all available fixtures with sizes."""
    if not FIXTURES_DIR.exists():
        print(f"Fixtures directory not found: {FIXTURES_DIR}", file=sys.stderr)
        sys.exit(1)

    files = sorted(FIXTURES_DIR.iterdir())
    if not files:
        print("No fixtures found.")
        return

    print(f"{'Name':<45} {'Size':>10}  {'Uncompressed':>12}")
    print("-" * 70)

    for f in files:
        if f.is_dir():
            continue
        size = f.stat().st_size
        stem = f.name.replace(".html.gz", "").replace(".html", "")

        if f.name.endswith(".gz"):
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                uncompressed = len(fh.read())
            print(f"{stem:<45} {size:>10,}  {uncompressed:>10,} B")
        else:
            print(f"{stem:<45} {size:>10,}")


def cmd_tags(args: argparse.Namespace) -> None:
    """Count and show tags matching a pattern."""
    name, html = _load_fixture(args.fixture)
    pattern = args.tag_pattern

    # Find all tags matching the pattern
    tag_re = re.compile(rf"<(/?)({pattern}[^>\s]*)([^>]*)>", re.IGNORECASE)
    matches = tag_re.findall(html)

    if not matches:
        print(f"No tags matching '{pattern}' in {name}")
        return

    # Count opening tags by tag name
    tag_counts: Counter[str] = Counter()
    for closing, tag_name, _attrs in matches:
        if not closing:
            tag_counts[tag_name] += 1

    print(f"Tags matching '{pattern}' in {name}:")
    print()
    for tag_name, count in tag_counts.most_common():
        print(f"  <{tag_name}>: {count}")

    # Show first few with context
    print()
    opening_matches = [
        (m.start(), m.group())
        for m in re.finditer(rf"<({pattern}[^>]*)>", html, re.IGNORECASE)
    ]
    show_count = min(5, len(opening_matches))
    print(f"First {show_count} occurrences (with attributes):")
    for i, (pos, match_text) in enumerate(opening_matches[:show_count]):
        # Strip style for readability
        clean = _strip_style_attrs(match_text)
        print(f"  [{i + 1}] pos {pos}: {clean[:120]}")


def cmd_search(args: argparse.Namespace) -> None:
    """Search fixture HTML for a regex pattern, show matches with context."""
    name, html = _load_fixture(args.fixture)
    pattern = args.regex
    context_chars = args.chars

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        print(f"Invalid regex: {e}", file=sys.stderr)
        sys.exit(1)

    matches = list(regex.finditer(html))
    if not matches:
        print(f"No matches for /{pattern}/ in {name}")
        return

    print(f"{len(matches)} matches for /{pattern}/ in {name}:")
    print()

    for i, m in enumerate(matches[:20]):
        start = max(0, m.start() - context_chars)
        end = min(len(html), m.end() + context_chars)
        context = html[start:end]
        context = _strip_style_attrs(context)
        # Collapse whitespace for readability
        context = re.sub(r"\s+", " ", context).strip()

        print(f"  [{i + 1}] pos {m.start()}-{m.end()}:")
        print(f"    ...{context}...")
        print()

    if len(matches) > 20:
        print(f"  (showing 20 of {len(matches)} matches)")


def cmd_context(args: argparse.Namespace) -> None:
    """Find text in fixture, show N chars of HTML context around it."""
    name, html = _load_fixture(args.fixture)
    text = args.text
    context_chars = args.chars

    # Find all occurrences
    positions = []
    start = 0
    lower_html = html.lower()
    lower_text = text.lower()
    while True:
        idx = lower_html.find(lower_text, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1

    if not positions:
        print(f"Text '{text}' not found in {name}")
        return

    print(f"{len(positions)} occurrences of '{text}' in {name}:")
    print()

    for i, pos in enumerate(positions[:15]):
        start_ctx = max(0, pos - context_chars)
        end_ctx = min(len(html), pos + len(text) + context_chars)
        context = html[start_ctx:end_ctx]
        context = _strip_style_attrs(context)

        # Show with match highlighted by markers
        match_start = pos - start_ctx
        match_end = match_start + len(text)
        before = context[:match_start]
        match = context[match_start:match_end]
        after = context[match_end:]

        print(f"  [{i + 1}] pos {pos}:")
        print(f"    ...{before}>>>{match}<<<{after}...")
        print()

    if len(positions) > 15:
        print(f"  (showing 15 of {len(positions)} occurrences)")


def cmd_structure(args: argparse.Namespace) -> None:
    """Show tag structure summary: tag counts, data-* attributes, class names."""
    name, html = _load_fixture(args.fixture)

    # Count all opening tags
    tag_re = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)\b([^>]*)>")
    tag_counts: Counter[str] = Counter()
    data_attrs: Counter[str] = Counter()
    class_names: Counter[str] = Counter()

    for match in tag_re.finditer(html):
        tag_name = match.group(1).lower()
        attrs = match.group(2)
        tag_counts[tag_name] += 1

        # Extract data-* attributes
        for data_match in re.finditer(r"(data-[a-z-]+)", attrs):
            data_attrs[data_match.group(1)] += 1

        # Extract class names
        class_match = re.search(r'class="([^"]*)"', attrs)
        if class_match:
            for cls in class_match.group(1).split():
                class_names[cls] += 1

    print(f"Structure of {name} ({len(html):,} chars):")
    print()

    print("Tag counts (top 25):")
    for tag, count in tag_counts.most_common(25):
        print(f"  <{tag}>: {count}")

    if data_attrs:
        print()
        print("data-* attributes:")
        for attr, count in data_attrs.most_common(20):
            print(f"  {attr}: {count}")

    if class_names:
        print()
        print("Class names (top 25):")
        for cls, count in class_names.most_common(25):
            print(f"  .{cls}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse HTML fixture files for the annotation pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List all available fixtures with sizes")

    # tags
    p_tags = subparsers.add_parser(
        "tags", help="Count and show tags matching a pattern"
    )
    p_tags.add_argument("fixture", help="Fixture name or path")
    p_tags.add_argument(
        "tag_pattern", help="Tag name pattern (regex, e.g. 'user-query')"
    )

    # search
    p_search = subparsers.add_parser(
        "search", help="Search fixture HTML for a regex pattern"
    )
    p_search.add_argument("fixture", help="Fixture name or path")
    p_search.add_argument("regex", help="Regex pattern to search for")
    p_search.add_argument(
        "--chars", type=int, default=80, help="Context chars around match (default: 80)"
    )

    # context
    p_context = subparsers.add_parser(
        "context", help="Find text and show HTML context around it"
    )
    p_context.add_argument("fixture", help="Fixture name or path")
    p_context.add_argument("text", help="Text to find (case-insensitive)")
    p_context.add_argument(
        "--chars",
        type=int,
        default=150,
        help="Context chars around match (default: 150)",
    )

    # structure
    p_structure = subparsers.add_parser("structure", help="Show tag structure summary")
    p_structure.add_argument("fixture", help="Fixture name or path")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "tags": cmd_tags,
        "search": cmd_search,
        "context": cmd_context,
        "structure": cmd_structure,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
