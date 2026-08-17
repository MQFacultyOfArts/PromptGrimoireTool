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


def _apply_conversion(value: object, conversion: str | None) -> object:
    """Apply an f-string-style conversion specifier (``!r``, ``!s``, ``!a``).

    Returns *value* unchanged when *conversion* is ``None`` or unrecognised.
    """
    if conversion == "r":
        return repr(value)
    if conversion == "s":
        return str(value)
    if conversion == "a":
        return ascii(value)
    return value


def _render_interpolation(item: Interpolation) -> str:
    """Render one t-string interpolation: conversion, format spec, escaping.

    Matches Python's f-string evaluation order -- conversion first, then
    format spec, then (unless the result is ``NoEscape``) LaTeX escaping.
    """
    value = _apply_conversion(item.value, item.conversion)
    if item.format_spec:
        value = format(value, item.format_spec)
    if isinstance(value, NoEscape):
        return str(value)
    return str(escape_latex(str(value)))


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
            parts.append(_render_interpolation(item))
    return "".join(parts)
