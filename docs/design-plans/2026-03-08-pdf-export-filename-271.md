# PDF Export Filename Convention Design

**GitHub Issue:** [#271](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/271)

## Summary

PDF export currently uses the generic basename `workspace_{workspace_id}`, which is opaque for marking, Turnitin uploads, and instructor workflows. This design replaces that generic name with a deterministic filename built from workspace placement and ownership metadata: `UnitCode_LastName_FirstName_ActivityName_WorkspaceTitle_YYYYMMDD.pdf`.

The implementation keeps the policy testable and narrowly scoped. A pure filename-policy helper in the export package formats and truncates the export stem from resolved metadata, while a small database helper resolves the correct owner-facing context for a workspace export. The export button wiring in `src/promptgrimoire/pages/annotation/pdf_export.py` computes the stem before calling the existing `export_annotation_pdf(..., filename=...)` seam; no PDF compilation or download transport changes are required.

The design also closes three ambiguity gaps in the current stub. First, filenames use the workspace owner name, not the current viewer name, so instructor exports still identify the student. Second, the date segment uses the application server's local date (deployment standard: `Australia/Sydney`) rather than raw UTC rollover. Third, course-placed and loose workspaces continue to export with stable fallback labels instead of failing when activity or unit metadata is absent.

## Definition of Done

1. The PDF export filename follows the format `UnitCode_LastName_FirstName_ActivityName_WorkspaceTitle_YYYYMMDD.pdf`.
2. The full filename, including the `.pdf` extension, is limited to 100 characters except in pathological cases where the non-negotiable core segments already exceed that budget.
3. Filenames are derived from the workspace owner, not the current exporting viewer.
4. Special characters are transliterated to ASCII-safe equivalents where possible, and spaces / punctuation are normalised to underscores for Turnitin and Windows compatibility.
5. Normal overflow handling truncates `WorkspaceTitle` first and `ActivityName` second.
6. If more reduction is required after `WorkspaceTitle` and `ActivityName` are exhausted, `FirstName` is reduced to a one-character initial as a last resort.
7. `UnitCode`, `LastName`, and `YYYYMMDD` are never truncated. If that non-negotiable core still exceeds the budget, the export keeps those segments and may exceed 100 characters rather than truncating them.
8. Course-placed and loose workspaces still export successfully by using deterministic fallback labels for missing placement metadata.

**Out of scope:** schema changes for separate first-name / last-name fields, AAF / Stytch profile enrichment for authoritative surname data, changes to PDF content/layout, download-route rewrites, or Turnitin-specific API integration.

## Acceptance Criteria

### pdf-export-filename-271.AC1: Export metadata is resolved from the workspace owner and placement
- **pdf-export-filename-271.AC1.1 Success:** Activity-placed workspace export uses the workspace owner's display name, the resolved unit code, the activity title, the workspace title, and the export date.
- **pdf-export-filename-271.AC1.2 Success:** If a privileged instructor or admin exports another user's workspace, the filename still uses the owner name rather than the current viewer name.
- **pdf-export-filename-271.AC1.3 Success:** Course-placed workspaces with no activity use the course code plus the activity fallback label `Loose_Work`.
- **pdf-export-filename-271.AC1.4 Success:** Fully loose / unplaced workspaces use `Unplaced` for the unit slot and `Loose_Work` for the activity slot instead of failing export.
- **pdf-export-filename-271.AC1.5 Edge:** Blank or null workspace titles use the fallback segment `Workspace`.
- **pdf-export-filename-271.AC1.6 Edge:** Blank or missing owner display names use the fallback name `Unknown Unknown`.

### pdf-export-filename-271.AC2: Owner display names are parsed and normalised deterministically
- **pdf-export-filename-271.AC2.1 Success:** Two-token display name `Ada Lovelace` maps to `LastName=Lovelace` and `FirstName=Ada` before sanitisation and final filename assembly.
- **pdf-export-filename-271.AC2.2 Success:** Multi-token display name `Mary Jane Smith` uses the first token for `FirstName` and the last token for `LastName`; middle tokens are ignored for filename purposes.
- **pdf-export-filename-271.AC2.3 Edge:** Single-token display name `Plato` fills both name slots as `Plato_Plato` so the filename remains non-empty and deterministic without adding schema.
- **pdf-export-filename-271.AC2.4 Success:** Diacritics and non-ASCII Latin characters are transliterated, so `José Núñez` yields `Nunez_Jose`.
- **pdf-export-filename-271.AC2.5 Success:** Unsafe punctuation and path separators are replaced with underscores, repeated underscores are collapsed, and leading/trailing underscores are stripped from each segment.
- **pdf-export-filename-271.AC2.6 Edge:** Emoji and symbols with no useful transliteration are removed rather than leaked verbatim into the output filename.

### pdf-export-filename-271.AC3: Length budgeting and truncation are deterministic
- **pdf-export-filename-271.AC3.1 Success:** When the fully rendered filename is 100 characters or fewer, no truncation occurs.
- **pdf-export-filename-271.AC3.2 Success:** When the filename exceeds 100 characters, truncation is applied to `WorkspaceTitle` before any truncation is applied to `ActivityName`.
- **pdf-export-filename-271.AC3.3 Success:** `UnitCode`, `LastName`, `FirstName`, and `YYYYMMDD` are preserved during normal overflow handling.
- **pdf-export-filename-271.AC3.4 Success:** If trimming `WorkspaceTitle` to empty is still insufficient, `ActivityName` is trimmed next until the 100-character limit is met.
- **pdf-export-filename-271.AC3.5 Edge:** If trimming `WorkspaceTitle` and `ActivityName` to empty is still insufficient, `FirstName` is trimmed next until only a one-character initial remains.
- **pdf-export-filename-271.AC3.6 Edge:** `UnitCode`, `LastName`, and `YYYYMMDD` are never truncated. If the filename still exceeds 100 characters with empty `WorkspaceTitle` / `ActivityName` and a one-character `FirstName` initial, the export keeps that overlong filename rather than truncating those non-negotiable segments.
- **pdf-export-filename-271.AC3.7 Success:** The final returned filename always ends with `.pdf` and is at or under 100 characters except for the pathological overflow case in AC3.6.

### pdf-export-filename-271.AC4: Annotation-page export uses the new policy without changing the lower export seam
- **pdf-export-filename-271.AC4.1 Success:** `src/promptgrimoire/pages/annotation/pdf_export.py` computes the filename before calling `export_annotation_pdf(...)`.
- **pdf-export-filename-271.AC4.2 Success:** `src/promptgrimoire/export/pdf_export.py` continues to accept a `filename` basename and writes the `.tex` / `.pdf` using that basename without new route or header logic.
- **pdf-export-filename-271.AC4.3 Success:** Export from either the Annotate tab or the Respond tab yields the same filename for the same workspace on the same date.
- **pdf-export-filename-271.AC4.4 Failure:** Missing placement metadata does not silently fall back to `workspace_{uuid}` once this feature is implemented.

### pdf-export-filename-271.AC5: Test coverage proves the thing itself
- **pdf-export-filename-271.AC5.1 Success:** Unit tests cover parsing, transliteration, underscore normalisation, loose-work fallbacks, and truncation order as pure functions.
- **pdf-export-filename-271.AC5.2 Success:** Integration tests cover owner-vs-viewer resolution and metadata lookup for activity-placed, course-placed, and loose workspaces.
- **pdf-export-filename-271.AC5.3 Success:** A download-facing test asserts the suggested exported filename matches the policy, not merely that a PDF download occurred.
- **pdf-export-filename-271.AC5.4 Success:** Regression coverage proves the old generic `workspace_{workspace_id}` basename is no longer used in annotation-page exports.

## Glossary

- **Activity fallback label**: The deterministic placeholder `Loose Work` used when a workspace has no concrete activity title but still needs to fill the `ActivityName` slot in the filename.
- **Export metadata**: The minimal set of fields required to build the filename: unit code, activity title, workspace title, owner display name, and export date.
- **Filename policy**: The pure formatting logic that parses names, sanitises segments, applies truncation, and returns the export stem that becomes the final `.pdf` filename.
- **Loose workspace**: A workspace with no `activity_id`. It may still be course-placed (`course_id` set) or fully unplaced.
- **Owner display name**: The `User.display_name` for the workspace's ACL owner row. This is the identity that should appear in the filename, even when a different viewer triggers export.
- **Placement context**: The resolved hierarchy metadata for a workspace, currently surfaced by `PlacementContext` in `src/promptgrimoire/db/workspaces.py`, including fields such as `course_code` and `activity_title`.
- **Safe segment**: One filename component after transliteration, punctuation replacement, underscore collapse, and trimming.
- **Server-local export date**: The `YYYYMMDD` segment derived from the application server's local date. For deployed PromptGrimoire this is expected to follow `Australia/Sydney`.
- **Unit code**: The course code shown to users as a unit identifier, stored as `Course.code` in the database.

## Architecture

### Problem

Annotation-page PDF export currently hardcodes `filename=f"workspace_{workspace_id}"` in `src/promptgrimoire/pages/annotation/pdf_export.py`. That gives a technically valid filename but fails the real workflow boundary: staff cannot identify the student or activity from the downloaded file, and batch uploads to Turnitin lose all useful context.

The lower export seam is already capable of receiving a meaningful basename. `export_annotation_pdf()` in `src/promptgrimoire/export/pdf_export.py` accepts a `filename` parameter, passes it through to `generate_tex_only()`, and `compile_latex()` derives the final `.pdf` path from the `.tex` stem. The missing piece is therefore not transport or LaTeX compilation; it is deterministic filename policy plus reliable workspace metadata resolution.

### Solution

Split the feature into a functional core and an imperative shell:

1. **Functional core:** A pure helper in `src/promptgrimoire/export/filename.py` accepts already-resolved export metadata and returns a safe export stem.
2. **Imperative shell:** A narrow async helper in `src/promptgrimoire/db/workspaces.py` resolves owner + placement metadata for a workspace export, and the annotation-page export handler calls both helpers before invoking the existing PDF export seam.

This keeps filename behaviour easy to test without database or NiceGUI machinery while reusing the page layer only for orchestration.

### Proposed contracts

```python
from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class WorkspaceExportMetadata:
    course_code: str | None
    activity_title: str | None
    workspace_title: str | None
    owner_display_name: str | None


async def get_workspace_export_metadata(
    workspace_id: UUID,
) -> WorkspaceExportMetadata | None: ...


@dataclass(frozen=True)
class PdfExportFilenameContext:
    course_code: str | None
    activity_title: str | None
    workspace_title: str | None
    owner_display_name: str | None
    export_date: date


def build_pdf_export_stem(ctx: PdfExportFilenameContext) -> str: ...
```

### Filename policy

The pure builder applies these rules in order:

1. Resolve fallback values:
   - `course_code`: use resolved course code, else `Unplaced`
   - `activity_title`: use resolved activity title, else `Loose Work`
   - `workspace_title`: use workspace title, else `Workspace`
   - `owner_display_name`: use owner display name, else `Unknown Unknown`
2. Parse `owner_display_name`:
   - collapse whitespace
   - `FirstName` = first token
   - `LastName` = last token
   - if only one token exists, use it for both slots
3. Sanitise each segment independently:
   - transliterate to ASCII (design assumes `Unidecode` or an equivalent deterministic transliterator)
   - replace whitespace and punctuation with underscores
   - collapse repeated underscores
   - strip leading/trailing underscores
4. Assemble the candidate stem:
   - `UnitCode_LastName_FirstName_ActivityName_WorkspaceTitle_YYYYMMDD`
5. Apply truncation budget against the full final filename length:
   - measure length as `f"{stem}.pdf"`
   - trim `WorkspaceTitle` first
   - if still too long, trim `ActivityName`
   - if still too long, trim `FirstName` down to a one-character initial
   - preserve `UnitCode`, `LastName`, and `YYYYMMDD` even in pathological overflow cases

### Data flow

```text
workspace_id
    |
    v
get_workspace_export_metadata(workspace_id)
    |  owner ACL join + optional Activity/Week/Course resolution
    v
PdfExportFilenameContext(..., export_date=server_local_date)
    |
    v
build_pdf_export_stem(context)
    |
    v
export_annotation_pdf(..., filename=<stem>)
    |
    v
compile_latex() -> <basename>.pdf
    |
    v
ui.download(pdf_path)
```

The lower pipeline remains unchanged. The filename work happens before `export_annotation_pdf(...)`, so the implementation does not need a new response header layer or a separate download endpoint.

## Existing Patterns

Investigation found four local patterns this design should follow:

- `src/promptgrimoire/export/pdf_export.py` already exposes the correct seam: `export_annotation_pdf(..., filename=...)`. The filename feature should use that existing parameter rather than changing the PDF compiler or introducing a custom HTTP download response.
- `PlacementContext` in `src/promptgrimoire/db/workspaces.py` is the existing source for resolved unit/activity placement metadata such as `course_code` and `activity_title`. The new export-metadata helper should follow the same hierarchy model instead of re-inventing placement rules in the UI.
- Owner identity is already resolved via owner-ACL joins in `src/promptgrimoire/db/acl.py` and `src/promptgrimoire/db/navigator.py`. The filename must follow that owner-based pattern, not the current viewer session heuristic in `src/promptgrimoire/pages/annotation/workspace.py`.
- The repo already isolates pure presentation logic in small formatter modules such as `src/promptgrimoire/pages/annotation/word_count_badge.py` and `src/promptgrimoire/export/latex_render.py`. The filename builder should follow that pattern so parsing and truncation can be unit-tested without DB or NiceGUI setup.

No schema changes are required. The design deliberately works with existing `User.display_name`, `Workspace.title`, `Course.code`, and `Activity.title` fields.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Pure Filename Policy

**Goal:** Implement the filename convention as pure, deterministic logic with no DB or UI dependencies.

**Components:**
- `src/promptgrimoire/export/filename.py` -- add `PdfExportFilenameContext` plus pure helpers for name parsing, segment sanitisation, truncation, and final stem assembly
- `pyproject.toml` -- add a transliteration dependency if `Unidecode` is chosen rather than a stdlib-only fallback
- `tests/unit/export/test_filename_policy.py` -- unit tests covering name parsing, transliteration, unsafe character replacement, underscore collapse, fallback labels, and truncation order

**Dependencies:** None

**Done when:** Pure tests cover `pdf-export-filename-271.AC2.*` and `pdf-export-filename-271.AC3.*`, and the builder returns an export stem whose final `.pdf` filename respects the 100-character budget.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Workspace Export Metadata Resolution

**Goal:** Resolve the correct owner-facing metadata for any exported workspace.

**Components:**
- `src/promptgrimoire/db/workspaces.py` -- add `WorkspaceExportMetadata` and `get_workspace_export_metadata(workspace_id)` using owner ACL join plus optional Activity/Week/Course traversal
- Integration tests in `tests/integration/` -- verify metadata resolution for activity-placed, course-placed, and loose workspaces, including owner-vs-viewer behaviour

**Dependencies:** Phase 1 is independent but recommended first so metadata tests can assert against the filename-policy contract

**Done when:** Integration tests verify `pdf-export-filename-271.AC1.*` using real database rows and owner ACL data rather than session heuristics.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Annotation-Page Export Wiring

**Goal:** Replace the hardcoded `workspace_{workspace_id}` basename in the annotation export flow.

**Components:**
- `src/promptgrimoire/pages/annotation/pdf_export.py` -- resolve workspace export metadata, build the filename context with the server-local export date, and pass the computed basename into `export_annotation_pdf(...)`
- `src/promptgrimoire/export/pdf_export.py` -- keep the existing `filename` seam intact; adapt tests only if needed to assert the basename path more explicitly
- `tests/integration/test_pdf_export.py` or a focused annotation export test file -- assert the basename passed into the export seam is the policy output, not the old generic workspace identifier

**Dependencies:** Phase 1 and Phase 2

**Done when:** Annotation-page exports satisfy `pdf-export-filename-271.AC4.*` and no code path in the annotation export flow still emits `workspace_{workspace_id}`.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Download-Facing Regression Coverage

**Goal:** Prove the user-visible download filename matches the new policy at the browser boundary.

**Components:**
- `tests/e2e/annotation_helpers.py` or a focused PDF export helper -- expose download filename assertions using Playwright's download API
- `tests/e2e/test_law_student.py` or a new focused E2E file -- assert `download.suggested_filename` matches the expected export filename pattern for a real workspace export
- Optional doc touch-up in `docs/export.md` if the team wants the convention recorded in operational docs after implementation lands

**Dependencies:** Phase 3

**Done when:** Download-facing tests cover `pdf-export-filename-271.AC5.3` and demonstrate that the browser-visible filename matches policy, not just that a file was downloaded.
<!-- END_PHASE_4 -->

## Additional Considerations

**Name parsing is heuristic by design.** The current schema stores a single `display_name`, not separate first-name / last-name fields. This design intentionally avoids a schema migration and uses a deterministic first-token / last-token split because `271` needs surname-first filenames now. That is sufficient for filename generation but should not be mistaken for a culturally universal person-name model.

**Authoritative name sources are a follow-up, not part of `271`.** The longer-term fix is to source structured person-name fields from institutional identity data such as AAF attributes exposed through Stytch and persist them in a way the export pipeline can trust. That would improve surname-first accuracy without changing the rest of the filename pipeline, but it is deliberately out of scope for this feature slice.

**Server-local date is the least surprising export boundary.** The deployment docs already standardise the production host on `Australia/Sydney`. Using the server-local date avoids UTC rollover producing "tomorrow's" filename during evening teaching sessions in Australia.

**No transport rewrite needed.** `ui.download(pdf_path)` already downloads the generated file path. Because the filename is encoded in the path stem passed to `export_annotation_pdf(...)`, there is no need for a separate `Content-Disposition` endpoint to implement this feature.

**Turnitin / Windows safety applies to the whole filename.** The 100-character limit in this design is interpreted as the full final filename including `.pdf`, not just the stem. That keeps the constraint aligned with what users actually upload or save.
