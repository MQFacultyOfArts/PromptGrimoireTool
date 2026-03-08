"""Unit tests for AnnotationDocument CRDT operations."""

from __future__ import annotations

from typing import Any

import pytest

from promptgrimoire.crdt.annotation_doc import AnnotationDocument


class TestGeneralNotes:
    """Tests for general_notes collaborative text field."""

    def test_general_notes_initially_empty(self) -> None:
        """New documents should have empty general notes."""
        doc = AnnotationDocument("test-doc")

        assert doc.get_general_notes() == ""

    def test_set_general_notes(self) -> None:
        """set_general_notes should update the notes content."""
        doc = AnnotationDocument("test-doc")

        doc.set_general_notes("Test notes content")

        assert doc.get_general_notes() == "Test notes content"

    def test_set_general_notes_with_origin_client(self) -> None:
        """set_general_notes should accept origin_client_id for echo prevention."""
        doc = AnnotationDocument("test-doc")
        doc.register_client("client-1", "User1")

        doc.set_general_notes("Notes from client 1", origin_client_id="client-1")

        assert doc.get_general_notes() == "Notes from client 1"

    def test_set_general_notes_replaces_content(self) -> None:
        """set_general_notes should replace existing content."""
        doc = AnnotationDocument("test-doc")

        doc.set_general_notes("First version")
        doc.set_general_notes("Second version")

        assert doc.get_general_notes() == "Second version"

    def test_general_notes_syncs_between_docs(self) -> None:
        """General notes should sync via CRDT updates."""
        doc1 = AnnotationDocument("test-doc")
        doc2 = AnnotationDocument("test-doc")

        # Get initial state to sync
        doc2.apply_update(doc1.get_full_state())

        # Update doc1
        doc1.set_general_notes("Shared notes")
        update = doc1.doc.get_update()

        # Apply to doc2
        doc2.apply_update(update)

        # Both should have same content
        assert doc2.get_general_notes() == "Shared notes"

    def test_general_notes_property_access(self) -> None:
        """general_notes property should return the Text object."""
        doc = AnnotationDocument("test-doc")

        # Property should return pycrdt Text object
        notes = doc.general_notes
        assert hasattr(notes, "__iadd__")  # Text has __iadd__ for appending


class TestHighlights:
    """Tests for highlight operations."""

    def test_add_highlight_stores_para_ref(self) -> None:
        """add_highlight should store the para_ref field."""
        doc = AnnotationDocument("test-doc")

        highlight_id = doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="jurisdiction",
            text="test text",
            author="TestAuthor",
            para_ref="[3]",
        )

        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["para_ref"] == "[3]"

    def test_add_highlight_para_ref_defaults_to_empty(self) -> None:
        """add_highlight without para_ref should default to empty string."""
        doc = AnnotationDocument("test-doc")

        highlight_id = doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="jurisdiction",
            text="test text",
            author="TestAuthor",
        )

        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["para_ref"] == ""


class TestHighlightUserId:
    """Tests for user_id field on highlights (AC3.3)."""

    def test_add_highlight_stores_user_id(self) -> None:
        """add_highlight with user_id should store it in the dict."""
        doc = AnnotationDocument("test-doc")

        highlight_id = doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="jurisdiction",
            text="test text",
            author="TestAuthor",
            user_id="user-abc-123",
        )

        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["user_id"] == "user-abc-123"

    def test_add_highlight_user_id_defaults_to_none(self) -> None:
        """add_highlight without user_id should store None (backwards compat)."""
        doc = AnnotationDocument("test-doc")

        highlight_id = doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="jurisdiction",
            text="test text",
            author="TestAuthor",
        )

        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["user_id"] is None


class TestUpdateHighlightParaRef:
    """Tests for update_highlight_para_ref CRDT operation (AC5.3)."""

    def test_update_highlight_para_ref_changes_value(self) -> None:
        """update_highlight_para_ref should change the para_ref field."""
        doc = AnnotationDocument("test-doc")
        highlight_id = doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="jurisdiction",
            text="test text",
            author="TestAuthor",
            para_ref="[3]",
        )

        result = doc.update_highlight_para_ref(highlight_id, "[3a]")

        assert result is True
        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["para_ref"] == "[3a]"

    def test_update_highlight_para_ref_preserves_other_fields(self) -> None:
        """update_highlight_para_ref should not modify other highlight fields."""
        doc = AnnotationDocument("test-doc")
        highlight_id = doc.add_highlight(
            start_char=10,
            end_char=20,
            tag="facts",
            text="important text",
            author="Author1",
            para_ref="[3]",
            user_id="user-abc",
        )

        doc.update_highlight_para_ref(highlight_id, "[5]")

        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["start_char"] == 10
        assert highlight["end_char"] == 20
        assert highlight["tag"] == "facts"
        assert highlight["text"] == "important text"
        assert highlight["author"] == "Author1"
        assert highlight["user_id"] == "user-abc"
        assert highlight["para_ref"] == "[5]"

    def test_update_highlight_para_ref_nonexistent_returns_false(self) -> None:
        """update_highlight_para_ref on non-existent highlight returns False."""
        doc = AnnotationDocument("test-doc")

        result = doc.update_highlight_para_ref("nonexistent-id", "[1]")

        assert result is False

    def test_update_highlight_para_ref_with_origin_client(self) -> None:
        """update_highlight_para_ref should accept origin_client_id."""
        doc = AnnotationDocument("test-doc")
        doc.register_client("client-1", "User1")
        highlight_id = doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="tag",
            text="text",
            author="Author",
            para_ref="[1]",
        )

        result = doc.update_highlight_para_ref(
            highlight_id, "[2]", origin_client_id="client-1"
        )

        assert result is True
        highlight = doc.get_highlight(highlight_id)
        assert highlight is not None
        assert highlight["para_ref"] == "[2]"


