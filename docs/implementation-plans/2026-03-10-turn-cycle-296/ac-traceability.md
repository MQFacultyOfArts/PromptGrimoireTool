# Wargame Turn Cycle Engine -- AC Traceability Matrix

**Issue:** #296

Every acceptance criterion mapped to the test(s) that verify it.

## AC1: Game Start Bootstrap

| AC | Description | Test File | Test Method | Phase |
|----|-------------|-----------|-------------|-------|
| AC1.1 | Bootstrap stored as user message (seq=1) with team codename | `test_turn_cycle_service.py` | `TestStartGame::test_ac1_1_bootstrap_expanded_with_codename` | 5 |
| AC1.1 | Bootstrap codename verified in full round trip | `test_turn_cycle_e2e.py` | `_assert_bootstrap_state` (codename in user message) | 8 |
| AC1.2 | AI response stored as assistant message (seq=2) with PydanticAI history in metadata_json | `test_turn_cycle_service.py` | `TestStartGame::test_ac1_2_assistant_message_with_pydantic_history` | 5 |
| AC1.2 | PydanticAI history verified in full round trip | `test_turn_cycle_e2e.py` | `_assert_bootstrap_state` (metadata_json deserialisable) | 8 |
| AC1.3 | game_state_text populated from TurnResult.game_state | `test_turn_cycle_service.py` | `TestStartGame::test_ac1_3_game_state_text_populated` | 5 |
| AC1.3 | game_state_text verified in full round trip | `test_turn_cycle_e2e.py` | `test_two_full_rounds` (step 1: `game_state_text is not None`) | 8 |
| AC1.4 | start_game rejects if game already started | `test_turn_cycle_service.py` | `TestStartGame::test_ac1_4_rejects_already_started` | 5 |

## AC2: Timer Management

| AC | Description | Test File | Test Method | Phase |
|----|-------------|-----------|-------------|-------|
| AC2.1 | Deadline polling worker fires callback when current_deadline expires | `test_deadline_worker.py` (integration) | `test_ac2_1_fires_for_expired_deadline` | 4 |
| AC2.1 | Unit-level query logic | `test_deadline_worker.py` (unit) | `test_check_expired_deadlines_fires_for_expired` | 4 |
| AC2.2 | Expired deadlines fire on first poll after restart | `test_deadline_worker.py` (integration) | `test_ac2_2_misfire_recovery` | 4 |
| AC2.3 | Setting current_deadline=None cancels deadline | `test_deadline_worker.py` (integration) | `test_ac2_3_cancelled_deadline_ignored` | 4 |
| AC2.4 | Wall-clock mode rolls to next day if time already past | `test_turn_cycle.py` (unit) | `TestCalculateDeadline::test_wall_clock_past_today_rolls_to_next_day` | 2 |
| AC2.4 | Wall-clock rollover verified end-to-end via publish_all | `test_turn_cycle_service.py` | `TestPublishAll::test_ac2_4_wall_clock_rollover` | 7 |

## AC3: Hard-Deadline Lock

| AC | Description | Test File | Test Method | Phase |
|----|-------------|-----------|-------------|-------|
| AC3.1 | All teams transition drafting to locked simultaneously | `test_turn_cycle_service.py` | `TestLockRound::test_ac3_1_all_teams_locked` | 5 |
| AC3.1 | Deadline path locks all teams | `test_turn_cycle_service.py` | `TestOnDeadlineFired::test_ac3_1_deadline_locks_all_teams` | 6 |
| AC3.1 | Verified in full round trip | `test_turn_cycle_e2e.py` | `test_two_full_rounds` (step 4: `round_state == "locked"`) | 8 |
| AC3.2 | current_deadline cleared on lock | `test_turn_cycle_service.py` | `TestLockRound::test_ac3_2_deadline_cleared` | 5 |
| AC3.3 | lock_round rejects if any team not in drafting state | `test_turn_cycle_service.py` | `TestLockRound::test_ac3_3_rejects_non_drafting` | 5 |

## AC4: Snapshot Pipeline (CRDT Extraction)

