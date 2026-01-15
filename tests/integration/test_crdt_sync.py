"""Integration tests for pycrdt CRDT synchronization.

Tests the core CRDT operations needed for Spike 1:
- Doc/Text creation and manipulation
- Sync between two Doc instances
- Observer callbacks on changes
"""

from pycrdt import Doc, Text, TransactionEvent


class TestDocTextCreation:
    """Test pycrdt Doc and Text type creation."""

    def test_create_doc_with_text(self) -> None:
        """Can create a Doc with a Text type."""
        doc = Doc()
        doc["text"] = Text()
        assert "text" in list(doc.keys())

    def test_text_initialized_empty(self) -> None:
        """Text type starts empty."""
        doc = Doc()
        doc["text"] = text = Text()
        assert str(text) == ""

    def test_text_initialized_with_value(self) -> None:
        """Text can be initialized with a string value."""
        doc = Doc()
        doc["text"] = text = Text("Hello")
        assert str(text) == "Hello"

    def test_text_append(self) -> None:
        """Can append to Text using += operator."""
        doc = Doc()
        doc["text"] = text = Text("Hello")
        text += " World"
        assert str(text) == "Hello World"

    def test_text_clear_and_set(self) -> None:
        """Can clear Text and set new content."""
        doc = Doc()
        doc["text"] = text = Text("Original")
        text.clear()
        text += "New content"
        assert str(text) == "New content"


class TestDocSynchronization:
    """Test sync between two Doc instances."""

    def test_full_state_sync(self) -> None:
        """Doc state can be transferred to another Doc."""
        # Source doc
        doc1 = Doc()
        doc1["text"] = Text("Hello from doc1")

        # Destination doc
        doc2 = Doc()
        doc2["text"] = text2 = Text()

        # Sync: get update from doc1, apply to doc2
        update = doc1.get_update()
        doc2.apply_update(update)

        assert str(text2) == "Hello from doc1"

    def test_incremental_sync(self) -> None:
        """Changes sync incrementally between docs."""
        doc1 = Doc()
        doc1["text"] = text1 = Text("Initial")

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        # Initial sync
        doc2.apply_update(doc1.get_update())
        assert str(text2) == "Initial"

        # Make change in doc1
        text1 += " + more"

        # Sync again
        doc2.apply_update(doc1.get_update())
        assert str(text2) == "Initial + more"

    def test_bidirectional_sync(self) -> None:
        """Changes can sync in both directions."""
        doc1 = Doc()
        doc1["text"] = text1 = Text()

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        # Doc1 makes a change
        text1 += "From doc1"
        doc2.apply_update(doc1.get_update())

        # Doc2 makes a change
        text2 += " and doc2"
        doc1.apply_update(doc2.get_update())

        # Both should have merged content
        assert str(text1) == "From doc1 and doc2"
        assert str(text2) == "From doc1 and doc2"

    def test_concurrent_edits_merge(self) -> None:
        """Concurrent edits are merged deterministically."""
        doc1 = Doc()
        doc1["text"] = text1 = Text("Base")

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        # Initial sync
        doc2.apply_update(doc1.get_update())

        # Both docs make concurrent changes (before syncing)
        text1 += " [edit1]"
        text2 += " [edit2]"

        # Exchange updates
        update1 = doc1.get_update()
        update2 = doc2.get_update()

        doc1.apply_update(update2)
        doc2.apply_update(update1)

        # Both docs should have same merged content
        assert str(text1) == str(text2)
        # Both edits should be present
        assert "[edit1]" in str(text1)
        assert "[edit2]" in str(text1)

    def test_update_is_idempotent(self) -> None:
        """Applying the same update multiple times is safe."""
        doc1 = Doc()
        doc1["text"] = Text("Content")

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        update = doc1.get_update()

        # Apply same update multiple times
        doc2.apply_update(update)
        doc2.apply_update(update)
        doc2.apply_update(update)

        assert str(text2) == "Content"

    def test_update_is_bytes(self) -> None:
        """Updates are bytes (suitable for network transmission)."""
        doc = Doc()
        doc["text"] = Text("Hello")

        update = doc.get_update()

        assert isinstance(update, bytes)
        assert len(update) > 0


