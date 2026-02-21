# Annotation Tag Configuration Design

**GitHub Issue:** #95

## WIP Status (2026-02-20)

**Branch:** `95-annotation-tags` (pushed)
**Current phase:** 5d — Refactor (next up)

### Completed
- **Phases 1–4:** DB models, migration, CRUD, CRDT cleanup, reorder/import, workspace cloning, annotation page integration (BriefTag fully replaced)
- **Phase 5a–5b:** Integration tests, code review fixes
- **Phase 5c:** UAT passed (all 11 confirm items + 4 boundary probes). Bugs found and fixed during UAT:
  - Tag button truncation: Quasar inner elements needed `!important` CSS targeting `.q-btn__content`
  - Tag descriptions added to toolbar tooltips (bold name + description via `q-tooltip` + `ui.html`)
  - Ungrouped tag baseline alignment (invisible group wrapper)
  - Highlight menu: grouped abbreviated tag buttons, JS positioning via `charOffsetToRect`, rebuild on tag changes
  - Keyboard shortcuts: filtered from INPUT/TEXTAREA/SELECT targets
  - Input validation: `maxlength=100` on name fields, unique name generation for new tags, IntegrityError catch
  - **Save-on-blur refactor:** replaced batch-save-on-Done with per-field save-on-blur (text on blur, colour on change, group on update). Extracted `_save_single_tag()` and `_save_single_group()` standalone functions. Done button now just closes + refreshes.
  - `bypass_lock` parameter added to `update_tag`/`delete_tag` for instructor operations

