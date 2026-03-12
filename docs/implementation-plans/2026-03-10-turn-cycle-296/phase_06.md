# Wargame Turn Cycle Engine — Phase 6: Service Layer — Preprocessing Pipeline

**Goal:** Implement `run_preprocessing()` and `on_deadline_fired()` in the imperative shell with CRDT extraction, AI calls, and history management.

**Architecture:** Extensions to `db/wargames.py` following the existing session management pattern. Per-team session isolation for fault containment — if one team's AI call fails, only that team's session rolls back. Successfully processed teams retain their writes. Failed teams are marked ``round_state="error"`` for retry. The one-response invariant (check for existing assistant message before writing) guards already-succeeded teams on retry.

**Tech Stack:** SQLModel, PydanticAI, pydantic_core.to_jsonable_python, ModelMessagesTypeAdapter, pycrdt

**Scope:** 8 phases from original design (phase 6 of 8)

**Codebase verified:** 2026-03-11

**Reference files:**
- Service layer patterns: `src/promptgrimoire/db/wargames.py` (session management, transaction patterns)
- Phase 5 functions: `start_game()`, `lock_round()` in `src/promptgrimoire/db/wargames.py`
- Models: `src/promptgrimoire/db/models.py:377-535` (WargameConfig, WargameTeam, WargameMessage)
- Pure core: `src/promptgrimoire/wargame/turn_cycle.py` (extract_move_text, build_turn_prompt)
- Agents: `src/promptgrimoire/wargame/agents.py` (turn_agent, TurnResult)
- CRDT extraction pattern: `src/promptgrimoire/db/crdt_extraction.py`
- Phase 5 tests: `tests/integration/test_turn_cycle_service.py`
- Testing docs: `docs/testing.md`

**Design decisions:**
- **Per-team session isolation:** `run_preprocessing()` uses a separate `get_session()` for each team, not one shared session. This matches the fault-containment pattern: if team N's AI call fails, only team N's session rolls back. Teams 1…N-1 already committed. Team N is marked ``round_state="error"`` in its own error-marking session. A retry attempt will re-process only the errored team (the one-response invariant skips already-succeeded teams).
- **One-response invariant (skip logic is necessary):** Before writing, each team's preprocessing checks whether an assistant message already exists for the current round (``sequence_no == current_round * 2``). If it does, the team is skipped. This is required because partial failures produce committed partial state — a retry must be able to resume without double-processing the teams that already succeeded. Without this guard, retrying would produce duplicate sequence numbers and violate the ``UNIQUE(team_id, sequence_no)`` constraint.
- **Application-managed sequence_no:** PostgreSQL SERIAL/IDENTITY columns produce global sequences — they'd give interleaved numbers across teams (team A: 1,3,5; team B: 2,4,6). The design requires contiguous per-team ordering (team A: 1,2,3; team B: 1,2,3) enforced by ``UNIQUE(team_id, sequence_no)``. Application-managed MAX+1 within the transaction is the correct pattern, consistent with existing `next_tag_order` / `next_group_order` counters in the codebase.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### turn-cycle-296.AC3: Hard-Deadline Lock (deadline-fired subset)
- **turn-cycle-296.AC3.1 Success:** All teams transition from drafting→locked simultaneously (via `on_deadline_fired`)

### turn-cycle-296.AC4: Snapshot Pipeline
- **turn-cycle-296.AC4.1 Success:** Markdown extracted from populated CRDT move buffer
- **turn-cycle-296.AC4.2 Edge:** None CRDT state → "No move submitted"
- **turn-cycle-296.AC4.3 Edge:** Whitespace-only CRDT content → "No move submitted"

### turn-cycle-296.AC5: AI Pre-processing
- **turn-cycle-296.AC5.1 Success:** turn_agent returns structured TurnResult (response_text + game_state)
- **turn-cycle-296.AC5.2 Success:** PydanticAI history restored from previous assistant message's metadata_json
- **turn-cycle-296.AC5.3 Success:** Updated PydanticAI history stored on new assistant message's metadata_json

