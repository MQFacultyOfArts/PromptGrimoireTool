#!/usr/bin/env python3
"""Manual PDF export test script for visual verification.

Usage:
    uv run python scripts/test_pdf_export.py

Produces output/183_annotated.pdf and opens it.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure we can import from the project
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from promptgrimoire.export.pdf_export import export_annotation_pdf
from promptgrimoire.parsers.rtf import parse_rtf

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


async def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Parse the RTF fixture
    rtf_path = FIXTURES_DIR / "183.rtf"
    print(f"Parsing {rtf_path}...")
    parsed = parse_rtf(rtf_path)

    # Sample annotations for testing
    highlights = [
        {
            "start_word": 100,
            "end_word": 120,
            "tag": "jurisdiction",
            "author": "Test User",
            "text": "sample highlighted text",
            "comments": [{"author": "Test User", "text": "This is a test comment"}],
        },
        {
            "start_word": 200,
            "end_word": 250,
            "tag": "legally_relevant_facts",
            "author": "Test User",
            "text": "another highlighted section",
            "comments": [],
        },
    ]

    tag_colours = {
        "jurisdiction": "#FFE4B5",
        "legally_relevant_facts": "#E6E6FA",
    }

    print("Exporting to PDF...")
    pdf_path = await export_annotation_pdf(
        html_content=parsed.html,
        highlights=highlights,
        tag_colours=tag_colours,
        general_notes="<p>Test notes for the document.</p>",
    )

    # Copy to output dir with nice name
    final_path = OUTPUT_DIR / "183_annotated.pdf"
    if pdf_path.exists():
        shutil.copy(pdf_path, final_path)
        print(f"PDF saved to: {final_path}")

        # Also copy .tex file for debugging
        tex_path = pdf_path.with_suffix(".tex")
        if tex_path.exists():
            shutil.copy(tex_path, OUTPUT_DIR / "183_annotated.tex")
            print(f"LaTeX saved to: {OUTPUT_DIR / '183_annotated.tex'}")

        # Open the PDF
        subprocess.run(["xdg-open", str(final_path)], check=False)
    else:
        print(f"ERROR: PDF not found at {pdf_path}")


if __name__ == "__main__":
    asyncio.run(main())