class TestCommentUserId:
    """Tests for user_id field on comments (AC3.3)."""

    def test_add_comment_stores_user_id(self) -> None:
        """add_comment with user_id should store it in the comment dict."""
        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(0, 5, "tag", "text", "author")

        comment_id = doc.add_comment(
            hl_id, "Commenter", "Nice work", user_id="user-xyz"
        )

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        comments = highlight.get("comments", [])
        assert len(comments) == 1
        comment = comments[0]
        assert comment["id"] == comment_id
        assert comment["user_id"] == "user-xyz"
        assert comment["author"] == "Commenter"
        assert comment["text"] == "Nice work"
        assert "created_at" in comment

    def test_add_comment_user_id_defaults_to_none(self) -> None:
        """add_comment without user_id should store None (backwards compat)."""
        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(0, 5, "tag", "text", "author")

        doc.add_comment(hl_id, "Commenter", "Some comment")

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        comments = highlight.get("comments", [])
        assert len(comments) == 1
        assert comments[0]["user_id"] is None

    def test_comment_dict_has_all_required_fields(self) -> None:
        """Comment dict must contain user_id, author, text, created_at (AC3.3)."""
        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(0, 5, "tag", "text", "author")

        doc.add_comment(hl_id, "Author1", "Comment text", user_id="user-1")

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        comment = highlight["comments"][0]
        required_keys = {"id", "user_id", "author", "text", "created_at"}
        assert required_keys.issubset(comment.keys())


class TestCommentChronology:
    """Tests for comment ordering and legacy display (AC3.1, AC3.2, AC3.7)."""

    def test_add_comment_appends_to_list(self) -> None:
        """AC3.1: add_comment appends to the highlight's comments list."""
        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(0, 5, "tag", "text", "author")

        doc.add_comment(hl_id, "User1", "First comment")

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        assert len(highlight["comments"]) == 1
        assert highlight["comments"][0]["text"] == "First comment"

    def test_two_comments_chronological_order(self) -> None:
        """AC3.2: Multiple comments appear in chronological order."""
        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(0, 5, "tag", "text", "author")

        doc.add_comment(hl_id, "User1", "First")
        doc.add_comment(hl_id, "User2", "Second")

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        comments = highlight["comments"]
        assert len(comments) == 2
        assert comments[0]["text"] == "First"
        assert comments[1]["text"] == "Second"
        # Verify chronological by created_at
        assert comments[0]["created_at"] <= comments[1]["created_at"]

    def test_legacy_highlight_no_user_id_has_author(self) -> None:
        """AC3.7: Highlight without user_id uses stored author value."""
        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(0, 5, "tag", "text", "OldAuthor")

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        # user_id defaults to None
        assert highlight["user_id"] is None
        # author is preserved
        assert highlight["author"] == "OldAuthor"

    def test_legacy_comment_no_user_id_has_author(self) -> None:
        """AC3.7: Comment without user_id uses stored author value."""
        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(0, 5, "tag", "text", "author")

        doc.add_comment(hl_id, "LegacyCommenter", "old comment")

        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        comment = highlight["comments"][0]
        assert comment["user_id"] is None
        assert comment["author"] == "LegacyCommenter"

    def test_missing_author_defaults_to_unknown(self) -> None:
        """AC3.7: get on missing author key returns 'Unknown'."""
        # Simulate a legacy comment dict without author key
        comment: dict[str, Any] = {"id": "c1", "text": "old"}
        assert comment.get("author", "Unknown") == "Unknown"


class TestDeleteCommentOwnership:
    """Tests for delete_comment ownership guard (AC3.4, AC3.5, AC1.5, AC1.8)."""

    def _setup_doc_with_comment(
        self,
        comment_user_id: str | None = "user-commenter",
    ) -> tuple[AnnotationDocument, str, str]:
        """Helper: create doc with one highlight and one comment.

        Returns (doc, highlight_id, comment_id).
        """
        doc = AnnotationDocument("test-doc")
        hl_id = doc.add_highlight(0, 5, "tag", "text", "author", user_id="user-owner")
        comment_id = doc.add_comment(
            hl_id, "Commenter", "A comment", user_id=comment_user_id
        )
        assert comment_id is not None
        return doc, hl_id, comment_id

    def test_creator_can_delete_own_comment(self) -> None:
        """AC3.4 / AC1.5: Creator (matching user_id) can delete own comment."""
        doc, hl_id, comment_id = self._setup_doc_with_comment()

        result = doc.delete_comment(
            hl_id, comment_id, requesting_user_id="user-commenter"
        )

        assert result is True
        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        assert len(highlight.get("comments", [])) == 0

    def test_workspace_owner_cannot_delete_others_comment(self) -> None:
        """Bug 3: Workspace owner (non-privileged) cannot delete others' comments."""
        doc, hl_id, comment_id = self._setup_doc_with_comment()

        result = doc.delete_comment(hl_id, comment_id, requesting_user_id="user-other")

        assert result is False

    def test_privileged_user_can_delete_any_comment(self) -> None:
        """Privileged user (instructor/admin) can delete any comment."""
        doc, hl_id, comment_id = self._setup_doc_with_comment()

        result = doc.delete_comment(
            hl_id, comment_id, requesting_user_id="user-other", is_privileged=True
        )

        assert result is True

    def test_peer_cannot_delete_others_comment(self) -> None:
        """AC1.8: Peer (non-matching user_id, not owner/privileged) cannot delete."""
        doc, hl_id, comment_id = self._setup_doc_with_comment()

        result = doc.delete_comment(hl_id, comment_id, requesting_user_id="user-other")

        assert result is False
        # Comment should still be there
        highlight = doc.get_highlight(hl_id)
        assert highlight is not None
        assert len(highlight.get("comments", [])) == 1

    def test_peer_can_delete_own_comment(self) -> None:
        """AC1.5: Peer can delete own comment (matching user_id)."""
        doc, hl_id, comment_id = self._setup_doc_with_comment()

        result = doc.delete_comment(
            hl_id, comment_id, requesting_user_id="user-commenter"
        )

        assert result is True

    def test_legacy_comment_without_user_id_only_privileged_can_delete(self) -> None:
        """Legacy comment (user_id=None) can only be deleted by privileged user."""
        doc, hl_id, comment_id = self._setup_doc_with_comment(comment_user_id=None)

        # Regular user cannot delete
        result = doc.delete_comment(hl_id, comment_id, requesting_user_id="user-anyone")
        assert result is False

        # Privileged user can delete
        result = doc.delete_comment(
            hl_id, comment_id, requesting_user_id="user-anyone", is_privileged=True
        )
        assert result is True

    def test_no_requesting_user_id_denied(self) -> None:
        """Without requesting_user_id, deletion is denied."""
        doc, hl_id, comment_id = self._setup_doc_with_comment()

        result = doc.delete_comment(hl_id, comment_id, requesting_user_id=None)

        assert result is False

    def test_backwards_compat_no_ownership_args(self) -> None:
        """delete_comment without ownership args denies by default."""
        doc, hl_id, comment_id = self._setup_doc_with_comment()

        # No ownership params -- should deny (safe default)
        result = doc.delete_comment(hl_id, comment_id)

        assert result is False