### Remaining
- **Phase 5d:** Refactor
- **Phase 6a–d:** Activity Settings + Course Defaults (AC8)
- **Final (#25):** Project context update, final review, test analysis

### Key files for Phase 5
- `src/promptgrimoire/pages/annotation/tag_management.py` — management dialog (save-on-blur)
- `src/promptgrimoire/pages/annotation/document.py` — highlight menu with grouped tags
- `src/promptgrimoire/pages/annotation/css.py` — tag toolbar + highlight CSS + truncation
- `src/promptgrimoire/pages/annotation/tags.py` — TagInfo with description field
- `src/promptgrimoire/db/tags.py` — tag CRUD with bypass_lock
- `src/promptgrimoire/static/annotation-highlight.js` — menu positioning
- `tests/integration/test_tags_*.py` — integration tests

---

## Summary

This design adds configurable, workspace-scoped annotation tags to replace the hardcoded `BriefTag` enum. Instructors create tag sets (organized into visual groups) within activity templates, which are then cloned into student workspaces when activities are claimed. Students annotate documents by applying these tags to text selections, creating highlights stored in the CRDT as tag UUID references. The design supports instructor control over whether students can create their own tags via a tri-state permission inherited from course defaults.

Implementation spans six phases: creating the `TagGroup` and `Tag` database tables with permission columns, building CRUD operations with lock enforcement, extending workspace cloning to propagate tags and remap CRDT references, replacing `BriefTag` throughout the annotation page with DB-backed dynamic tags, adding tag management UI (quick-create dialog and full management dialog) to the annotation toolbar, and wiring tag creation permissions into activity/course settings dialogs. Tags are stored per-workspace (snapshot semantics) rather than shared globally, ensuring student workspaces remain independent after cloning. The locked flag allows instructors to protect specific tags from student modification while still permitting their use for annotation.

## Definition of Done

1. **Tag data model** — `TagGroup` (visual container, per-workspace) and `Tag` (per-workspace copy) tables. Boolean `locked` field on Tag controls editability. Replaces the `BriefTag` StrEnum, `TAG_COLORS`, and `TAG_SHORTCUTS`.
2. **Workspace tag editing permission** — `allow_tag_creation` tri-state on Activity (with Course default) controls whether students can create new tags and groups.
3. **Tag CRUD** — Create, read, update, delete, reorder for tags and groups. Locked tags cannot be modified or deleted by students.
4. **Workspace cloning propagates tags** — Cloning duplicates TagGroup and Tag rows into the student workspace (snapshot). CRDT highlights remapped to new Tag UUIDs.
5. **Student tag creation** — Students can create tags and groups when `allow_tag_creation` resolves to True.
6. **Course-level tag convenience** — "Import tags from..." copies tags from another activity's template into the current workspace.
7. **Annotation integration** — Tag loading reads from DB instead of `BriefTag`. CRDT highlights reference Tag UUIDs. Annotation UI (toolbar, cards, organise, respond, PDF export) works with dynamic tags. No untagged state — every highlight requires a tag.
8. **Tag/group ordering** — Reorder tags within groups and groups within workspaces via management dialog.
9. **Tag deletion** — Deleting a tag deletes associated highlights (with confirmation showing count). Group deletion ungroups its tags.
10. **Tag management UX** — Quick tag creation (+ button) and full tag management dialog (gear button) in the annotation page toolbar. Tag buttons truncate with ellipsis and tooltip; toolbar wraps to two rows.

## Acceptance Criteria

### 95-annotation-tags.AC1: Data model and migration
- **95-annotation-tags.AC1.1 Success:** TagGroup table exists with workspace_id FK (CASCADE), name, order_index, created_at
- **95-annotation-tags.AC1.2 Success:** Tag table exists with workspace_id FK (CASCADE), group_id FK (SET NULL), name, description, color, locked, order_index, created_at
- **95-annotation-tags.AC1.3 Success:** Seed data: one "Legal Case Brief" TagGroup and 10 Tags with colorblind-accessible palette exist after migration
- **95-annotation-tags.AC1.4 Success:** Activity has `allow_tag_creation` nullable boolean; Course has `default_allow_tag_creation` boolean (default TRUE)
- **95-annotation-tags.AC1.5 Success:** PlacementContext resolves `allow_tag_creation` via tri-state inheritance (Activity explicit → Course default)
- **95-annotation-tags.AC1.6 Failure:** Deleting a Workspace CASCADEs to its TagGroup and Tag rows
- **95-annotation-tags.AC1.7 Failure:** Deleting a TagGroup sets `group_id=NULL` on its Tags (SET NULL), does not delete Tags

### 95-annotation-tags.AC2: Tag CRUD
- **95-annotation-tags.AC2.1 Success:** Create tag with name, color, optional group_id, optional description
- **95-annotation-tags.AC2.2 Success:** Update tag name, color, description, group_id
- **95-annotation-tags.AC2.3 Success:** Delete tag removes the Tag row and all CRDT highlights referencing its UUID
- **95-annotation-tags.AC2.4 Success:** Create and update TagGroup (name, order_index)
- **95-annotation-tags.AC2.5 Success:** Delete TagGroup ungroups its tags (SET NULL)
- **95-annotation-tags.AC2.6 Success:** Reorder tags within a group (update order_index)
- **95-annotation-tags.AC2.7 Success:** Reorder groups within a workspace (update order_index)
- **95-annotation-tags.AC2.8 Failure:** Update or delete a tag with `locked=True` is rejected
- **95-annotation-tags.AC2.9 Failure:** Create tag on workspace where `allow_tag_creation` resolves to False is rejected

### 95-annotation-tags.AC3: Import tags from another activity
- **95-annotation-tags.AC3.1 Success:** Import copies TagGroup and Tag rows from source activity's template workspace into target workspace
- **95-annotation-tags.AC3.2 Success:** Imported tags get new UUIDs (independent copies)
- **95-annotation-tags.AC3.3 Success:** Imported tags preserve name, color, description, locked, group assignment, order

### 95-annotation-tags.AC4: Workspace cloning propagates tags
- **95-annotation-tags.AC4.1 Success:** Cloning creates independent copies of all TagGroups in the student workspace
- **95-annotation-tags.AC4.2 Success:** Cloning creates independent copies of all Tags with group_id remapped to new TagGroup UUIDs
- **95-annotation-tags.AC4.3 Success:** CRDT highlights in cloned workspace reference the new Tag UUIDs (not template UUIDs)
- **95-annotation-tags.AC4.4 Success:** CRDT tag_order in cloned workspace uses new Tag UUIDs as keys
- **95-annotation-tags.AC4.5 Success:** Locked flag is preserved on cloned tags
- **95-annotation-tags.AC4.6 Edge:** Template with no tags clones cleanly (empty tag set)

### 95-annotation-tags.AC5: Annotation page integration
- **95-annotation-tags.AC5.1 Success:** Tag toolbar renders from DB-backed tag list, not BriefTag enum
- **95-annotation-tags.AC5.2 Success:** Keyboard shortcuts 1-0 map positionally to the first 10 tags in order
- **95-annotation-tags.AC5.3 Success:** Highlight cards display color from DB-backed tag data
- **95-annotation-tags.AC5.4 Success:** Tag dropdown on highlight cards lists all workspace tags
- **95-annotation-tags.AC5.5 Success:** Organise tab renders one column per tag (no untagged column)
- **95-annotation-tags.AC5.6 Success:** Respond tab renders tag-grouped highlights from DB-backed tags
- **95-annotation-tags.AC5.7 Success:** PDF export uses tag colors from DB
- **95-annotation-tags.AC5.8 Success:** Creating a highlight requires selecting a tag (no untagged highlights)
- **95-annotation-tags.AC5.9 Success:** Tag buttons truncate with ellipsis; full name shown on hover tooltip
- **95-annotation-tags.AC5.10 Success:** Tag toolbar wraps to two rows when needed (no horizontal scroll)
- **95-annotation-tags.AC5.11 Success:** `BriefTag`, `TAG_COLORS`, `TAG_SHORTCUTS` are deleted from codebase

### 95-annotation-tags.AC6: Tag management UX — quick create
- **95-annotation-tags.AC6.1 Success:** "+" button on toolbar opens quick-create dialog with name, color picker, optional group
- **95-annotation-tags.AC6.2 Success:** Creating a tag via quick-create applies it to the current text selection
- **95-annotation-tags.AC6.3 Failure:** "+" button is hidden when `allow_tag_creation` resolves to False

### 95-annotation-tags.AC7: Tag management UX — full dialog
- **95-annotation-tags.AC7.1 Success:** Gear button opens management dialog showing tags grouped by TagGroup
- **95-annotation-tags.AC7.2 Success:** Tags can be renamed, recolored, and given descriptions inline
- **95-annotation-tags.AC7.3 Success:** Tags can be moved between groups or ungrouped
- **95-annotation-tags.AC7.4 Success:** Tags and groups can be reordered via drag
- **95-annotation-tags.AC7.5 Success:** Tag deletion shows highlight count and requires confirmation
- **95-annotation-tags.AC7.6 Success:** Group deletion moves tags to ungrouped (no highlight loss)
- **95-annotation-tags.AC7.7 Success:** "Import tags from..." dropdown lists activities in course (instructor on template only)
- **95-annotation-tags.AC7.8 Success:** Lock toggle available for instructors on template workspaces
- **95-annotation-tags.AC7.9 Failure:** Locked tags show lock icon; edit/delete controls disabled for students

### 95-annotation-tags.AC8: Activity settings + course defaults
- **95-annotation-tags.AC8.1 Success:** Activity settings dialog shows `allow_tag_creation` tri-state select
- **95-annotation-tags.AC8.2 Success:** Course settings dialog shows `default_allow_tag_creation` switch
- **95-annotation-tags.AC8.3 Success:** Activity `allow_tag_creation=NULL` inherits Course default
- **95-annotation-tags.AC8.4 Success:** Activity `allow_tag_creation=TRUE` overrides Course default FALSE
- **95-annotation-tags.AC8.5 Success:** Activity `allow_tag_creation=FALSE` overrides Course default TRUE

## Glossary

- **CRDT (Conflict-Free Replicated Data Type)**: Data structure that allows multiple users to edit the same document concurrently and automatically merge changes without conflicts. Used here to store annotation highlights in a JSON document (`AnnotationDocument`).
- **Workspace**: Container for a student's or instructor's work on an activity. Each workspace has its own copy of documents, highlights, and (after this design) tags.
- **Activity template**: The instructor-created original version of an activity. When students "claim" an activity, the template workspace is cloned into a student workspace.
- **Workspace cloning**: Process of copying a template workspace into a new student workspace, including documents, CRDT state, and (after this design) tags with UUID remapping.
- **Tri-state permission**: Configuration pattern where an activity can explicitly set a permission to True/False, or leave it NULL to inherit from the parent course's default.
- **CASCADE/SET NULL**: SQL foreign key constraints. CASCADE deletes child rows when parent is deleted; SET NULL sets the FK to NULL instead of deleting the child.
- **SQLModel**: Python library combining Pydantic (data validation) and SQLAlchemy (ORM) for database models with type hints.
- **Alembic**: Database migration tool for SQLAlchemy. Changes to the schema must go through Alembic migrations, not direct table creation.
- **UUID remapping**: When cloning, replacing old UUIDs (template workspace's tag IDs) with new UUIDs (student workspace's tag IDs) in CRDT highlight data.
- **Colorblind-accessible palette**: Set of colors chosen to be distinguishable by users with color vision deficiencies.
- **FK (Foreign Key)**: Database constraint linking one table's column to another table's primary key, enforcing referential integrity.

## Architecture

### Data Model

Two new tables, two modified tables.

**`TagGroup`** — visual container, per-workspace. Groups are presentation-level organisation with no editability semantics.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK → Workspace (CASCADE), NOT NULL |
| `name` | VARCHAR(100) | NOT NULL |
| `order_index` | INTEGER | NOT NULL, default 0 |
| `created_at` | TIMESTAMPTZ | NOT NULL |

CASCADE on workspace — groups are workspace-local. A group is a labelled box drawn around a cluster of tags. Tags may exist outside any group.

**`Tag`** — per-workspace copy. Each workspace has its own independent Tag rows.

| Column | Type | Constraint |
|--------|------|------------|
| `id` | UUID | PK |
| `workspace_id` | UUID | FK → Workspace (CASCADE), NOT NULL |
| `group_id` | UUID | FK → TagGroup (SET NULL), nullable |
| `name` | VARCHAR(100) | NOT NULL |
| `description` | TEXT | nullable |
| `color` | VARCHAR(7) | NOT NULL |
| `locked` | BOOLEAN | NOT NULL, default FALSE |
| `order_index` | INTEGER | NOT NULL, default 0 |
| `created_at` | TIMESTAMPTZ | NOT NULL |

CASCADE on workspace. SET NULL on group deletion — tag survives, becomes ungrouped. `locked=True` means students cannot rename, recolor, regroup, or delete this tag. Locked does NOT prevent using the tag to annotate.

**Modified: `Activity`** — adds `allow_tag_creation: BOOLEAN NULL` (tri-state: NULL=inherit from course, TRUE=allowed, FALSE=not allowed). Same pattern as `copy_protection` and `allow_sharing`.

**Modified: `Course`** — adds `default_allow_tag_creation: BOOLEAN NOT NULL DEFAULT TRUE`.

**Seed data:** One TagGroup ("Legal Case Brief") and 10 Tag rows using the existing colorblind-accessible palette from `TAG_COLORS`. Available via "Import tags from..." on any workspace.

### CRDT Integration

CRDT highlights currently store `tag` as a `BriefTag.value` string (e.g. `"jurisdiction"`). After: Tag UUID string (e.g. `"550e8400-..."`). UUIDs are globally unique (no collision between groups), stable across renames and recolors.

- `highlight["tag"]`: BriefTag value → Tag UUID string. Required — no untagged state.
- `tag_order` keys: BriefTag value strings → Tag UUID strings.
- No structural change to `AnnotationDocument` — still string-keyed maps. Just different strings.

The annotation page resolves UUID → display info (name, color) from a DB query at workspace load.

### Tag Management UX

Tag management lives in the annotation page. Two entry points:

**Quick tag creation** — "+" button at the end of the tag toolbar. Small dialog: name, color picker (preset colorblind-accessible palette), optional group dropdown. Creates the tag and applies it to the current selection. Only visible when `allow_tag_creation` is True.

**Full management dialog** — gear icon button at the end of the tag toolbar. Larger dialog with:
- Tag list grouped by TagGroup, plus an "Ungrouped" section for `group_id=NULL` tags
- Per tag: inline-editable name, color swatch, description (expandable), lock icon (disabled for students)
- Per group: name, drag handle for reordering, collapsible
- Actions: create tag, create group, assign tag to group, delete tag (with highlight count confirmation), delete group (tags become ungrouped)
- Import tags from...: dropdown listing other activities in the course (instructor only, on template workspaces). Copies TagGroup + Tag rows from the selected activity's template.
- Instructors on template workspaces can toggle the lock on individual tags

**Tag toolbar changes:** Builds from `list[TagInfo]` loaded from DB. Tags displayed in `order_index` order, grouped by TagGroup (subtle visual divider between groups). Keyboard shortcuts 1-0 assigned positionally to the first 10 tags. Tag buttons have `max-width` with `text-overflow: ellipsis` and `.tooltip()` for full name. Toolbar wraps to two rows when needed, no horizontal scroll.

**Activity settings:** The existing `tune` dialog gains `allow_tag_creation` as a tri-state `ui.select` (Inherit from course / Allowed / Not allowed) alongside `copy_protection` and `allow_sharing`. Course settings dialog gains `default_allow_tag_creation` as a `ui.switch`.

### Workspace Cloning

When a student clones from an activity template, `clone_workspace_from_activity()` gains tag cloning:

1. Query TagGroup rows for the template workspace → create copies with new UUIDs, `workspace_id` = student workspace. Build `group_id_map: dict[UUID, UUID]`.
2. Query Tag rows for the template workspace → create copies with new UUIDs, `workspace_id` = student workspace, `group_id` remapped via `group_id_map`. Build `tag_id_map: dict[UUID, UUID]`.
3. In `_replay_crdt_state()`: remap `highlight["tag"]` via `tag_id_map` (same pattern as existing `document_id` remapping). Rebuild `tag_order` with remapped keys (fix: currently `tag_order` is not cloned at all).

All within the existing atomic session.

### Editability Enforcement

| Action | `locked=True` | `locked=False` | `allow_tag_creation=False` | `allow_tag_creation=True` |
|--------|--------------|----------------|---------------------------|--------------------------|
| Annotate with tag | Yes | Yes | Yes | Yes |
| Rename/recolor tag | No | Yes | Yes (unlocked) | Yes |
| Delete tag | No | Yes | Yes (unlocked) | Yes |
| Move tag between groups | No | Yes | Yes | Yes |
| Create new tag | — | — | No | Yes |
| Create new group | — | — | No | Yes |

Tag deletion deletes all highlights using that tag. Confirmation dialog shows the count. Group deletion sets `group_id=NULL` on member tags — no highlight impact.

## Existing Patterns

### Tri-State Activity Settings (`db/models.py`, `pages/courses.py`)

`allow_tag_creation` follows the exact pattern of `copy_protection` and `allow_sharing`:
- `Activity.allow_tag_creation: bool | None` with `Course.default_allow_tag_creation: bool`
- Resolved in `PlacementContext` using `_resolve_activity_placement()`
- UI: `ui.select` with `_model_to_ui()` / `_ui_to_model()` pure functions in `pages/courses.py`
- Course settings: `ui.switch` in `open_course_settings()`

### TagInfo Abstraction (`pages/annotation/tags.py`)

The three-tab-ui design introduced `TagInfo` as a deliberate seam point. `organise.py` and `respond.py` already import `TagInfo` only (never `BriefTag`). The mapper function `brief_tags_to_tag_info()` is the single replacement point — it becomes a DB query returning the same `TagInfo` interface.

### Workspace Cloning ID Remapping (`db/workspaces.py`)

`_replay_crdt_state()` already remaps `document_id` using `doc_id_map: dict[str, str]`. Tag UUID remapping follows the identical pattern — iterate highlights, swap old UUID for new UUID via the map.

### Reference Data as Seed in Migration (`db/models.py`, Alembic)

The ACL design (Seam D) seeds `Permission` and `CourseRole` reference tables in the migration. The Legal Case Brief tags follow the same pattern — seed data in the migration, not in `seed-data` script.

### Activity Settings Dialog (`pages/courses.py`)

`open_activity_settings()` is a modal dialog triggered by a `tune` icon button on the activity row. Adding `allow_tag_creation` extends this with one more `ui.select` — same component, same tri-state mapping.

### New Pattern: Per-Workspace DB Entities

TagGroup and Tag are the first entities scoped to a workspace via FK (beyond WorkspaceDocument). This establishes a pattern for future workspace-local structured data. CASCADE on workspace deletion ensures cleanup.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Data Model + Migration

**Goal:** Create TagGroup and Tag tables, add tag creation policy columns, seed the Legal Case Brief tag set.

**Components:**
- `TagGroup` SQLModel class in `db/models.py`
- `Tag` SQLModel class in `db/models.py`
- `Activity.allow_tag_creation` and `Course.default_allow_tag_creation` columns in `db/models.py`
- `PlacementContext.allow_tag_creation` resolution in `db/workspaces.py`
- Alembic migration creating tables with seed data

**Dependencies:** None (first phase)

**Done when:** Migration runs cleanly, seed data present (1 TagGroup + 10 Tags for Legal Case Brief), models importable, PlacementContext resolves `allow_tag_creation`. Covers 95-annotation-tags.AC1.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Tag CRUD

**Goal:** Database operations for tag and group management.

**Components:**
- `db/tags.py` — create/read/update/delete for TagGroup and Tag, reorder functions, import-from-activity, locked enforcement
- Tag deletion cascades to CRDT highlights (queries workspace CRDT state, removes matching highlights, persists)

**Dependencies:** Phase 1 (tables must exist)

**Done when:** All CRUD operations work, locked tags reject modification, import-from-activity copies tags between workspaces, tag deletion removes associated highlights. Covers 95-annotation-tags.AC2, AC3.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Workspace Cloning

**Goal:** Propagate tags through workspace cloning with CRDT remapping.

**Components:**
- Extended `clone_workspace_from_activity()` in `db/workspaces.py` — clones TagGroup and Tag rows, builds `group_id_map` and `tag_id_map`
- Extended `_replay_crdt_state()` in `db/workspaces.py` — remaps `highlight["tag"]` via `tag_id_map`, rebuilds `tag_order` with remapped keys

**Dependencies:** Phase 2 (tag CRUD for creating cloned rows)

**Done when:** Cloning an activity template produces a student workspace with independent copies of all tags and groups, CRDT highlights reference the new Tag UUIDs, tag_order is populated. Covers 95-annotation-tags.AC4.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Annotation Page Integration

**Goal:** Replace `BriefTag` throughout the annotation page with DB-backed dynamic tags.

**Components:**
- `pages/annotation/tags.py` — `workspace_tags(workspace_id) -> list[TagInfo]` DB query replaces `brief_tags_to_tag_info()`. `TagInfo.raw_key` becomes UUID string.
- `pages/annotation/__init__.py` — `PageState.tag_info_list` populated from DB at workspace load
- `pages/annotation/css.py` — `_build_tag_toolbar()` takes `list[TagInfo]`, positional keyboard shortcuts, CSS class names from UUIDs, tag button truncation with `max-width` + `text-overflow: ellipsis` + `.tooltip()`, toolbar wraps (no scroll)
- `pages/annotation/document.py` — `handle_tag_click` takes UUID, keyboard handler uses positional lookup
- `pages/annotation/highlights.py` — `_add_highlight()` requires tag (UUID string), no default fallback
- `pages/annotation/cards.py` — color lookup and tag dropdown from `tag_info_list`
- `pages/annotation/organise.py` — remove untagged column, tag columns from DB-backed list
- `pages/annotation/pdf_export.py` — `tag_colours` dict from DB query
- Delete `BriefTag`, `TAG_COLORS`, `TAG_SHORTCUTS` from `models/case.py` and `models/__init__.py`

**Dependencies:** Phase 1 (Tag model), Phase 2 (read query)

**Done when:** Annotation page loads tags from DB, highlights store Tag UUIDs in CRDT, toolbar/cards/organise/respond/export all work with dynamic tags, `BriefTag` is deleted. Covers 95-annotation-tags.AC5.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Tag Management UX

**Goal:** UI for creating, editing, and organising tags within the annotation page.

**Components:**
- `pages/annotation/tag_management.py` — quick-create dialog (+ button) and full management dialog (gear button)
- Quick-create: name field, preset color picker, optional group dropdown, creates tag + applies to selection
- Full management: grouped tag list, inline editing (name, color, description), group CRUD, reorder (drag), delete with highlight count confirmation, import-from-activity dropdown (instructor only)
- Lock toggle (instructor only on template workspaces)
- Visibility gated by `PlacementContext.allow_tag_creation` for creation controls

**Dependencies:** Phase 2 (CRUD functions), Phase 4 (annotation page integration)

**Done when:** Students can create/edit/delete tags and groups (when permitted), instructors can lock tags and import from other activities, tag management is accessible from the annotation toolbar. Covers 95-annotation-tags.AC6, AC7.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Activity Settings + Course Defaults

**Goal:** Wire `allow_tag_creation` into the activity/course settings UI.

**Components:**
- `pages/courses.py` — `open_activity_settings()` gains `allow_tag_creation` tri-state `ui.select` with `_model_to_ui()` / `_ui_to_model()`
- `pages/courses.py` — `open_course_settings()` gains `default_allow_tag_creation` `ui.switch`
- `db/activities.py` — `create_activity()` and `update_activity()` accept `allow_tag_creation` parameter

**Dependencies:** Phase 1 (columns exist)

**Done when:** Instructors can set tag creation policy per-activity and per-course, tri-state inheritance works correctly. Covers 95-annotation-tags.AC8.
<!-- END_PHASE_6 -->

## Additional Considerations

**Keyboard shortcuts with >10 tags:** Only the first 10 tags get shortcuts (1-9, 0). Tags beyond 10 are toolbar-click only. This matches the current behaviour limit.

**Colorblind accessibility:** The preset color palette for the quick-create dialog reuses the existing colorblind-tested palette from `TAG_COLORS`. Students choosing custom colours are responsible for their own accessibility.

**Tag ordering persistence:** Reorder operations update `order_index` in the DB immediately (no CRDT involvement). The annotation page reads tag order from DB at load time.

**Future: live-link tags.** The current design uses snapshot (per-workspace copy) semantics. If a future requirement needs instructor tag changes to propagate to existing student workspaces, this could be layered on by adding a `source_tag_id` FK on Tag pointing to the template's original. The current design does not preclude this.
