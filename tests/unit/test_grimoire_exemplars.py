"""Unit tests for the exemplar-selection pure core (scripts/grimoire_exemplars.py).

These exercise the metric extraction off a real in-memory AnnotationDocument
(no DB, no network) and the thoughtfulness score that ranks workspaces for the
faculty-exec demo.  The load-bearing property is Brian's spec: a thoughtful,
moderately-annotated, commented workspace must OUTSCORE a "p100 over-highlighter"
that highlighted nearly the whole document with no comments.
"""

from __future__ import annotations

import pytest
from scripts.grimoire_exemplars import (
    DEFAULT_WEIGHTS,
    Candidate,
    WorkspaceMetrics,
    _deserialise,
    build_report,
    compute_metrics,
    is_eligible,
    render_html,
    thoughtfulness_score,
)

from promptgrimoire.crdt.annotation_doc import AnnotationDocument


def _doc(name: str = "test") -> AnnotationDocument:
    return AnnotationDocument(name)


def _add_tag(doc: AnnotationDocument, tag_id: str, name: str) -> None:
    doc.set_tag(tag_id=tag_id, name=name, colour="#1f77b4", order_index=0)


# --------------------------------------------------------------------------- #
# compute_metrics                                                             #
# --------------------------------------------------------------------------- #


def test_empty_document_yields_zero_metrics() -> None:
    m = compute_metrics(_doc(), source_chars=1000)
    assert m.highlight_count == 0
    assert m.comment_count == 0
    assert m.highlights_with_comments == 0
    assert m.distinct_tags == 0
    assert m.highlighted_chars == 0
    assert m.organise_engaged is False
    assert m.respond_words == 0
    assert m.notes_words == 0


def test_counts_highlights_comments_and_distinct_tags() -> None:
    doc = _doc()
    _add_tag(doc, "tag-a", "Issue")
    _add_tag(doc, "tag-b", "Rule")
    h1 = doc.add_highlight(0, 10, "tag-a", "first span", "alice")
    doc.add_highlight(20, 25, "tag-a", "again", "alice")
    doc.add_highlight(30, 50, "tag-b", "third span", "alice")
    doc.add_comment(h1, "alice", "this is the key issue")
    doc.add_comment(h1, "alice", "second comment same highlight")

    m = compute_metrics(doc, source_chars=1000)

    assert m.highlight_count == 3
    assert m.comment_count == 2
    assert m.highlights_with_comments == 1  # both comments on h1
    assert m.distinct_tags == 2  # tag-a, tag-b
    assert m.highlighted_chars == 10 + 5 + 20


def test_coverage_ratio_uses_source_chars() -> None:
    doc = _doc()
    _add_tag(doc, "tag-a", "Issue")
    doc.add_highlight(0, 250, "tag-a", "x" * 250, "alice")
    m = compute_metrics(doc, source_chars=1000)
    assert m.coverage_ratio == pytest.approx(0.25)


def test_coverage_ratio_safe_when_source_chars_zero() -> None:
    doc = _doc()
    _add_tag(doc, "tag-a", "Issue")
    doc.add_highlight(0, 10, "tag-a", "span", "alice")
    m = compute_metrics(doc, source_chars=0)
    assert m.coverage_ratio >= 0.0  # no ZeroDivisionError


def test_organise_engaged_true_after_card_move() -> None:
    doc = _doc()
    _add_tag(doc, "tag-a", "Issue")
    _add_tag(doc, "tag-b", "Rule")
    hid = doc.add_highlight(0, 10, "tag-a", "span", "alice")
    # Plain annotation does NOT populate the tag's ordered highlight list.
    assert compute_metrics(doc, 1000).organise_engaged is False
    # Dragging the card in the Organise tab does.
    doc.move_highlight_to_tag(hid, from_tag="tag-a", to_tag="tag-b")
    assert compute_metrics(doc, 1000).organise_engaged is True


def test_metrics_survive_crdt_roundtrip() -> None:
    """The prod path: metrics after get_full_state() -> apply_update() must
    match those computed on the live doc (the script reads stored CRDT bytes)."""
    doc = _doc()
    _add_tag(doc, "tag-a", "Issue")
    _add_tag(doc, "tag-b", "Rule")
    h1 = doc.add_highlight(0, 10, "tag-a", "span one", "alice")
    doc.add_highlight(12, 30, "tag-b", "span two", "alice")
    doc.add_comment(h1, "alice", "key point")
    doc.move_highlight_to_tag(h1, from_tag="tag-a", to_tag="tag-b")  # organise
    draft = doc.response_draft_markdown
    draft += "a written response here"

    live = compute_metrics(doc, source_chars=500)
    restored_doc = _deserialise(doc.get_full_state())
    assert restored_doc is not None
    assert compute_metrics(restored_doc, source_chars=500) == live


def test_respond_and_notes_word_counts() -> None:
    doc = _doc()
    # response_draft_markdown is a read-only property; mutate the Text in place.
    draft = doc.response_draft_markdown
    draft += "one two three four"
    doc.set_general_notes("alpha beta")
    m = compute_metrics(doc, source_chars=1000)
    assert m.respond_words == 4
    assert m.notes_words == 2


# --------------------------------------------------------------------------- #
# thoughtfulness_score                                                        #
# --------------------------------------------------------------------------- #


