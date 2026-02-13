"""Tests for BLNS corpus parsing."""

from tests.unit.conftest import BLNS_BY_CATEGORY, BLNS_INJECTION_SUBSET


class TestBLNSParsing:
    """Verify BLNS corpus is parsed correctly."""

    def test_blns_has_categories(self) -> None:
        """BLNS should parse into multiple categories."""
        assert len(BLNS_BY_CATEGORY) > 10, "Expected at least 10 categories"

    def test_blns_has_two_byte_characters(self) -> None:
        """Two-Byte Characters category should exist with CJK strings."""
        assert "Two-Byte Characters" in BLNS_BY_CATEGORY
        strings = BLNS_BY_CATEGORY["Two-Byte Characters"]
        assert len(strings) > 0
        # Should contain Japanese
        assert any("\u7530\u4e2d" in s for s in strings)

    def test_injection_subset_populated(self) -> None:
        """Injection subset should contain strings from injection categories."""
        assert len(BLNS_INJECTION_SUBSET) > 20, "Expected at least 20 injection strings"

    def test_injection_subset_has_sql(self) -> None:
        """Injection subset should include SQL injection strings."""
        assert any("SELECT" in s or "DROP" in s for s in BLNS_INJECTION_SUBSET)