class TestMoveHighlight:
    """Tests for move_highlight_to_tag using tags Map."""

    def test_move_highlight_to_tag_appends(self) -> None:
        """move_highlight_to_tag removes from source, appends to target."""
        doc = AnnotationDocument("test-doc")
        doc.set_tag(tag_id="issue", name="Issue", colour="#ff0000", order_index=0)
        doc.set_tag(tag_id="facts", name="Facts", colour="#00ff00", order_index=1)
        h1 = doc.add_highlight(0, 5, "issue", "text", "author")
        h2 = doc.add_highlight(6, 10, "issue", "more", "author")
        h3 = doc.add_highlight(11, 15, "facts", "data", "author")
        doc.set_tag(
            tag_id="issue",
            name="Issue",
            colour="#ff0000",
            order_index=0,
            highlights=[h1, h2],
        )
        doc.set_tag(
            tag_id="facts",
            name="Facts",
            colour="#00ff00",
            order_index=1,
            highlights=[h3],
        )

        result = doc.move_highlight_to_tag(h2, from_tag="issue", to_tag="facts")

        assert result is True
        assert doc.get_tag_highlights("issue") == [h1]
        assert doc.get_tag_highlights("facts") == [h3, h2]

    def test_move_highlight_to_tag_at_position(self) -> None:
        """move_highlight_to_tag inserts at the given position."""
        doc = AnnotationDocument("test-doc")
        doc.set_tag(tag_id="facts", name="Facts", colour="#00ff00", order_index=0)
        doc.set_tag(tag_id="issue", name="Issue", colour="#ff0000", order_index=1)
        h1 = doc.add_highlight(0, 5, "facts", "a", "author")
        h2 = doc.add_highlight(6, 10, "facts", "b", "author")
        h3 = doc.add_highlight(11, 15, "issue", "c", "author")
        doc.set_tag(
            tag_id="facts",
            name="Facts",
            colour="#00ff00",
            order_index=0,
            highlights=[h1, h2],
        )
        doc.set_tag(
            tag_id="issue",
            name="Issue",
            colour="#ff0000",
            order_index=1,
            highlights=[h3],
        )

        doc.move_highlight_to_tag(h3, from_tag="issue", to_tag="facts", position=1)

        assert doc.get_tag_highlights("facts") == [h1, h3, h2]
        assert doc.get_tag_highlights("issue") == []

    def test_move_highlight_to_tag_updates_highlight_tag(self) -> None:
        """move_highlight_to_tag updates the highlight's tag field."""
        doc = AnnotationDocument("test-doc")
        doc.set_tag(tag_id="old_tag", name="Old", colour="#ff0000", order_index=0)
        doc.set_tag(tag_id="new_tag", name="New", colour="#00ff00", order_index=1)
        h1 = doc.add_highlight(0, 5, "old_tag", "text", "author")
        doc.set_tag(
            tag_id="old_tag",
            name="Old",
            colour="#ff0000",
            order_index=0,
            highlights=[h1],
        )

        doc.move_highlight_to_tag(h1, from_tag="old_tag", to_tag="new_tag")

        hl = doc.get_highlight(h1)
        assert hl is not None
        assert hl["tag"] == "new_tag"

    def test_move_highlight_to_tag_nonexistent_highlight(self) -> None:
        """move_highlight_to_tag returns False for nonexistent highlight."""
        doc = AnnotationDocument("test-doc")

        result = doc.move_highlight_to_tag(
            "nonexistent-id", from_tag=None, to_tag="facts"
        )

        assert result is False

    def test_move_highlight_updates_tags_map_highlights(self) -> None:
        """move_highlight_to_tag updates highlights field in tags Map for both tags."""
        doc = AnnotationDocument("test-doc")
        doc.set_tag(tag_id="issue", name="Issue", colour="#ff0000", order_index=0)
        doc.set_tag(tag_id="facts", name="Facts", colour="#00ff00", order_index=1)
        h1 = doc.add_highlight(0, 5, "issue", "text", "author")
        doc.set_tag(
            tag_id="issue",
            name="Issue",
            colour="#ff0000",
            order_index=0,
            highlights=[h1],
        )
        doc.set_tag(
            tag_id="facts",
            name="Facts",
            colour="#00ff00",
            order_index=1,
            highlights=[],
        )

        doc.move_highlight_to_tag(h1, from_tag="issue", to_tag="facts")

        from_entry = doc.get_tag("issue")
        assert from_entry is not None
        assert h1 not in from_entry["highlights"]

        to_entry = doc.get_tag("facts")
        assert to_entry is not None
        assert h1 in to_entry["highlights"]

    def test_move_highlight_tags_map_no_entry_graceful(self) -> None:
        """move_highlight_to_tag is graceful when tags Map lacks entries."""
        doc = AnnotationDocument("test-doc")
        h1 = doc.add_highlight(0, 5, "old", "text", "author")

        # Tags Map has no entries for "old" or "new" -- should not crash
        result = doc.move_highlight_to_tag(h1, from_tag="old", to_tag="new")

        assert result is True
        # highlight's tag field updated
        hl = doc.get_highlight(h1)
        assert hl is not None
        assert hl["tag"] == "new"

    def test_move_highlight_reorder_same_tag_updates_tags_map(self) -> None:
        """Reordering within same tag updates tags Map highlights."""
        doc = AnnotationDocument("test-doc")
        h1 = doc.add_highlight(0, 5, "tag-a", "a", "author")
        h2 = doc.add_highlight(6, 10, "tag-a", "b", "author")
        doc.set_tag(
            tag_id="tag-a",
            name="Tag A",
            colour="#ff0000",
            order_index=0,
            highlights=[h1, h2],
        )

        # Move h2 to position 0 within same tag
        doc.move_highlight_to_tag(h2, from_tag="tag-a", to_tag="tag-a", position=0)

        tag_entry = doc.get_tag("tag-a")
        assert tag_entry is not None
        assert tag_entry["highlights"] == [h2, h1]

    def test_tag_highlights_sync_between_docs(self) -> None:
        """Tag highlights sync via CRDT updates."""
        doc1 = AnnotationDocument("test-doc")
        doc2 = AnnotationDocument("test-doc")

        # Sync initial state
        doc2.apply_update(doc1.get_full_state())

        # Set tag with highlights in doc1
        doc1.set_tag(
            tag_id="jurisdiction",
            name="Jurisdiction",
            colour="#ff0000",
            order_index=0,
            highlights=["h1", "h2", "h3"],
        )
        update = doc1.doc.get_update()

        # Apply to doc2
        doc2.apply_update(update)

        assert doc2.get_tag_highlights("jurisdiction") == ["h1", "h2", "h3"]


