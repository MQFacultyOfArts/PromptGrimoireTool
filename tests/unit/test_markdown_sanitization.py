"""Tests verifying markdown2 sanitization for XSS protection.

HIGH-1: Verify that markdown2 with safe_mode='escape' properly escapes
potentially dangerous HTML like script tags. LLM-generated reasoning traces
are rendered via ui.markdown(), so we need to ensure malicious content is
safely escaped.

NOTE: NiceGUI's ui.markdown() does NOT use safe_mode by default. This test
documents the correct usage for secure rendering. If these tests fail,
we need to:
1. Either configure NiceGUI/markdown2 with safe_mode='escape'
2. Or switch to rendering as plain text (ui.label with font-mono)
"""

from __future__ import annotations

import markdown2


class TestMarkdown2SafeModeEscape:
    """Test markdown2 with safe_mode='escape' sanitizes dangerous HTML.

    These tests verify that when safe_mode='escape' is used, HTML is properly
    escaped to prevent XSS attacks.
    """

    def test_script_tags_are_escaped(self) -> None:
        """Script tags should be escaped, not rendered as executable HTML."""
        malicious_input = '<script>alert("xss")</script>'
        result = markdown2.markdown(malicious_input, safe_mode="escape")

        # The script tag should be escaped
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_javascript_href_sanitized(self) -> None:
        """javascript: URLs in links should be sanitized."""
        malicious_input = '[click me](javascript:alert("xss"))'
        result = markdown2.markdown(malicious_input, safe_mode="escape")

        # markdown2 safe_mode replaces javascript: hrefs with "#"
        assert "javascript:" not in result
        assert 'href="#"' in result  # Link is neutered

    def test_raw_html_javascript_escaped(self) -> None:
        """Raw HTML with javascript: should be escaped."""
        malicious_input = '<a href="javascript:alert(1)">click</a>'
        result = markdown2.markdown(malicious_input, safe_mode="escape")

        # Raw HTML should be escaped
        assert "&lt;a href" in result

    def test_event_handlers_escaped(self) -> None:
        """HTML event handlers like onclick should be escaped."""
        malicious_input = '<div onclick="alert(1)">test</div>'
        result = markdown2.markdown(malicious_input, safe_mode="escape")

        # Raw HTML should be escaped
        assert "&lt;div onclick" in result

    def test_iframe_escaped(self) -> None:
        """iframes should be escaped."""
        malicious_input = '<iframe src="https://evil.com"></iframe>'
        result = markdown2.markdown(malicious_input, safe_mode="escape")

        # iframe should be escaped
        assert "&lt;iframe" in result
        assert "<iframe" not in result

    def test_img_onerror_escaped(self) -> None:
        """img onerror handlers should be escaped."""
        malicious_input = '<img src="x" onerror="alert(1)">'
        result = markdown2.markdown(malicious_input, safe_mode="escape")

        # Raw HTML should be escaped
        assert "&lt;img" in result

    def test_normal_markdown_works(self) -> None:
        """Normal markdown should still render correctly."""
        normal_input = "# Heading\n\nSome **bold** and *italic* text."
        result = markdown2.markdown(normal_input, safe_mode="escape")

        # Should render markdown formatting
        assert "<h1>" in result
        assert "<strong>" in result or "<em>" in result

    def test_code_blocks_preserved(self) -> None:
        """Code blocks should preserve their content escaped."""
        code_input = '```\n<script>alert("xss")</script>\n```'
        result = markdown2.markdown(
            code_input, safe_mode="escape", extras=["fenced-code-blocks"]
        )

        # Script in code block should be escaped
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestMarkdown2DefaultUnsafe:
    """Document that markdown2 without safe_mode is UNSAFE.

    These tests document the vulnerability that exists when safe_mode is not used.
    They pass to demonstrate the problem - they are not testing desired behavior.
    """

    def test_default_mode_allows_script_tags(self) -> None:
        """Without safe_mode, script tags pass through (UNSAFE!)."""
        malicious_input = '<script>alert("xss")</script>'
        result = markdown2.markdown(malicious_input)  # No safe_mode!

        # This PASSES because script tags are NOT escaped - this is a vulnerability
        assert "<script>" in result, "This documents that default mode is unsafe"
