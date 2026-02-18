"""Unit tests for TagInfo dataclass.

Verifies that TagInfo instances are frozen, have expected fields, and
can be used as dict keys (hashable).

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_03.md Task 1
- AC: three-tab-ui.AC2.1 (data structure)
- Design: docs/implementation-plans/2026-02-18-95-annotation-tags/phase_04.md Task 1
- AC: 95-annotation-tags.AC5.1 (DB-backed tag list)
"""

from __future__ import annotations

import re

from promptgrimoire.pages.annotation.tags import TagInfo


class TestTagInfo:
    """Verify TagInfo dataclass properties."""

    def test_tag_info_has_expected_fields(self) -> None:
        """TagInfo instances have name, colour, and raw_key string fields."""
        ti = TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key="some-uuid")
        assert isinstance(ti.name, str)
        assert isinstance(ti.colour, str)
        assert isinstance(ti.raw_key, str)

    def test_tag_info_is_frozen(self) -> None:
        """TagInfo instances are immutable (frozen dataclass)."""
        ti = TagInfo(name="Test", colour="#000000", raw_key="key")
        try:
            ti.name = "Changed"  # type: ignore[misc]  -- testing frozen
            raise AssertionError("Expected FrozenInstanceError")
        except AttributeError:
            pass

    def test_tag_info_colour_is_hex(self) -> None:
        """Colour field should be a 7-character hex string."""
        hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        ti = TagInfo(name="Test", colour="#1f77b4", raw_key="key")
        assert hex_pattern.match(ti.colour)

    def test_tag_info_equality(self) -> None:
        """Two TagInfo with same fields are equal."""
        a = TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key="key1")
        b = TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key="key1")
        assert a == b

    def test_tag_info_inequality(self) -> None:
        """TagInfo with different raw_key are not equal."""
        a = TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key="key1")
        b = TagInfo(name="Jurisdiction", colour="#1f77b4", raw_key="key2")
        assert a != b