class TestGetTagHighlights:
    """Tests for get_tag_highlights reading from tags Map."""

    def test_get_tag_highlights_empty_when_no_tag(self) -> None:
        """get_tag_highlights returns empty list for unknown tag."""
        doc = AnnotationDocument("test-doc")

        assert doc.get_tag_highlights("nonexistent") == []

    def test_get_tag_highlights_returns_highlights_from_tags_map(self) -> None:
        """get_tag_highlights reads from the tags Map highlights field."""
        doc = AnnotationDocument("test-doc")
        doc.set_tag(
            tag_id="tag-1",
            name="Issue",
            colour="#ff0000",
            order_index=0,
            highlights=["h1", "h2", "h3"],
        )

        result = doc.get_tag_highlights("tag-1")

        assert result == ["h1", "h2", "h3"]

    def test_get_tag_highlights_empty_when_no_highlights(self) -> None:
        """get_tag_highlights returns empty list when tag has no highlights."""
        doc = AnnotationDocument("test-doc")
        doc.set_tag(tag_id="tag-1", name="Issue", colour="#ff0000", order_index=0)

        result = doc.get_tag_highlights("tag-1")

        assert result == []


class TestTagOrderBackwardCompat:
    """Backward compatibility: old CRDT state with tag_order Map."""

    def test_apply_update_with_legacy_tag_order_no_exception(self) -> None:
        """Applying state from a doc that had tag_order does not crash."""
        from pycrdt import Array, Doc, Map

        # Simulate old-style doc that includes tag_order
        old_doc = Doc()
        old_doc["highlights"] = Map()
        old_doc["client_meta"] = Map()
        old_doc["tag_order"] = Map()
        old_doc["tags"] = Map()
        old_doc["tag_groups"] = Map()

        # Write some tag_order data
        old_doc["tag_order"]["some-tag"] = Array(["h1", "h2"])
        state = old_doc.get_update()

        # New AnnotationDocument (no longer initialises tag_order)
        new_doc = AnnotationDocument("test-doc")
        new_doc.apply_update(state)

        # tags Map should still be accessible
        assert new_doc.tags is not None
        assert new_doc.list_tags() == {}

    def test_tag_order_not_initialised_on_new_doc(self) -> None:
        """New AnnotationDocument does not eagerly create tag_order."""
        doc = AnnotationDocument("test-doc")

        # tag_order should NOT be in the doc keys initially
        # (it's lazily created on property access)
        with pytest.raises(KeyError):
            doc.doc["tag_order"]

    def test_tag_order_property_lazy_creates(self) -> None:
        """Accessing tag_order property lazily creates the Map."""
        doc = AnnotationDocument("test-doc")

        # Access the deprecated property — should not raise
        tag_order = doc.tag_order

        assert tag_order is not None
        # Now the key should exist (no KeyError)
        assert doc.doc["tag_order"] is not None


class TestResponseDraft:
    """Tests for response_draft XmlFragment field."""

    def test_response_draft_property_returns_xml_fragment(self) -> None:
        """doc.response_draft returns an XmlFragment instance."""
        from pycrdt import XmlFragment

        doc = AnnotationDocument("test-doc")

        assert isinstance(doc.response_draft, XmlFragment)

    def test_response_draft_coexists_with_other_fields(self) -> None:
        """response_draft, highlights, and general_notes all work on the same doc."""
        doc = AnnotationDocument("test-doc")

        h_id = doc.add_highlight(0, 5, "tag", "text", "author")
        doc.set_general_notes("some notes")
        draft = doc.response_draft

        assert doc.get_highlight(h_id) is not None
        assert doc.get_general_notes() == "some notes"
        assert draft is not None

    def test_response_draft_survives_full_state_sync(self) -> None:
        """XmlFragment is present after syncing full state to a new doc."""
        from pycrdt import XmlFragment

        doc1 = AnnotationDocument("test-doc")
        state = doc1.get_full_state()

        doc2 = AnnotationDocument("test-doc")
        doc2.apply_update(state)

        assert isinstance(doc2.response_draft, XmlFragment)


