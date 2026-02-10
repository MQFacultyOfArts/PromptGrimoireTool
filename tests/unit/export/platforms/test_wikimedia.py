"""Unit tests for Wikimedia platform handler."""

from __future__ import annotations

from promptgrimoire.export.platforms.wikimedia import WikimediaHandler


class TestWikimediaHandlerMatches:
    """Tests for Wikimedia platform detection."""

    def test_matches_html_with_mw_parser_output(self) -> None:
        """Handler matches HTML containing mw-parser-output class."""
        handler = WikimediaHandler()
        html = '<div class="mw-parser-output"><p>Content</p></div>'
        assert handler.matches(html) is True

    def test_matches_html_with_mw_body_content(self) -> None:
        """Handler matches HTML containing mw-body-content class."""
        handler = WikimediaHandler()
        html = '<div id="mw-content-text" class="mw-body-content">Content</div>'
        assert handler.matches(html) is True

    def test_matches_html_with_vector_header(self) -> None:
        """Handler matches HTML containing vector-header class."""
        handler = WikimediaHandler()
        html = '<header class="vector-header mw-header">Nav</header>'
        assert handler.matches(html) is True

    def test_does_not_match_openai_html(self) -> None:
        """Handler does not match OpenAI exports."""
        handler = WikimediaHandler()
        html = '<div class="agent-turn">Content</div>'
        assert handler.matches(html) is False

    def test_does_not_match_empty_html(self) -> None:
        """Handler does not match empty HTML."""
        handler = WikimediaHandler()
        assert handler.matches("") is False

    def test_does_not_match_plain_html(self) -> None:
        """Handler does not match plain HTML without MediaWiki markers."""
        handler = WikimediaHandler()
        html = "<html><body><p>Just some text</p></body></html>"
        assert handler.matches(html) is False


class TestWikimediaHandlerPreprocess:
    """Tests for Wikimedia HTML preprocessing."""

    def test_strips_navigation(self) -> None:
        """Preprocessing removes navigation elements."""
        handler = WikimediaHandler()
        html = """<html><body>
        <nav class="vector-main-menu-landmark">Menu</nav>
        <div id="mw-content-text" class="mw-body-content">
            <div class="mw-parser-output">
                <p>Article content</p>
            </div>
        </div>
        </body></html>"""
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Article content" in result
        assert "vector-main-menu" not in result

    def test_strips_sidebar(self) -> None:
        """Preprocessing removes sidebar elements."""
        handler = WikimediaHandler()
        html = """<html><body>
        <div id="mw-panel" class="vector-sidebar">Sidebar</div>
        <div id="mw-content-text" class="mw-body-content">
            <div class="mw-parser-output">
                <p>Article content</p>
            </div>
        </div>
        </body></html>"""
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Article content" in result
        assert "vector-sidebar" not in result

    def test_strips_edit_section_links(self) -> None:
        """Preprocessing removes [edit] section links."""
        handler = WikimediaHandler()
        html = """<html><body>
        <div id="mw-content-text" class="mw-body-content">
            <div class="mw-parser-output">
                <h2>Title<span class="mw-editsection">[edit]</span></h2>
                <p>Article content</p>
            </div>
        </div>
        </body></html>"""
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Article content" in result
        assert "Title" in result
        assert "mw-editsection" not in result
        assert "[edit]" not in result

    def test_strips_table_of_contents(self) -> None:
        """Preprocessing removes table of contents."""
        handler = WikimediaHandler()
        html = """<html><body>
        <div id="mw-content-text" class="mw-body-content">
            <div class="mw-parser-output">
                <div id="toc" class="toc">Table of contents</div>
                <p>Article content</p>
            </div>
        </div>
        </body></html>"""
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Article content" in result
        assert "Table of contents" not in result

    def test_strips_header_and_footer(self) -> None:
        """Preprocessing removes header and footer chrome."""
        handler = WikimediaHandler()
        html = """<html><body>
        <header class="vector-header mw-header">Header nav</header>
        <div id="mw-content-text" class="mw-body-content">
            <div class="mw-parser-output">
                <p>Article content</p>
            </div>
        </div>
        <footer id="footer" class="mw-footer">Footer</footer>
        </body></html>"""
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Article content" in result
        assert "Header nav" not in result
        assert "mw-footer" not in result

    def test_strips_categories(self) -> None:
        """Preprocessing removes category links."""
        handler = WikimediaHandler()
        html = """<html><body>
        <div id="mw-content-text" class="mw-body-content">
            <div class="mw-parser-output">
                <p>Article content</p>
            </div>
        </div>
        <div id="catlinks">Categories: Foo | Bar</div>
        </body></html>"""
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Article content" in result
        assert "catlinks" not in result

    def test_preserves_article_body(self) -> None:
        """Preprocessing preserves all article body content."""
        handler = WikimediaHandler()
        html = """<html><body>
        <div id="mw-content-text" class="mw-body-content">
            <div class="mw-parser-output">
                <h1>Don Quixote</h1>
                <p>En un lugar de la Mancha, de cuyo nombre no quiero acordarme.</p>
                <blockquote>A famous quote</blockquote>
            </div>
        </div>
        </body></html>"""
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        handler.preprocess(tree)
        result = tree.html or ""

        assert "Don Quixote" in result
        assert "En un lugar de la Mancha" in result
        assert "A famous quote" in result


