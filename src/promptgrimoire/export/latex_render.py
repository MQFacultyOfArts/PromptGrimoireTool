"""LaTeX rendering utilities: NoEscape, escape_latex, latex_cmd, render_latex.

Replaces PyLaTeX's useful patterns without the dependency.  Provides two
tools for two patterns:

- ``latex_cmd("definecolor", "mycolor", "HTML", "FF0000")`` for simple
  ``\\name{arg1}{arg2}`` commands -- no ``{{`` brace escaping needed.
- ``render_latex(t"\\textbf{{{val}}}")`` for complex templates where
  command structure is irregular -- interpolated values are auto-escaped.

Both auto-escape interpolated/argument values unless marked ``NoEscape``.
"""

from __future__ import annotations

from string.templatelib import Interpolation, Template

__all__ = ["NoEscape", "escape_latex", "latex_cmd", "render_latex"]

# The same 10 LaTeX specials are defined as _LATEX_SPECIAL_CHARS in
# unicode_latex.py (list-of-tuples for chained str.replace in the full
# Unicode pipeline).  This dict serves escape_latex().  Keep in sync.
_LATEX_SPECIALS: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "#": r"\#",
    "$": r"\$",
    "%": r"\%",
    "&": r"\&",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


class NoEscape(str):
    """Mark a string as trusted LaTeX that should not be escaped."""


def escape_latex(text: str) -> NoEscape:
    """Escape LaTeX special characters in *text*.

    If *text* is already a ``NoEscape`` instance it is returned unchanged.
    Otherwise all 10 LaTeX special characters are replaced and the result
    is wrapped in ``NoEscape`` (it is now safe for inclusion in LaTeX).

    Uses character-by-character replacement to avoid double-escaping
    (e.g. ``\\`` -> ``\\textbackslash{}`` must not then escape the ``{}``).
    """
    if isinstance(text, NoEscape):
        return text
    parts: list[str] = []
    for ch in text:
        parts.append(_LATEX_SPECIALS.get(ch, ch))
    return NoEscape("".join(parts))


def latex_cmd(name: str, *args: str | NoEscape) -> NoEscape:
    r"""Build a LaTeX command ``\name{arg1}{arg2}...``.

    Each argument is auto-escaped via ``escape_latex`` unless it is
    already a ``NoEscape`` instance.  The returned string is marked
    ``NoEscape`` since the complete command is trusted.
    """
    parts: list[str] = [f"\\{name}"]
    for arg in args:
        safe = arg if isinstance(arg, NoEscape) else escape_latex(arg)
        parts.append(f"{{{safe}}}")
    return NoEscape("".join(parts))


def render_latex(template: Template) -> str:
    """Render a t-string template with auto-escaping of interpolations.

    Static text (literal parts of the template) is emitted verbatim --
    it contains intentional LaTeX markup.  Interpolated values are
    escaped via ``escape_latex`` unless they are ``NoEscape`` instances.

    Conversion specifiers (``!r``, ``!s``, ``!a``) and format specs
    are applied before escaping, matching Python's f-string semantics.
    """
    parts: list[str] = []
    for item in template:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, Interpolation):
            value = item.value
            # Apply conversion (!r, !s, !a) if specified
            if item.conversion == "r":
                value = repr(value)
            elif item.conversion == "s":
                value = str(value)
            elif item.conversion == "a":
                value = ascii(value)
            # Apply format_spec if specified
            if item.format_spec:
                value = format(value, item.format_spec)
            # Auto-escape unless NoEscape
            if isinstance(value, NoEscape):
                parts.append(str(value))
            else:
                parts.append(str(escape_latex(str(value))))
    return "".join(parts)
