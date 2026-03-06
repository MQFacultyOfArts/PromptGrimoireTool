# Tag Lifecycle Refactor -- Test Requirements

**Design:** `docs/design-plans/2026-03-06-tag-lifecycle-235-291.md`
**Issues:** #235, #291

This document maps every acceptance criterion from the design to automated tests or documented human verification. Each entry includes the AC identifier, full AC text, test type, expected test file path, implementing phase, and a description of what the test verifies.

---

## AC1: Tag metadata in DB and CRDT

### tag-lifecycle-235-291.AC1.1

**AC text:** Creating a tag writes metadata to both DB `tag` table and CRDT `tags` Map with matching fields.

| Attribute | Value |
|-----------|-------|
| Test type | unit + integration |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Phase | Phase 1 (CRDT write), Phase 2 (dual write) |
| Description | **Unit:** `set_tag()` stores all fields correctly; `get_tag()` retrieves them with matching values. Verifies CRDT structure in isolation. **Integration:** `create_tag(ws_id, name, color, crdt_doc=doc)` -- assert both DB row exists AND `doc.get_tag(tag.id)` returns matching name, colour, order_index, group_id, description, and empty highlights list. |

---

### tag-lifecycle-235-291.AC1.2

**AC text:** Updating a tag's name/colour/description in the management dialog updates both DB and CRDT.

| Attribute | Value |
|-----------|-------|
| Test type | unit + integration |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Phase | Phase 1 (CRDT update), Phase 2 (dual write) |
| Description | **Unit:** Calling `set_tag()` again with the same ID and different name/colour/description overwrites correctly. **Integration:** Create tag with `crdt_doc`, then `update_tag(tag_id, name="New", crdt_doc=doc)` -- verify CRDT entry has new name and existing highlights list is preserved. Also test update without `crdt_doc` (DB-only, no crash). |

---

### tag-lifecycle-235-291.AC1.3

**AC text:** Deleting a tag removes it from both DB and CRDT, including its highlights list.

| Attribute | Value |
|-----------|-------|
| Test type | unit + integration |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Phase | Phase 1 (CRDT delete), Phase 2 (dual write) |
| Description | **Unit:** `delete_tag()` removes the tag; subsequent `get_tag()` returns None. Delete on non-existent ID does not raise. **Integration:** Create tag with crdt_doc, add highlights, then `delete_tag(tag_id, crdt_doc=doc)` -- verify tag removed from CRDT `tags` Map, highlights removed, `tag_order` entry removed, and DB row deleted. |

---

### tag-lifecycle-235-291.AC1.4

**AC text:** Creating/updating/deleting a tag group writes to both DB and CRDT.

| Attribute | Value |
|-----------|-------|
| Test type | unit + integration |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Phase | Phase 1 (CRDT group methods), Phase 2 (dual write) |
| Description | **Unit:** `set_tag_group()` stores name/colour/order_index; `get_tag_group()` retrieves them; `delete_tag_group()` removes the entry; operations on non-existent groups don't raise; CRDT sync between two docs works. **Integration:** `create_tag_group(ws_id, name, crdt_doc=doc)` -- verify both DB row and CRDT entry. `update_tag_group(group_id, name="New", crdt_doc=doc)` -- verify CRDT entry updated. `delete_tag_group(group_id, crdt_doc=doc)` -- verify removed from both. Edge: operations without `crdt_doc` update DB only, no crash. |

---

### tag-lifecycle-235-291.AC1.5

**AC text:** On workspace load, if CRDT maps are empty but DB has tags, CRDT is hydrated from DB.

| Attribute | Value |
|-----------|-------|
| Test type | unit + integration |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Phase | Phase 1 (hydration method), Phase 3 (consistency check integration) |
| Description | **Unit:** Call `hydrate_tags_from_db()` on an empty doc with tag/group data -- verify all entries populated with correct values. Empty lists produce no errors. **Integration:** Create workspace with tags in DB, create AnnotationDocument with NO tag data in CRDT state, call `_ensure_crdt_tag_consistency()` -- verify CRDT maps now populated with correct data matching DB. |

---

### tag-lifecycle-235-291.AC1.6

**AC text:** On workspace load, if DB has a tag the CRDT doesn't, CRDT is reconciled (tag added).

| Attribute | Value |
|-----------|-------|
| Test type | unit + integration |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Phase | Phase 1 (hydration overwrites), Phase 3 (reconciliation) |
| Description | **Unit:** Call `hydrate_tags_from_db()` on a doc that already has a tag with a stale name -- verify name is overwritten with DB value (DB wins). **Integration:** Create workspace with tags in DB, create CRDT with most tags but missing one -- verify `_ensure_crdt_tag_consistency()` adds the missing tag. Also test: CRDT has tag not in DB -- tag removed from CRDT, WARNING logged. Empty DB + empty CRDT -- no changes, no errors. |