class TestObserverCallbacks:
    """Test observer pattern for detecting changes."""

    def test_doc_observe_fires_on_change(self) -> None:
        """Doc observer fires when text changes."""
        doc = Doc()
        doc["text"] = text = Text()

        events: list[TransactionEvent] = []

        def on_change(event: TransactionEvent) -> None:
            events.append(event)

        doc.observe(on_change)

        text += "Hello"

        assert len(events) == 1

    def test_observer_receives_update_bytes(self) -> None:
        """Observer event contains update bytes."""
        doc = Doc()
        doc["text"] = text = Text()

        received_update: bytes | None = None

        def on_change(event: TransactionEvent) -> None:
            nonlocal received_update
            received_update = event.update

        doc.observe(on_change)

        text += "Hello"

        assert received_update is not None
        assert isinstance(received_update, bytes)

    def test_observer_update_can_sync_another_doc(self) -> None:
        """Update from observer can be used to sync another doc."""
        doc1 = Doc()
        doc1["text"] = text1 = Text()

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        # Set up observer to forward updates
        def forward_to_doc2(event: TransactionEvent) -> None:
            doc2.apply_update(event.update)

        doc1.observe(forward_to_doc2)

        # Change in doc1 should automatically sync to doc2
        text1 += "Auto-synced!"

        assert str(text2) == "Auto-synced!"

    def test_multiple_changes_fire_multiple_events(self) -> None:
        """Each change fires a separate observer event."""
        doc = Doc()
        doc["text"] = text = Text()

        event_count = 0

        def on_change(_event: TransactionEvent) -> None:
            nonlocal event_count
            event_count += 1

        doc.observe(on_change)

        text += "One"
        text += "Two"
        text += "Three"

        assert event_count == 3

    def test_transaction_batches_changes(self) -> None:
        """Multiple changes in a transaction fire one event."""
        doc = Doc()
        doc["text"] = text = Text()

        event_count = 0

        def on_change(_event: TransactionEvent) -> None:
            nonlocal event_count
            event_count += 1

        doc.observe(on_change)

        with doc.transaction():
            text += "One"
            text += "Two"
            text += "Three"

        assert event_count == 1

    def test_unobserve_stops_callbacks(self) -> None:
        """Can unsubscribe from observer."""
        doc = Doc()
        doc["text"] = text = Text()

        event_count = 0

        def on_change(_event: TransactionEvent) -> None:
            nonlocal event_count
            event_count += 1

        subscription_id = doc.observe(on_change)

        text += "First"
        assert event_count == 1

        doc.unobserve(subscription_id)

        text += "Second"
        assert event_count == 1  # Still 1, callback not fired


class TestEdgeCases:
    """Edge cases and error conditions."""

    def test_empty_update_is_valid(self) -> None:
        """Getting update from empty doc returns valid bytes."""
        doc = Doc()
        doc["text"] = Text()

        update = doc.get_update()

        assert isinstance(update, bytes)

    def test_apply_empty_doc_update(self) -> None:
        """Applying update from empty doc doesn't break things."""
        doc1 = Doc()
        doc1["text"] = Text()

        doc2 = Doc()
        doc2["text"] = text2 = Text("Existing")

        doc2.apply_update(doc1.get_update())

        assert str(text2) == "Existing"

    def test_large_text_syncs(self) -> None:
        """Large text content syncs correctly."""
        doc1 = Doc()
        doc1["text"] = text1 = Text()

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        # Add large content
        large_content = "x" * 10000
        text1 += large_content

        doc2.apply_update(doc1.get_update())

        assert str(text2) == large_content
        assert len(str(text2)) == 10000

    def test_unicode_content_syncs(self) -> None:
        """Unicode content syncs correctly."""
        doc1 = Doc()
        doc1["text"] = text1 = Text()

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        unicode_content = "Hello 世界 🌍 émojis Ω"
        text1 += unicode_content

        doc2.apply_update(doc1.get_update())

        assert str(text2) == unicode_content

    def test_rapid_successive_updates(self) -> None:
        """Rapid successive updates all sync correctly."""
        doc1 = Doc()
        doc1["text"] = text1 = Text()

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        # Simulate rapid typing
        for i in range(100):
            text1 += str(i)
            doc2.apply_update(doc1.get_update())

        expected = "".join(str(i) for i in range(100))
        assert str(text2) == expected