### turn-cycle-296.AC8: One-Response Invariant
- **turn-cycle-296.AC8.1 Failure:** run_preprocessing rejects if assistant message already exists for current round

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Implement run_preprocessing()

**Files:**
- Modify: `src/promptgrimoire/db/wargames.py`

**Implementation:**

Add `run_preprocessing(activity_id: UUID) -> None` to `db/wargames.py`. This function:

1. Opens a single session via `get_session()`
2. Loads `WargameConfig` and all `WargameTeam` rows for the activity
3. **Precondition check:** if any team has `round_state != "locked"`, raise `ValueError("not all teams in locked state")`
4. For each team (serial):
   a. **One-response invariant:** Calculate the expected assistant sequence number for this round: `expected_assistant_seq = team.current_round * 2`. Query `WargameMessage` for an assistant message with this team and sequence. If one exists, raise `ValueError("assistant message already exists for current round")`
   b. **Snapshot:** Call `extract_move_text(team.move_buffer_crdt)` → move text (handles None/whitespace → "No move submitted")
   c. **Restore history:** Load the most recent assistant message for this team (highest `sequence_no` where `role="assistant"`). Deserialise its `metadata_json` via `ModelMessagesTypeAdapter.validate_python()` → `message_history`
   d. **Build prompt:** `build_turn_prompt(move_text, team.game_state_text or "")` → prompt
   e. **Store user message:** `WargameMessage(team_id=team.id, sequence_no=expected_assistant_seq - 1, role="user", content=move_text)`
   f. **AI call:** `turn_agent.run(prompt, message_history=message_history, instructions=config.system_prompt)` → result
   g. **Store assistant message:** `WargameMessage(team_id=team.id, sequence_no=expected_assistant_seq, role="assistant", content=result.output.response_text, metadata_json=to_jsonable_python(result.all_messages()))`
   h. **Update game state:** `team.game_state_text = result.output.game_state`
5. Session auto-commits on exit

**Sequence number scheme** (worked example):

| Round | current_round | user seq | assistant seq | Formula |
|-------|---------------|----------|---------------|---------|
| Bootstrap (start_game) | 1 | 1 | 2 | current_round*2-1, current_round*2 |
| After first publish | 2 | 3 | 4 | current_round*2-1, current_round*2 |
| After second publish | 3 | 5 | 6 | current_round*2-1, current_round*2 |

Formula: `expected_assistant_seq = team.current_round * 2`, `expected_user_seq = team.current_round * 2 - 1`.

This gives contiguous per-team sequences where even numbers are always assistant messages.

Import additions needed (beyond Phase 5 imports):
```python
from pydantic_ai.messages import ModelMessagesTypeAdapter
from promptgrimoire.wargame.turn_cycle import extract_move_text
```