---

## AC2: Tag lifecycle sync

### tag-lifecycle-235-291.AC2.1

**AC text:** Creating a tag via quick create immediately appears on all connected clients' tag bars (no refresh).

| Attribute | Value |
|-----------|-------|
| Test type | unit + e2e |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (e2e) | `tests/e2e/test_tag_sync.py` |
| Phase | Phase 3 (CRDT-primary rendering + broadcast), Phase 4 (quick create dual write) |
| Description | **Unit:** `workspace_tags_from_crdt()` on an empty doc returns empty list; on a doc with tags/groups returns correctly ordered `TagInfo` instances. CRDT sync test: set tag on doc A, sync to doc B, call `workspace_tags_from_crdt(doc_b)` -- tag appears. **E2E:** Two browser contexts on same workspace. Client A creates tag via quick create. Client B sees tag in toolbar within seconds, no refresh. Assert via `page_b.get_by_test_id("tag-chip-<tag_name>")`. |

---

### tag-lifecycle-235-291.AC2.2

**AC text:** Creating a tag via management dialog immediately appears on all connected clients.

| Attribute | Value |
|-----------|-------|
| Test type | e2e |
| Test file | `tests/e2e/test_tag_sync.py` |
| Phase | Phase 3 (E2E test), Phase 4 (management dialog dual write) |
| Description | Covered by the same E2E test as AC2.1 (`test_tag_create_propagates_to_second_client`). The broadcast pipeline is the same regardless of creation source. If distinct test desired: Client A creates tag via management dialog, Client B sees it appear. |

---

### tag-lifecycle-235-291.AC2.3

**AC text:** Editing a tag's name updates on all connected clients' toolbars.

| Attribute | Value |
|-----------|-------|
| Test type | unit + integration |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Phase | Phase 3 (broadcast callback), Phase 4 (management dialog save) |
| Description | **Unit:** CRDT sync test -- update tag name on doc A, sync to doc B, call `workspace_tags_from_crdt(doc_b)` -- verify updated name. **Integration:** Create tag with crdt_doc, update name with crdt_doc, verify CRDT and DB both reflect the new name. The broadcast callback (`handle_update_from_other`) rebuilds `tag_info_list` from CRDT, which propagates name changes to all clients. |

---

### tag-lifecycle-235-291.AC2.4

**AC text:** Editing a tag's colour updates highlight CSS on all connected clients.

| Attribute | Value |
|-----------|-------|
| Test type | integration + e2e |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Test file (e2e) | `tests/e2e/test_tag_sync.py` |
| Phase | Phase 3 (broadcast callback), Phase 4 (colour persistence E2E) |
| Description | **Integration:** Create tag, update colour with crdt_doc, verify DB and CRDT both have new colour. **E2E:** `test_tag_colour_propagates_to_second_client` -- open two browser contexts. Client A changes tag colour. Client B's highlight CSS updates to the new colour without refresh. |

---

### tag-lifecycle-235-291.AC2.5

**AC text:** Deleting a tag removes it from all connected clients' toolbars and organise tabs.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 3 (broadcast callback), Phase 4 (management dialog delete) |
| Description | Delete tag with crdt_doc -- verify removed from both DB and CRDT. The broadcast callback rebuilds `tag_info_list` from CRDT on receiving clients, which removes the tag from toolbar rendering. |

---

### tag-lifecycle-235-291.AC2.6

**AC text:** Every newly created tag has a group assignment (never "uncategorised" unless explicitly ungrouped).

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 4 |
| Description | Create tag via quick create with no group explicitly selected -- verify the created tag has a non-None `group_id`. The UI must assign a default group (first existing group). If no groups exist, the quick create button is disabled. |

---

### tag-lifecycle-235-291.AC2.7

**AC text:** Creating a tag with a duplicate name within the same workspace is rejected.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 4 |
| Description | Call `create_tag()` twice with the same name and workspace_id -- verify IntegrityError or graceful rejection. Verify the error message is surfaced (not silently swallowed). |

---

## AC3: Unified import

### tag-lifecycle-235-291.AC3.1

**AC text:** User can import tags from a workspace they have read access to.

| Attribute | Value |
|-----------|-------|
| Test type | integration + e2e |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Test file (e2e) | `tests/e2e/test_tag_import.py` |
| Phase | Phase 6 |
| Description | **Integration:** `import_tags_from_workspace(source_ws, target_ws, user_id, crdt_doc=doc)` with user having read access to source -- verify tags created in target DB and CRDT. **E2E:** `test_student_can_import_tags` -- student logs in, opens workspace, opens tag management, selects source workspace from picker, clicks import, verifies tags appear in toolbar. |

---

