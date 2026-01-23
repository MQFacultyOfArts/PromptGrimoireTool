"""Tests for _WordSpanProcessor legal paragraph number extraction.

Tests the heuristic that tracks the highest paragraph number seen
to distinguish judgment paragraphs from sub-lists (court orders, etc.).
"""

from __future__ import annotations


# Import will work once we make the class public or use a test helper
# For now, we import from the module directly
def get_processor():
    """Get the processor class (handles private import)."""
    from promptgrimoire.pages.live_annotation_demo import _WordSpanProcessor

    return _WordSpanProcessor


class TestLegalParagraphExtraction:
    """Tests for legal paragraph number extraction from HTML."""

    def test_simple_ol_no_start_attribute(self) -> None:
        """First ol without start attr should be paragraphs 1, 2, 3."""
        html = """
        <ol>
            <li>First paragraph content</li>
            <li>Second paragraph content</li>
            <li>Third paragraph content</li>
        </ol>
        """
        processor = get_processor()()
        processor.process(html)

        # Word "First" should be in para 1
        assert processor.word_to_legal_para[0] == 1
        # Word "Second" should be in para 2
        second_idx = processor.words.index("Second")
        assert processor.word_to_legal_para[second_idx] == 2
        # Word "Third" should be in para 3
        third_idx = processor.words.index("Third")
        assert processor.word_to_legal_para[third_idx] == 3

    def test_ol_with_start_attribute(self) -> None:
        """ol with start="4" should have paragraphs 4, 5, 6."""
        html = """
        <ol start="4">
            <li>Fourth paragraph</li>
            <li>Fifth paragraph</li>
        </ol>
        """
        processor = get_processor()()
        processor.process(html)

        fourth_idx = processor.words.index("Fourth")
        assert processor.word_to_legal_para[fourth_idx] == 4
        fifth_idx = processor.words.index("Fifth")
        assert processor.word_to_legal_para[fifth_idx] == 5

    def test_content_before_first_ol_has_no_para(self) -> None:
        """Content in header tables before first ol should have para=None."""
        html = """
        <table>
            <tr><td>Case Name: Lawlis v R</td></tr>
        </table>
        <ol>
            <li>First paragraph</li>
        </ol>
        """
        processor = get_processor()()
        processor.process(html)

        # "Case" should have no paragraph number
        case_idx = processor.words.index("Case")
        assert processor.word_to_legal_para[case_idx] is None
        # "First" should be in para 1
        first_idx = processor.words.index("First")
        assert processor.word_to_legal_para[first_idx] == 1

    def test_content_between_ols_carries_previous_para(self) -> None:
        """Section headings between ol blocks carry the previous paragraph."""
        html = """
        <ol>
            <li>Para one</li>
        </ol>
        <p>GROUNDS OF APPEAL</p>
        <ol start="2">
            <li>Para two</li>
        </ol>
        """
        processor = get_processor()()
        processor.process(html)

        # "GROUNDS" carries forward from para 1 until para 2 starts
        grounds_idx = processor.words.index("GROUNDS")
        assert processor.word_to_legal_para[grounds_idx] == 1
        # "Para two" is in para 2
        two_idx = processor.words.index("two")
        assert processor.word_to_legal_para[two_idx] == 2

    def test_highest_para_heuristic_continues_sublist(self) -> None:
        """After seeing para 48, content in sub-ol continues with para 48."""
        html = """
        <ol start="45">
            <li>Para forty-five</li>
            <li>Para forty-six</li>
            <li>Para forty-seven</li>
            <li>Para forty-eight with orders</li>
        </ol>
        <ol>
            <li>Order one - grant leave</li>
            <li>Order two - allow appeal</li>
        </ol>
        """
        processor = get_processor()()
        processor.process(html)

        # "forty-five" should be in para 45
        p45_idx = processor.words.index("forty-five")
        assert processor.word_to_legal_para[p45_idx] == 45

        # "forty-eight" should be in para 48
        p48_idx = processor.words.index("forty-eight")
        assert processor.word_to_legal_para[p48_idx] == 48

        # "Order" in the second ol continues para 48 (sub-list content)
        order_indices = [i for i, w in enumerate(processor.words) if w == "Order"]
        for idx in order_indices:
            assert processor.word_to_legal_para[idx] == 48

    def test_highest_para_heuristic_continues_with_low_start(self) -> None:
        """ol start="7" after para 45 continues with para 45."""
        html = """
        <ol start="45">
            <li>Para forty-five</li>
        </ol>
        <ol start="7">
            <li>Order seven</li>
        </ol>
        """
        processor = get_processor()()
        processor.process(html)

        # "forty-five" should be para 45 (first item in start=45)
        p45_idx = processor.words.index("forty-five")
        assert processor.word_to_legal_para[p45_idx] == 45

        # "Order" continues with para 45 (7 < 45, so it's sub-content)
        order_idx = processor.words.index("Order")
        assert processor.word_to_legal_para[order_idx] == 45

    def test_sequential_ols_with_increasing_start(self) -> None:
        """Multiple ols with increasing start values work correctly."""
        html = """
        <ol>
            <li>One</li>
            <li>Two</li>
            <li>Three</li>
        </ol>
        <p>Heading</p>
        <ol start="4">
            <li>Four</li>
        </ol>
        <ol start="5">
            <li>Five</li>
            <li>Six</li>
        </ol>
        """
        processor = get_processor()()
        processor.process(html)

        assert processor.word_to_legal_para[processor.words.index("One")] == 1
        assert processor.word_to_legal_para[processor.words.index("Two")] == 2
        assert processor.word_to_legal_para[processor.words.index("Three")] == 3
        assert processor.word_to_legal_para[processor.words.index("Four")] == 4
        assert processor.word_to_legal_para[processor.words.index("Five")] == 5
        assert processor.word_to_legal_para[processor.words.index("Six")] == 6

    def test_highest_para_seen_is_tracked(self) -> None:
        """_highest_para_seen should be updated as we process."""
        html = """
        <ol start="10">
            <li>Ten</li>
            <li>Eleven</li>
        </ol>
        """
        processor = get_processor()()
        processor.process(html)

        assert processor._highest_para_seen == 11

    def test_real_world_case_structure(self) -> None:
        """Test with structure similar to 183.rtf."""
        html = """
        <table><tr><td>Case Name: Lawlis v R</td></tr></table>
        <p>JUDGMENT</p>
        <ol>
            <li>THE COURT: After hearing...</li>
            <li>Joel Lawlis appealed...</li>
            <li>Mr Lawlis was sentenced...</li>
        </ol>
        <p>Grounds of Appeal</p>
        <ol start="4">
            <li>Mr Lawlis sought leave...</li>
        </ol>
        <p>Remarks on Sentence</p>
        <ol start="5">
            <li>Judge Abadee sentenced...</li>
            <li>His Honour applied...</li>
        </ol>
        """
        processor = get_processor()()
        processor.process(html)

        # Metadata has no para (before first ol)
        assert processor.word_to_legal_para[processor.words.index("Case")] is None
        # JUDGMENT heading has no para (before first ol)
        assert processor.word_to_legal_para[processor.words.index("JUDGMENT")] is None
        # First three paragraphs
        assert processor.word_to_legal_para[processor.words.index("THE")] == 1
        assert processor.word_to_legal_para[processor.words.index("Joel")] == 2
        # "Grounds" heading carries forward from para 3
        assert processor.word_to_legal_para[processor.words.index("Grounds")] == 3
        # Para 4
        assert processor.word_to_legal_para[processor.words.index("sought")] == 4
        # "Remarks" heading carries forward from para 4
        assert processor.word_to_legal_para[processor.words.index("Remarks")] == 4
        # Para 5-6
        assert processor.word_to_legal_para[processor.words.index("Judge")] == 5
        assert processor.word_to_legal_para[processor.words.index("Honour")] == 6


class TestProcessedDocumentIncludesLegalPara:
    """Tests that _ProcessedDocument exposes word_to_legal_para."""

    def test_html_to_word_spans_includes_legal_para(self) -> None:
        """_html_to_word_spans should return doc with word_to_legal_para."""
        from promptgrimoire.pages.live_annotation_demo import _html_to_word_spans

        html = """
        <ol>
            <li>First para</li>
        </ol>
        """
        doc = _html_to_word_spans(html)

        assert hasattr(doc, "word_to_legal_para")
        assert doc.word_to_legal_para[0] == 1
