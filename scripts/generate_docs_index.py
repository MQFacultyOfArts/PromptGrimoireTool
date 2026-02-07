"""Generate docs/_index.md from cached documentation frontmatter.

Scans docs/ subdirectories for .md files with YAML frontmatter,
extracts summaries, and writes a structured index file.

Usage:
    uv run python scripts/generate_docs_index.py
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS_DIR = Path(__file__).parent.parent / "docs"
INDEX_PATH = DOCS_DIR / "_index.md"

# Directories that aren't cached library docs
SKIP_DIRS = {"design-plans", "implementation-plans", "wip", "reviews"}

# Files at docs/ root that aren't library docs
SKIP_FILES = {"_index.md", "ARCHITECTURE.md", "dependency-rationale.md", "testing.md"}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
SUMMARY_RE = re.compile(r"^summary:\s*(.+)$", re.MULTILINE)
TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def extract_summary(path: Path) -> str:
    """Extract summary from YAML frontmatter, or first heading as fallback."""
    text = path.read_text(encoding="utf-8")

    fm_match = FRONTMATTER_RE.match(text)
    if fm_match:
        summary_match = SUMMARY_RE.search(fm_match.group(1))
        if summary_match:
            return summary_match.group(1).strip()

    title_match = TITLE_RE.search(text)
    if title_match:
        return title_match.group(1).strip()

    return path.stem.replace("-", " ").title()


def collect_docs() -> dict[str, list[tuple[str, str]]]:
    """Collect docs grouped by subdirectory.

    Returns: {dir_name: [(relative_path, summary), ...]}
    """
    groups: dict[str, list[tuple[str, str]]] = {}

    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        rel = md_file.relative_to(DOCS_DIR)

        if rel.name in SKIP_FILES and len(rel.parts) == 1:
            continue

        if any(rel.parts[0] == skip for skip in SKIP_DIRS):
            continue

        if len(rel.parts) == 1:
            # Root-level doc (like testing.md) — skip, handled separately
            continue

        dir_name = rel.parts[0]
        summary = extract_summary(md_file)
        groups.setdefault(dir_name, []).append((str(rel), summary))

    return groups


def generate_index() -> str:
    """Generate the full index markdown."""
    groups = collect_docs()

    lines = [
        "# Cached Documentation Index",
        "",
        "This directory contains cached documentation for project dependencies.",
        "Documentation is automatically cached by the `cache-docs` skill when fetching",
        "library references during development.",
        "",
        "**Auto-generated** by `scripts/generate_docs_index.py`"
        " — do not edit manually.",
        "",
    ]

    for dir_name in sorted(groups):
        lines.append(f"## {dir_name}")
        lines.append("")
        for rel_path, summary in groups[dir_name]:
            lines.append(f"- [{summary}]({rel_path})")
        lines.append("")

    # Standalone docs at root level
    lines.append("---")
    lines.append("")
    lines.append("## Project Documents")
    lines.append("")
    lines.append("- [Testing Guidelines](testing.md)")
    lines.append("- [Architecture](ARCHITECTURE.md)")
    lines.append("- [Dependency Rationale](dependency-rationale.md)")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    content = generate_index()
    INDEX_PATH.write_text(content, encoding="utf-8")
    print(f"Written {INDEX_PATH}")
