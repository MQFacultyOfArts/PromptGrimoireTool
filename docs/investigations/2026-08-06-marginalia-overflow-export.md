# Causal Analysis: marginalia overflow-endnotes fallback never triggers

Date: 2026-08-06
Investigator: Claude (marginalia-diag, Sonnet 4.5), diagnosing for team-lead
Status: Reviewed (see Peer Review) — revised after a High-severity audit
pass, then further updated with a five-point CI sample (2026-05-08 through
2026-07-16) and a rule-out of team-lead's 2026-04-04 suspect commits

**Note on provenance:** this file was regenerated after the working copy was
lost between drafting and peer review (the original was overwritten/removed
by some part of the toolchain between when I wrote it and when I went to
apply the reviewer's corrections — cause not determined). This is the
corrected version, written directly from the verified evidence below; it was
not re-diffed against the lost draft line-by-line, but every claim in it was
re-checked against the repo/filesystem/`gh` output during this pass.

## Summary

The overflow-to-endnotes safety net in `has_marginalia_placement_warnings()`
(`src/promptgrimoire/export/pdf.py:120-130`) searches a LaTeX compile log for
the literal string `"Package marginalia Warning: Problems in placement"`.
The `marginalia` package installed on this development machine (v0.83.30,
self-declared date 2026-07-28, installed locally on 2026-07-30 per
`~/.TinyTeX/texmf-var/web2c/tlmgr.log`) never emits that string — it uses
LaTeX's kernel `module_warning` mechanism, which prints `"Module marginalia
Warning: Problems in placement."` (`Module`, not `Package`). This is
**demonstrated** on the production code path: I compiled the exact fixture
the failing test uses, through the real `export_annotation_pdf()` function,
and confirmed both that the real warning fires and that the code's string
search misses it.

The practical effect is not cosmetic. When this fixture's 23 margin
annotations overflow the available margin column, marginalia silently drops
the ones that get pushed above the page top — no error, no second page, no
endnotes section, no exception. Rendering the actual PDF from my
reproduction shows the margin column contains boxes for only 9 of the 23
annotation numbers (15 through 23); annotations 1–14 have no margin box at
all. Independently, extracting the full PDF text and searching for every
fixture comment string shows 17 of the 23 comments are absent from the
document altogether — the identical set team-lead's own test run reported
(hl-0,1,2,3,5,6,7,8,9,10,11,13,14,15,16,17,20). **I have not reconciled these
two counts (14 vs. 17) against each other on a per-annotation basis** — the
fixture's highlight-list index does not map 1:1 onto the printed annotation
number (some highlights carry multiple comments, each becoming a separate
numbered `\annot` call), and I did not build that mapping. Both
measurements independently show substantial, silent annotation loss; I am
not claiming they are the same 14/17 annotations without doing that work.
`export_annotation_pdf()` returns normally and logs `export_complete` — the
pipeline believes this export succeeded either way.

**Update, after team-lead supplied the full nightly-workflow history back to
its creation (2026-03-29):** the window is now tightly bounded and much
better sampled. I checked five nightly runs' **LuaLaTeX compile lane**
(`-m latexmk_full`) logs, spread across ten weeks —
2026-05-08, 2026-06-05, 2026-07-03, 2026-07-10, 2026-07-16 — and every one
shows the identical result: `41 passed, 2 skipped, 5369 deselected, 1
xfailed`, with `test_some_annotations_remain_in_margin` correctly `XFAIL`.
(I still could not verify the separate **smoke lane**'s isolated result on
any of these dates — its artifacts have all expired, and none of these
runs' smoke-lane console sections show unambiguous per-test output the way
the latexmk_full sections do — so this remains latexmk_full-lane evidence
specifically, not smoke-lane evidence.) No nightly run exists after
2026-07-16 (workflow auto-disabled). So: this exact test passed
identically in real CI on five separate dates spanning 2026-05-08 through
2026-07-16, and is broken today (2026-08-06), with **zero CI data points in
the 2026-07-16 → 2026-08-06 gap** because nothing ran.

Team-lead independently found the nightly workflow's *overall* conclusion
was `success` on 2026-04-02 and `failure` every night from 2026-04-03
onward, and proposed several 2026-04-04 commits as suspects. I can rule
those out directly from git history, no compile needed: the overflow-
detection mechanism itself (`has_marginalia_placement_warnings`,
`inject_annot_force_endnotes` — commit `2869a678`) and the test that
exercises it (`091ee530`) were both authored on **2026-04-07**, three days
*after* the April 3 red streak began (2026-04-07T08:44:40Z and
2026-04-07T10:12:43Z respectively, vs. the first red run at
2026-04-03T17:16:19Z — confirmed in UTC, not just local commit-author time,
so the AEDT/AEST transition in that window doesn't create ambiguity here).
The suspect commits (`ad60435f`/`524346f4` at 2026-04-04T07:45Z,
`d7b6d4a6` at 2026-04-04T09:08Z) predate the feature's existence by three
days. The April 3 red streak cannot be about marginalia-overflow
detection — that code path and its test did not exist yet. It must be a
different lane or test, exactly as team-lead's own caveat anticipated.

I did not attempt to check out historical PromptGrimoire commits and
re-run the test locally, which team-lead's message also suggested as a
verification path. I don't think it would be informative: TinyTeX/marginalia
lives in `~/.TinyTeX`, entirely outside this repository and not pinned per
commit. Any commit from 2026-04-07 onward, tested today, would hit today's
(broken) marginalia regardless of what that commit actually changed —
local checkout-and-run can't distinguish a PromptGrimoire-side regression
from an environment change. Only point-in-time CI logs, where the
environment was whatever it was on that date, can do that — which is why I
went back to `gh run view --log` instead.

This is a genuine, current defect confirmed on this development machine. I
could **not** confirm or rule out whether the live `grimoire.drbbs.org`
production server is affected — TinyTeX there is provisioned once manually
(`docs/deployment.md` §9) rather than re-run on every deploy, so its
marginalia version depends on when it was last (re)provisioned, which I have
no access to check.

## Causal Chain

1. **Detection is single-point-of-failure and string-literal.**
   `compile_latex()` (`src/promptgrimoire/export/pdf.py:165-213`) runs
   `latexmk` once, then calls `has_marginalia_placement_warnings(log_file)`
   (`pdf.py:201`) as the *only* signal that annotations overflowed the
   margin. If that check returns `False`, the function returns the
   first-pass PDF as-is — there is no other overflow signal anywhere in the
   pipeline (verified by reading the full file; `_run_latexmk`,
   `_log_latex_errors` only look at process return code and PDF existence,
   never at warnings).

2. **The check's literal string does not match the installed package's
   output.** `has_marginalia_placement_warnings()` (`pdf.py:120-130`) does:
   ```python
   return "Package marginalia Warning: Problems in placement" in content
   ```
   The installed `marginalia.sty` (`/home/brian/.TinyTeX/texmf-dist/tex/lualatex/marginalia/marginalia.sty`,
   `\ProvidesExplPackage{marginalia}{2026-07-28}{0.83.30}`) is an
   `expl3`/Lua-based rewrite. Its placement-problem message is built in
   `marginalia.lua:342-349` (`write_problem_report()`), which delegates to
   `write_report()` (`marginalia.lua:310-341`), which calls
   `warning('Problems in placement.', ...)` (line 317 for the
   zero-max-length path, line 339 for the normal path) →
   `luatexbase.module_warning(module_name, ...)` (`marginalia.lua:37-38`).
   That resolves to LaTeX's own kernel implementation: `module_warning`
   (`/home/brian/.TinyTeX/texmf-dist/tex/latex/base/ltluatex.lua:104-107`)
   calls `msg_format` (`ltluatex.lua:73-99`), whose format-string line is
   `first_head = leader .. "Module " .. mod .. " " .. msg_type .. ":"`
   (`ltluatex.lua:84`) — i.e. **`"Module marginalia Warning:"`**, never
   `"Package marginalia Warning:"`. `\PackageWarning` (the classic LaTeX2e
   macro that *would* produce the "Package" form) is not called anywhere in
   `marginalia.sty` or `marginalia.lua` — confirmed by grep across both
   files.

3. **The mismatch is invisible to the existing unit tests.**
   `tests/unit/export/test_marginalia_overflow.py:23-32`
   (`test_detects_placement_warning`) feeds `has_marginalia_placement_warnings`
   a *hand-written* log fixture containing the literal string the production
   code searches for. It cannot fail regardless of what the real
   `marginalia` package emits — it is a tautology with respect to the
   integration question ("does this detect real overflow?"), not a bug in
   the unit test itself (it correctly tests the function's own logic in
   isolation).

4. **Consequently, the fallback never fires**, confirmed by direct
   execution against the real artifact (see Claim Verification below):
   `\annotforceendnotestrue` is never injected, `compile_latex()` returns
   the first-pass PDF unchanged, and `.sty:135-146`'s `\flushannotendnotes`
   never emits an "Annotations" or "Long Annotations" section because
   `\ifannothasendnotes` was never set (nothing was routed to endnotes).

5. **Annotations that don't fit are dropped by marginalia itself, not by
   PromptGrimoire code.** `promptgrimoire-export.sty:199-207`'s "short
   annotation" branch calls `\marginalia[ysep=3pt]{...}` unconditionally
   for any annotation under the 4cm height threshold — this is the normal,
   intended path when force-endnotes is *not* active. marginalia's own
   placement algorithm, when items don't fit, pushes earlier items above
   the page top and (per the visual reproduction) simply does not render
   them. This is expected/documented marginalia behaviour for overflow —
   the PromptGrimoire pipeline's job was to detect this via the log warning
   and compensate, and that detection is what's broken.

## Evidence Grading

| # | Finding | Grade | Positive border | Negative border | Upgrade path |
|---|---------|-------|------------------|------------------|---------------|
| 1 | `has_marginalia_placement_warnings()` returns `False` against the real, current marginalia overflow warning on the production code path | **Demonstrated** | Compiled the real "Dog's Breakfast" fixture through `export_annotation_pdf()`; the resulting `.log` contains `Module marginalia Warning: Problems in placement.` (line 1097) | Called `has_marginalia_placement_warnings()` directly against that same real log file; it returned `False`; `grep -c "Package marginalia"` on the same file returns `0` | — |
| 2 | Annotation content is visibly, silently missing from the rendered PDF (not just absent from an endnotes section) | **Demonstrated** (as "substantial content is missing"); **not** demonstrated that the two measurement methods agree on *which* annotations | Rendered the real PDF from my reproduction to PNG and visually inspected it: only annotations 15–23 appear in the margin column (9 boxes); 1–14 have no margin box | pymupdf text extraction over the same PDF confirms 17 of 23 highlight *comments* are absent from the full document text, and this specific set matches team-lead's independently-obtained failure list exactly (hl-0,1,2,3,5,6,7,8,9,10,11,13,14,15,16,17,20) — but I did not build the highlight-index → printed-annotation-number crosswalk needed to check this against the visual "14 missing boxes" finding | Re-run the reproduction and emit one per-annotation table (annotation #, margin-box present?, comment text found?) instead of two separate headline counts |
| 3 | This exact test module passed consistently in real GitHub Actions CI from 2026-05-08 through 2026-07-16 | **Plausible**, well-corroborated by repeated sampling, and specifically as *latexmk_full-lane* evidence, not smoke-lane evidence | Five nightly runs' "LuaLaTeX compile lane" sections (`-m latexmk_full`, per `src/promptgrimoire/cli/e2e/__init__.py:317-323`), spread across ten weeks — 2026-05-08 (run 25570162106), 2026-06-05 (27030535657), 2026-07-03 (28675366859), 2026-07-10 (29111617717), 2026-07-16 (29520257240) — every one shows the byte-identical result: `test_some_annotations_remain_in_margin` `XFAIL` (the designed, working outcome) and `41 passed, 2 skipped, 5369 deselected, 1 xfailed` | The same runs' separate smoke lane (`-m smoke`, `test-smoke.log`) also selects this test file (it carries both markers via `requires_full_latexmk`, `tests/conftest.py:108-110`) but I could not verify its isolated result on any of these five dates — the uploaded artifacts have all expired (`gh api .../artifacts` shows `"expired":true`), and the console logs show implausibly short (~38s) smoke-lane windows with zero occurrences of this test's ID, which is hard to reconcile with the lane actually having run it | Re-run the smoke lane fresh (locally or via a re-enabled/manually-dispatched nightly run) and check in isolation |
| 4 | The regression is attributable to a marginalia package upgrade rather than a PromptGrimoire code change | **Plausible** | No PromptGrimoire commit touches `pdf.py`'s detection logic or the `.sty` between the test's authoring (2026-04-07, commit `091ee530`) and today — `git log 091ee530..HEAD -- src/promptgrimoire/export/pdf.py` returns exactly one commit (`175e6276`), and its diff only changes a subprocess timeout constant (120s→60s), not the detection logic; `git status` confirms both files are unmodified on this working tree. Locally, `marginalia` was updated twice since the test's authoring per `tlmgr.log`: 2026-07-10 (rev 77235→79621) and 2026-07-30 (rev 79621→79811, the version now installed). The 2026-07-10 CI run (above) still passed — since CI's own `tlmgr update --self --all` on that date would have pulled at least whatever was on CTAN by then, this weakly suggests rev 79621 was not yet the breaking change, and the 2026-07-30 update (self-declared package date 2026-07-28) is the better-supported candidate | Did not obtain a copy of the pre-07-10 or the 79621 (07-10–07-30) marginalia release to diff directly — only the current (79811) version exists on this filesystem, and the package's public Codeberg source repo returned 404 for the path I tried. The "CI's tlmgr pulled the same revision as local on the same day" inference is itself unverified — CI's TinyTeX is a separate install and I have no direct record of what CTAN revision it actually resolved to on any given date; nor can I rule out a different package updated in the same 2026-07-30 local batch as a contributing factor, though the source-level mechanism (finding #1) does not depend on that distinction | Obtain marginalia CTAN revisions 77235 and 79621 from a TeX Live historic archive and diff their warning-emission code directly against 79811 |
| 5 | CI's regular gate (`ci.yml`'s "Run unit and integration tests" step) has never exercised this test, despite its name | **Demonstrated** | Direct read of `.github/workflows/ci.yml:177-181`: the step runs `uv run grimoire test all` | Direct read of `src/promptgrimoire/cli/testing.py:673-677`: `all_tests()`'s `default_args` is `["tests/unit", "-m", _TEST_ALL_MARKER_EXPRESSION]` — only the `tests/unit` directory, and `_TEST_ALL_MARKER_EXPRESSION` (line 81) explicitly excludes `smoke`; `tests/integration` is never named | — |
| 6 | Production (`grimoire.drbbs.org`) is currently affected | **Speculative** | This dev machine reproduces the bug | Have no access to the production host's `~/.TinyTeX` to check its marginalia version or last-provisioned date; `docs/deployment.md` §9 and `deploy/restart.sh` show TinyTeX is a one-time manual install, not refreshed on every deploy, so production's exposure depends entirely on when/whether an admin last ran `setup_latex.py` there | SSH to the production host (or ask an admin with access) and check `marginalia.sty`'s `\ProvidesExplPackage` date, or `~/.TinyTeX/texmf-var/web2c/tlmgr.log`'s last marginalia entry |
| 7 | The nightly workflow's April 3–onward overall red streak is unrelated to marginalia-overflow detection | **Demonstrated** | UTC commit timestamps: `2869a678` (detection mechanism) at 2026-04-07T08:44:40Z, `091ee530` (test) at 2026-04-07T10:12:43Z. First red nightly run at 2026-04-03T17:16:19Z (run `23955039851`), three-plus days earlier | Both the detection code and the test file are absent from the repository at the April 3 commit — neither could have been exercised by that run or the several days of red runs preceding 2026-04-07. This is a straightforward git-history fact, not an inference about test behaviour | — |

## Claim Verification

| # | Claim | Evidence | Falsification test | Result |
|---|-------|----------|---------------------|--------|
| 1 | `has_marginalia_placement_warnings` checks for `"Package marginalia Warning: Problems in placement"` | `pdf.py:130` | Read the line directly | Not falsified — exact string confirmed |
| 2 | The real, currently-installed marginalia package emits `"Module marginalia Warning: Problems in placement."` on overflow, not the `"Package"` form | `marginalia.lua:37-38,310-349`; `ltluatex.lua:73-99,84,104-107` | Compiled the real fixture end-to-end via `export_annotation_pdf()` and grepped the resulting `.log` for both forms; separately read the Lua/kernel source directly without relying on log output alone | Not falsified — `Module marginalia Warning: Problems in placement.` present at log line 1097; `Package marginalia` absent (0 matches); source-level construction confirms the format string independently |
| 3 | Given that log, `has_marginalia_placement_warnings()` returns `False` on the production path | `pdf.py:120-130` reasoning from claims 1+2 | Called the actual imported function against the actual generated log file (not a mock, not a hand-written fixture) | Not falsified — returned `False` |
| 4 | The recompile-with-endnotes fallback never ran for this export | `pdf.py:197-211` | Checked for the `marginalia_placement_overflow` structlog line in the repro's stdout (emitted only inside the `if has_marginalia_placement_warnings(...)` branch, `pdf.py:202-207`) | Not falsified — line absent from the run's output |
| 5 | Annotation comment text is missing from the compiled PDF, not just from an endnotes section | `test_all_comments_present` logic ported to a standalone script against the real PDF | Extracted full PDF text with pymupdf and searched for every fixture comment string; also rendered the page to PNG and visually inspected the margin column | Not falsified as two separate findings — 17/23 comments absent from text; PNG shows 14 of 23 annotation numbers have no margin box. **Not** shown to be the same 14/17 annotations — see finding 2 in Evidence Grading |
| 6 | `test_all_annotation_numbers_present` passes even though comments are missing, because superscript numbers are typeset independently of the margin box | `.sty:200-201` (`\textsuperscript{...}` precedes the `\marginalia{...}` call in the short-annotation branch) | Cross-checked against team-lead's report: that specific test was reported PASSED, consistent with this reading | Not falsified — no contradiction found; superscript markers for annotations 1–14 are visible in the rendered PNG even though their margin boxes are gone |
| 7 | CI's default gate never runs the smoke lane (so this could have regressed silently) | `.github/workflows/ci.yml:177-181`, `src/promptgrimoire/cli/testing.py:670-719` | Read both files directly; independently re-derived the marker exclusion (`not e2e and not nicegui_ui and not latexmk_full and not smoke`) rather than trusting CLAUDE.md's prose description | Not falsified |
| 8 | The nightly `e2e slow` workflow — the one lane that does run smoke — is currently disabled | `gh workflow list --all` output: `Nightly E2E Slow  disabled_inactivity` | Ran the command directly | Not falsified as to *state* (`disabled_inactivity` confirmed). **The specific mechanism I originally attributed this to — "60 days with no successful run" — is wrong.** GitHub's documented trigger is 60 days with no *new commit* to the repository, not run success/failure. This repository has continuous recent commit activity, so the documented mechanism does not obviously explain why this workflow is disabled; I have not identified the actual cause |
| 9 | The 2026-07-16 nightly run's `latexmk_full` lane actually passed this test, including its designed XFAIL | Full job log for run `29520257240` | Searched the full log for the pytest summary line and the specific XFAIL entry, and confirmed via `src/promptgrimoire/cli/e2e/__init__.py:317-323` which marker expression that lane uses | Not falsified — confirmed this is the `latexmk_full` lane's own output, correctly attributed (this corrects an earlier mislabelling as "the smoke lane" — see Peer Review) |

## Epistemic Boundary

- **Demonstrated:** The detection function's string check does not match the
  real marginalia package's actual output, on the actual production code
  path, verified against a real compile of the real failing-test fixture
  (both borders: real warning present, code's check absent/`False`),
  corroborated independently by reading the Lua/kernel source rather than
  relying on log output alone. Annotation content is genuinely, silently
  absent from the rendered PDF by two independent measurement methods (text
  extraction, visual rendering) — though those two methods have not been
  reconciled against each other per-annotation. CI's regular gate never
  running this test is demonstrated by direct source read of both the
  workflow file and the CLI's marker logic.

- **Plausible, well-corroborated:** That this is a *regression* tied to a
  marginalia package upgrade (rather than the test having been broken since
  authorship) rests on five CI data points (2026-05-08, 06-05, 07-03, 07-10,
  07-16 — all `latexmk_full` lane green, byte-identical results, including
  this exact test's designed XFAIL) plus two candidate local update events
  (2026-07-10 and 2026-07-30). The 07-10 CI pass makes the 07-10 local
  update the weaker candidate; 07-30 (package self-dated 07-28) is better
  supported, but I cannot fully rule out 07-10, since I don't have a direct
  record of what CTAN revision CI's separate TinyTeX install actually
  resolved to on any of these dates. The regression window itself —
  2026-07-16 to 2026-08-06 — is solid: no CI run exists in that window at
  all (nightly auto-disabled), so I can't narrow it further with CI
  evidence, only with the local tlmgr history, which is a different
  environment.

- **Speculative:** Whether the live production server is currently affected,
  and the exact mechanism behind the nightly workflow's `disabled_inactivity`
  state (I confirmed the state but not GitHub's actual reason, since the
  documented 60-day-no-commit trigger doesn't obviously fit this repo's
  activity).

- **What I could not check:**
  - The production server's installed marginalia version or provisioning
    date.
  - The isolated smoke-lane (`-m smoke`) result for this test on
    2026-07-16 — the artifact expired before I could inspect it, and the
    console log's ~38-second smoke-lane window is inconsistent with this
    test having actually run there, which I cannot explain.
  - Which of the two local marginalia updates (2026-07-10 or 2026-07-30)
    — or a different, simultaneously-updated package — actually changed the
    warning format, since only the current (79811) release is available on
    this filesystem to inspect.
  - Why every nightly run back to 2026-06-07 shows overall `failure` — I
    saw unrelated PostgreSQL type-introspection output in one failed run's
    log and did not chase it; it may or may not be connected to why the
    workflow was later auto-disabled.
  - The actual reason GitHub reports this specific workflow as
    `disabled_inactivity` given the repository's active commit history.
  - Whether any other environment (a teammate's machine, a different CI
    runner) still has a pre-regression marginalia and would show the tests
    passing — I only had this one machine to test on.

## Answers to the assigned questions

**1. Root cause.** `has_marginalia_placement_warnings()`
(`src/promptgrimoire/export/pdf.py:130`) searches for the literal string
`"Package marginalia Warning: Problems in placement"`. The installed
marginalia package (v0.83.30) emits `"Module marginalia Warning: Problems in
placement."` instead (`\ProvidesExplPackage` header in `marginalia.sty`;
message construction in `marginalia.lua:310-349` via
`luatexbase.module_warning`, formatted by the LaTeX kernel's `msg_format`
in `ltluatex.lua:73-99`, format string at line 84: `"Module <name>
<type>:"`). The string never matches, so the overflow-recompile-to-endnotes
fallback (`pdf.py:197-211`) never runs. Grade: demonstrated, including
independent verification of the source-level mechanism (not just log
output).

**2. When did it break?** Best evidence: this exact test module passed
identically in five separate real GitHub Actions runs spanning 2026-05-08
through 2026-07-16 (`latexmk_full` lane; runs 25570162106, 27030535657,
28675366859, 29111617717, 29520257240 — all `41 passed, 2 skipped, 5369
deselected, 1 xfailed`, correct XFAIL each time). Broken as of today,
2026-08-06, both in team-lead's run and my independent reproduction. No CI
data exists in the 2026-07-16 → 2026-08-06 gap for either lane — the
nightly workflow that would have caught it is currently disabled and has
not run since 2026-07-16. On this local machine, marginalia was updated
twice in the broader window (2026-07-10 and 2026-07-30); since CI still
passed on 2026-07-10, that update is the weaker candidate, and 2026-07-30
(self-declared package date 2026-07-28) is better supported, though not
proven — see Evidence Grading row 4. Separately, and independent of all of
the above: team-lead's suspect commits from 2026-04-04 are **ruled out** —
the detection mechanism and its test were both authored 2026-04-07, three
days after those commits and three days after the April-3 nightly red
streak began, so neither the code nor the test existed for that streak's
first several days. Grade: the 2026-07-16 → 2026-08-06 window is plausible
and well-sampled going in; the April-4 rule-out is demonstrated (git
timestamps, no inference required). Could not confirm which lane (smoke
vs. latexmk_full) actually validated it on any of the five dates — only
latexmk_full's pass is confirmed throughout.

**3. Severity — what does a real user get?** Severe, and silent. I compiled
the actual "Dog's Breakfast" fixture (23 highlights, one short page) through
the real export pipeline and rendered the output PDF. The margin column
contains boxes for only 9 of the 23 annotation numbers (15 through 23);
annotations 1–14 have no margin box on the page at all — not on a second
page, not in an endnotes section, nowhere in the PDF. Independently,
extracting the full PDF text shows 17 of 23 comment strings are absent from
the document (I have not reconciled this set against the "14 missing boxes"
set — see Epistemic Boundary — but both measurements independently indicate
severe loss). The export pipeline logs `export_complete` and returns a
valid, non-empty PDF; nothing in the user-facing flow indicates anything
went wrong. A student or instructor who exports a heavily-annotated document
(this fixture's design intent, and a realistic case for a legal-annotation
classroom tool used mid-semester) can lose most of their annotation
comments without any error, warning, or visual cue beyond "the numbers in
the margin don't go all the way up" — something a time-pressured user is
unlikely to notice. This is not a missing-heading cosmetic issue; it is
undetected data loss in an assessment-adjacent artifact.

**4. Proposed fix (not applied).** Broaden
`has_marginalia_placement_warnings()` to match both `"Package marginalia
Warning:"` and `"Module marginalia Warning:"` (or, more robustly, match on
`"marginalia Warning: Problems in placement"` regardless of the
Package/Module prefix, since that prefix is an implementation detail of
*how* the package reports warnings, not something PromptGrimoire should be
coupled to). The string-matching change itself is mechanically small, but I
have not tested it (it is explicitly not applied), so I am not asserting a
risk level for it beyond "small surface area." The current unit tests only
assert against a hand-written fixture and would not have caught this — any
fix should also add a regression test that runs a real compile (like
`tests/integration/test_marginalia_overflow_export.py` already does) rather
than relying solely on a mocked log string, and CI needs a path that
actually and verifiably runs the smoke lane regularly. The deeper risk is
that `scripts/setup_latex.py:192` runs `tlmgr update --self --all`
unconditionally (in CI, on every job run, cache hit or not; the same is
true if anyone re-runs it manually on a dev machine or production), with no
version pinning — so this class of break (a third-party CTAN package
silently changing its diagnostic output format) can recur for any of the
~20 other packages in `REQUIRED_PACKAGES` that PromptGrimoire's own code
parses log output from or otherwise depends on undocumented behaviour of.

**5. What I could not check.** See "What I could not check" under
Epistemic Boundary above — production's marginalia version, the isolated
smoke-lane result for 2026-07-16, which of the two local marginalia updates
is responsible, why the nightly workflow's earlier runs were red, and the
actual `disabled_inactivity` cause.

## Reproduction

```bash
mkdir -p /tmp/marginalia_diag/out
uv run python - <<'EOF'
import asyncio, json
from pathlib import Path
from promptgrimoire.export.pdf_export import export_annotation_pdf

async def main():
    fixture = json.loads(Path("tests/fixtures/workspace_dogs_breakfast_overflow.json").read_text())
    pdf_path = await export_annotation_pdf(
        html_content=fixture["html_content"],
        highlights=fixture["highlights"],
        tag_colours=fixture["tag_colours"],
        output_dir=Path("/tmp/marginalia_diag/out"),
    )
    print("PDF at:", pdf_path)

asyncio.run(main())
EOF
grep -n "arginalia Warning" /tmp/marginalia_diag/out/annotated_document.log
uv run python -c "
from pathlib import Path
from promptgrimoire.export.pdf import has_marginalia_placement_warnings
print(has_marginalia_placement_warnings(Path('/tmp/marginalia_diag/out/annotated_document.log')))
"
```

Note: at the time of writing, `/tmp/marginalia_diag/out/` (including the
rendered `page_1.png`) still exists on this machine from the original run,
but is not committed to the repository and may not survive a reboot/tmp
cleanup. Re-run the above to regenerate it.

## Peer Review

A clean `code-reviewer` subagent (no prior context, full repo + filesystem
+ `gh` access) audited the first draft of this analysis per the
systematic-debugging skill's Phase 3d protocol. It found **3 High, 2
Medium, 3 Low** severity issues. All three High findings were independently
re-verified by me before this revision and are reflected above:

1. **Wrong install date for marginalia** (claimed 2026-08-03; actual,
   per `tlmgr.log`, 2026-07-30). Corrected throughout; also surfaced a
   second, earlier local update (2026-07-10) I had not previously
   considered.
2. **CI evidence mislabelled as "smoke lane" when it was actually the
   separate `latexmk_full` lane.** Corrected throughout; the isolated
   smoke-lane result for 2026-07-16 is now stated as unverified (artifact
   expired before I could check).
3. **Unreconciled 14-vs-17 annotation counts presented as "exact match"
   corroboration.** Corrected — the two measurements are now presented as
   independent, non-reconciled findings, both indicating severe loss, with
   the specific per-annotation crosswalk explicitly flagged as not done.

The two Medium findings (a mis-cited `ltluatex.lua` line number for the
format-string construction; an unverified claim about GitHub's
`disabled_inactivity` trigger mechanism) and three Low findings (an elided
intermediate function call in the `marginalia.lua` trace; an unaddressed
single commit touching `pdf.py` that a naive `git log` check would surface;
overconfident "low risk" language for an untested fix) are also corrected
above.

The reviewer's own verification independently re-derived the core
source-level mechanism (marginalia.lua → ltluatex.lua format string)
without relying on this document's transcription, and confirmed it
matches — its assessment was that the central technical diagnosis is sound
and "can ship as-is," while the surrounding regression-window narrative
needed the corrections applied here.

## Post-commit reconciliation of the 14-vs-17 counts (2026-08-06)

The section above left the two severity measurements — 14 annotations with no
margin box, 17 comment strings absent from extracted text — explicitly
unreconciled. A second reviewer (a different model, working from the
pre-correction draft) completed that reconciliation. Its result was verified
against the fixture before being recorded here.

**The two counts are consistent, and 14 is the defensible figure.**

- Of the 17 comments the PyMuPDF assertion reports missing, **13 belong to
  genuinely absent margin boxes**. The remaining four belong to boxes that are
  *visible* in the PDF, and are false negatives caused by line-break
  hyphenation at extraction time — the extracted text contains `In- sufficient`,
  `At- testation` and `Wit- ness`, which an exact-substring search does not
  match.
- The printed annotation number is **not** the fixture's highlight-list index,
  because a single highlight carrying multiple comments produces several
  numbered `\annot` calls. Any 0-index-to-1-index mapping between the two sets
  is therefore invalid, including the one the first reviewer used to argue the
  sets do not nest.

**Defensible severity: 14 of 23 annotations absent from the visible PDF, 13 of
them carrying comment text.** This is an output-integrity failure. The source
annotations are not deleted from the application; the export path returns a
non-empty PDF and reaches its normal `export_complete` path.

### A test weakness this exposed

`test_all_comments_present` searches the whole extracted document for each
comment string, so a comment appearing on more than one annotation cannot
distinguish which copy survived.

The fixture contains exactly one such duplicate. Verified directly against
`tests/fixtures/workspace_dogs_breakfast_overflow.json`: of 22 comments,
`"Insufficient identification of property"` appears **twice**. One copy is on a
visible annotation and one on an absent annotation, so a global search finds
the visible copy and reports the absent one as present.

The test can therefore pass while annotation content is missing. A reliable
version must bind each comment to its printed annotation number or its margin
box, and must dehyphenate extracted text before matching. Neither the original
investigation nor the first peer review caught this.
