# ty-bump Toolchain & Conventions Campaign — Tracker

**Goal:** Latest uv-locked toolchain (ty 0.0.72 / ruff 0.16.3 / complexipy
7.0.1), zero ty and ruff diagnostics without suppressions, every function
≤15 cognitive complexity, PLR rules enforced. Decision authority: ADRs
0004–0007. Query idiom: `tstring()` per docs/architecture/raw-sql-convention.md.

**Branch:** `ty-bump`. Everything uncommitted until final gates pass.

**Statuses:** `[x]` done+verified · `[~]` done, awaiting gate · `[ ]` pending

---

## Phases

- [x] **P1 Toolchain single-sourcing** (ADR 0006) — dev deps + `uv run`
  everywhere + local pre-commit hooks + bounded gate exceptions + hook
  rewrite ported. Verified: versions resolve, no stale pins (`rg 'uvx ty|ty@0\.0\.'`).
- [x] **P2 ruff 0.16.3 clean at old scope** — md format exclusion, RUF036
  fix. Verified: `ruff check .` at flip time.
- [x] **P3 PLR re-scope** (ADR 0007) — global ignores removed, scoped
  per-file-ignores with rationale. 203 errors exposed for burndown.
- [x] **P4 SQLAlchemy 2.1.0b3 override** (ADR 0005) — unit 4037 + integration
  931 + JS 123 + BATS green on the beta. Full `e2e all` gate still owed (P10).
- [x] **P5 Wave 1: test-file ty fixes** — 18 files, 0 diagnostics except 6
  deferred SQLModel sites (now wave-2 scope). Unit lane green post-reboot.
- [x] **P6 Wave 1: export/navigator/scripts refactors** — complexity + PLR
  in export pipeline, navigator, incident parsers. Unit+integration green.
- [~] **P7 Wave 2: db/cli tstring migration + remaining complexity**
  - [x] w2-acl-workspaces: acl.py + workspaces.py 37→0 diagnostics; 330
    integration tests green; resolve_annotation_context migrated (single
    round trip held, ≤5-query test passed; to_jsonb for scalar entities,
    w.* + model_validate for the bytea-bearing Workspace).
  - [x] w2-scripts: ingest.py 10→0; analyse_fixture/jsonl_to_md/
    profile_workspace + PLR singles; 4 new test files; 225 tests green.
  - [x] w2-annotation: four complexity monsters 28/24/18/20 → 10/0/7/2;
    respond+tags ty 11→0; long-tail PLR; 24 new unit tests; 262 tests green.
  - [x] w2-db-rest: 56→0 across 13 files; 416 tests passed (incl. 3 new for
    previously-uncovered list_students_without_workspaces); closed a latent
    update_tag(color=None) validation-bypass hole; _UNSET sentinel fixed to
    enum (object() never narrowed under ty).
  - [x] w2-cli: 24→0 diagnostics; complexity 35/32/32/27/18/16 all ≤14;
    tstring migrations with attribute-by-label rows; 26 new tests (20
    against real Postgres for previously-uncovered loadtest queries); 127
    tests + 2 live E2E smokes green. setattr monkey-patch gotcha added to
    convention doc.
- [~] **P8 Findings review** — ledger items 3, 4 (test-runner: per-lane
  partition fix + help-bypasses-lock, with new tests), 5 (wait_for overloads,
  3 casts deleted), 6 (15 dead ignores swept), 9 (both leftover diags fixed
  properly: TypedDict gained NotRequired _pending_timer; redundant cast
  removed) all FIXED. Long-tail ty singles (14) fixed. **Tree-wide ty: 0
  diagnostics.** Items 7 (NoEscape), 8/8b (coordinated migrations) remain
  open decisions. w3-plr-tail agent sweeping the final ~60 ruff PLR findings.
- [x] **P9 Final static gates** — ALL GREEN 2026-08-17: ty 0 diagnostics,
  ruff 0 errors, format clean (689 files), complexipy 0 functions over 15
  across bare src/+scripts/. Pre-commit complexipy exclude shrunk from 16
  production files to `^tests/` only. w3-plr-tail swept the final tail
  (caller-verified `*` fixes where possible, reasoned tracker-linked noqas
  for ledger-8 deferred signatures).
- [x] **P10 ADR 0005 suite gate** — `uv run grimoire e2e all`: ALL 8 LANES
  PASS on 2.1.0b3 (2026-08-17, attempt 2). Attempt 1 exposed a genuine
  order-dependent structlog-contextvars leak from broadcast.py into
  TestNullContextFields (pytest-randomly ordering); root-fixed with an
  autouse clear_contextvars fixture in tests/conftest.py, red→green
  verified deterministically with -p no:randomly. Not beta-related.
- [ ] **P11 Docs & housekeeping** — convention doc gotchas (Row attribute
  access, to_jsonb/bytea), CLAUDE.md hook-section accuracy, update
  `.notes/project_session-state-2026-08-17-ty-bump.md`, prune docs/_index.