### tag-lifecycle-235-291.AC3.2

**AC text:** Imported tags merge additively -- existing tags are preserved.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 6 |
| Description | Create target workspace with existing tags. Import from source. Verify existing tags in target are unchanged and new tags from source are added. |

---

### tag-lifecycle-235-291.AC3.3

**AC text:** Tags with duplicate names in the target workspace are skipped.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 6 |
| Description | Create target workspace with a tag named "Foo". Source workspace also has a tag named "Foo" (case-insensitive match). Import -- verify no new "Foo" tag created, existing one unchanged. |

---

### tag-lifecycle-235-291.AC3.4

**AC text:** Imported tag groups and ordering are preserved, appended after existing tags.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 6 |
| Description | Target has 3 existing tags (order_index 0-2). Source has 2 tags. After import, verify imported tags have order_index 3-4. Verify imported groups also have order_index values offset past existing groups. |

---

### tag-lifecycle-235-291.AC3.5

**AC text:** Imported tags default to unlocked regardless of source locked status.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 6 |
| Description | Source workspace has a tag with `locked=True`. Import to target. Verify the imported tag in target has `locked=False`. |

---

### tag-lifecycle-235-291.AC3.6

**AC text:** Import is available to all users, not just instructors.

| Attribute | Value |
|-----------|-------|
| Test type | e2e |
| Test file | `tests/e2e/test_tag_import.py` |
| Phase | Phase 6 |
| Description | `test_student_can_import_tags` -- log in as a student user (not instructor, not admin). Open workspace with write access. Open tag management dialog. Verify import section is visible (`get_by_test_id("import-workspace-select")` exists). Select source workspace, click import, verify tags appear. This catches regressions where the instructor gate is re-added. |

---

### tag-lifecycle-235-291.AC3.7

**AC text:** Importing from a workspace with no tags produces no error and no changes.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 6 |
| Description | Source workspace has zero tags and zero groups. Call `import_tags_from_workspace()`. Verify no error raised, target workspace unchanged, return value is empty list. |

---

## AC4: Tag colour persistence

### tag-lifecycle-235-291.AC4.1

**AC text:** Changing a tag's colour in the management dialog persists across page refresh.

| Attribute | Value |
|-----------|-------|
| Test type | integration + e2e |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Test file (e2e) | `tests/e2e/test_tag_sync.py` |
| Phase | Phase 4 |
| Description | **Integration:** Create tag with crdt_doc, update colour with crdt_doc, verify DB and CRDT both have new colour. **E2E:** `test_tag_colour_persists_across_refresh` -- open workspace, open tag management dialog, change tag colour, close dialog (Done button saves), refresh page, reopen dialog, verify colour persisted (not reverted). Verify highlight CSS on annotation page uses the new colour. |

---

### tag-lifecycle-235-291.AC4.2

**AC text:** Colour change propagates to all connected clients' highlight rendering.

| Attribute | Value |
|-----------|-------|
| Test type | e2e |
| Test file | `tests/e2e/test_tag_sync.py` |
| Phase | Phase 4 |
| Description | `test_tag_colour_propagates_to_second_client` -- open two browser contexts on same workspace. Client A changes tag colour via management dialog. Client B's highlight CSS updates to new colour without refresh. |

---

## AC5: Organise tab sync

### tag-lifecycle-235-291.AC5.1

**AC text:** Reordering tags in the organise tab propagates to all connected clients.

| Attribute | Value |
|-----------|-------|
| Test type | unit + integration |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Phase | Phase 5 (dual write), Phase 2 (reorder functions) |
| Description | **Unit:** `set_tag_order()` syncs highlights to `tags` Map `highlights` field. **Integration:** Reorder tags with crdt_doc -- verify CRDT entries have updated `order_index` values. The broadcast callback rebuilds tag state on receiving clients. |

---

### tag-lifecycle-235-291.AC5.2

**AC text:** Reassigning a tag to a different group propagates to all connected clients.

| Attribute | Value |
|-----------|-------|
| Test type | integration + e2e |
| Test file (integration) | `tests/integration/test_tag_crud.py` |
| Test file (e2e) | `tests/e2e/test_tag_sync.py` |
| Phase | Phase 4 (group reassignment via management dialog), Phase 5 (E2E) |
| Description | **Integration:** Update tag's group_id with crdt_doc -- verify CRDT and DB both reflect new group. **E2E:** `test_tag_group_reassignment_propagates` -- two browser contexts. Client A changes tag's group via management dialog. Client B's organise tab shows the tag in the new group without refresh. |

---

### tag-lifecycle-235-291.AC5.3

**AC text:** Dragging a highlight between tag columns updates the tag's highlight list in the CRDT.

