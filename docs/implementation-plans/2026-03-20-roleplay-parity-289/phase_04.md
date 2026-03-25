# Roleplay Parity Implementation Plan — Phase 4: End-of-Conversation Detection

**Goal:** Detect `<endofconversation>` marker in streaming response and signal the UI via StreamChunk dataclass.

**Architecture:** Pure async detection function wraps `AsyncIterator[str]` → `AsyncIterator[StreamChunk]`, handling marker detection including chunk boundary spanning. Wired into `stream_message_only()`. End-of-conversation instruction appended to system prompt. `Session.ended` field added.

**Tech Stack:** Python 3.14 dataclasses, async generators

**Scope:** Phase 4 of 7 from original design

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-parity-289.AC3: End-of-conversation flow
- **roleplay-parity-289.AC3.1 Success:** `<endofconversation>` marker detected in streamed response and stripped from displayed text
- **roleplay-parity-289.AC3.2 Edge:** Marker spanning two streaming chunks is correctly detected and stripped
- **roleplay-parity-289.AC3.3 Success:** `StreamChunk.ended` is `True` when marker present, `False` for normal responses

---

<!-- START_TASK_1 -->
### Task 1: Add Session.ended field

**Verifies:** roleplay-parity-289.AC3.3 (prerequisite)

**Files:**
- Modify: `src/promptgrimoire/models/scenario.py:120-136` (Session dataclass)

**Implementation:**

Add `ended: bool = False` field to the `Session` dataclass after the `created_at` field:

```python
ended: bool = False
```

Update the docstring to include:
```
ended: Whether the conversation has concluded (endofconversation detected or user finished early).
```

**Verification:**
Run: `uvx ty check`
Expected: No new type errors

**Commit:** `feat: add Session.ended flag for end-of-conversation tracking`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Create StreamChunk dataclass and pure detection function

**Verifies:** roleplay-parity-289.AC3.1, roleplay-parity-289.AC3.2, roleplay-parity-289.AC3.3

**Files:**
- Modify: `src/promptgrimoire/llm/client.py` — add StreamChunk dataclass and detection function at module level (before ClaudeClient class)
- Test: `tests/unit/test_end_of_conversation.py` (unit, new file)

**Implementation:**

Add `StreamChunk` dataclass at module level in `client.py`:

```python
@dataclass(frozen=True)
class StreamChunk:
    """A chunk of streamed text with end-of-conversation signal.

    Attributes:
        text: The text content of this chunk (marker stripped if present).
        ended: True when the <endofconversation> marker was detected.
        thinking: Extended thinking content (None if thinking is disabled).
    """

    text: str
    ended: bool = False
    thinking: str | None = None
```

Add the end-of-conversation marker constant:

```python
_END_MARKER = "<endofconversation>"
```

Add a pure async generator function `detect_end_of_conversation()`:

```python
async def detect_end_of_conversation(
    chunks: AsyncIterator[str],
) -> AsyncIterator[StreamChunk]:
    """Detect <endofconversation> marker in a stream of text chunks.

    Buffers up to len(marker)-1 characters to handle marker spanning
    chunk boundaries. Case-sensitive exact match only.

    Yields StreamChunk with ended=True on the chunk containing the marker.
    All text after the marker in the same or subsequent chunks is discarded.
    """
```

Detection strategy — sliding window buffer:
- Maintain a `buffer: str` that holds the trailing `len(_END_MARKER) - 1` characters from the previous chunk plus the current chunk
- On each incoming chunk, prepend the buffer, search for `_END_MARKER` in the combined text
- If found: yield any text before the marker as `StreamChunk(text=..., ended=True)`, then stop iterating
- If not found: yield all text except the trailing `len(_END_MARKER) - 1` characters (which become the new buffer for boundary detection)
- After the iterator is exhausted without finding the marker: flush the remaining buffer as `StreamChunk(text=..., ended=False)`

**Testing:**

Create `tests/unit/test_end_of_conversation.py` with tests:

