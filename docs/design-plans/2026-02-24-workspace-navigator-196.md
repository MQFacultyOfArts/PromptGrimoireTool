# Workspace Navigator Design

**GitHub Issue:** #196, #192, #187

## Summary

The Workspace Navigator replaces the current home page with a structured, searchable dashboard that gives every user — student or instructor — a single place to find all their work. The page is organised into four sections rendered as one scrollable list: work the user owns, activities they have not yet started, workspaces explicitly shared with them by a peer or instructor, and workspaces shared across each enrolled unit. The sections are role-aware: instructors see real student names and all student workspaces (paginated); students see anonymised peer names and only workspaces peers have chosen to share.

Search is layered. From the first keystroke, client-side JavaScript filters what is already on screen — no server round-trip. When the query reaches three characters, a debounced PostgreSQL full-text search runs against document content and surfaces matches the title filter would have missed, with a highlighted snippet explaining why each result matched. Supporting infrastructure includes a generated `tsvector` column on the document table (with a GIN index) built from HTML-stripped content, and a single consolidated data-loader query that fetches everything the page needs in one pass. New interaction patterns introduced here — inline workspace rename and cursor-based pagination for the instructor roster — have no existing precedent in the codebase and are documented as new conventions.

## Definition of Done

The home page (`/`) serves as the primary way students and instructors find, resume, and discover work across all activity types (annotation, roleplay, future LLM playground).

1. **Navigator page** at `/` (replaces current index page) — a prominent search box followed by four sections as a single scrollable list: My Work, Unstarted Work, Shared With Me, and Shared in [Unit] (per enrolled unit). Every published activity from every enrolled unit appears.
2. **Search** — client-side title/metadata filter from character 1, PostgreSQL FTS on document content from character 3 with debounce. FTS results show `ts_headline` snippets explaining why a result matched.
3. **Workspace titles** — pencil icon for inline rename on the navigator. New workspaces default to the activity name. Title click navigates to the workspace (not rename).
4. **Navigation chrome** — home icon on the annotation tab bar (and other pages) to return to navigator. No global header bar imposed on pages that don't want one. Navigator itself has a minimal top line (identity, logout).
5. **i18n: "Unit" not "Course"** — UI labels display "Unit" throughout the application (MQ terminology). Implemented as a configurable label, defaulting to "Unit."
6. **Instructor view** — same navigator, different data. "Shared in [Unit]" shows all student workspaces grouped by student (real names), with cursor pagination (50 students at a time). Students with no workspaces listed at bottom. Student view of the same section uses anonymised names and filters to shared-only workspaces.
7. **Loose workspaces** (course-placed, no activity) appear under "Unsorted" within each student grouping.
8. **Group work support** — workspaces shared via explicit ACL (editor/viewer) appear under "Shared With Me," visually distinct from peer-broadcast class workspaces.

**Out of scope:**
- Formal workspace tagging system (title conventions + search suffice)
- Faceted search (search + hierarchy grouping is sufficient for MVP)
- LLM playground integration (future — navigator design accommodates it)
- Standalone instructor roster page (instructors use navigator with role-appropriate views)
- Home icon UX details on annotation page (separate design concern)

## Acceptance Criteria

### workspace-navigator-196.AC1: Navigator page renders all sections
- **workspace-navigator-196.AC1.1 Success:** Student sees "My Work" with all owned workspaces grouped by unit > week > activity
- **workspace-navigator-196.AC1.2 Success:** Student sees "Unstarted Work" with all published activities they haven't started
- **workspace-navigator-196.AC1.3 Success:** Student sees "Shared With Me" with workspaces shared via explicit ACL (editor/viewer)
- **workspace-navigator-196.AC1.4 Success:** Student sees "Shared in [Unit]" per enrolled unit, with peer workspaces grouped by anonymised student
- **workspace-navigator-196.AC1.5 Success:** Instructor sees "Shared in [Unit]" with all student workspaces grouped by real student name
- **workspace-navigator-196.AC1.6 Success:** Loose workspaces (no activity) appear under "Unsorted" within each student grouping
- **workspace-navigator-196.AC1.7 Edge:** Empty sections (no shared workspaces, no unstarted work) are hidden, not rendered empty
- **workspace-navigator-196.AC1.8 Edge:** Student enrolled in multiple units sees separate "Shared in [Unit]" section per unit