| AC | Description | Test File | Test Method | Phase |
|----|-------------|-----------|-------------|-------|
| AC4.1 | Markdown extracted from populated CRDT move buffer | `test_turn_cycle.py` (unit) | `TestExtractMoveText::test_populated_crdt_returns_content` | 2 |
| AC4.1 | Integration extraction via run_preprocessing | `test_turn_cycle_service.py` | `TestRunPreprocessing::test_ac4_1_markdown_extracted_from_crdt` | 6 |
| AC4.1 | CRDT-extracted move text in full round trip | `test_turn_cycle_e2e.py` | `_assert_round2_messages` (move text in user message) | 8 |
| AC4.2 | None CRDT state produces "No move submitted" | `test_turn_cycle.py` (unit) | `TestExtractMoveText::test_none_returns_sentinel` | 2 |
| AC4.2 | Integration: None CRDT gives sentinel | `test_turn_cycle_service.py` | `TestRunPreprocessing::test_ac4_2_none_crdt_gives_sentinel` | 6 |
| AC4.2 | Empty moves verified in full round trip | `test_turn_cycle_e2e.py` | `TestEdgeCases::test_empty_moves_all_teams` | 8 |
| AC4.3 | Whitespace-only CRDT produces "No move submitted" | `test_turn_cycle.py` (unit) | `TestExtractMoveText::test_whitespace_only_returns_sentinel` | 2 |
| AC4.3 | Integration: whitespace CRDT gives sentinel | `test_turn_cycle_service.py` | `TestRunPreprocessing::test_ac4_3_whitespace_crdt_gives_sentinel` | 6 |

## AC5: AI Pre-processing

| AC | Description | Test File | Test Method | Phase |
|----|-------------|-----------|-------------|-------|
| AC5.1 | turn_agent returns structured TurnResult | `test_wargame_agents.py` (unit) | `TestTurnAgent::test_returns_turn_result` | 3 |
| AC5.1 | Assistant message has non-empty content | `test_turn_cycle_service.py` | `TestRunPreprocessing::test_ac5_1_assistant_message_with_content` | 6 |
| AC5.2 | PydanticAI history restored from previous metadata_json | `test_turn_cycle_service.py` | `TestStartGame::test_ac5_2_ac5_3_metadata_history_round_trip` | 5 |
| AC5.2 | Metadata includes bootstrap history in preprocessing | `test_turn_cycle_service.py` | `TestRunPreprocessing::test_ac5_2_metadata_includes_bootstrap_history` | 6 |
| AC5.2 | History accumulation across rounds in full round trip | `test_turn_cycle_e2e.py` | `_assert_round2_messages` (`len(restored) > 2`) | 8 |
| AC5.3 | Updated PydanticAI history stored on new metadata_json | `test_turn_cycle_service.py` | `TestStartGame::test_ac5_2_ac5_3_metadata_history_round_trip` | 5 |
| AC5.3 | New metadata usable as message_history | `test_turn_cycle_service.py` | `TestRunPreprocessing::test_ac5_3_metadata_usable_as_message_history` | 6 |
| AC5.4 | summary_agent returns structured StudentSummary | `test_wargame_agents.py` (unit) | `TestSummaryAgent::test_returns_student_summary` | 3 |

## AC6: Publish Pipeline

| AC | Description | Test File | Test Method | Phase |
|----|-------------|-----------|-------------|-------|
| AC6.1 | Student summaries generated per team on publish | `test_turn_cycle_service.py` | `TestPublishAll::test_ac6_1_summary_text_populated` | 7 |
| AC6.1 | Summary populated in full round trip | `test_turn_cycle_e2e.py` | `_assert_publish_state` (`student_summary_text is not None`) | 8 |
| AC6.2 | current_round advances for all teams | `test_turn_cycle_service.py` | `TestPublishAll::test_ac6_2_round_advanced` | 7 |
| AC6.2 | Round advance in full round trip | `test_turn_cycle_e2e.py` | `_assert_publish_state` (`current_round == expected_round`) | 8 |
| AC6.3 | round_state transitions locked to drafting | `test_turn_cycle_service.py` | `TestPublishAll::test_ac6_3_state_back_to_drafting` | 7 |
| AC6.3 | State transition in full round trip | `test_turn_cycle_e2e.py` | `_assert_publish_state` (`round_state == "drafting"`) | 8 |
| AC6.4 | move_buffer_crdt cleared to None | `test_turn_cycle_service.py` | `TestPublishAll::test_ac6_4_move_buffer_cleared` | 7 |
| AC6.4 | Buffer cleared in full round trip | `test_turn_cycle_e2e.py` | `_assert_publish_state` (`move_buffer_crdt is None`) | 8 |
| AC6.5 | Next deadline set on all teams via current_deadline | `test_turn_cycle_service.py` | `TestPublishAll::test_ac6_5_deadline_set` | 7 |
| AC6.5 | Deadline set in full round trip | `test_turn_cycle_e2e.py` | `_assert_publish_state` (`current_deadline > now`) | 8 |