class TestWikimediaHandlerTurnMarkers:
    """Tests for Wikimedia turn marker patterns."""

    def test_get_turn_markers_returns_empty(self) -> None:
        """Wikimedia content has no speaker turns — returns empty markers."""
        handler = WikimediaHandler()
        markers = handler.get_turn_markers()
        assert markers == {}


class TestWikimediaHandlerPipeline:
    """Integration test with the full preprocessing pipeline."""

    def test_chinese_wikipedia_fixture_processed(self) -> None:
        """Pipeline processes chinese_wikipedia.html fixture."""
        from promptgrimoire.export.platforms import preprocess_for_export
        from tests.conftest import load_conversation_fixture

        html = load_conversation_fixture("chinese_wikipedia.html")
        result = preprocess_for_export(html)

        assert len(result) > 0
        # Should be much smaller after stripping wiki chrome
        assert len(result) < len(html)

    def test_chinese_wikipedia_strips_navigation(self) -> None:
        """Pipeline strips navigation chrome from real Wikipedia fixture."""
        from promptgrimoire.export.platforms import preprocess_for_export
        from tests.conftest import load_conversation_fixture

        html = load_conversation_fixture("chinese_wikipedia.html")
        result = preprocess_for_export(html)

        # Navigation chrome removed
        assert "vector-main-menu-landmark" not in result
        assert "vector-header-container" not in result
        # Edit links removed
        assert "mw-editsection" not in result

    def test_chinese_wikipedia_preserves_content(self) -> None:
        """Pipeline preserves article content from real Wikipedia fixture."""
        from promptgrimoire.export.platforms import preprocess_for_export
        from tests.conftest import load_conversation_fixture

        html = load_conversation_fixture("chinese_wikipedia.html")
        result = preprocess_for_export(html)

        # The Chinese Wikipedia fixture is the main page — should have some content
        assert "维基百科" in result

    def test_wikisource_don_quijote_processed(self) -> None:
        """Pipeline processes Wikisource Don Quijote fixture."""
        from promptgrimoire.export.platforms import preprocess_for_export
        from tests.conftest import load_conversation_fixture

        html = load_conversation_fixture("wikisource_es_don_quijote")
        result = preprocess_for_export(html)

        assert len(result) > 0
        assert len(result) < len(html)

    def test_wikisource_don_quijote_strips_chrome(self) -> None:
        """Pipeline strips wiki chrome from Wikisource fixture."""
        from promptgrimoire.export.platforms import preprocess_for_export
        from tests.conftest import load_conversation_fixture

        html = load_conversation_fixture("wikisource_es_don_quijote")
        result = preprocess_for_export(html)

        assert "vector-main-menu-landmark" not in result
        assert "vector-header-container" not in result
        assert "mw-editsection" not in result

    def test_wikisource_don_quijote_preserves_content(self) -> None:
        """Pipeline preserves article content from Wikisource fixture."""
        from promptgrimoire.export.platforms import preprocess_for_export
        from tests.conftest import load_conversation_fixture

        html = load_conversation_fixture("wikisource_es_don_quijote")
        result = preprocess_for_export(html)

        # Don Quijote article content should be preserved
        assert "Quijote" in result or "Quixote" in result
