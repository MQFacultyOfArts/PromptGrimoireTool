"""Unit tests for AnnotationDocument CRDT operations."""

from __future__ import annotations

from typing import Any

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


class TestTagOrder:
    """Tests for tag_order operations."""

    def test_get_tag_order_empty_tag(self) -> None:
        """get_tag_order returns empty list for unknown tag."""
        doc = AnnotationDocument("test-doc")

        assert doc.get_tag_order("nonexistent") == []

    def test_set_and_get_tag_order(self) -> None:
        """set_tag_order stores IDs; get_tag_order retrieves them."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag_order("jurisdiction", ["h1", "h2", "h3"])

        assert doc.get_tag_order("jurisdiction") == ["h1", "h2", "h3"]

    def test_set_tag_order_replaces_existing(self) -> None:
        """Setting tag_order again replaces the previous order."""
        doc = AnnotationDocument("test-doc")

        doc.set_tag_order("jurisdiction", ["h1", "h2"])
        doc.set_tag_order("jurisdiction", ["h3", "h1"])

        assert doc.get_tag_order("jurisdiction") == ["h3", "h1"]

    def test_move_highlight_to_tag_appends(self) -> None:
        """move_highlight_to_tag removes from source, appends to target."""
        doc = AnnotationDocument("test-doc")
        h1 = doc.add_highlight(0, 5, "issue", "text", "author")
        h2 = doc.add_highlight(6, 10, "issue", "more", "author")
        h3 = doc.add_highlight(11, 15, "facts", "data", "author")
        doc.set_tag_order("issue", [h1, h2])
        doc.set_tag_order("facts", [h3])

        result = doc.move_highlight_to_tag(h2, from_tag="issue", to_tag="facts")

        assert result is True
        assert doc.get_tag_order("issue") == [h1]
        assert doc.get_tag_order("facts") == [h3, h2]

    def test_move_highlight_to_tag_at_position(self) -> None:
        """move_highlight_to_tag inserts at the given position."""
        doc = AnnotationDocument("test-doc")
        h1 = doc.add_highlight(0, 5, "facts", "a", "author")
        h2 = doc.add_highlight(6, 10, "facts", "b", "author")
        h3 = doc.add_highlight(11, 15, "issue", "c", "author")
        doc.set_tag_order("facts", [h1, h2])
        doc.set_tag_order("issue", [h3])

        doc.move_highlight_to_tag(h3, from_tag="issue", to_tag="facts", position=1)

        assert doc.get_tag_order("facts") == [h1, h3, h2]
        assert doc.get_tag_order("issue") == []

    def test_move_highlight_to_tag_updates_highlight_tag(self) -> None:
        """move_highlight_to_tag updates the highlight's tag field."""
        doc = AnnotationDocument("test-doc")
        h1 = doc.add_highlight(0, 5, "old_tag", "text", "author")
        doc.set_tag_order("old_tag", [h1])

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

    def test_tag_order_syncs_between_docs(self) -> None:
        """tag_order changes sync via CRDT updates."""
        doc1 = AnnotationDocument("test-doc")
        doc2 = AnnotationDocument("test-doc")

        # Sync initial state
        doc2.apply_update(doc1.get_full_state())

        # Set tag order in doc1
        doc1.set_tag_order("jurisdiction", ["h1", "h2", "h3"])
        update = doc1.doc.get_update()

        # Apply to doc2
        doc2.apply_update(update)

        assert doc2.get_tag_order("jurisdiction") == ["h1", "h2", "h3"]


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
        """Broadcast callback fires for highlights, tag_order, and general_notes."""
        doc = AnnotationDocument("test-doc")
        fired: list[str] = []

        def on_update(_update: bytes, _origin: str | None) -> None:
            fired.append("update")

        doc.set_broadcast_callback(on_update)

        # Modify highlights
        doc.add_highlight(0, 5, "tag", "text", "author")
        # Modify tag_order
        doc.set_tag_order("tag", ["fake-id"])
        # Modify general_notes
        doc.set_general_notes("notes")

        assert len(fired) >= 3  # At least one update per mutation

    def test_full_state_includes_all_fields(self) -> None:
        """Full state sync transfers highlights, tag_order, general_notes."""
        doc1 = AnnotationDocument("test-doc")

        h_id = doc1.add_highlight(0, 5, "jurisdiction", "text", "author")
        doc1.set_tag_order("jurisdiction", [h_id])
        doc1.set_general_notes("shared notes")

        # Create new doc and sync full state
        doc2 = AnnotationDocument("test-doc")
        doc2.apply_update(doc1.get_full_state())

        assert doc2.get_highlight(h_id) is not None
        assert doc2.get_tag_order("jurisdiction") == [h_id]
        assert doc2.get_general_notes() == "shared notes"