**Commit:** `feat: add run_preprocessing() to wargame service layer (#296)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement on_deadline_fired()

**Files:**
- Modify: `src/promptgrimoire/db/wargames.py`

**Implementation:**

Add `on_deadline_fired(activity_id: UUID) -> None` to `db/wargames.py`. This is the APScheduler callback that fires when a round deadline expires. It orchestrates lock + preprocessing in a single atomic operation:

1. Opens a single session via `get_session()`
2. Loads all `WargameTeam` rows for the activity
3. **Lock phase:** For all teams in `round_state="drafting"`: set `round_state="locked"`, `current_deadline=None`
4. **Preprocessing phase:** Calls the internal preprocessing logic (same as `run_preprocessing` but sharing the session)
5. Session auto-commits on exit

**Implementation note:** To share a session between lock and preprocessing, extract the core logic of both into `_with_session` internal helpers:
- `_lock_round_with_session(session, activity_id)` — performs steps 2-4 of `lock_round()`
- `_run_preprocessing_with_session(session, activity_id)` — performs steps 2-4 of `run_preprocessing()`

Refactor `lock_round()` and `run_preprocessing()` to be thin wrappers that open a session and delegate to these helpers. Then `on_deadline_fired()` opens one session and calls both helpers sequentially.

This ensures atomicity: if preprocessing crashes after locking, the lock is also rolled back. The deadline re-fires and the full operation restarts from the drafting state.

**Note on lock precondition:** `_lock_round_with_session` called from `on_deadline_fired` should check that teams are in `drafting` state but not raise — if teams are already locked (shouldn't happen, but defensive), it logs a warning and proceeds to preprocessing. The public `lock_round()` retains its strict `ValueError` behaviour.

**Commit:** `feat: add on_deadline_fired() orchestrator to wargame service layer (#296)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Integration tests for run_preprocessing() and on_deadline_fired()

**Verifies:** turn-cycle-296.AC3.1, turn-cycle-296.AC4.1, turn-cycle-296.AC4.2, turn-cycle-296.AC4.3, turn-cycle-296.AC5.1, turn-cycle-296.AC5.2, turn-cycle-296.AC5.3, turn-cycle-296.AC8.1

**Files:**
- Modify: `tests/integration/test_turn_cycle_service.py` (extend with new test class)

**Testing:**

These are integration tests requiring a real database. Use the DB skip guard and `turn_agent.override(model=TestModel())` to avoid real AI calls.

**Setup:** Each test starts by calling `start_game()` (from Phase 5) to establish initial state, then transitions teams to `drafting` state for the preprocessing tests.

**run_preprocessing tests:**
- **AC4.1:** Create a pycrdt document with markdown content in `Text("content_markdown")`, assign to `team.move_buffer_crdt`. After `run_preprocessing()`, verify the user message (seq=3) contains the extracted markdown text
- **AC4.2:** Leave `team.move_buffer_crdt` as `None`. After `run_preprocessing()`, verify the user message content is `"No move submitted"`
- **AC4.3:** Create a pycrdt document with whitespace-only content. After `run_preprocessing()`, verify the user message content is `"No move submitted"`
- **AC5.1:** After `run_preprocessing()`, verify the assistant message (seq=4) has non-empty `content` (TurnResult.response_text)
- **AC5.2:** Verify the `metadata_json` on the new assistant message contains valid PydanticAI history that includes messages from both the bootstrap round AND the new round (deserialise with `ModelMessagesTypeAdapter.validate_python()`, check length > 2)
- **AC5.3:** Verify the new `metadata_json` can be passed as `message_history` to a subsequent agent call without error
- **AC8.1:** After `run_preprocessing()` completes, calling it again raises `ValueError` (one-response invariant)

**on_deadline_fired tests:**
- **AC3.1 (deadline path):** Start with teams in `drafting` state. After `on_deadline_fired()`, all teams have `round_state="locked"`
- **Full pipeline:** After `on_deadline_fired()`, each team has both the lock applied AND new user/assistant messages from preprocessing
- **Atomicity:** Verify that if preprocessing fails (e.g., mock `turn_agent.run` to raise), the lock is also rolled back (teams remain in `drafting` state)

**CRDT fixture helper:** Create a `_make_crdt_bytes(markdown: str) -> bytes` helper in `tests/integration/conftest.py` that builds a pycrdt `Doc` with `XmlFragment("content")` and `Text("content_markdown")`, sets the markdown text, and returns the serialised bytes. Place it in conftest so Phase 8 tests can reuse it. This mirrors the pattern from `src/promptgrimoire/db/crdt_extraction.py`.

All agent calls must be wrapped in `with turn_agent.override(model=TestModel()):`.

**Verification:**
```bash
uv run grimoire test run tests/integration/test_turn_cycle_service.py
```
Expected: All tests pass (requires test database).

**Commit:** `test: add integration tests for run_preprocessing and on_deadline_fired (#296)`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
