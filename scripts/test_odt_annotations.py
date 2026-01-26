#!/usr/bin/env python3
"""Proof of concept: inject annotations into ODT and render PDF via LibreOffice.

Test: Can we inject comments at word positions and have LibreOffice render them?

Usage:
    uv run python scripts/test_odt_annotations.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Will need: uv add odfdo
try:
    from odfdo import Document, Paragraph
except ImportError:
    print("Install odfdo: uv add odfdo")
    raise

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "183.rtf"


def rtf_to_odt(rtf_path: Path, output_dir: Path) -> Path:
    """Convert RTF to ODT using LibreOffice."""
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        "odt",
        "--outdir",
        str(output_dir),
        str(rtf_path),
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, capture_output=True)
    return output_dir / (rtf_path.stem + ".odt")


def odt_to_pdf(odt_path: Path, output_dir: Path) -> Path:
    """Convert ODT to PDF using LibreOffice."""
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(odt_path),
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, capture_output=True)
    return output_dir / (odt_path.stem + ".pdf")


def get_word_at_position(document: Document, word_index: int) -> tuple[str, Paragraph]:
    """Find word at given index and its containing paragraph.

    Returns (word, paragraph) tuple.
    """
    body = document.body
    current_index = 0

    for paragraph in body.paragraphs:
        text = str(paragraph)
        words = text.split()

        if current_index + len(words) > word_index:
            # Word is in this paragraph
            local_index = word_index - current_index
            if local_index < len(words):
                return words[local_index], paragraph

        current_index += len(words)

    raise ValueError(
        f"Word index {word_index} out of range (total words: {current_index})"
    )


def inject_annotations(odt_path: Path, annotations: list[dict]) -> Path:
    """Inject annotations into ODT at specified word positions.

    Args:
        odt_path: Path to input ODT file.
        annotations: List of dicts with keys:
            - start_word: int - word index where annotation starts
            - text: str - annotation body text
            - author: str - annotation creator

    Returns:
        Path to modified ODT file.
    """
    document = Document(str(odt_path))

    for ann in annotations:
        word_index = ann["start_word"]
        try:
            word, paragraph = get_word_at_position(document, word_index)
            preview = ann["text"][:40]
            print(f"Annotation at word {word_index} ('{word}'): {preview}...")

            paragraph.insert_annotation(
                after=word,
                body=ann["text"],
                creator=ann.get("author", "PromptGrimoire"),
            )
        except ValueError as e:
            print(f"Warning: {e}")

    # Save to new file
    output_path = odt_path.with_stem(odt_path.stem + "_annotated")
    document.save(str(output_path))
    print(f"Saved: {output_path}")
    return output_path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Convert RTF to ODT
    print("\n=== Step 1: RTF → ODT ===")
    odt_path = rtf_to_odt(FIXTURE, OUTPUT_DIR)
    print(f"Created: {odt_path}")

    # Step 2: Count words to understand document structure
    print("\n=== Step 2: Analyze document ===")
    document = Document(str(odt_path))
    total_words = 0
    for para in document.body.paragraphs:
        words = str(para).split()
        total_words += len(words)
    print(f"Total words in document: {total_words}")

    # Step 3: Inject test annotations
    print("\n=== Step 3: Inject annotations ===")
    test_annotations = [
        {
            "start_word": 100,
            "text": "This is comment one - testing annotation at word 100",
            "author": "Test User",
        },
        {
            "start_word": 200,
            "text": "This is comment two - testing annotation at word 200. "
            "This comment is longer to test multiline rendering.",
            "author": "Test User",
        },
    ]

    annotated_odt = inject_annotations(odt_path, test_annotations)

    # Step 4: Render PDF
    print("\n=== Step 4: ODT → PDF ===")
    pdf_path = odt_to_pdf(annotated_odt, OUTPUT_DIR)
    print(f"Created: {pdf_path}")

    print("\n=== Done ===")
    print(f"Check the PDF at: {pdf_path}")
    print("Annotations should appear in the margin/sidebar.")


if __name__ == "__main__":
    main()
