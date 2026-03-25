# Clobber Scan Prompt — for Codex/Gemini

**Date:** 2026-03-24
**Context:** During #377 workspace performance investigation, we found commit `bd3cdfbe` silently destroyed diff-based card updates. A grep-based scan of the full codebase found only this one instance, but the approach has blind spots. This prompt is designed for independent verification by Codex/Gemini.

**To run:** Pass this prompt to Codex or Gemini with access to the PromptGrimoireTool repository (main branch).

---

```markdown
# Task: Detect Silently Reverted Features in PromptGrimoireTool

## Context

We discovered that commit `bd3cdfbe` ("fix: coerce CRDT highlight char offsets
to int at read boundary") silently destroyed a diff-based card update system.
The commit claimed to add int() casts but actually rewrote
`src/promptgrimoire/pages/annotation/cards.py`, replacing an O(1) diff-based
`_diff_annotation_cards()` with an O(n) `container.clear()` + full rebuild.
The architecture doc at `docs/architecture/dfd/5-annotate-texts.md:90` still
specifies the diff-based approach.

We believe there are MORE cases like this. A grep-based scan of removed `def`
lines found only this one, but that approach misses:
- Function bodies gutted while signature remains
- Algorithms replaced with naive versions under the same name
- Logic branches removed (e.g., early returns, caching, optimisation paths)
- Features described in docs/design-plans/ that don't match implementation

## Your Task

Use TWO independent detection strategies and report findings from both.

### Strategy 1: Architecture-vs-Implementation Audit

Compare what the documentation SAYS the code does against what it ACTUALLY does.

Files to cross-reference:
- `docs/architecture/dfd/*.md` — Yourdon-DeMarco DFDs with process descriptions
- `docs/design-plans/*.md` — Design documents with specified behaviour
- `docs/database.md` — Schema and access patterns
- `docs/testing.md` — Testing patterns and conventions
- `docs/annotation-architecture.md` — Annotation page structure
- `CLAUDE.md` — Project conventions and rules

For each process/feature described in these docs:
1. Read the documented behaviour
2. Find the implementing code
3. Check: does the code match the documented behaviour?
4. If not: when did it diverge? (use `git log -p --follow -- <file>`)

Known example: DFD process 5.5 says "diff-based card updates, no
container.clear()". Implementation at cards.py:588 does container.clear().
Divergence: commit bd3cdfbe.

### Strategy 2: Semantic Diff of "fix:" Commits

For every commit whose message starts with "fix:" or "fix(":

```bash
git log --all --oneline --grep="^fix" | head -100
```

For each, compute:
- Lines added vs removed (from `git show --stat`)
- If removals > 20 lines: do a SEMANTIC comparison, not just def-line grep
- Read the BEFORE and AFTER of the changed functions
- Ask: "Did any behaviour that existed before this fix disappear without
  being mentioned in the commit message?"

Focus on:
- Caching/memoization logic removed
- Conditional branches collapsed (e.g., if/else reduced to just one path)
- Optimisation paths removed (e.g., early returns, batch operations)
- Error handling removed or simplified
- Async patterns changed (e.g., concurrent calls serialized)
- Data structures downgraded (e.g., dict lookup replaced with linear scan)

### Strategy 3: Test Coverage Gaps

Find tests that USED to pass testing a specific behaviour, where that
behaviour no longer exists in the code:

```bash
# Find test functions that were removed
git log --all --oneline -p -- "tests/" | grep "^-def test_\|^-    def test_\|^-async def test_" | sort -u
```

Cross-reference: if a test for feature X was removed, does feature X
still exist in the code? If the test was removed but the feature was
supposed to stay, something was clobbered.

## Output Format

For each finding:

```
FINDING: [sequential number]
SEVERITY: high (feature logic lost) | medium (optimisation lost) | low (style/minor)
SOURCE: strategy 1 (docs-vs-code) | strategy 2 (semantic diff) | strategy 3 (test gaps)
FILE: [current file path]
WHAT DOCS/TESTS SAY: [documented or tested behaviour]
WHAT CODE DOES: [actual current behaviour]
DIVERGENCE COMMIT: [hash and message, if identifiable]
EVIDENCE: [specific line numbers, git show output, etc.]
```

## Important

- Do NOT report cases where docs are aspirational (describing future work).
  Only report cases where docs describe behaviour that WAS implemented and
  then lost.
- Verify each finding by reading the actual code. Do not rely solely on
  grep patterns.
- If you find zero findings from a strategy, say so explicitly.
- The repository is at the current working directory. Main branch is `main`.
```

---

## What our grep-based scan found (for comparison)

Only one high-severity finding: `bd3cdfbe` clobbering diff-based cards (already known). All other function removals across ~100 commits were explained in commit bodies (inlining, renames, intentional deletion) or were in low-severity CLI tooling.

**Known blind spots of the grep approach:**
1. Only catches removed `def` lines — misses gutted function bodies
2. Can't detect algorithm replacement under the same function name
3. Crude rename detection (string matching)
4. No semantic equivalence checking
