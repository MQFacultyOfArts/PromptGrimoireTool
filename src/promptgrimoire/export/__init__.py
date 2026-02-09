"""PDF export with annotated margins using LaTeX marginalia.

This module provides HTML-to-PDF export for annotated legal documents,
rendering annotations as numbered margin notes.
"""

from promptgrimoire.export.pandoc import convert_html_to_latex
from promptgrimoire.export.pdf import compile_latex
from promptgrimoire.export.pdf_export import export_annotation_pdf

__all__ = [
    "compile_latex",
    "convert_html_to_latex",
    "export_annotation_pdf",
]