- [x] **P12 Commits & stacking** — DONE 2026-08-17: seven-commit split
  landed, then rebased onto origin/perf/initial-snapshot-delivery @
  f1f7f177 via `--onto` (backup ref ty-bump-pre-stack-backup). (a) tags.py
  / items_serialise.py resolved to their re-export shims; the typing +
  keyword-only fixes re-derived into annotation_core.py (their relocated
  copies still carried the 5 ty errors and the positional signature —
  now 0 diagnostics, `*` after tag_colours, all call sites verified
  keyword-safe). (b) Quality pass over their modules: one PLR0917 in
  test_assessment_cram_load.py fixed keyword-only (30f86001); snapshot
  modules read via existing db helpers, so ADR 0004-compliant by
  construction; stacked tree fully static-green. Bonus: Alembic
  c9d1e7a40b21 adds the four promoted partial indices (817cb8e7),
  if_not_exists, up+down round-tripped on dev. (c) `test all` green on
  the stack (4090 unit); `e2e all` result recorded under P13 evidence.
  (d) 100-way leg: peer waits for the PR ping.
  Their session state: .notes/project_session-state-2026-08-17-snapshot-spike.md.
- [ ] **P13 UAT** — Brian reviews; PR description tells the ADR story.
  PR-notes flag (from initial-snapshot-delivery session): that branch pins
  `ty@0.0.24` in .claude/hooks/{python_lint,final_lint}.py; this branch made
  those hooks versionless (`uv run ty check`, ADR 0006). Whichever merges
  second resolves the hook files to the versionless form — a version pin
  reappearing there is a merge mistake.

---

## Findings ledger (P8 — each needs a decision or a fix)

1. **[DONE]** ty Row[Any]/session.exec/select-wrapper/Core-column/sentinel
   gotchas documented in raw-sql-convention.md § "ty gotchas" (sourced from
   w2-acl + w2-db-rest reports).
2. **[DONE in doc; guard open]** `to_jsonb()` bytea corruption documented in
   the same section. Optional later: an AST/review guard against to_jsonb on
   bytes-bearing entities.
3. **[bug, tooling — PRIORITY, hit independently twice]** `grimoire test run`
   with mixed nicegui + plain paths silently drops the plain paths
   (`_detect_test_type()` classifies the whole invocation; both w2-acl and
   w2-db-rest lost a run to it). False-green risk. → Fix in cli/testing.py
   (small), after w2-cli finishes to avoid collision.
4. **[bug, tooling]** `grimoire test run --help` acquires the global flock +
   load gate (70+ min for --help during contention). → Same file, same fix pass.
5. **[fix-in-branch]** `wait_for[T]` in tests/integration/nicegui_helpers.py
   doesn't unwrap async condition callables → root-fix, then delete the 3
   casts in test_tag_management_crdt_sync.py.
6. **[fix-in-branch]** ~15 dead mypy-style `# type: ignore` comments in
   test_settings.py — approved sweep.
7. **[correctness, needs Brian]** NoEscape + format-spec in latex_render
   silently loses the trust marker (pre-existing, pinned in test docstring).
   Decide: forbid format-specs on NoEscape, or make NoEscape.__format__
   preserve the subclass.
8. **[deferred, coordinated]** Param-object migrations blocked by cross-file
   call sites / API-guard tests: add_highlight (~149 sites), set_tag (~75),
   pdf_export pair (~24), grant_share, _dispatch_parser, and the 8
   annotation functions w2-annotation verified as guard-blocked
   (resolve_broadcast_label, render_workspace_header,
   render_document_container, render_organise_tab, serialise_items,
   refresh_items, AnnotationSidebar.__init__, _save_all_modified_rows,
   _log_page_load_profile). These carry explicit signature-regression
   guards; changing them is API design work, not lint burndown. Also (from
   w2-db-rest): create_tag (~145 sites), update_tag (~20), update_activity
   (~51), update_course (~31), add_document (~71). → Single coordinated
   follow-up after this branch, or accept noqa where applied.
8b. **[deferred]** export_jobs.py's 5 remaining col() sites + users.py's 1 —
   already ty-clean; migrate to tstring next time those functions are
   touched (ADR 0004 alignment, no urgency).
9. **[leftover diags]** tag_management_save.py:117 invalid-key (TypedDict),
   workspace.py:340 redundant-cast — unowned; fold into P9 sweep.
10. **[watch]** Drop the sqlalchemy override at 2.1 GA when SQLModel lifts
    its cap (ADR 0005 consequence).