## AC7: Completion Gating

| AC | Description | Test File | Test Method | Phase |
|----|-------------|-----------|-------------|-------|
| AC7.1 | publish_all rejects if any team missing draft response | `test_turn_cycle_service.py` | `TestPublishAll::test_ac7_1_rejects_missing_assistant_messages` | 7 |
| AC7.2 | publish_all rejects if any team not in locked state | `test_turn_cycle_service.py` | `TestPublishAll::test_ac7_2_rejects_drafting_state` | 7 |

## AC8: One-Response Invariant

| AC | Description | Test File | Test Method | Phase |
|----|-------------|-----------|-------------|-------|
| AC8.1 | run_preprocessing skips if assistant message exists for round | `test_turn_cycle_service.py` | `TestRunPreprocessing::test_ac8_1_one_response_invariant` | 6 |
| AC8.2 | publish_all verifies exactly one assistant message per round | `test_turn_cycle_service.py` | `TestPublishAll::test_ac8_2_duplicate_assistant_message_rejected` | 7 |
| AC8.3 | No code path creates duplicate assistant message (full lifecycle) | `test_turn_cycle_e2e.py` | `TestEdgeCases::test_ac8_3_no_duplicate_assistants_across_rounds` | 8 |
| AC8.3 | Invariant verified in full round trip | `test_turn_cycle_e2e.py` | `test_two_full_rounds` (step 5: unique sequence numbers) | 8 |

## Additional Coverage (Non-AC Tests)

Tests that verify robustness beyond the acceptance criteria:

| Test File | Test Method | What It Verifies | Phase |
|-----------|-------------|------------------|-------|
| `test_turn_cycle_service.py` | `TestStartGame::test_teams_locked_after_start` | Teams in round=1, state=locked after bootstrap | 5 |
| `test_turn_cycle_service.py` | `TestOnDeadlineFired::test_full_pipeline_lock_and_preprocess` | Full pipeline: lock AND create messages | 6 |
| `test_turn_cycle_service.py` | `TestOnDeadlineFired::test_lock_committed_even_when_preprocessing_fails` | Lock phase commits independently of preprocessing errors | 6 |
| `test_turn_cycle_service.py` | `TestOnDeadlineFired::test_partial_failure_marks_errored_team_continues_others` | Per-team isolation: one failure does not block others | 6 |
| `test_turn_cycle_service.py` | `TestPublishAll::test_error_teams_skipped` | Error-state teams skipped by publish_all | 7 |
| `test_turn_cycle_e2e.py` | `TestEdgeCases::test_empty_moves_all_teams` | Empty moves processed correctly through full publish | 8 |
| `test_turn_cycle_e2e.py` | `TestEdgeCases::test_mixed_moves` | Mixed moves (some content, some None) processed correctly | 8 |
| `test_deadline_worker.py` (integration) | `test_idempotency_locked_teams_skipped` | Locked teams not re-processed by deadline worker | 4 |
| `test_deadline_worker.py` (unit) | `test_check_expired_deadlines_skips_future` | Future deadlines not fired | 4 |
| `test_deadline_worker.py` (unit) | `test_check_expired_deadlines_exception_doesnt_prevent_others` | Exception in one callback does not block others | 4 |
| `test_deadline_worker.py` (unit) | `test_next_deadline_seconds_returns_none_when_no_deadlines` | No deadlines returns None sleep interval | 4 |
| `test_turn_cycle.py` (unit) | `TestExpandBootstrap::*` | Bootstrap template expansion edge cases | 2 |
| `test_turn_cycle.py` (unit) | `TestCalculateDeadline::*` | Deadline calculation edge cases (delta, wall-clock, errors) | 2 |
| `test_turn_cycle.py` (unit) | `TestRenderPrompt::*` | T-string template rendering | 2 |
| `test_turn_cycle.py` (unit) | `TestBuildTurnPrompt::*` | Turn prompt assembly with XML tags | 2 |
| `test_turn_cycle.py` (unit) | `TestBuildSummaryPrompt::*` | Summary prompt assembly | 2 |
| `test_wargame_agents.py` (unit) | `TestTurnAgent::*` | Agent configuration and history round-trip | 3 |
| `test_wargame_agents.py` (unit) | `TestSummaryAgent::*` | Summary agent configuration | 3 |
| `test_wargame_agents.py` (unit) | `TestOutputModels::*` | Pydantic model field validation | 3 |
