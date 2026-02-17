# Annotation Module Split — Phase 4: Anti-Clobber Documentation Updates

**Goal:** Update project documentation so future sessions and implementation plans reference the package structure, not the monolith.

**Architecture:** Update CLAUDE.md project structure, align annotation-perf.md Phase 1 with actual module names, file follow-up issue for paste handler JS extraction.

**Tech Stack:** Markdown, GitHub CLI

**Scope:** 4 phases from original design (phase 4 of 4)

**Codebase verified:** 2026-02-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 120-annotation-split.AC5: Documentation updated
- **120-annotation-split.AC5.1 Success:** `CLAUDE.md` project structure section lists the annotation package modules
- **120-annotation-split.AC5.2 Success:** `annotation-perf.md` Phase 1 references actual module names and post-CSS-Highlight-API functions
- **120-annotation-split.AC5.3 Success:** Follow-up issue filed for paste handler JS extraction

---

<!-- START_TASK_1 -->
### Task 1: Update CLAUDE.md project structure

**Verifies:** 120-annotation-split.AC5.1

**Files:**
- Modify: `CLAUDE.md` (line 193 — project structure section, and line 462 — copy protection reference)

**Implementation:**

**Change 1: Project structure section (line 193).**

Replace the single `annotation.py` entry in the `pages/` section:

```
│   ├── annotation.py    # Main annotation page (CSS Highlight API rendering)
```

With the package directory listing:

```
│   ├── annotation/      # Main annotation page (CSS Highlight API rendering)
│   │   ├── __init__.py  # Core types (PageState, _RemotePresence), route
│   │   ├── broadcast.py # Multi-client sync, remote presence
│   │   ├── cards.py     # Annotation card UI
│   │   ├── content_form.py # Content paste/upload form
│   │   ├── css.py       # CSS constants, tag toolbar
│   │   ├── document.py  # Document rendering, selection wiring
│   │   ├── highlights.py # Highlight CRUD, JSON, push-to-client
│   │   ├── organise.py  # Tab 2 — organise highlights by tag
│   │   ├── pdf_export.py # PDF export orchestration
│   │   ├── respond.py   # Tab 3 — respond with references
│   │   ├── tags.py      # Tag abstractions (TagInfo)
│   │   └── workspace.py # Workspace view, header, copy protection
```

