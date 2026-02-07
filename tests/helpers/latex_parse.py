"""LaTeX AST parse helpers for test assertions.

Thin wrappers around pylatexenc's LatexWalker, configured with
the custom macros used by the PromptGrimoire export pipeline.
"""

from __future__ import annotations

from pylatexenc.latexwalker import (
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexMacroNode,
    LatexWalker,
    get_default_latex_context_db,
)
from pylatexenc.macrospec import MacroSpec


def _build_latex_context():
    """Build a latex context with our custom macros."""
    ctx = get_default_latex_context_db()
    ctx = ctx.filter_context(keep_categories=["latex-base"])
    ctx.add_context_category(
        "promptgrimoire-export",
        macros=[
            MacroSpec("highLight", "[{"),
            MacroSpec("underLine", "[{"),
            MacroSpec("annot", "{"),
            MacroSpec("definecolor", "{{{"),
            MacroSpec("colorlet", "{{"),
            MacroSpec("cjktext", "{"),
            MacroSpec("emoji", "{"),
        ],
    )
    return ctx


def parse_latex(text: str) -> list:
    """Parse LaTeX text into a node list.

    Uses a LatexWalker configured with the custom macros from
    the PromptGrimoire export pipeline.
    """
    ctx = _build_latex_context()
    walker = LatexWalker(
        text,
        latex_context=ctx,
        tolerant_parsing=True,
    )
    nodelist, _, _ = walker.get_latex_nodes(pos=0)
    return list(nodelist)


def find_macros(
    nodes: list,
    name: str,
) -> list[LatexMacroNode]:
    """Recursively find all macro nodes with the given name."""
    found: list[LatexMacroNode] = []
    _walk(nodes, name, found)
    return found


def _walk(
    nodes: list,
    name: str,
    found: list[LatexMacroNode],
) -> None:
    """Recurse through node tree collecting matching macros."""
    for node in nodes:
        if isinstance(node, LatexMacroNode):
            if node.macroname == name:
                found.append(node)
            # Recurse into macro arguments
            if node.nodeargd and node.nodeargd.argnlist:
                for arg in node.nodeargd.argnlist:
                    if arg is not None and hasattr(arg, "nodelist") and arg.nodelist:
                        _walk(
                            list(arg.nodelist),
                            name,
                            found,
                        )
        elif isinstance(
            node,
            (LatexEnvironmentNode, LatexGroupNode),
        ):
            if node.nodelist:
                _walk(list(node.nodelist), name, found)


def require_opt_arg(node: LatexMacroNode) -> str:
    """Like get_opt_arg but asserts the arg exists. For test assertions."""
    result = get_opt_arg(node)
    assert result is not None, f"Expected optional arg on \\{node.macroname}, got None"
    return result


def get_opt_arg(node: LatexMacroNode) -> str | None:
    """Extract the text of the optional [...] argument.

    Returns None if the macro has no optional argument.
    """
    if not node.nodeargd or not node.nodeargd.argnlist:
        return None
    for arg in node.nodeargd.argnlist:
        if arg is None:
            continue
        if hasattr(arg, "delimiters"):
            delims = arg.delimiters
            if delims and delims[0] == "[":
                return _flatten_text(arg)
    return None


def get_body_text(node: LatexMacroNode) -> str:
    """Extract flattened text of the first mandatory {...} argument.

    Recurses through nested macros to get leaf text.
    """
    if not node.nodeargd or not node.nodeargd.argnlist:
        return ""
    for arg in node.nodeargd.argnlist:
        if arg is None:
            continue
        if hasattr(arg, "delimiters"):
            delims = arg.delimiters
            if delims and delims[0] == "{":
                return _flatten_text(arg)
    return ""


def get_mandatory_args(node: LatexMacroNode) -> list[str]:
    """Extract flattened text of all mandatory {...} arguments."""
    if not node.nodeargd or not node.nodeargd.argnlist:
        return []
    result: list[str] = []
    for arg in node.nodeargd.argnlist:
        if arg is None:
            continue
        if hasattr(arg, "delimiters"):
            delims = arg.delimiters
            if delims and delims[0] == "{":
                result.append(_flatten_text(arg))
    return result


def _flatten_text(node) -> str:
    """Recursively flatten a node tree into plain text."""
    if not hasattr(node, "nodelist") or node.nodelist is None:
        if hasattr(node, "chars"):
            return node.chars
        return ""
    parts: list[str] = []
    for child in node.nodelist:
        if isinstance(child, LatexMacroNode):
            # Recurse into macro's body argument
            body = get_body_text(child)
            if body:
                parts.append(body)
            elif hasattr(child, "chars"):
                parts.append(child.chars)
        elif isinstance(
            child,
            (LatexEnvironmentNode, LatexGroupNode),
        ):
            parts.append(_flatten_text(child))
        elif hasattr(child, "chars"):
            parts.append(child.chars)
    return "".join(parts)