### workspace-navigator-196.AC2: Workspace navigation
- **workspace-navigator-196.AC2.1 Success:** Clicking workspace title navigates to `/annotation?workspace_id=<uuid>`
- **workspace-navigator-196.AC2.2 Success:** Clicking action button (Resume/Open/View) navigates to workspace
- **workspace-navigator-196.AC2.3 Success:** Clicking [Start] on unstarted activity clones template and navigates to new workspace
- **workspace-navigator-196.AC2.4 Success:** Each workspace entry shows last edit date (`updated_at`)
- **workspace-navigator-196.AC2.5 Failure:** Unauthenticated user redirected to login, not shown navigator

### workspace-navigator-196.AC3: Search
- **workspace-navigator-196.AC3.1 Success:** Typing filters visible workspaces by title, unit code, and activity name instantly (client-side)
- **workspace-navigator-196.AC3.2 Success:** At >=3 characters, FTS fires (with debounce) and surfaces content matches with `ts_headline` snippet
- **workspace-navigator-196.AC3.4 Success:** FTS results that weren't visible from title match show a content snippet explaining the match
- **workspace-navigator-196.AC3.5 Edge:** Clearing search restores full unfiltered list
- **workspace-navigator-196.AC3.6 Edge:** Search with no results shows "No workspaces match" with clear option

### workspace-navigator-196.AC4: Inline title rename
- **workspace-navigator-196.AC4.1 Success:** Pencil icon next to workspace title activates inline edit
- **workspace-navigator-196.AC4.2 Success:** Enter or blur saves the new title
- **workspace-navigator-196.AC4.3 Success:** Escape cancels edit without saving
- **workspace-navigator-196.AC4.4 Success:** New workspaces created via [Start] default title to activity name
- **workspace-navigator-196.AC4.5 Failure:** Clicking pencil does not navigate to workspace (only title click navigates)

### workspace-navigator-196.AC5: Cursor pagination
- **workspace-navigator-196.AC5.1 Success:** Initial load shows first 50 rows across all sections
- **workspace-navigator-196.AC5.2 Success:** "Load more" fetches next 50 rows, appended into correct sections
- **workspace-navigator-196.AC5.3 Success:** Students with no workspaces (instructor view) appear at end of their unit section
- **workspace-navigator-196.AC5.4 Edge:** Total rows fewer than 50 — loads all in one page, no "Load more"
- **workspace-navigator-196.AC5.5 Edge:** Works correctly with 1100+ students in a single unit

### workspace-navigator-196.AC6: Navigation chrome
- **workspace-navigator-196.AC6.1 Success:** Home icon on annotation tab bar navigates to `/`
- **workspace-navigator-196.AC6.2 Success:** Home icon on roleplay and courses pages navigates to `/`
- **workspace-navigator-196.AC6.3 Failure:** No global header bar imposed on annotation page (preserves existing layout)

### workspace-navigator-196.AC7: i18n terminology
- **workspace-navigator-196.AC7.1 Success:** All user-facing text displays "Unit" not "Course"
- **workspace-navigator-196.AC7.2 Success:** Label is configurable via pydantic-settings, defaults to "Unit"

### workspace-navigator-196.AC8: FTS infrastructure
- **workspace-navigator-196.AC8.1 Success:** `workspace_document` table has generated `tsvector` column with GIN index
- **workspace-navigator-196.AC8.2 Success:** HTML tags stripped from indexed content (not indexed as words)
- **workspace-navigator-196.AC8.3 Success:** `ts_headline` returns snippet with matched terms highlighted
- **workspace-navigator-196.AC8.4 Edge:** Short queries (<3 chars) do not trigger FTS
- **workspace-navigator-196.AC8.5 Edge:** Empty document content produces valid (empty) tsvector, no errors

## Glossary