class TestDifferentialSync:
    """Test efficient differential synchronization using state vectors."""

    def test_differential_sync_with_state_vector(self) -> None:
        """Differential sync sends only missing updates."""
        doc1 = Doc()
        doc1["text"] = text1 = Text("Initial")

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        # Initial full sync
        doc2.apply_update(doc1.get_update())
        assert str(text2) == "Initial"

        # Record doc2's state before doc1's next change
        state_before = doc2.get_state()

        # doc1 makes more changes
        text1 += " more"

        # Differential sync - only get what doc2 is missing
        diff_update = doc1.get_update(state_before)
        full_update = doc1.get_update()

        # Diff should be smaller than full update
        assert len(diff_update) < len(full_update)

        # Applying diff should still result in correct state
        doc2.apply_update(diff_update)
        assert str(text2) == "Initial more"

    def test_bidirectional_differential_sync(self) -> None:
        """Both docs can exchange only missing updates."""
        doc1 = Doc()
        doc1["text"] = text1 = Text("Start")

        doc2 = Doc()
        doc2["text"] = text2 = Text()

        # Initial sync
        doc2.apply_update(doc1.get_update())

        # Both make independent changes
        text1 += " from doc1"
        text2 += " from doc2"

        # Get state vectors
        sv1 = doc1.get_state()
        sv2 = doc2.get_state()

        # Compute differential updates
        diff1_to_2 = doc1.get_update(sv2)  # What doc2 is missing from doc1
        diff2_to_1 = doc2.get_update(sv1)  # What doc1 is missing from doc2

        # Apply diffs
        doc1.apply_update(diff2_to_1)
        doc2.apply_update(diff1_to_2)

        # Both should have merged content
        assert str(text1) == str(text2)
        assert "from doc1" in str(text1)
        assert "from doc2" in str(text1)

    def test_no_update_when_already_synced(self) -> None:
        """Differential update is minimal when already synced."""
        doc1 = Doc()
        doc1["text"] = Text("Content")

        doc2 = Doc()
        doc2["text"] = Text()

        # Full sync
        doc2.apply_update(doc1.get_update())

        # Get update using doc2's current state (should be minimal)
        diff = doc1.get_update(doc2.get_state())

        # Diff should be very small (just header, no actual changes)
        # The exact size depends on encoding, but should be much smaller than content
        full = doc1.get_update()
        assert len(diff) < len(full) // 2


class TestOriginTracking:
    """Test transaction origin for coordinating updates.

    Note: pycrdt's TransactionEvent does not expose origin in the observer callback.
    The origin is only accessible during the transaction itself (via txn.origin).
    For echo prevention, applications need to track this at the application level,
    e.g., by wrapping update broadcasts with origin metadata.
    """

    def test_transaction_can_have_origin(self) -> None:
        """Transaction can be created with an origin, accessible during transaction."""
        doc = Doc()
        doc["text"] = text = Text()

        captured_origin = None

        with doc.transaction(origin="client-1") as txn:
            captured_origin = txn.origin
            text += "Hello"

        assert captured_origin == "client-1"

    def test_origin_is_none_by_default(self) -> None:
        """Transactions without explicit origin have None."""
        doc = Doc()
        doc["text"] = text = Text()

        captured_origin = "not-set"

        with doc.transaction() as txn:
            captured_origin = txn.origin
            text += "Hello"

        assert captured_origin is None

    def test_nested_transaction_inherits_origin(self) -> None:
        """Nested transactions reuse the outer transaction's origin."""
        doc = Doc()
        doc["text"] = text = Text()

        inner_origin = None

        with doc.transaction(origin="outer"):
            text += "First"
            # Nested transaction reuses outer
            with doc.transaction() as inner_txn:
                inner_origin = inner_txn.origin
                text += " Second"

        # Inner should see outer's origin (same transaction)
        assert inner_origin == "outer"

    def test_observer_receives_update_bytes(self) -> None:
        """Observer can use update bytes for sync, tracking origin separately."""
        doc = Doc()
        doc["text"] = text = Text()

        received_updates: list[bytes] = []

        def on_change(event: TransactionEvent) -> None:
            received_updates.append(event.update)

        doc.observe(on_change)

        # Make a change
        with doc.transaction(origin="test-client"):
            text += "Hello"

        # Observer receives update bytes (origin tracking must be done separately)
        assert len(received_updates) == 1
        assert isinstance(received_updates[0], bytes)


