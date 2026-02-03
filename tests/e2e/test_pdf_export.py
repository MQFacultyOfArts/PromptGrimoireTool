"""End-to-end tests for PDF export with annotations.

STUBBED: Needs rewrite to use new fixture infrastructure.
The test used `live_annotation_url` fixture from the old /demo/live-annotation route
which was removed in the 101-cjk-blns merge.

Workflow to be tested (preserve when reimplementing):
- Two users (Alice, Bob) collaborating on a shared document
- Alice creates 10 annotations covering all tags with overlapping highlights:
  - jurisdiction at para 48
  - legally_relevant_facts at grounds section
  - legal_issues at intro
  - reasons at para 7 AND para 15 (two instances)
  - courts_reasoning at para 16 (starts where reasons ends - edge case)
  - decision at para 48
  - order overlapping with reasons at 893-905 (overlap edge case)
  - domestic_sources at para 23
  - reflection at para 23 overlapping with domestic_sources (overlap edge case)
- Alice adds comment on jurisdiction: "it's excessive"
- Bob joins, adds procedural_history on case name
- Bob replies to Alice's jurisdiction comment
- Alice replies back to Bob
- Alice adds lipsum comments to courts_reasoning
- Alice writes general notes
- Alice exports PDF
- Verify PDF was generated successfully

Key edge cases this workflow covers:
1. Overlapping highlights (order + reasons, domestic_sources + reflection)
2. Adjacent highlights (reasons ends where courts_reasoning starts)
3. Multi-user collaboration with CRDT sync
4. Comments and reply threads
5. All 10 tags used
6. General notes section
7. Full PDF export pipeline

To reimplement:
- Use `two_authenticated_contexts` or `two_annotation_contexts` fixture
- Use `/annotation` route with workspace/document setup
- Port the helper functions (_create_highlight, _add_comment_to_visible_card, etc.)

Blocked on:
- Issue #106: HTML paste/upload (test needs arbitrary HTML, not hardcoded AustLII)
- Issue #101: BLNS/Unicode compatibility in PDF export
- Issue #76: Stop cheating with AustLII fixture - need proper document upload
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(
    reason="Stubbed: uses obsolete live_annotation_url fixture. "
    "See module docstring for workflow to reimplement."
)
class TestPdfExportWorkflow:
    """Test the complete PDF export workflow with multi-user collaboration."""

    def test_two_users_collaborate_and_export_pdf(self) -> None:
        """Full workflow: two users annotate with comments, add notes, export PDF.

        See module docstring for detailed workflow steps and edge cases.
        """
        pass
