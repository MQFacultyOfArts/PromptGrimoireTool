"""Guard test: every role from every registered handler has CSS, LaTeX, and Lua styling.

If a new handler introduces a role (e.g. "system") but forgets to add the
corresponding CSS rule, LaTeX environment, or Lua speaker entry, this test
will catch it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# File paths for the styling resources
# ---------------------------------------------------------------------------
_EXPORT_DIR = Path(__file__).resolve().parents[4] / "src" / "promptgrimoire" / "export"
_CSS_FILE = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "promptgrimoire"
    / "pages"
    / "annotation"
    / "css.py"
)
_STY_FILE = _EXPORT_DIR / "promptgrimoire-export.sty"
_LUA_FILE = _EXPORT_DIR / "filters" / "libreoffice.lua"


def _assert_role_has_styling(
    role: str, css_text: str, sty_text: str, lua_text: str
) -> None:
    """Assert that *role* has matching CSS, LaTeX, and Lua styling.

    Raises ``AssertionError`` with a descriptive message if any of the three
    styling artefacts is missing.

    Args:
        role: Speaker role name (e.g. ``"user"``, ``"assistant"``).
        css_text: Full text of the CSS source file.
        sty_text: Full text of the ``.sty`` LaTeX package.
        lua_text: Full text of the Lua Pandoc filter.
    """
    css_selector = f'[data-speaker="{role}"]'
    assert css_selector in css_text, f"CSS is missing a rule for {css_selector}"

    sty_env = f"]{{{role}turn}}"
    assert sty_env in sty_text, (
        f"LaTeX .sty is missing \\newmdenv definition ending with {sty_env}"
    )

    # The Lua table uses bare identifiers as keys, e.g.  user = {
    # Match the role as a table key (with optional whitespace around '=').
    assert f"{role}" in lua_text, (
        f"Lua filter speaker_roles table is missing key '{role}'"
    )
    # Stricter check: role appears as a key in the speaker_roles table
    # (format: "  role_name  = {")
    import re

    lua_key_pattern = rf"^\s*{re.escape(role)}\s*="
    assert re.search(lua_key_pattern, lua_text, re.MULTILINE), (
        f"Lua filter speaker_roles table has no key entry for '{role}'"
    )


def _collect_all_handler_roles() -> set[str]:
    """Return the union of all role names from all registered handlers."""
    from promptgrimoire.export.platforms import _handlers

    roles: set[str] = set()
    for handler in _handlers.values():
        roles.update(handler.get_turn_markers().keys())
    return roles


# ---------------------------------------------------------------------------
# Parametrised guard test
# ---------------------------------------------------------------------------

# Collect roles at module load so pytest can parametrise.
_ALL_ROLES = sorted(_collect_all_handler_roles())


@pytest.mark.parametrize("role", _ALL_ROLES)
class TestRoleStylingCoverage:
    """Every handler role must have CSS, LaTeX (.sty), and Lua styling."""

    def test_role_has_all_styling(self, role: str) -> None:
        """Role '{role}' has matching CSS, LaTeX, and Lua definitions."""
        css_text = _CSS_FILE.read_text()
        sty_text = _STY_FILE.read_text()
        lua_text = _LUA_FILE.read_text()

        _assert_role_has_styling(role, css_text, sty_text, lua_text)


class TestNegativeCoverage:
    """Verify the helper actually catches missing styling."""

    def test_unknown_role_raises_assertion_error(self) -> None:
        """A fake role that has no styling raises AssertionError."""
        css_text = _CSS_FILE.read_text()
        sty_text = _STY_FILE.read_text()
        lua_text = _LUA_FILE.read_text()

        with pytest.raises(AssertionError):
            _assert_role_has_styling("unknown_role", css_text, sty_text, lua_text)