- **ACL (Access Control List)**: A per-resource list of users and their permission levels (owner, editor, viewer). Used here to represent workspaces shared directly with a specific person, as opposed to workspaces broadcast to a whole class.
- **Alembic**: The database migration tool used by the project. The only permitted way to create or modify database tables.
- **anonymise_author()**: A project function that replaces a student's real name with a consistent pseudonym in contexts where identity should be hidden.
- **clone_workspace_from_activity**: An existing project function that copies an activity's template workspace into a new workspace owned by the requesting user.
- **CTE (Common Table Expression)**: A named subquery within a SQL `WITH` clause. Used to structure complex multi-join queries into readable, composable steps.
- **cursor pagination / keyset pagination**: A database pagination strategy that uses an ordered column value (e.g., the last-seen student name) as a bookmark, rather than `OFFSET`.
- **debounce**: A technique that delays executing a function until a quiet period has elapsed after the last triggering event. Used here so FTS is not fired on every keystroke.
- **FTS (Full-Text Search)**: PostgreSQL's built-in engine for linguistic search against document content. Supports stemming, ranking, and snippet generation.
- **GIN index (Generalised Inverted Index)**: A PostgreSQL index type optimised for composite values such as `tsvector`. Required for performant full-text search queries.
- **NiceGUI**: The Python web UI framework used by the project. Pages are Python functions decorated with a route; UI elements are created by calling `ui.*` methods.
- **page_route**: The project's decorator that registers a NiceGUI page function with the application router, attaching metadata such as route, title, and authentication requirements.
- **pydantic-settings**: The configuration library used by the project. Reads environment variables and `.env` files into typed Python models.
- **Quasar**: The Vue-based component framework that NiceGUI renders to. Responsible for responsive layout behaviour.
- **ts_headline**: A PostgreSQL function that returns a short excerpt from a document with query-matching terms wrapped in highlight tags.
- **to_tsquery / to_tsvector**: PostgreSQL functions that convert a search string or document text into a normalised lexeme representation for full-text matching.
- **tsvector**: A PostgreSQL data type that stores a pre-processed, lexeme-indexed representation of text. Stored as a generated column so it is automatically maintained when source content changes.
- **ui.refreshable**: A NiceGUI decorator that marks a component function as re-renderable in-place without a full page reload.
- **Unit**: The MQ (Macquarie University) term for what the codebase calls a "Course." The navigator introduces a configurable label so this terminology can be used in the UI.

## Architecture

The navigator is a single NiceGUI page at `/` that loads all workspace data for the authenticated user and renders it as a searchable, sectioned list. Search has two tiers: instant client-side filtering and server-side PostgreSQL FTS.

### Components

**Navigator page** (`src/promptgrimoire/pages/navigator.py`): The page function, registered via `@page_route`. Calls a single data-loading function, renders the four sections, wires up search.

**Navigator data loader** (`src/promptgrimoire/db/navigator.py`): A single UNION ALL query returning all rows across all four sections, ordered by section priority then sort key (last edit descending). Cursor-paginated: LIMIT 50 per page, keyset cursor on `(section, sort_key)` for subsequent pages. WHERE clauses handle permission filtering per section (owned workspaces, enrolled activities, ACL entries, peer/instructor visibility). The page groups received rows into section headers as they render. FTS is a separate query, fired by user interaction.

**FTS infrastructure**: A generated `tsvector` column on `WorkspaceDocument` with a GIN index. HTML content stripped via `regexp_replace` in the column expression. Search query uses `to_tsquery` with `ts_headline` for snippet generation.

**Home icon on annotation** (`src/promptgrimoire/pages/annotation/workspace.py`): A small home icon added to the left edge of the existing tab bar. Single `ui.navigate.to("/")` on click.

### Data flow

```
Login → / (navigator)
         ├── Search box (client-side filter from char 1, FTS from char 3)
         ├── My Work (owner workspaces with activity context)
         ├── Unstarted Work (enrolled activities minus started)
         ├── Shared With Me (editor/viewer ACL entries)
         └── Shared in [Unit] (peer workspaces OR instructor roster)
                └── Cursor-paginated, 50 students per page

Click workspace → /annotation?workspace_id=<uuid>
Click [Start]   → clone template → /annotation?workspace_id=<uuid>
Home icon        → / (navigator)
```

### Search architecture

| Tier | Trigger | Mechanism | Latency |
|------|---------|-----------|---------|
| Client-side filter | Every keystroke | JavaScript hides non-matching DOM elements by title, unit code, activity name, student name | <1ms |
| Server-side FTS | >=3 chars + 500ms debounce | `SELECT workspace_id, ts_headline(...) FROM workspace_document WHERE search_vector @@ to_tsquery(...)` | ~50-200ms |

FTS results that weren't visible from the client-side filter reappear with a content snippet underneath, explaining the match.

### Instructor vs student view

Same page component. The data layer returns different rows based on role:

