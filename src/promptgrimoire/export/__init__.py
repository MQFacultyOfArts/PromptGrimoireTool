"""PDF export with annotated margins using LaTeX marginalia.

This module provides HTML-to-PDF export for annotated legal documents,
rendering annotations as numbered margin notes.
"""

from promptgrimoire.export.latex_render import (
    NoEscape,
    escape_latex,
    latex_cmd,
    render_latex,
)
from promptgrimoire.export.pandoc import (
    convert_html_to_latex,
    convert_html_with_annotations,
)
from promptgrimoire.export.pdf import compile_latex
from promptgrimoire.export.pdf_export import export_annotation_pdf, generate_tex_only
from promptgrimoire.export.preamble import build_annotation_preamble

__all__ = [
    "NoEscape",
    "build_annotation_preamble",
    "compile_latex",
    "convert_html_to_latex",
    "convert_html_with_annotations",
    "escape_latex",
    "export_annotation_pdf",
    "generate_tex_only",
    "latex_cmd",
    "render_latex",
]