- roleplay-parity-289.AC3.1: Marker in a single chunk — detected and stripped
- roleplay-parity-289.AC3.1: Marker at end of response — text before marker yielded, marker stripped
- roleplay-parity-289.AC3.1: Marker in middle of chunk — text before marker yielded, text after discarded
- roleplay-parity-289.AC3.2: Marker spanning two chunks (e.g., `"<endofconv"` + `"ersation>"`) — correctly detected
- roleplay-parity-289.AC3.2: Marker spanning three chunks — correctly detected
- roleplay-parity-289.AC3.3: No marker in response — all chunks have `ended=False`
- roleplay-parity-289.AC3.3: Normal text containing `<` but not the marker — not falsely triggered
- Edge case: Empty stream — no chunks yielded
- Edge case: Marker is the entire response — yields `StreamChunk(text="", ended=True)`

Use simple async generators as test input — no API mocking needed for this pure function.

```python
async def _chunks(*texts: str) -> AsyncIterator[str]:
    for t in texts:
        yield t
```

**Verification:**
Run: `uv run grimoire test run tests/unit/test_end_of_conversation.py`
Expected: All tests pass

**Commit:** `feat: add StreamChunk and end-of-conversation detection with chunk boundary handling`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Wire detection into stream_message_only() and add system prompt instruction

**Verifies:** roleplay-parity-289.AC3.1, roleplay-parity-289.AC3.3

**Files:**
- Modify: `src/promptgrimoire/llm/client.py:201-254` (stream_message_only)
- Modify: `src/promptgrimoire/llm/prompt.py` (build_system_prompt — append end-of-conversation instruction)
- Test: `tests/unit/test_prompt_assembly.py` (unit — add test for instruction presence)

**Implementation:**

In `stream_message_only()`:
- Change return type from `AsyncIterator[str]` to `AsyncIterator[StreamChunk]`
- Extract the raw text streaming into an inner async generator
- Wrap it with `detect_end_of_conversation()`
- Yield `StreamChunk` objects instead of plain strings
- Track whether conversation ended via the `ended` flag on the final chunk

The existing `full_response` buffer and `finally` block remain — the full response text is still accumulated for the session turn, but now from `chunk.text` instead of raw text.

In `build_system_prompt()`:
- Add a constant for the end-of-conversation instruction:

```python
_END_OF_CONVERSATION_INSTRUCTION = (
    "\n\nWhen the conversation reaches a natural conclusion — the client "
    "has said goodbye, all topics are addressed, or the interview is clearly "
    "over — emit the marker <endofconversation> at the very end of your "
    "final response. Do not explain the marker; it is invisible to the user."
)
```

- Append this instruction after all ST-parity slots (after the `mes_example` / dialogueExamples slot) but before placeholder substitution, so it's part of the final system prompt.

**Callers to update:** Known callers of `stream_message_only()`:
- `src/promptgrimoire/pages/roleplay.py:140` — `_handle_send()` function, line `async for chunk in client.stream_message_only(session):`

This is the only caller. Update it to handle `StreamChunk` instead of plain `str`:
- Use `chunk.text` for display (previously the chunk was a plain string)
- Check `chunk.ended` (Phase 7 wires this to the completion flow, but for Phase 4 just log it)

**Testing:**

Add test to `test_prompt_assembly.py`:
- System prompt includes end-of-conversation instruction text (verify `<endofconversation>` instruction is present in output)
- End-of-conversation instruction appears after all other slots

**Verification:**
Run: `uv run grimoire test run tests/unit/test_prompt_assembly.py tests/unit/test_end_of_conversation.py`
Expected: All tests pass

**Commit:** `feat: wire end-of-conversation detection into streaming and add system prompt instruction`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run tests: `uv run grimoire test run tests/unit/test_end_of_conversation.py tests/unit/test_prompt_assembly.py`
2. [ ] Verify all detection tests pass (single chunk, spanning chunks, no marker)
3. [ ] Run: `uvx ty check` — verify no type errors from StreamChunk return type change
4. [ ] Start the app: `uv run run.py`
5. [ ] Navigate to `/roleplay` and send a message
6. [ ] Verify the conversation streams normally (no regression from StreamChunk change)

## Evidence Required

- [ ] Test output showing all detection and prompt assembly tests green
- [ ] `uvx ty check` output clean
- [ ] Successful streaming conversation in the app