| Section | Student sees | Instructor sees |
|---------|-------------|----------------|
| My Work | Own workspaces | Own workspaces (templates, demos) |
| Unstarted Work | Unpublished activities not yet started | Likely empty (instructors don't "start" activities) |
| Shared With Me | Workspaces shared via ACL | Student workspaces shared with them |
| Shared in [Unit] | Anonymised peer workspaces (shared only) | All student workspaces grouped by student name, cursor-paginated |

Anonymisation handled by existing `anonymise_author()`. Visibility filtering handled by permission resolution in the data loader query.

## Existing Patterns

**Page layout** (`src/promptgrimoire/pages/layout.py`): A `page_layout` context manager provides header + drawer + content area. Currently only used by the index page. The navigator does NOT use `page_layout` — it has its own minimal layout (search-focused, no drawer). Other pages (courses, annotation) already build their own layouts.

**Page registry** (`src/promptgrimoire/pages/registry.py`): `@page_route` decorator registers pages with metadata (route, title, icon, category, auth requirements). Navigator registers at `/` with `category="main"`, `order=10` (highest priority).

**Workspace queries** (`src/promptgrimoire/db/acl.py`): Existing functions — `list_accessible_workspaces`, `list_peer_workspaces_with_owners`, `list_activity_workspaces` — demonstrate the JOIN patterns needed. The navigator data loader consolidates these into a single query.

**Courses page hierarchy** (`src/promptgrimoire/pages/courses.py`): Pre-loads enrolled courses → weeks → activities in `course_detail_page`. The navigator does the same but across ALL enrolled units, not one at a time. The `_build_peer_map` pattern (lines 75-111) shows how to pre-process peer workspace data with anonymisation.

**Inline title editing**: No existing pattern in the codebase. New pattern introduced here: `ui.input` that appears on pencil-icon click, saves on blur/Enter, cancels on Escape.

**Cursor pagination**: No existing pattern. New pattern: keyset cursor on compound key `(section, sort_key)` with LIMIT 50. "Load more" trigger at the bottom of the rendered list fetches the next page and appends rows into the correct section containers.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: FTS Infrastructure

**Goal:** Add full-text search capability to workspace documents.

**Components:**
- Alembic migration adding a generated `tsvector` column (`search_vector`) to `workspace_document` with GIN index. Column expression: `to_tsvector('english', regexp_replace(content, '<[^>]+>', ' ', 'g'))`.
- `WorkspaceDocument` model update in `src/promptgrimoire/db/models.py` to include the `search_vector` column.
- FTS query helper in `src/promptgrimoire/db/search.py` — accepts a search string, returns matching workspace IDs with `ts_headline` snippets.

**Dependencies:** None (first phase).

**Done when:** FTS query returns workspace IDs and snippets for content matches. Tests verify indexing, querying, HTML stripping, and empty/short query handling.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Navigator Data Loader

**Goal:** A single entry point that returns all data the navigator page needs.

**Components:**
- `src/promptgrimoire/db/navigator.py` — async function `load_navigator_page(user_id, is_privileged, cursor=None, limit=50)` returning a flat list of rows ordered by section then sort key. Each row carries a section tag (my_work, unstarted, shared_with_me, shared_in_unit) plus the unit/week/activity/workspace/display-name context needed for rendering. Single UNION ALL query with keyset cursor pagination.

**Dependencies:** Phase 1 (FTS infrastructure, for content search integration).

**Done when:** Data loader returns correct, complete results for student and instructor roles. Tests cover all four sections, permission filtering, anonymisation, and pagination.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Navigator Page (Core)

**Goal:** The navigator renders at `/` with four sections and basic interaction.

**Components:**
- `src/promptgrimoire/pages/navigator.py` — page function registered via `@page_route` at `/`, replaces current index page in `src/promptgrimoire/pages/index.py`.
- Page layout: minimal top line (app name, user email, logout), prominent search input, four sections with section headers, workspace cards showing title + unit/week/activity breadcrumb + last edit date + action button (Resume/Start/Open/View).
- Title click and action button both navigate to workspace.
- "Start" button clones activity template (reuses existing `clone_workspace_from_activity`).

**Dependencies:** Phase 2 (data loader).

**Done when:** Navigator renders all four sections with correct data. Clicking workspace titles and action buttons navigates correctly. Starting an activity clones and navigates.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Search

**Goal:** Two-tier search — client-side instant filter and server-side FTS.

**Components:**
- Client-side JavaScript filter: on every keystroke, hides workspace cards whose title/unit/activity/student name doesn't match. Injected via `ui.add_body_html` or inline `ui.run_javascript`.
- Server-side FTS trigger: fires at >=3 characters with 500ms debounce. Calls FTS query helper from Phase 1. Results that weren't visible from client-side filter reappear with a `ts_headline` snippet rendered below the workspace title.
- Search input placeholder: "Search titles and content..."

**Dependencies:** Phase 1 (FTS query helper), Phase 3 (navigator page to wire into).

**Done when:** Client-side filter responds instantly to typing. FTS fires after 3 chars + debounce and surfaces content matches with snippets. Search across all sections works. Empty results show "No workspaces match" with clear-filter option.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Inline Title Rename

**Goal:** Students can rename workspace titles from the navigator.

**Components:**
- Pencil icon next to each workspace title in the navigator. Click activates an inline `ui.input` pre-filled with current title.
- Save on blur or Enter, cancel on Escape. Writes to `Workspace.title` via existing workspace update path.
- New workspaces created via "Start" default their title to the activity name.

**Dependencies:** Phase 3 (navigator page rendering workspace cards).

**Done when:** Pencil icon activates inline edit. Blur/Enter saves. Escape cancels. Default title on new workspaces matches activity name. Title persists across page reload.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Cursor Pagination

**Goal:** Navigator loads incrementally via keyset cursor on the unified query.

**Components:**
- Initial page load fetches first 50 rows from `load_navigator_page`. Scroll or "Load more" trigger fetches next page using the cursor returned from the previous page.
- Page appends new rows into the correct section containers as they arrive (NiceGUI dynamic rendering via `@ui.refreshable` or container append).
- Students with no workspaces (instructor view) appear at the end of the "Shared in [Unit]" section after all workspace-bearing students.

**Dependencies:** Phase 2 (data loader with cursor support), Phase 3 (navigator page).

**Done when:** Initial load shows first 50 rows. Loading more appends next batch into correct sections. Works for both students and instructors. Handles 1100+ student units without degradation.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Navigation Chrome & i18n

**Goal:** Home icon on annotation and "Unit" terminology throughout.

**Components:**
- Home icon added to annotation tab bar in `src/promptgrimoire/pages/annotation/workspace.py` — left edge before existing tabs, `ui.navigate.to("/")` on click.
- Same pattern for roleplay page (`src/promptgrimoire/pages/roleplay.py`) and courses page.
- i18n label: configurable "unit"/"course" string in `src/promptgrimoire/config.py` (pydantic-settings), defaulting to "Unit". Used in navigator section headers, courses page, and anywhere "Course" currently appears in UI text.

**Dependencies:** Phase 3 (navigator exists to navigate back to).

**Done when:** Home icon visible on annotation, roleplay, and courses pages. Clicking returns to navigator. All user-facing text says "Unit" not "Course". Label is configurable via settings.
<!-- END_PHASE_7 -->

## Additional Considerations

**Mobile responsiveness:** NiceGUI uses Quasar which is responsive by default. The single-column scrollable list works naturally on mobile. The search box should be full-width. No special mobile layout needed for MVP.

**Empty states:** "My Work" empty → "No workspaces yet. Start an activity from the list below." "Shared With Me" empty → section hidden entirely. "Shared in [Unit]" empty → section hidden. Only sections with content render.

**Performance at scale:** 1100 students × multiple activities could produce a large dataset. The cursor pagination (Phase 6) handles the UI side. The database query should use indexes on `course_enrollment.user_id`, `workspace.activity_id`, `workspace.shared_with_class`, and the new `search_vector` GIN index.

**Future accommodation:** The four-section layout accommodates new workspace types (LLM playground, roleplay sessions) without structural changes — they appear in "My Work" like any other workspace, distinguished by activity type or a type badge.

**MVP priority ordering:** Phases 2, 3, 7 (data loader, core page, chrome/i18n) are MVP-critical — students need to find and open their work. Phases 1, 4, 5, 6 (FTS, search, rename, pagination) are high-value but can ship incrementally after launch if time is tight.

**Client-side filter + NiceGUI re-render:** When FTS results arrive and the page adds new DOM elements, client-side JS filter state must be re-applied. The annotation page works around similar issues with `ui.add_body_html` for script injection. Implementation should account for this interaction.

**FTS HTML stripping limitation:** The `regexp_replace` approach strips tags but does not decode HTML entities (`&amp;`, `&nbsp;`). These will be indexed as literal strings. Acceptable for MVP search quality — content from the input pipeline is well-formed HTML from selectolax, not arbitrary user input.