class TestResponseDraftMarkdown:
    """Tests for response_draft_markdown Text field."""

    def test_response_draft_markdown_property(self) -> None:
        """doc.response_draft_markdown returns a Text instance."""
        from pycrdt import Text

        doc = AnnotationDocument("test-doc")

        assert isinstance(doc.response_draft_markdown, Text)

    def test_get_response_draft_markdown_empty(self) -> None:
        """get_response_draft_markdown returns empty string for new doc."""
        doc = AnnotationDocument("test-doc")

        assert doc.get_response_draft_markdown() == ""

    def test_response_draft_markdown_round_trip(self) -> None:
        """Markdown content set on doc1 syncs to doc2 via CRDT."""
        doc1 = AnnotationDocument("test-doc")
        doc2 = AnnotationDocument("test-doc")

        # Sync initial state
        doc2.apply_update(doc1.get_full_state())

        # Write markdown on doc1 (access Text object, then use iadd)
        md = doc1.response_draft_markdown
        md += "# Heading\n\nSome **bold** text."
        update = doc1.doc.get_update()

        # Apply to doc2
        doc2.apply_update(update)

        assert doc2.get_response_draft_markdown() == "# Heading\n\nSome **bold** text."

    def test_response_draft_markdown_coexists(self) -> None:
        """response_draft_markdown does not break other fields."""
        doc = AnnotationDocument("test-doc")

        h_id = doc.add_highlight(0, 5, "tag", "text", "author")
        doc.set_general_notes("notes")
        md = doc.response_draft_markdown
        md += "markdown content"
        _ = doc.response_draft  # access XmlFragment

        assert doc.get_highlight(h_id) is not None
        assert doc.get_general_notes() == "notes"
        assert doc.get_response_draft_markdown() == "markdown content"


class TestCrdtCoexistence:
    """Tests verifying new CRDT fields do not break existing operations."""

    def test_existing_highlights_unaffected(self) -> None:
        """Highlight add/get/remove work identically with new fields present."""
        doc = AnnotationDocument("test-doc")

        h_id = doc.add_highlight(0, 10, "jurisdiction", "some text", "Author")
        assert doc.get_highlight(h_id) is not None

        all_hl = doc.get_all_highlights()
        assert len(all_hl) == 1
        assert all_hl[0]["id"] == h_id

        removed = doc.remove_highlight(h_id)
        assert removed is True
        assert doc.get_highlight(h_id) is None

    def test_existing_general_notes_unaffected(self) -> None:
        """General notes set/get work identically with new fields present."""
        doc = AnnotationDocument("test-doc")

        doc.set_general_notes("Test content")
        assert doc.get_general_notes() == "Test content"

        doc.set_general_notes("Replaced content")
        assert doc.get_general_notes() == "Replaced content"

    def test_broadcast_fires_for_all_field_types(self) -> None:
        """Broadcast callback fires for highlights, tags, and general_notes."""
        doc = AnnotationDocument("test-doc")
        fired: list[str] = []

        def on_update(_update: bytes, _origin: str | None) -> None:
            fired.append("update")

        doc.set_broadcast_callback(on_update)

        # Modify highlights
        doc.add_highlight(0, 5, "tag", "text", "author")
        # Modify tags Map
        doc.set_tag(tag_id="tag", name="Tag", colour="#ff0000", order_index=0)
        # Modify general_notes
        doc.set_general_notes("notes")

        assert len(fired) >= 3  # At least one update per mutation

    def test_full_state_includes_all_fields(self) -> None:
        """Full state sync transfers highlights, tags, general_notes."""
        doc1 = AnnotationDocument("test-doc")

        h_id = doc1.add_highlight(0, 5, "jurisdiction", "text", "author")
        doc1.set_tag(
            tag_id="jurisdiction",
            name="Jurisdiction",
            colour="#ff0000",
            order_index=0,
            highlights=[h_id],
        )
        doc1.set_general_notes("shared notes")

        # Create new doc and sync full state
        doc2 = AnnotationDocument("test-doc")
        doc2.apply_update(doc1.get_full_state())

        assert doc2.get_highlight(h_id) is not None
        assert doc2.get_tag_highlights("jurisdiction") == [h_id]
        assert doc2.get_general_notes() == "shared notes"


class TestTagsMap:
    """Tests for tags Map on AnnotationDocument (AC1.1 CRDT structure)."""

    def test_tags_map_exists_on_new_doc(self) -> None:
        """AC1.1: A freshly created AnnotationDocument has an empty tags Map."""
        doc = AnnotationDocument("test-doc")

        tags = doc.tags
        assert len(tags) == 0

    def test_tags_property_returns_pycrdt_map(self) -> None:
        """AC1.4: The tags property returns a pycrdt Map instance."""
        from pycrdt import Map

        doc = AnnotationDocument("test-doc")

        assert isinstance(doc.tags, Map)


class TestTagGroupsMap:
    """Tests for tag_groups Map on AnnotationDocument (AC1.4 CRDT structure)."""

    def test_tag_groups_map_exists_on_new_doc(self) -> None:
        """AC1.4: A freshly created AnnotationDocument has an empty tag_groups Map."""
        doc = AnnotationDocument("test-doc")

        tag_groups = doc.tag_groups
        assert len(tag_groups) == 0

    def test_tag_groups_property_returns_pycrdt_map(self) -> None:
        """AC1.4: The tag_groups property returns a pycrdt Map instance."""
        from pycrdt import Map

        doc = AnnotationDocument("test-doc")

        assert isinstance(doc.tag_groups, Map)