11. **[follow-up, post-branch]** Index-candidate enumeration from the
    migrated queries (ADR 0004 consequence; the old design's Phase 6 idea).
12. **[found by w2-cli, needs Brian]** `_parallel.py::_run_parallel_e2e` is
    dead code (defined, never called; grep-verified). The per-file-isolated
    DB machinery is production-reachable only via the nicegui lane. Decide:
    delete, or wire the playwright lane back through it.
13a. **[progress 2026-08-17]** Exact pins DONE (ruff==0.16.3,
    complexipy==7.0.1). Convention doc DONE: to_jsonb type allowlist with
    mechanisms (DBA conditions a+d), tzinfo note, ORDER BY rule.
    Share-button conversion DONE: predicates extracted to SharingUiFlags
    properties, 11 behavioural tests replace the inline-tautology tables +
    ast-grep shape guard. Index measurement DONE: 4 PROMOTE (user.is_admin,
    shared_with_class ×2, search_dirty 30-40×), 4 REJECT on evidence, 2
    INCONCLUSIVE (export_job unseeded — loadtest generator gap noted);
    migrations deferred to stack assembly. DBA conditions b+c DONE
    (w5-hydration-fix): _HydratedRowEntities threading (staff −1 query,
    peer −2 per page load), to_jsonb field-type guard
    (falsification-verified), crdt_state byte-equality test, staff-derived
    permission test (non-default value). NOTE: _resolve_enrollment_permission
    at complexity exactly 15, no headroom. IN FLIGHT: w5-orderby-migrate
    (14 sites, 7 files), w5-marking-e2e (instructor journey, Brian-approved).
    NEW worktree .worktrees/test-codepath-tracing forked from this branch's
    full uncommitted state, verified green — for the test→codepath tracing
    audit (scoping with Brian pending).
13. **[directive, Brian 2026-08-17, refined]** ORDER BY is a raw-SQL signal:
    any ordered query is a display read — migrate every remaining
    ORM+order_by site to tstring (activities ×2, weeks student-visibility).
    Core-column form survives only in unordered unit-of-work predicates
    (delete-fetch .in_, .returning). Named exception: ordered queue-claim
    (ORDER BY + FOR UPDATE SKIP LOCKED) may stay ORM if one ever needs to.
    Update raw-sql-convention.md with this rule. Also convert
    test_share_button_guard_expression from shape-pin to behavioural test
    (extract visibility predicate, test flag combinations). Queued behind
    the running e2e slow.
14. **[ratified, Brian 2026-08-17]** Judgement items 3 (per-lane test-run
    dispatch), 4 (--help lock bypass), 5 (tests keep PLR2004/PLR0913
    per-file-ignores), 6 (informational write hook) accepted. Item 7
    DIRECTED: exact-pin all three tools (ruff, complexipy join ty at ==);
    bumps go through the ADR 0003 controlled-upgrade ritual. pyproject edit
    + relock queued behind the suite (identical resolved versions, so no
    env drift).
15. **[PARKED for tonight's test-quality layer, Brian 2026-08-17]** Two
    CONFIRMED pre-existing placement bugs (verified against HEAD — not
    migration-introduced): (1) _course_placement ignores
    course.default_allow_tag_creation (course-placed workspaces never get
    the course tag policy); (2) get_placement_context's is_template overlay
    exists only in the activity branch — course-placed/loose template
    workspaces lose the flag. Fix TDD-style with the Gemini semantic-audit
    cleanup (semantic_audit_report.md), whose other claims (anonymise
    tautology oracle, client_registry/factory vacuous mocks, admission dead
    path) still need verify-against-source before acting.
16. **[resolved]** JS lane vacuous pass ("vitest not installed" + exit 0) —
    npm ci restored it; the runner's exit-0-on-missing-vitest behaviour is
    part of finding 3/4's fix pass.
17. **[FIXED on branch value-capture-courses, Brian's "you find it, you
    fix it" 2026-08-17]** All six courses.py forms now capture client-side:
    `on_submit_with_values` (multi-field dict variant of the hardening
    helper) wires course/week/activity create and edit; enrolment email
    uses the single-value helper. The guard now traces closure variables
    bound to `ui.input/textarea/number` constructor chains (red→green
    verified: 24 flags before the fix, 0 after). NiceGUI User-harness
    clicks read the trigger's `_value_capture_inputs` simulation hook so
    fill+click tests stay faithful without a racy server-side fallback in
    production. Original finding below.
    Week-create form value-capture race (pre-existing,
    courses.py ~1501): `submit()` reads `title.value` server-side instead
    of using `ui_helpers.on_submit_with_value` — the exact race pattern 2
    in CLAUDE.md exists to prevent. Under socketio task reordering the
    click precedes the value update, the "Title is required" guard
    early-returns, no navigation happens, and any E2E waiting on the
    redirect times out. Fingerprint: test_instructor_marking failed at
    add_week in 1 of 4 parallel playwright-lane runs; isolation retry and
    full lane rerun both green; my commits touch only noqa comments in
    courses.py. Mechanism is a strong hypothesis (guard-return fits the
    no-navigation timeout exactly) — confirm by capturing the notify in a
    repro before fixing. Sibling forms in courses.py (add-activity,
    course-create) likely share the pattern; sweep them in the same fix.
    Single-input `on_submit_with_value` suffices for the title guard;
    week_number keeps its server-side read (numeric default, not
    guard-relevant).
18. **[OPEN — feed into the test-codepath-tracing audit]** `grimoire e2e
    changed` deselected all 233 E2E tests for a courses.py edit (observed
    2026-08-17): the AST dependency analysis follows imports, but E2E
    tests reach page code through URLs and data-testids, so page-module
    changes select nothing. A change-selection run that deselects
    everything is a vacuous pass, not evidence — the tracing audit should
    give the selector a page-route/testid mapping or make all-deselected
    runs fail loudly.
