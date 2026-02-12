"""PDF export with annotated margins using LaTeX marginalia.

This module provides HTML-to-PDF export for annotated legal documents,
rendering annotations as numbered margin notes.
"""

from promptgrimoire.export.pandoc import (
    convert_html_to_latex,
    convert_html_with_annotations,
)
from promptgrimoire.export.pdf import compile_latex
from promptgrimoire.export.pdf_export import export_annotation_pdf, generate_tex_only
from promptgrimoire.export.preamble import build_annotation_preamble

__all__ = [
    "build_annotation_preamble",
    "compile_latex",
    "convert_html_to_latex",
    "convert_html_with_annotations",
    "export_annotation_pdf",
    "generate_tex_only",
]