class TestTagCrud:
    """Tests for tag CRUD methods on AnnotationDocument."""

    def test_set_tag_stores_all_fields(self) -> None:
        """AC1.1: set_tag stores all fields correctly."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag(
            "tag-1",
            "Jurisdiction",
            "#3366cc",
            0,
            group_id="group-1",
            description="Legal jurisdiction",
        )

        tag = doc.get_tag("tag-1")
        assert tag is not None
        assert tag["name"] == "Jurisdiction"
        assert tag["colour"] == "#3366cc"
        assert tag["order_index"] == 0
        assert tag["group_id"] == "group-1"
        assert tag["description"] == "Legal jurisdiction"
        assert list(tag["highlights"]) == []

    def test_set_tag_defaults(self) -> None:
        """set_tag optional fields default correctly."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag("tag-1", "Facts", "#ff0000", 1)

        tag = doc.get_tag("tag-1")
        assert tag is not None
        assert tag["group_id"] is None
        assert tag["description"] is None
        assert list(tag["highlights"]) == []

    def test_set_tag_overwrites_existing(self) -> None:
        """AC1.2: Calling set_tag again overwrites name/colour/description."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag("tag-1", "Old Name", "#000000", 0)
        doc.set_tag(
            "tag-1",
            "New Name",
            "#ffffff",
            1,
            description="Updated",
        )

        tag = doc.get_tag("tag-1")
        assert tag is not None
        assert tag["name"] == "New Name"
        assert tag["colour"] == "#ffffff"
        assert tag["order_index"] == 1
        assert tag["description"] == "Updated"

    def test_delete_tag_removes_tag(self) -> None:
        """AC1.3: delete_tag removes the tag."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag("tag-1", "Facts", "#ff0000", 0)
        doc.delete_tag("tag-1")

        assert doc.get_tag("tag-1") is None

    def test_get_tag_nonexistent_returns_none(self) -> None:
        """Edge: get_tag on non-existent ID returns None."""
        doc = AnnotationDocument("test-doc")

        assert doc.get_tag("nonexistent") is None

    def test_delete_tag_nonexistent_does_not_raise(self) -> None:
        """Edge: delete_tag on non-existent ID does not raise."""
        doc = AnnotationDocument("test-doc")

        doc.delete_tag("nonexistent")  # Should not raise

    def test_list_tags_empty(self) -> None:
        """Edge: list_tags on empty doc returns empty dict."""
        doc = AnnotationDocument("test-doc")

        assert doc.list_tags() == {}

    def test_list_tags_returns_all(self) -> None:
        """list_tags returns all stored tags."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag("tag-1", "Facts", "#ff0000", 0)
        doc.set_tag("tag-2", "Issues", "#00ff00", 1)

        tags = doc.list_tags()
        assert len(tags) == 2
        assert "tag-1" in tags
        assert "tag-2" in tags
        assert tags["tag-1"]["name"] == "Facts"
        assert tags["tag-2"]["name"] == "Issues"

    def test_set_tag_with_highlights_preserves_ordering(self) -> None:
        """Edge: set_tag with highlights list preserves ordering."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag(
            "tag-1",
            "Facts",
            "#ff0000",
            0,
            highlights=["h3", "h1", "h2"],
        )

        tag = doc.get_tag("tag-1")
        assert tag is not None
        assert list(tag["highlights"]) == ["h3", "h1", "h2"]

    def test_tag_syncs_between_docs(self) -> None:
        """CRDT sync: tag data syncs between two docs."""
        doc1 = AnnotationDocument("test-doc")
        doc2 = AnnotationDocument("test-doc")

        # Sync initial state
        doc2.apply_update(doc1.get_full_state())

        # Write tag to doc1
        doc1.set_tag("tag-1", "Facts", "#ff0000", 0)
        update = doc1.doc.get_update()

        # Apply to doc2
        doc2.apply_update(update)

        tag = doc2.get_tag("tag-1")
        assert tag is not None
        assert tag["name"] == "Facts"
        assert tag["colour"] == "#ff0000"


