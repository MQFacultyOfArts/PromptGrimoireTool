# Idle Tab Eviction Implementation Plan

**Goal:** Update user-facing and operator documentation to reflect idle eviction behaviour and /welcome landing page

**Architecture:** Infrastructure phase — update `.env.example` with `IDLE__` vars, `docs/configuration.md` with config reference, `using_promptgrimoire.py` with student-facing guide entry, and `CLAUDE.md` with developer reference. Verify with `uv run grimoire docs build`.

**Tech Stack:** pandoc, mkdocs (already in use)

**Scope:** 7 phases from original design (phases 1-7, Phase 5 replaced)

**Codebase verified:** 2026-04-03

---

## Acceptance Criteria Coverage

This phase is infrastructure — no ACs verified by tests.

**Verifies: None** (documentation phase, verified operationally by `docs build` success)

---

<!-- START_TASK_1 -->
### Task 1: Add IDLE__ env vars to .env.example

**Files:**
- Modify: `.env.example` (add `IDLE__` section after `ADMISSION__` section, around line 179)

**Implementation:**

Add a new section following the existing `ADMISSION__` pattern:

```
# ── Idle tab eviction ──────────────────────────────────────────
# Automatically pause inactive browser tabs to free server memory.
# Paused students can resume from /paused with priority re-entry.

# Enable/disable idle tab eviction (default: true)
# Set to false to disable without a code deploy.
# IDLE__ENABLED=true

# Seconds of inactivity before a tab is evicted (default: 1800 = 30 minutes)
# IDLE__TIMEOUT_SECONDS=1800

# Seconds of warning countdown before eviction (default: 60)
# IDLE__WARNING_SECONDS=60
```

**Verification:**

Run: `grep -A5 "IDLE__" .env.example`
Expected: Shows all three vars with defaults

**Commit:** `docs(config): add IDLE__ env vars to .env.example`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update docs/configuration.md

**Files:**
- Modify: `docs/configuration.md` (add `IDLE__` config group description)

**Implementation:**

Add a section describing the idle eviction config group, following the existing format in the file. Include the three env vars with types, defaults, and descriptions.

**Verification:**

Read the file and verify the section appears correctly.

**Commit:** `docs(config): add idle eviction to configuration reference`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update using_promptgrimoire.py guide

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` (add guide entry for idle timeout and /welcome)

**Implementation:**

Add a guide step explaining session timeout behaviour for students:
- What happens when you're idle for 30 minutes (warning modal appears)
- How to stay active (click "Stay Active" or interact with the page)
- What happens if evicted (navigate to /paused, click Resume, no work lost)
- Mention /welcome as the recommended bookmark for returning to PromptGrimoire

Follow the existing Guide DSL pattern: `with guide.step("question", level=3) as g:` + `g.note()`.

**Verification:**

Run: `uv run grimoire docs build`
Expected: Docs build succeeds, generated guide contains the new section

**Commit:** `docs: add idle eviction and /welcome to student guide`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update CLAUDE.md with idle eviction reference

**Files:**
- Modify: `CLAUDE.md` (add idle eviction section, update project structure for new files)

**Implementation:**

Add an "Idle Tab Eviction" section to CLAUDE.md (near the Admission Gate section) documenting:
- Architecture: client-side idle tracking, `/paused` landing page, `/welcome` pre-auth page
- Config: `IDLE__` prefix with key vars
- Key files: `idle-tracker.js`, `/paused` handler, `/welcome` handler
- Relationship to admission gate (priority re-entry for evicted users)

Update the project structure section to include new files:
- `src/promptgrimoire/static/idle-tracker.js`

Verify the design plan at `docs/design-plans/2026-04-03-idle-tab-eviction-471.md` already has AC6 marked as DROPPED and AC7 added (done during implementation planning).

**Verification:**

Read CLAUDE.md and verify the new section is accurate.

**Commit:** `docs: add idle eviction to CLAUDE.md developer reference`
<!-- END_TASK_4 -->