class TestPositionBasedEditing:
    """Test position-based text operations for cursor-aware editing."""

    def test_insert_at_position(self) -> None:
        """Can insert text at specific index."""
        doc = Doc()
        doc["text"] = text = Text("Hello World!")
        text.insert(5, ",")
        assert str(text) == "Hello, World!"

    def test_insert_at_beginning(self) -> None:
        """Can insert at position 0."""
        doc = Doc()
        doc["text"] = text = Text("World")
        text.insert(0, "Hello ")
        assert str(text) == "Hello World"

    def test_insert_at_end(self) -> None:
        """Can insert at the end position."""
        doc = Doc()
        doc["text"] = text = Text("Hello")
        text.insert(5, " World")
        assert str(text) == "Hello World"

    def test_insert_at_position_syncs(self) -> None:
        """Position-based insert syncs correctly."""
        doc1 = Doc()
        doc1["text"] = text1 = Text("Hello World")

        doc2 = Doc()
        doc2["text"] = text2 = Text()
        doc2.apply_update(doc1.get_update())

        # Insert at position 5 in doc1
        text1.insert(5, " Beautiful")

        doc2.apply_update(doc1.get_update())
        assert str(text2) == "Hello Beautiful World"

    def test_delete_at_position(self) -> None:
        """Can delete text at specific index."""
        doc = Doc()
        doc["text"] = text = Text("Hello, World!")
        del text[5]  # Delete the comma
        assert str(text) == "Hello World!"

    def test_delete_range(self) -> None:
        """Can delete a range of text."""
        doc = Doc()
        doc["text"] = text = Text("Hello, World!")
        del text[5:7]  # Delete ", "
        assert str(text) == "HelloWorld!"

    def test_delete_to_end(self) -> None:
        """Can delete from position to end."""
        doc = Doc()
        doc["text"] = text = Text("Hello World")
        del text[5:]
        assert str(text) == "Hello"

    def test_replace_range(self) -> None:
        """Can replace text at specific range."""
        doc = Doc()
        doc["text"] = text = Text("Hello, World!")
        text[7:12] = "Brian"
        assert str(text) == "Hello, Brian!"

    def test_concurrent_position_inserts_different_positions(self) -> None:
        """Concurrent inserts at different positions merge correctly."""
        doc1 = Doc()
        doc1["text"] = text1 = Text("Hello World")

        doc2 = Doc()
        doc2["text"] = text2 = Text()
        doc2.apply_update(doc1.get_update())

        # doc1 inserts at position 0
        text1.insert(0, "Say: ")

        # doc2 inserts at end (position 11)
        text2.insert(11, "!")

        # Exchange updates
        update1 = doc1.get_update()
        update2 = doc2.get_update()
        doc1.apply_update(update2)
        doc2.apply_update(update1)

        # Both should have same merged result
        assert str(text1) == str(text2)
        assert "Say:" in str(text1)
        assert "!" in str(text1)

    def test_concurrent_inserts_at_same_position(self) -> None:
        """Concurrent inserts at same position are both preserved."""
        doc1 = Doc()
        doc1["text"] = text1 = Text("AC")

        doc2 = Doc()
        doc2["text"] = text2 = Text()
        doc2.apply_update(doc1.get_update())

        # Both insert at position 1 (between A and C)
        text1.insert(1, "B1")
        text2.insert(1, "B2")

        # Exchange updates
        update1 = doc1.get_update()
        update2 = doc2.get_update()
        doc1.apply_update(update2)
        doc2.apply_update(update1)

        # Both edits should be present, order determined by CRDT
        assert str(text1) == str(text2)
        assert "B1" in str(text1)
        assert "B2" in str(text1)
        assert str(text1).startswith("A")
        assert str(text1).endswith("C")


class TestStickyIndex:
    """Test StickyIndex for cursor position tracking."""

    def test_sticky_index_survives_insert_before(self) -> None:
        """StickyIndex adjusts when text inserted before it."""
        doc = Doc()
        doc["text"] = text = Text("Hello World")

        # Create sticky index at position 6 (start of "World")
        sticky = text.sticky_index(6)
        assert sticky.get_index() == 6

        # Insert text before the sticky position
        text.insert(0, "Say ")

        # Sticky index should have moved
        assert sticky.get_index() == 10  # "Say Hello ".length

    def test_sticky_index_stable_on_insert_after(self) -> None:
        """StickyIndex stays put when text inserted after it."""
        doc = Doc()
        doc["text"] = text = Text("Hello World")

        # Create sticky index at position 5 (end of "Hello")
        sticky = text.sticky_index(5)
        assert sticky.get_index() == 5

        # Insert text after the sticky position
        text.insert(6, " Beautiful")

        # Sticky index should not have moved
        assert sticky.get_index() == 5

    def test_sticky_index_at_insertion_point(self) -> None:
        """StickyIndex with AFTER assoc moves with insert at same position."""
        doc = Doc()
        doc["text"] = text = Text("AB")

        # Create sticky index at position 1, associating AFTER
        sticky = text.sticky_index(1)  # Default is Assoc.AFTER

        # Insert at the same position
        text.insert(1, "X")

        # With AFTER assoc, sticky should move after inserted text
        assert sticky.get_index() == 2  # Now after "AX"

    def test_sticky_index_serialization(self) -> None:
        """StickyIndex can be serialized and deserialized."""
        doc = Doc()
        doc["text"] = text = Text("Hello World")

        sticky = text.sticky_index(6)

        # Serialize to bytes
        encoded = sticky.encode()
        assert isinstance(encoded, bytes)

        # Deserialize
        restored = type(sticky).decode(encoded, text)
        assert restored.get_index() == 6

    def test_sticky_index_survives_concurrent_edit(self) -> None:
        """StickyIndex maintains correct position through sync."""
        doc1 = Doc()
        doc1["text"] = text1 = Text("Hello World")

        doc2 = Doc()
        doc2["text"] = text2 = Text()
        doc2.apply_update(doc1.get_update())

        # Create sticky index in doc1 at "World"
        sticky = text1.sticky_index(6)

        # doc2 inserts text at beginning
        text2.insert(0, "Say ")

        # Sync
        doc1.apply_update(doc2.get_update())

        # Sticky index should have adjusted
        assert sticky.get_index() == 10  # "Say Hello " is 10 chars