class TestTagGroupCrud:
    """Tests for tag group CRUD methods on AnnotationDocument (AC1.4)."""

    def test_set_tag_group_stores_all_fields(self) -> None:
        """AC1.4: set_tag_group stores name, colour, order_index."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag_group("group-1", "Legal Issues", 0, colour="#3366cc")

        group = doc.get_tag_group("group-1")
        assert group is not None
        assert group["name"] == "Legal Issues"
        assert group["colour"] == "#3366cc"
        assert group["order_index"] == 0

    def test_set_tag_group_colour_defaults_to_none(self) -> None:
        """set_tag_group without colour stores None."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag_group("group-1", "Facts", 0)

        group = doc.get_tag_group("group-1")
        assert group is not None
        assert group["colour"] is None

    def test_set_tag_group_overwrites_existing(self) -> None:
        """AC1.4: Calling set_tag_group again with same ID overwrites."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag_group("group-1", "Old Name", 0, colour="#000000")
        doc.set_tag_group("group-1", "New Name", 1, colour="#ffffff")

        group = doc.get_tag_group("group-1")
        assert group is not None
        assert group["name"] == "New Name"
        assert group["colour"] == "#ffffff"
        assert group["order_index"] == 1

    def test_delete_tag_group_removes_group(self) -> None:
        """AC1.4: delete_tag_group removes the group."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag_group("group-1", "Facts", 0)
        doc.delete_tag_group("group-1")

        assert doc.get_tag_group("group-1") is None

    def test_get_tag_group_nonexistent_returns_none(self) -> None:
        """Edge: get_tag_group on non-existent ID returns None."""
        doc = AnnotationDocument("test-doc")

        assert doc.get_tag_group("nonexistent") is None

    def test_delete_tag_group_nonexistent_does_not_raise(self) -> None:
        """Edge: delete_tag_group on non-existent ID does not raise."""
        doc = AnnotationDocument("test-doc")

        doc.delete_tag_group("nonexistent")  # Should not raise

    def test_list_tag_groups_empty(self) -> None:
        """Edge: list_tag_groups on empty doc returns empty dict."""
        doc = AnnotationDocument("test-doc")

        assert doc.list_tag_groups() == {}

    def test_list_tag_groups_returns_all(self) -> None:
        """list_tag_groups returns all stored groups."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag_group("group-1", "Legal Issues", 0, colour="#3366cc")
        doc.set_tag_group("group-2", "Facts", 1, colour="#ff0000")

        groups = doc.list_tag_groups()
        assert len(groups) == 2
        assert "group-1" in groups
        assert "group-2" in groups
        assert groups["group-1"]["name"] == "Legal Issues"
        assert groups["group-2"]["name"] == "Facts"

    def test_tag_group_syncs_between_docs(self) -> None:
        """CRDT sync: group data syncs between two docs."""
        doc1 = AnnotationDocument("test-doc")
        doc2 = AnnotationDocument("test-doc")

        # Sync initial state
        doc2.apply_update(doc1.get_full_state())

        # Write group to doc1
        doc1.set_tag_group("group-1", "Legal Issues", 0, colour="#3366cc")
        update = doc1.doc.get_update()

        # Apply to doc2
        doc2.apply_update(update)

        group = doc2.get_tag_group("group-1")
        assert group is not None
        assert group["name"] == "Legal Issues"
        assert group["colour"] == "#3366cc"


class TestHydrateTagsFromDb:
    """Tests for hydrate_tags_from_db method (AC1.5, AC1.6)."""

    def test_hydrate_populates_empty_doc(self) -> None:
        """AC1.5: hydrate_tags_from_db on empty doc populates tags and groups."""
        doc = AnnotationDocument("test-doc")

        groups = [
            {
                "id": "group-1",
                "name": "Legal Issues",
                "colour": "#3366cc",
                "order_index": 0,
            },
        ]
        tags = [
            {
                "id": "tag-1",
                "name": "Jurisdiction",
                "colour": "#ff0000",
                "order_index": 0,
                "group_id": "group-1",
                "description": "Legal jurisdiction",
                "highlights": ["h1", "h2"],
            },
            {
                "id": "tag-2",
                "name": "Facts",
                "colour": "#00ff00",
                "order_index": 1,
                "group_id": None,
                "description": None,
            },
        ]

        doc.hydrate_tags_from_db(tags, groups)

        # Verify group
        group = doc.get_tag_group("group-1")
        assert group is not None
        assert group["name"] == "Legal Issues"
        assert group["colour"] == "#3366cc"
        assert group["order_index"] == 0

        # Verify tag with all fields
        tag1 = doc.get_tag("tag-1")
        assert tag1 is not None
        assert tag1["name"] == "Jurisdiction"
        assert tag1["colour"] == "#ff0000"
        assert tag1["order_index"] == 0
        assert tag1["group_id"] == "group-1"
        assert tag1["description"] == "Legal jurisdiction"
        assert list(tag1["highlights"]) == ["h1", "h2"]

        # Verify tag with defaults
        tag2 = doc.get_tag("tag-2")
        assert tag2 is not None
        assert tag2["name"] == "Facts"
        assert tag2["group_id"] is None
        assert tag2["description"] is None
        assert list(tag2["highlights"]) == []

    def test_hydrate_overwrites_stale_data(self) -> None:
        """AC1.6: hydrate_tags_from_db overwrites existing CRDT entries (DB wins)."""
        doc = AnnotationDocument("test-doc")

        # Pre-populate with stale data
        doc.set_tag("tag-1", "Stale Name", "#000000", 0)
        doc.set_tag_group("group-1", "Stale Group", 0, colour="#000000")

        # Hydrate with DB data
        groups = [
            {
                "id": "group-1",
                "name": "Fresh Group",
                "colour": "#ffffff",
                "order_index": 1,
            },
        ]
        tags = [
            {
                "id": "tag-1",
                "name": "Fresh Name",
                "colour": "#ffffff",
                "order_index": 1,
                "group_id": "group-1",
                "description": "Updated",
            },
        ]

        doc.hydrate_tags_from_db(tags, groups)

        tag = doc.get_tag("tag-1")
        assert tag is not None
        assert tag["name"] == "Fresh Name"
        assert tag["colour"] == "#ffffff"

        group = doc.get_tag_group("group-1")
        assert group is not None
        assert group["name"] == "Fresh Group"
        assert group["colour"] == "#ffffff"

    def test_hydrate_empty_lists_no_error(self) -> None:
        """Edge: Empty lists produce no errors and do not remove existing entries."""
        doc = AnnotationDocument("test-doc")

        # Pre-populate
        doc.set_tag("tag-1", "Facts", "#ff0000", 0)
        doc.set_tag_group("group-1", "Legal", 0)

        doc.hydrate_tags_from_db([], [])

        # Existing entries should remain
        assert doc.get_tag("tag-1") is not None
        assert doc.get_tag_group("group-1") is not None

    def test_hydrate_tag_with_group_reference(self) -> None:
        """Edge: Tags with group_id referencing a group resolve."""
        doc = AnnotationDocument("test-doc")

        groups = [
            {
                "id": "group-1",
                "name": "Analysis",
                "colour": "#3366cc",
                "order_index": 0,
            },
        ]
        tags = [
            {
                "id": "tag-1",
                "name": "Key Facts",
                "colour": "#ff0000",
                "order_index": 0,
                "group_id": "group-1",
            },
        ]

        doc.hydrate_tags_from_db(tags, groups)

        tag = doc.get_tag("tag-1")
        assert tag is not None
        assert tag["group_id"] == "group-1"

        group = doc.get_tag_group("group-1")
        assert group is not None


class TestWorkspaceTagsFromCrdt:
    """Tests for workspace_tags_from_crdt() pure function."""

    def test_empty_crdt_returns_empty_list(self) -> None:
        """Empty CRDT doc returns empty list."""
        from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt

        doc = AnnotationDocument("test-doc")

        result = workspace_tags_from_crdt(doc)

        assert result == []

    def test_tags_with_all_fields_populated(self) -> None:
        """Tags with all fields produce correct TagInfo instances."""
        from promptgrimoire.pages.annotation.tags import (
            TagInfo,
            workspace_tags_from_crdt,
        )

        doc = AnnotationDocument("test-doc")
        doc.set_tag_group("group-1", "Legal Issues", 0, colour="#3366cc")
        doc.set_tag(
            "tag-1",
            "Jurisdiction",
            "#ff0000",
            0,
            group_id="group-1",
            description="Legal jurisdiction",
        )

        result = workspace_tags_from_crdt(doc)

        assert len(result) == 1
        assert result[0] == TagInfo(
            name="Jurisdiction",
            colour="#ff0000",
            raw_key="tag-1",
            group_name="Legal Issues",
            group_colour="#3366cc",
            description="Legal jurisdiction",
        )

    def test_group_metadata_resolved_from_tag_groups_map(self) -> None:
        """Group name and colour are resolved from tag_groups Map."""
        from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt

        doc = AnnotationDocument("test-doc")
        doc.set_tag_group("group-1", "Analysis", 0, colour="#aabbcc")
        doc.set_tag("tag-1", "Facts", "#112233", 0, group_id="group-1")

        result = workspace_tags_from_crdt(doc)

        assert result[0].group_name == "Analysis"
        assert result[0].group_colour == "#aabbcc"

    def test_ungrouped_tags_appear_after_grouped_tags(self) -> None:
        """Tags without groups appear after grouped tags."""
        from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt

        doc = AnnotationDocument("test-doc")
        doc.set_tag_group("group-1", "Group A", 0)
        doc.set_tag("tag-grouped", "Grouped Tag", "#ff0000", 0, group_id="group-1")
        doc.set_tag("tag-ungrouped", "Ungrouped Tag", "#00ff00", 0)

        result = workspace_tags_from_crdt(doc)

        assert len(result) == 2
        assert result[0].name == "Grouped Tag"
        assert result[1].name == "Ungrouped Tag"
        assert result[1].group_name is None

    def test_ordered_by_group_order_index_then_tag_order_index(self) -> None:
        """Tags ordered by group order_index then tag order_index."""
        from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt

        doc = AnnotationDocument("test-doc")
        doc.set_tag_group("group-b", "Group B", 1)
        doc.set_tag_group("group-a", "Group A", 0)
        doc.set_tag("tag-b1", "B First", "#ff0000", 0, group_id="group-b")
        doc.set_tag("tag-b2", "B Second", "#ff0000", 1, group_id="group-b")
        doc.set_tag("tag-a1", "A First", "#00ff00", 0, group_id="group-a")
        doc.set_tag("tag-a2", "A Second", "#00ff00", 1, group_id="group-a")

        result = workspace_tags_from_crdt(doc)

        names = [t.name for t in result]
        assert names == ["A First", "A Second", "B First", "B Second"]

    def test_tag_without_matching_group_has_none_group_fields(self) -> None:
        """Tag referencing non-existent group has None group fields."""
        from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt

        doc = AnnotationDocument("test-doc")
        doc.set_tag("tag-1", "Orphan", "#ff0000", 0, group_id="nonexistent-group")

        result = workspace_tags_from_crdt(doc)

        assert len(result) == 1
        assert result[0].group_name is None
        assert result[0].group_colour is None


class TestTagSyncViaCrdt:
    """Tests for CRDT sync pathway used by broadcast (Task 4).

    Verifies that tags set on one AnnotationDocument propagate to
    another via get_full_state/apply_update, which is the mechanism
    the broadcast callback relies on.
    """

    def test_sync_tag_from_doc_a_to_doc_b(self) -> None:
        """Tag set on doc A appears on doc B after sync."""
        from promptgrimoire.pages.annotation.tags import (
            workspace_tags_from_crdt,
        )

        doc_a = AnnotationDocument("doc-a")
        doc_b = AnnotationDocument("doc-b")

        # Sync initial state so both docs share the same baseline
        doc_b.apply_update(doc_a.get_full_state())
        doc_a.apply_update(doc_b.get_full_state())

        # Set a tag on doc A
        doc_a.set_tag("tag-1", "Synced Tag", "#cc3366", 0)

        # Sync doc A's state to doc B
        doc_b.apply_update(doc_a.get_full_state())

        result = workspace_tags_from_crdt(doc_b)
        assert len(result) == 1
        assert result[0].name == "Synced Tag"
        assert result[0].colour == "#cc3366"
        assert result[0].raw_key == "tag-1"

    def test_sync_tag_update_propagates(self) -> None:
        """Tag colour update on doc A propagates to doc B."""
        from promptgrimoire.pages.annotation.tags import (
            workspace_tags_from_crdt,
        )

        doc_a = AnnotationDocument("doc-a")
        doc_b = AnnotationDocument("doc-b")

        # Sync baselines
        doc_b.apply_update(doc_a.get_full_state())
        doc_a.apply_update(doc_b.get_full_state())

        # Create then update tag
        doc_a.set_tag("tag-1", "Colour Test", "#000000", 0)
        doc_b.apply_update(doc_a.get_full_state())
        doc_a.set_tag("tag-1", "Colour Test", "#ff0000", 0)
        doc_b.apply_update(doc_a.get_full_state())

        result = workspace_tags_from_crdt(doc_b)
        assert result[0].colour == "#ff0000"

    def test_sync_tag_deletion_propagates(self) -> None:
        """Tag deleted on doc A disappears from doc B."""
        from promptgrimoire.pages.annotation.tags import (
            workspace_tags_from_crdt,
        )

        doc_a = AnnotationDocument("doc-a")
        doc_b = AnnotationDocument("doc-b")

        # Sync baselines
        doc_b.apply_update(doc_a.get_full_state())
        doc_a.apply_update(doc_b.get_full_state())

        doc_a.set_tag("tag-1", "Doomed", "#ff0000", 0)
        doc_b.apply_update(doc_a.get_full_state())
        assert len(workspace_tags_from_crdt(doc_b)) == 1

        doc_a.delete_tag("tag-1")
        doc_b.apply_update(doc_a.get_full_state())

        assert len(workspace_tags_from_crdt(doc_b)) == 0
