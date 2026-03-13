# Guide UAT Findings — 2026-03-13

Tracked during docs-infrastructure branch work (issue #230, #281).

## Critical Fixes (must fix before merge)

### 1. RTF claim in guide is false
- **File:** `using_promptgrimoire.py` `_entry_upload_document()`
- **Claim:** "Supported formats: PDF (.pdf), Word (.docx), HTML, RTF, and plain text."
- **Reality:** `input_pipeline/html_input.py` raises `NotImplementedError("Conversion from rtf not yet implemented")`
- **Fix:** Remove RTF from the supported formats list
- **Status:** DONE

### 2. Login guide ignores SSO/AAF primary flow
- **File:** `using_promptgrimoire.py` `_entry_log_in()`
- **Claim:** "Enter your university email address and click Send Magic Link."
- **Reality:** Production login page renders AAF SSO button as primary, with Google/GitHub OAuth fallbacks. Magic link is the fallback, not the primary path.
- **Fix:** Update text to mention SSO as primary, magic link as fallback. Screenshot shows mock auth (test mode) so can't show real SSO — note this limitation.
- **Status:** DONE — route fixed (`/auth/login` → `/login`), text updated, screenshot captioned as test view

### 3. Spike screenshots in docs/guides/screenshots/
- **Files:** `phase2-initial-load.png`, `phase2-check-editor.png`
- **Reality:** These are leftovers from a Milkdown editor spike — yellow warning banner, not production UI
- **Fix:** Delete these orphan files
- **Status:** DONE — confirmed absent from worktree (already deleted)

## Codex Audit Findings (2026-03-13)

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | Login route `/auth/login` → `/login` + SSO text | High | DONE |
| 2 | Tag import sources misattributed (template-only → any readable) | High | DONE |
| 3 | Deletion hierarchy partially overstated (admin force-delete) | Medium | DONE |
| 4 | Export overclaims "organised notes" | High | DONE |
| 5 | Enrolment location wrong ("in Unit Settings" → separate page) | Medium | DONE |
| 6 | Respond layout backwards (left/right swapped) | Medium | DONE |
| 7 | Sharing constraints omitted (owner-only, existing accounts) | Medium | DONE |
| 8 | "Annotate immediately" too strong (empty template caveat) | Low | DONE |

## Feature Coverage Gaps (post-fix, guide expansion)

| Feature | Issues | Status |
|---------|--------|--------|
| Bulk enrollment from XLSX | #320 | DONE — `_entry_bulk_enrolment()` |
| Word count display & enforcement | #262, #47 | DONE — `_entry_word_count()` |
| Tag import workflow (how-to) | #235 | DONE — `_entry_import_tags()` updated |
| Supported paste platforms | #209, #232, #106 | DONE — `_entry_paste_sources()` |
| Overlapping highlights | #81 | DONE — `_entry_overlapping_highlights()` |
| Peer workspace viewing | #192 | DONE — `_entry_peer_viewing()` |
| Copy protection | #103, #163, #164 | DONE — `_entry_copy_protection()` |
| PDF export filename convention | #271 | DONE — `_entry_pdf_filename()` |
| Edit/rename weeks/activities/units | #229 | DONE — `_entry_rename_entities()` |
| Locate button | personal grimoire only | DONE — `_entry_locate_button()` |
| Real-time collaboration | #20 | DONE — `_entry_collaboration()` |
| Drag-scroll on Organise tab | #128 | DONE — `_entry_drag_organise()` |
| Enrollment invitations | #70 | DONE — `_entry_enrolment_invitations()` |
| AAF/SAML SSO login | #189 | DONE — `_entry_sso_login()` |
| Roleplay / AI conversation | #32, #36, #258 | DONE — 3 entries: `_entry_start_roleplay()`, `_entry_roleplay_mechanics()`, `_entry_export_roleplay()` |