def _metrics(
    *,
    highlight_count: int = 0,
    comment_count: int = 0,
    highlights_with_comments: int = 0,
    distinct_tags: int = 0,
    highlighted_chars: int = 0,
    source_chars: int = 1000,
    coverage_ratio: float = 0.0,
    organise_engaged: bool = False,
    respond_words: int = 0,
    notes_words: int = 0,
) -> WorkspaceMetrics:
    return WorkspaceMetrics(
        highlight_count=highlight_count,
        comment_count=comment_count,
        highlights_with_comments=highlights_with_comments,
        distinct_tags=distinct_tags,
        highlighted_chars=highlighted_chars,
        source_chars=source_chars,
        coverage_ratio=coverage_ratio,
        organise_engaged=organise_engaged,
        respond_words=respond_words,
        notes_words=notes_words,
    )


def test_thoughtful_outscores_p100_overhighlighter() -> None:
    """The core spec: do NOT reward 'highlighted everything, no thought'."""
    thoughtful = _metrics(
        highlight_count=25,
        comment_count=10,
        highlights_with_comments=10,
        distinct_tags=5,
        coverage_ratio=0.20,
        organise_engaged=True,
        respond_words=300,
    )
    over = _metrics(
        highlight_count=150,
        comment_count=0,
        highlights_with_comments=0,
        distinct_tags=1,
        coverage_ratio=0.95,
        organise_engaged=False,
        respond_words=0,
    )
    assert thoughtfulness_score(thoughtful, DEFAULT_WEIGHTS) > thoughtfulness_score(
        over, DEFAULT_WEIGHTS
    )


def test_count_term_saturates_so_more_is_not_linearly_better() -> None:
    """30->150 highlights must gain far less than 0->30 (diminishing returns)."""
    score = lambda n: thoughtfulness_score(  # noqa: E731
        _metrics(highlight_count=n), DEFAULT_WEIGHTS
    )
    first_gain = score(30) - score(0)
    second_gain = score(150) - score(30)
    assert second_gain < first_gain


def test_adding_comments_strictly_raises_score() -> None:
    low = _metrics(highlight_count=10, comment_count=1, highlights_with_comments=1)
    high = _metrics(highlight_count=10, comment_count=5, highlights_with_comments=4)
    assert thoughtfulness_score(high, DEFAULT_WEIGHTS) > thoughtfulness_score(
        low, DEFAULT_WEIGHTS
    )


def test_organise_and_respond_are_bonuses() -> None:
    plain = _metrics(highlight_count=10, comment_count=3, highlights_with_comments=3)
    with_bonus = _metrics(
        highlight_count=10,
        comment_count=3,
        highlights_with_comments=3,
        organise_engaged=True,
        respond_words=200,
    )
    assert thoughtfulness_score(with_bonus, DEFAULT_WEIGHTS) > thoughtfulness_score(
        plain, DEFAULT_WEIGHTS
    )


def test_high_coverage_penalises_score() -> None:
    discerning = _metrics(highlight_count=20, comment_count=5, coverage_ratio=0.2)
    indiscriminate = _metrics(highlight_count=20, comment_count=5, coverage_ratio=0.9)
    assert thoughtfulness_score(discerning, DEFAULT_WEIGHTS) > thoughtfulness_score(
        indiscriminate, DEFAULT_WEIGHTS
    )


# --------------------------------------------------------------------------- #
# is_eligible                                                                 #
# --------------------------------------------------------------------------- #


def test_eligibility_requires_comment_and_highlight_floor() -> None:
    assert is_eligible(_metrics(highlight_count=10, comment_count=2), min_highlights=5)
    # No comments -> not eligible (Brian: "with comments").
    assert not is_eligible(
        _metrics(highlight_count=10, comment_count=0), min_highlights=5
    )
    # Below highlight floor -> not eligible.
    assert not is_eligible(
        _metrics(highlight_count=2, comment_count=5), min_highlights=5
    )


# --------------------------------------------------------------------------- #
# build_report + render_html (the demo deliverable)                           #
# --------------------------------------------------------------------------- #


def _cand(score: float, *, hl: int = 10, comments: int = 1) -> Candidate:
    return Candidate(
        workspace_id=f"ws-{score}",
        owner_email="stu@uni.edu",
        owner_name="Stu Dent",
        week_number=1,
        week_title="Intro",
        score=score,
        metrics=_metrics(
            highlight_count=hl,
            comment_count=comments,
            highlights_with_comments=comments,
            organise_engaged=True,
            respond_words=120,
        ),
        teaser="“the duty of care” — this is the central issue",
    )


def test_build_report_selects_top_n_by_score_and_renders_links() -> None:
    units = {
        ("LAWS1100", "Torts", "2026 S1", False): {
            "Essay 1": [_cand(2.0), _cand(1.0), _cand(3.0), _cand(0.5)],
        }
    }
    report = build_report(units, top=2, min_highlights=5, base_url="https://g.example")
    assert report.totals.units == 1
    assert report.totals.examples == 2
    block = report.units[0].assessments[0]
    assert block.candidate_workspaces == 4
    assert block.fallback_no_commented_examples is False
    assert [e.score for e in block.examples] == [3.0, 2.0]  # top-2 by score desc

    html = render_html(report, "https://g.example")
    assert "https://g.example/annotation?workspace_id=ws-3.0" in html
    assert "target='_blank'" in html
    assert "organised" in html and "responded" in html


def test_build_report_falls_back_when_no_commented_examples() -> None:
    units = {
        ("X", "Y", "2026 S1", False): {
            # 20 highlights but zero comments -> ineligible as an "example".
            "Quiz": [_cand(5.0, hl=20, comments=0)],
        }
    }
    report = build_report(units, top=3, min_highlights=5, base_url="https://g")
    block = report.units[0].assessments[0]
    assert block.fallback_no_commented_examples is True
    assert len(block.examples) == 1  # fallback still surfaces the best one
    assert "fallback" in render_html(report, "https://g")
