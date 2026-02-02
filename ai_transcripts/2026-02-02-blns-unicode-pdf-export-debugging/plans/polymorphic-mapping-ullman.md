# Plugin Peer Review & Customization Plan

## Context

**Goal**: Apply proleptic reasoning (Socratic method) to all plugins - treating each design decision as a claim requiring anticipation of objections, charitable articulation, and response. Rebrand and customize for Brian's workflow.

**Brian's Stack**: Python, SQL, LaTeX (NOT TypeScript/React)
**New Prefix**: `denubis-` (replacing `ed3d-`) - matches GitHub handle
**Approach**: Full audit, one plugin at a time, committing after each

---

## Proleptic Review Framework

From Brian's paper: proleptic reasoning creates a "tether" distinguishing knowledge from mere true belief through anticipating and responding to objections.

### The Proleptic Loop

```
CLAIM (design decision)
    |
OBJECTION (anticipated counterargument/counterexample)
    |
CHARITABLE ARTICULATION (steelman the objection)
    |
RESPONSE (defend, modify, or abandon the claim)
    |
REVISED CLAIM (if needed) -> back to OBJECTION
```

### Per-Plugin Review Process

1. **Identify Core Claims** - What design decisions does this plugin make?
2. **Anticipate Objections** - What would Reviewer 2 say?
3. **Articulate Charitably** - Steelman the objections
4. **Respond** - Defend OR revise
5. **Brian's Stamp** - Customize for Python/SQL/LaTeX workflow
6. **Anthropic Synthesis** - Add confidence scoring, security monitoring, auto-invocation, parallel agents where appropriate
7. **Rename** - ed3d-X -> denubis-X
8. **Commit** - Each plugin gets its own commit

---

## Review Sequence

### Phase 1: Foundations

**1. ed3d-basic-agents -> denubis-basic-agents**

Claims to challenge:
- C1: Three tiers (haiku/sonnet/opus) map to thinking depth
- C2: All agents must check skills before executing
- C3: Generic agents should be "unprompted"

Customizations needed:
- Review model selection philosophy for Python/data science work
- Consider whether skill-checking overhead is justified

**2. ed3d-house-style -> denubis-house-style**

Claims to challenge:
- C1: FCIS mandatory
- C2: Pattern classification comments mandatory
- C3: Defense in depth everywhere
- C4: No utils.ts files
- C5: Rule of three for abstraction

**MAJOR CHANGES NEEDED:**
- Remove TypeScript/React skills (irrelevant)
- Add Python coding standards
- Add SQL patterns (Postgres remains relevant)
- Add LaTeX conventions
- Decide which of Ed's opinions Brian agrees with

New skills to create:
- `howto-code-in-python` (replacing TypeScript)
- `howto-write-latex` (new)
- Review/keep `howto-develop-with-postgres`

### Phase 2: Research Layer

**3. ed3d-research-agents -> denubis-research-agents**

Claims to challenge:
- C1: Research output in response text only
- C2: Codebase investigator verifies assumptions
- C3: Remote code researcher clones repos

Anthropic patterns to consider:
- Parallel agents (5 agents for investigation)
- Could make investigation faster

### Phase 3: Core Workflow

**4. ed3d-plan-and-execute -> denubis-plan-and-execute**

Claims to challenge:
- C1: Three-phase workflow prevents hallucination
- C2: Design archival, implementation just-in-time
- C3: /clear between phases
- C4: Tasks 2-5 minutes
- C5: Block on ALL severities
- C6: Haiku for implementation

Anthropic patterns to consider:
- Confidence-based scoring for code review
- Parallel agents for review
- Auto-invocation of skills

This is the biggest plugin - expect substantial discussion.

### Phase 4: Extensions

**5. ed3d-extending-claude -> denubis-extending-claude**

Claims to challenge:
- C1: CLAUDE.md active maintenance
- C2: TDD for skills
- C3: One example beats five

**6. ed3d-playwright -> denubis-playwright**

Claims to challenge:
- C1: Accessibility tree over screenshots
- C2: Structure over pixels

Consider: Is Playwright relevant to Brian's Python/SQL/LaTeX workflow?

**7. Hooks -> denubis-hook-***

Claims to challenge:
- C1: Hooks should nudge, not block
- C2: Skill reinforcement helps

New hook to add:
- Security monitoring (PreToolUse for injection, etc.)

### Phase 5: Synthesis

**8. Integrate Anthropic patterns systematically**
**9. Integrate /transcript skill into workflow**
   - Ensure conversation logs are captured for future reference
   - Add to session-end hooks or workflow completion points
**10. Update marketplace.json with all renames**
**11. Final verification that everything works together**

---

## Per-Plugin Deliverables

For each of the 9 plugins:
1. Proleptic analysis (claims, objections, responses) in conversation
2. Revised/renamed plugin files
3. CHANGELOG.md entry
4. Version bump in plugin.json
5. marketplace.json update
6. Git commit

---

## Key Technical Changes

### Rename Operations

```
ed3d-00-getting-started     -> denubis-00-getting-started
ed3d-plan-and-execute       -> denubis-plan-and-execute
ed3d-house-style            -> denubis-house-style
ed3d-basic-agents           -> denubis-basic-agents
ed3d-research-agents        -> denubis-research-agents
ed3d-extending-claude       -> denubis-extending-claude
ed3d-playwright             -> denubis-playwright
ed3d-hook-skill-reinforcement -> denubis-hook-skill-reinforcement
ed3d-hook-claudemd-reminder -> denubis-hook-claudemd-reminder
```

### House Style Skill Replacements

```
REMOVE:
- howto-code-in-typescript/
- programming-in-react/

KEEP (review):
- howto-develop-with-postgres/
- howto-functional-vs-imperative/ (evaluate for Python)
- defense-in-depth/
- writing-good-tests/
- property-based-testing/
- coding-effectively/ (rewrite for Python)
- writing-for-a-technical-audience/

ADD:
- howto-code-in-python/
- howto-write-latex/
```

---

## Verification

After each plugin:
- Plugin loads without errors
- Commands/agents/skills invoke correctly
- No broken cross-plugin references

After all plugins:
- Full workflow test (design -> plan -> execute)
- Verify marketplace.json is coherent

---

## Files Modified

Each plugin review touches:
```
plugins/[plugin-name]/
  .claude-plugin/plugin.json  # version bump, name change
  *.md                        # content updates

.claude-plugin/marketplace.json  # after each rename
CHANGELOG.md                     # entry per plugin
```