Also remove the satellite module entries if they appear separately (they shouldn't after Phase 3, but verify).

**Change 2: Copy protection reference (line 462).**

Replace:
```
- **JS injection** (`_inject_copy_protection()` in `annotation.py`):
```

With:
```
- **JS injection** (`_inject_copy_protection()` in `annotation/workspace.py`):
```

**Change 3: Static assets section.**

Update the `static/` listing to include the two new JS files from Phase 1:

```
├── static/              # Static assets (JS, CSS)
│   ├── annotation-highlight.js # Text walker, highlight rendering, remote presence
│   ├── annotation-card-sync.js # Scroll-sync card positioning
│   └── annotation-copy-protection.js # Copy/cut/drag/print blocking
```

**Pre-check: Enumerate all `annotation.py` references in CLAUDE.md.**

Before making changes, run `grep -n "annotation\.py" CLAUDE.md` to find all references. As of codebase verification date, there are exactly 2:
- Line 193: project structure tree entry
- Line 462: copy protection JS injection reference

If additional references have appeared since, update them too.

**Verification:**

```bash
# Verify no stale annotation.py references remain in CLAUDE.md
grep "annotation\.py" CLAUDE.md
# Expected: No matches (or only in historical context like git log examples)
```

**Commit:** `docs: update CLAUDE.md project structure for annotation package`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update annotation-perf.md Phase 1

**Verifies:** 120-annotation-split.AC5.2

**Files:**
- Modify: `docs/design-plans/2026-02-10-annotation-perf-142.md` (lines 44–47 for AC4, lines 125–142 for Phase 1 module list)

**Implementation:**

**Change 1: Update AC4 status (lines 44–47).**

The annotation-perf.md AC4 criteria are:
```
### annotation-perf.AC4: Module split
- **annotation-perf.AC4.1 Success:** annotation.py replaced by pages/annotation/ package with focused modules
- **annotation-perf.AC4.2 Success:** All existing tests pass without modification (except import paths if needed)
- **annotation-perf.AC4.3 Success:** No logic changes — pure mechanical move
```

Add a note marking this as addressed:

```
> **Addressed by:** Issue #120 (annotation-split). See `docs/design-plans/2026-02-14-annotation-split-120.md`.
```

**Change 2: Update Phase 1 module list (lines 125–142).**

The current Phase 1 lists 7 modules (`tabs.py`, `setup.py` which don't exist in the actual design). Replace with the actual 9-module + 3-satellite structure:

```
- `src/promptgrimoire/pages/annotation/__init__.py` — Core types (PageState, _RemotePresence), globals, route entry point
- `src/promptgrimoire/pages/annotation/broadcast.py` — Multi-client sync, remote presence, Yjs update relay
- `src/promptgrimoire/pages/annotation/cards.py` — Annotation card UI (build, expand, comments, refresh)
- `src/promptgrimoire/pages/annotation/content_form.py` — Content paste/upload form with platform detection
- `src/promptgrimoire/pages/annotation/css.py` — CSS constants (_PAGE_CSS), tag toolbar, highlight pseudo-CSS
- `src/promptgrimoire/pages/annotation/document.py` — Document rendering with CSS Highlight API, selection handlers
- `src/promptgrimoire/pages/annotation/highlights.py` — Highlight CRUD, JSON serialisation, push-to-client, warp
- `src/promptgrimoire/pages/annotation/organise.py` — Tab 2: organise highlights by tag (drag-and-drop columns)
- `src/promptgrimoire/pages/annotation/pdf_export.py` — PDF export orchestration with loading notification
- `src/promptgrimoire/pages/annotation/respond.py` — Tab 3: respond with reference panel and CRDT markdown
- `src/promptgrimoire/pages/annotation/tags.py` — Tag abstractions (TagInfo, brief_tags_to_tag_info)
- `src/promptgrimoire/pages/annotation/workspace.py` — Workspace view orchestrator, header, placement, copy protection
```

Update any function name references to reflect post-CSS-Highlight-API names (e.g., `_render_document_with_highlights()` instead of older names if they differ). Check the actual functions in the codebase at time of implementation.

**Verification:**

Visual inspection — the module list should match the actual package contents.

**Commit:** `docs: update annotation-perf.md Phase 1 for actual module structure`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: File GitHub issue for paste handler JS extraction

**Verifies:** 120-annotation-split.AC5.3

**Files:** None (GitHub CLI only)

**Implementation:**

File a GitHub issue for the deferred paste handler JS extraction. The 472-line paste event handler in `content_form.py` is the largest remaining embedded JS block.

```bash
gh issue create \
  --title "refactor: extract paste handler JS from content_form.py to static file" \
  --body "$(cat <<'EOF'
## Summary

The 472-line paste event handler in `pages/annotation/content_form.py` (inside `_render_add_content_form()`) is the largest remaining embedded JS block after the annotation module split (#120).

## Why deferred

Extracting it requires restructuring from a closure-based `<script>` tag to a parameterised function. This changes runtime behaviour and requires careful platform-specific testing across 6 chatbot exports.

## Context

- Part of the annotation module split (#120) — JS extraction phase
- `annotation-card-sync.js` and `annotation-copy-protection.js` were extracted in #120
- This paste handler was explicitly deferred because it is tightly coupled to NiceGUI element IDs
- See design plan: `docs/design-plans/2026-02-14-annotation-split-120.md` (Additional Considerations)

## Acceptance Criteria

- [ ] Paste handler JS extracted to `static/annotation-paste-handler.js`
- [ ] Function exposes parameterised entry point (element IDs passed from Python)
- [ ] All 6 chatbot export formats tested (paste detection works for each)
- [ ] No `_PASTE_HANDLER_JS` string constant in Python code
EOF
)"
```

**Verification:**

```bash
# Verify issue was created
gh issue list --search "paste handler JS" --limit 1
```

**Commit:** No commit for this task (GitHub issue only).
<!-- END_TASK_3 -->
