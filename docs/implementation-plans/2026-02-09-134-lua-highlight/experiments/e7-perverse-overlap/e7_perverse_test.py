"""E7: Perverse overlapping highlight experiment.

Exercises the FULL existing pipeline:
  marker insertion -> Pandoc -> marker replacement -> LaTeX generation -> PDF compilation.

The test case has 4 highlights that overlap across an h1 heading and a paragraph,
creating every combination of nesting and crossing.
"""

import sys

sys.path.insert(
    0,
    "/home/brian/people/Brian/PromptGrimoireTool/.worktrees/134-lua-highlight/src",
)

import subprocess

from promptgrimoire.export.latex import (
    MarkerToken,
    Region,
    _insert_markers_into_html,
    _replace_markers_with_annots,
    build_regions,
    tokenize_markers,
)

html = (
    "<h1>This is demo. With silly header.</h1>\n"
    "<p>Foo bar the test text is going here but is very mixed up.</p>"
)

highlights = [
    {
        "start_char": 5,
        "end_char": 62,
        "tag": "jurisdiction",
        "author": "Alice",
        "text": "is demo...going",
        "comments": [],
    },
    {
        "start_char": 19,
        "end_char": 72,
        "tag": "legal_issues",
        "author": "Bob",
        "text": "silly...but ",
        "comments": [],
    },
    {
        "start_char": 54,
        "end_char": 79,
        "tag": "ratio",
        "author": "Carol",
        "text": "is going...very",
        "comments": [],
    },
    {
        "start_char": 68,
        "end_char": 71,
        "tag": "obiter",
        "author": "Dave",
        "text": "but",
        "comments": [],
    },
]

print("=== INPUT HTML ===")
print(html)
print()

# Step 1: Insert markers
marked_html, marker_highlights = _insert_markers_into_html(html, highlights)
print("=== MARKED HTML ===")
print(marked_html)
print()

# Show which markers map to which highlights
print("=== MARKER MAPPING ===")
for i, mh in enumerate(marker_highlights):
    print(f"  marker {i}: tag={mh['tag']}, start={mh['start_char']}, end={mh['end_char']}")
print()

# Step 2: Run pandoc
pandoc_result = subprocess.run(
    ["pandoc", "-f", "html", "-t", "latex"],
    input=marked_html,
    capture_output=True,
    text=True,
)
if pandoc_result.returncode != 0:
    print("=== PANDOC STDERR ===")
    print(pandoc_result.stderr)
marked_latex = pandoc_result.stdout
print("=== MARKED LATEX (after Pandoc) ===")
print(marked_latex)
print()

# Step 3: Tokenize and show regions
tokens = tokenize_markers(marked_latex)
print("=== TOKENS ===")
for i, t in enumerate(tokens):
    val_preview = t.value[:60].replace("\n", "\\n")
    print(f"  [{i}] {t.type.value:10s} idx={t.index} val={val_preview!r}")
print()

regions = build_regions(tokens)
print("=== REGIONS ===")
for i, r in enumerate(regions):
    active_names = []
    for idx in sorted(r.active):
        active_names.append(f"hl{idx}={marker_highlights[idx]['tag']}")
    annot_names = [f"ann{a}" for a in r.annots]
    text_preview = r.text[:80].replace("\n", "\\n")
    print(f"  [{i}] active={{{', '.join(active_names)}}} annots={annot_names}")
    print(f"      text={text_preview!r}")
print()

# Step 4: Replace markers with highlights
highlighted_latex = _replace_markers_with_annots(marked_latex, marker_highlights)
print("=== HIGHLIGHTED LATEX ===")
print(highlighted_latex)
print()

print("=== DONE ===")