| Attribute | Value |
|-----------|-------|
| Test type | unit + e2e |
| Test file (unit) | `tests/unit/test_annotation_doc.py` |
| Test file (e2e) | `tests/e2e/test_tag_sync.py` |
| Phase | Phase 5 |
| Description | **Unit:** `move_highlight_to_tag()` updates both `tag_order` and `tags` Map `highlights` fields. Source tag loses the highlight, target tag gains it at correct position. Edge: move when tags Map entry doesn't exist (graceful no-op for tags Map part). **E2E:** `test_highlight_drag_between_tags_persists` -- drag highlight from tag A column to tag B column in organise tab, refresh page, verify highlight is still in tag B. If SortableJS drag simulation is too complex, an integration test calling `move_highlight_to_tag()` directly is acceptable. |

---

## AC6: Existing contracts preserved

### tag-lifecycle-235-291.AC6.1

**AC text:** PDF export produces correct tag colours and names from DB data.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 8 |
| Description | Create workspace with tags and highlights. Build `tag_colours` dict from `state.tag_info_list` (CRDT source). Verify dict contains correct tag UUID to colour mappings. Pass to `generate_tag_colour_definitions(tag_colours)` -- assert returned LaTeX string contains a `\definecolor` command for each tag UUID with the correct colour value. |

---

### tag-lifecycle-235-291.AC6.2

**AC text:** FTS search worker resolves tag UUIDs to names from DB.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 8 |
| Description | Create workspace with tags and highlights. Call `extract_searchable_text(crdt_state, tag_names)` where `tag_names` is built from DB query (existing pattern). Verify tag names appear in the extracted search text. |

---

### tag-lifecycle-235-291.AC6.3

**AC text:** LaTeX preamble generates correct `\definecolor` commands from DB tag data.

| Attribute | Value |
|-----------|-------|
| Test type | integration |
| Test file | `tests/integration/test_tag_crud.py` |
| Phase | Phase 8 |
| Description | Create tags with known colours. Call `generate_tag_colour_definitions()` with the tag colour dict. Assert the LaTeX output contains `\definecolor{<tag_uuid>}{HTML}{<hex_value>}` for each tag. This is tested alongside AC6.1 as they exercise the same export pipeline seam. |

---

## Summary: Test File Inventory

| Test file | Type | Phases | ACs covered |
|-----------|------|--------|-------------|
| `tests/unit/test_annotation_doc.py` | unit | 1, 3, 5 | AC1.1-AC1.6, AC2.1, AC2.3, AC5.1, AC5.3 |
| `tests/integration/test_tag_crud.py` | integration | 2, 3, 4, 5, 6, 8 | AC1.1-AC1.6, AC2.3-AC2.7, AC3.1-AC3.5, AC3.7, AC4.1, AC5.1, AC5.2, AC6.1-AC6.3 |
| `tests/e2e/test_tag_sync.py` | e2e | 3, 4, 5 | AC2.1, AC2.2, AC2.4, AC4.1, AC4.2, AC5.2, AC5.3 |
| `tests/e2e/test_tag_import.py` | e2e | 6 | AC3.1, AC3.6 |
| `tests/integration/test_migrate_backfill.py` | integration | 7 | (infrastructure, no AC) |

## Summary: Phase-to-AC Matrix

| Phase | ACs tested |
|-------|-----------|
| Phase 1 | AC1.1 (CRDT), AC1.2 (CRDT), AC1.3 (CRDT), AC1.4 (CRDT), AC1.5 (method), AC1.6 (method) |
| Phase 2 | AC1.1, AC1.2, AC1.3, AC1.4, AC5.1 (reorder) |
| Phase 3 | AC1.5, AC1.6, AC2.1, AC2.2, AC2.3, AC2.4, AC2.5 |
| Phase 4 | AC2.1, AC2.2, AC2.3, AC2.4, AC2.5, AC2.6, AC2.7, AC4.1, AC4.2 |
| Phase 5 | AC5.1, AC5.2, AC5.3 |
| Phase 6 | AC3.1, AC3.2, AC3.3, AC3.4, AC3.5, AC3.6, AC3.7 |
| Phase 7 | (infrastructure -- migration script, no AC) |
| Phase 8 | AC6.1, AC6.2, AC6.3 |

## Human Verification Requirements

All acceptance criteria in this design are fully automatable. No manual human verification steps are required.

The E2E tests for multi-client sync (AC2.1, AC2.2, AC2.4, AC4.2, AC5.2, AC5.3) use Playwright with two browser contexts to simulate the two-client scenario. This is the standard pattern established in `docs/testing.md` and does not require manual observation.

The migration script (Phase 7) is verified by integration tests that exercise `_backfill_tags()` directly, plus an operational verification step (running the CLI command against a seeded dev database). The operational verification is part of the implementation phase's verification checklist, not a separate human-only gate.
