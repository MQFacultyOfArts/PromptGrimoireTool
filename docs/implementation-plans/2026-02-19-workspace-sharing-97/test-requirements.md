# Test Requirements — Workspace Sharing & Visibility (#97)

Generated from acceptance criteria in the design plan.

## AC1: Peer Permission Level

| ID | Type | Criterion | Phase | Test Type |
|----|------|-----------|-------|-----------|
| AC1.1 | Success | Permission table contains 'peer' with level 15 | P1 | Integration |
| AC1.2 | Success | Peer can view documents and highlights in shared workspace | P4 | UAT |
| AC1.3 | Success | Peer can create highlights and tags in shared workspace | P4 | UAT |
| AC1.4 | Success | Peer can add comments on highlights | P4 | UAT |
| AC1.5 | Success | Peer can delete own comments | P3 | Unit |
| AC1.6 | Failure | Peer cannot add or delete documents | P4 | UAT |
| AC1.7 | Failure | Peer cannot manage ACL (share workspace) | P4 | Unit + UAT |
| AC1.8 | Failure | Peer cannot delete others' comments | P3 | Unit |

## AC2: Enrollment-Based Discovery

| ID | Type | Criterion | Phase | Test Type |
|----|------|-----------|-------|-----------|
| AC2.1 | Success | Student enrolled + allow_sharing=True + shared_with_class=True -> peer | P2, P6 | Integration |
| AC2.2 | Success | Explicit ACL entry with higher permission wins over enrollment-derived peer | P2 | Integration |
| AC2.3 | Success | Student's own workspace returns owner, not peer | P2 | Integration |
| AC2.4 | Failure | Student not enrolled gets None | P2 | Integration |
| AC2.5 | Failure | allow_sharing=False gets None | P2 | Integration |
| AC2.6 | Failure | shared_with_class=False gets None | P2 | Integration |
| AC2.7 | Edge | Loose workspace: only explicit ACL, no enrollment derivation | P2 | Integration |
| AC2.8 | Edge | Course-placed workspace: no peer discovery | P2 | Integration |

## AC3: Annotation Comments

| ID | Type | Criterion | Phase | Test Type |
|----|------|-----------|-------|-----------|
| AC3.1 | Success | User can add flat reply to any highlight | P3 | Unit |
| AC3.2 | Success | Multiple replies shown chronologically | P3 | Unit |
| AC3.3 | Success | Comment stores user_id, author, text, timestamp | P3 | Unit |
| AC3.4 | Success | Comment creator can delete own comment | P3 | Unit |
| AC3.5 | Success | Workspace owner can delete any comment | P3 | Unit |
| AC3.6 | Failure | Viewer cannot add comments | P4 | UAT |
| AC3.7 | Edge | Existing highlights without user_id display 'Unknown' | P3 | Unit |

## AC4: Anonymity Control

| ID | Type | Criterion | Phase | Test Type |
|----|------|-----------|-------|-----------|
| AC4.1 | Success | anonymous_sharing=True hides names from peer viewers | P1, P6 | Integration + UAT |
| AC4.2 | Success | anonymous_sharing=None inherits course default | P1 | Integration |
| AC4.3 | Success | Instructor always sees true author | P3, P7 | Unit |
| AC4.4 | Success | Owner viewing own workspace sees true author names | P3 | Unit |
| AC4.5 | Success | Peer sees own as real, others anonymised | P3, P7 | Unit |
| AC4.6 | Success | Deterministic adjective-animal labels per user_id | P3 | Unit |
| AC4.7 | Success | PDF export respects anonymity flag | P7 | Unit + UAT |
| AC4.8 | Success | Instructor PDF export shows true names | P7 | Unit |
| AC4.9 | Edge | Broadcast cursor/selection labels anonymised for peer viewers | P7 | Unit + UAT |

## AC5: Workspace Titles

| ID | Type | Criterion | Phase | Test Type |
|----|------|-----------|-------|-----------|
| AC5.1 | Success | Workspace has optional title field (VARCHAR 200, nullable) | P1 | Integration |
| AC5.2 | Success | Title displayed in workspace header, peer list, instructor roster | P6 | UAT |
| AC5.3 | Edge | Workspace without title displays fallback ('Untitled Workspace') | P6 | UAT |

## AC6: Instructor View Page

| ID | Type | Criterion | Phase | Test Type |
|----|------|-----------|-------|-----------|
| AC6.1 | Success | Staff-enrolled user can access workspace roster page | P6 | UAT |
| AC6.2 | Success | Roster lists workspaces with stats (PARTIAL: highlight count omitted) | P6 | Integration + UAT |
| AC6.3 | Success | Activity-level stats: N started / M enrolled | P6 | UAT |
| AC6.4 | Success | Click-through to annotation page | P6 | UAT |
| AC6.5 | Failure | Non-staff user cannot access instructor view | P6 | UAT |
| AC6.6 | Edge | Empty state with enrolled count | P6 | UAT |

## AC7: Sharing UX

| ID | Type | Criterion | Phase | Test Type |
|----|------|-----------|-------|-----------|
| AC7.1 | Success | Instructor can toggle allow_sharing per activity (tri-state) | P5 | UAT |
| AC7.2 | Success | Instructor can toggle anonymous_sharing per activity (tri-state) | P5 | UAT |
| AC7.3 | Success | Instructor can set course defaults for both | P5 | UAT |
| AC7.4 | Success | Owner sees 'Share with class' toggle when activity allows sharing | P5 | UAT |
| AC7.5 | Success | Owner can toggle shared_with_class on and off | P5 | Integration + UAT |
| AC7.6 | Success | Owner can share loose workspace via grant_share | P5 | UAT |
| AC7.7 | Failure | Share toggle hidden when activity disallows sharing | P5 | UAT |
| AC7.8 | Failure | Non-owner cannot see sharing controls | P5 | UAT |

## AC8: Permission-Aware Rendering

| ID | Type | Criterion | Phase | Test Type |
|----|------|-----------|-------|-----------|
| AC8.1 | Success | Viewer sees read-only UI | P4 | UAT |
| AC8.2 | Success | Peer sees annotate UI without upload | P4 | UAT |
| AC8.3 | Success | Editor sees full UI with upload | P4 | UAT |
| AC8.4 | Success | Owner sees full UI + ACL management | P4 | UAT |
| AC8.5 | Edge | Permission threaded via PageState.effective_permission | P4 | Unit |

## Test File Inventory

| File | Phase | Contents |
|------|-------|----------|
| `tests/integration/test_anonymous_sharing_resolution.py` | P1 | PlacementContext tri-state resolution for anonymous_sharing |
| `tests/integration/test_permission_resolution.py` (extend) | P2 | Student peer access path, highest-wins, own-workspace |
| `tests/integration/test_peer_discovery.py` | P2 | `list_peer_workspaces` query results |
| `tests/unit/test_comment_crud.py` | P3 | Comment add/delete, ownership guard |
| `tests/unit/test_anonymise.py` | P3 | `anonymise_author` and `anonymise_display_name` pure functions |
| `tests/unit/test_pdf_anonymise.py` | P7 | `_anonymise_highlights` pre-processing |
| `tests/unit/test_broadcast_anonymise.py` | P7 | Per-recipient broadcast anonymisation |
| `tests/integration/test_instructor_roster.py` | P6 | `list_activity_workspaces_with_stats` query |
