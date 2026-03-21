"""Tests for stripping code fences around bullet-point lists in PDF markdown.

pymupdf4llm wraps some bullet-point lists in triple-backtick code fences,
which pandoc renders as <pre><code> blocks instead of <ul><li> lists.
See: https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/349
"""

from promptgrimoire.input_pipeline.converters import strip_bullet_code_fences


class TestStripBulletCodeFences:
    """Unit tests for the bullet code fence stripper."""

    def test_single_bullet_in_code_fence_is_unwrapped(self) -> None:
        """A single bullet item wrapped in code fences becomes a bare bullet."""
        md = "Some text:\n\n```\n- First item\n```\n\nMore text."
        result = strip_bullet_code_fences(md)
        assert "```" not in result
        assert "- First item" in result

    def test_multiple_bullets_in_code_fence_are_unwrapped(self) -> None:
        """Multiple bullet items in one code fence all become bare bullets."""
        md = (
            "People:\n\n"
            "```\n"
            "- Wurundjeri (Bundoora)\n"
            "\n"
            "- Wurundjeri / Boonerwrung (City)\n"
            "\n"
            "- Dja Dja Wurrung (Bendigo)\n"
            "\n"
            "- Latji Latji / Barkindji (Mildura)\n"
            "```\n"
            "\nMore text."
        )
        result = strip_bullet_code_fences(md)
        assert "```" not in result
        assert "- Wurundjeri (Bundoora)" in result
        assert "- Latji Latji / Barkindji (Mildura)" in result

    def test_indented_bullets_in_code_fence_are_unwrapped(self) -> None:
        """Bullets with leading whitespace are still recognised."""
        md = "Questions:\n\n```\n  - How might tort law evolve?\n```\n"
        result = strip_bullet_code_fences(md)
        assert "```" not in result
        assert "- How might tort law evolve?" in result

    def test_non_bullet_code_fence_is_preserved(self) -> None:
        """Code fences containing actual code are left intact."""
        md = "Example:\n\n```python\ndef hello():\n    print('hi')\n```\n"
        result = strip_bullet_code_fences(md)
        assert "```python" in result
        assert "def hello():" in result

    def test_mixed_content_code_fence_is_preserved(self) -> None:
        """Code fence with non-bullet lines mixed in is left alone."""
        md = "Mixed:\n\n```\n- a bullet\nsome other text\n```\n"
        result = strip_bullet_code_fences(md)
        assert "```" in result

    def test_empty_input_returns_empty(self) -> None:
        result = strip_bullet_code_fences("")
        assert result == ""

    def test_no_code_fences_returns_unchanged(self) -> None:
        md = "Just some text\n\n- a bullet\n- another\n"
        result = strip_bullet_code_fences(md)
        assert result == md

    def test_surrounding_context_preserved(self) -> None:
        """Text before and after the code fence is untouched."""
        md = "Before.\n\n```\n- item\n```\n\nAfter."
        result = strip_bullet_code_fences(md)
        assert result.startswith("Before.")
        assert result.endswith("After.")
