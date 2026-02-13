"""LaTeX annotation formatting.

Produces pre-formatted ``\\annot{colour}{content}`` LaTeX strings for the
``data-annots`` span attribute consumed by ``highlight.lua``.

Separated from ``highlight_spans.py`` (HTML region computation) for
single-responsibility clarity.
"""

from __future__ import annotations

from typing import Any

from promptgrimoire.export.latex_render import NoEscape, latex_cmd
from promptgrimoire.export.preamble import _format_timestamp, _strip_test_uuid
from promptgrimoire.export.unicode_latex import escape_unicode_latex


def format_annot_latex(
    highlight: dict[str, Any],
    para_ref: str = "",
) -> str:
    r"""Format a highlight as a LaTeX ``\annot`` command.

    Layout in margin note::

        **Tag** [para]
        name, date
        ---
        comment text...

    Adapts the logic from ``_format_annot()`` (formerly in ``latex.py``) for
    use by ``compute_highlight_spans()`` when populating the ``data-annots``
    attribute.

    Args:
        highlight: Highlight dict with ``tag``, ``author``, ``text``,
            ``comments``, ``created_at``.
        para_ref: Paragraph reference string (e.g. ``"[45]"`` or
            ``"[45]-[48]"``).

    Returns:
        LaTeX ``\annot{colour}{margin_content}`` command string.
    """
    tag = highlight.get("tag", "jurisdiction")
    author = _strip_test_uuid(highlight.get("author", "Unknown"))
    comments = highlight.get("comments", [])
    created_at = highlight.get("created_at", "")

    # Tag colour name (matches \definecolor name).
    # NoEscape: colour names may contain '#' (pre-existing bug, see AC4.4).
    colour_name = NoEscape(f"tag-{tag.replace('_', '-')}")

    # Build margin content
    tag_display = tag.replace("_", " ").title()
    timestamp = _format_timestamp(created_at)

    # escape_unicode_latex() already escapes LaTeX specials, so its output
    # is trusted LaTeX (NoEscape).  Do NOT layer escape_latex() on top.
    tag_esc = NoEscape(escape_unicode_latex(tag_display))

    # Line 1: **Tag** [para]
    tag_bold = latex_cmd("textbf", tag_esc)
    if para_ref:
        margin_parts: list[str] = [f"{tag_bold} {para_ref}"]
    else:
        margin_parts = [str(tag_bold)]

    # Line 2: name, date (scriptsize)
    author_esc = NoEscape(escape_unicode_latex(author))
    byline = f"{author_esc}, {timestamp}" if timestamp else str(author_esc)
    margin_parts.append(f"\\par{{\\scriptsize {byline}}}")

    # Separator and comments if present
    if comments:
        margin_parts.append("\\par\\hrulefill")
        for comment in comments:
            c_author = _strip_test_uuid(comment.get("author", "Unknown"))
            c_text = comment.get("text", "")
            c_timestamp = _format_timestamp(comment.get("created_at", ""))
            c_author_esc = NoEscape(escape_unicode_latex(c_author))
            c_text_esc = NoEscape(escape_unicode_latex(c_text))
            if c_timestamp:
                c_bold = latex_cmd("textbf", c_author_esc)
                attribution = f"{c_bold}, {c_timestamp}:"
            else:
                c_bold = latex_cmd("textbf", NoEscape(f"{c_author_esc}:"))
                attribution = str(c_bold)
            margin_parts.append(f"\\par{{\\scriptsize {attribution}}} {c_text_esc}")

    margin_content = NoEscape("".join(margin_parts))

    return str(latex_cmd("annot", colour_name, margin_content))
