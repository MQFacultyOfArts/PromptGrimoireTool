# Pull Request Guidelines

## The One-Concern Rule

Every PR should address **one logical concern**. Ask yourself: "Can I describe this PR in one sentence without using 'and'?"

**Good:**
- "Add PDF export for Case Brief Tool"
- "Fix Python 3.14 compatibility in CRDT sync"
- "Optimize RTF parser test performance"

**Bad:**
- "Add PDF export and fix Python compatibility and optimize tests"

## Recommended PR Sizes

| Metric | Target | Maximum |
|--------|--------|---------|
| Files changed | 5-10 | 20 |
| Lines changed | 100-300 | 500 |
| Commits | 1-5 | 10 |

PRs exceeding these limits should be split.

## When to Split PRs

Split your work when you have:

1. **Multiple features** - Each feature gets its own PR
2. **Refactoring + feature** - Refactor first, then feature
3. **Infrastructure + code** - Setup/tooling separate from application code
4. **Test improvements + fixes** - Test infrastructure separate from bug fixes

## PR Stacking Strategy

For large features, use a PR stack:

```
main
  └── feature/base-models (PR #1: models + migrations)
        └── feature/service-layer (PR #2: business logic)
              └── feature/ui (PR #3: NiceGUI pages)
```

Each PR builds on the previous. Merge in order.

## Example: Splitting a Large PR

Given PR #55 with 18 commits across 4 topics:

### Before (Hard to Review)
```
PR #55: "Add Claude Code async dev setup script and Python 3.13 fix"
  - 18 commits, 38 files, +4,061 lines
  - Bundles: setup scripts, Python fixes, test optimization,
    PDF export, Course RBAC, navigation
```

### After (Easy to Review)
```
PR #55a: "Add async dev setup script for Claude Code"
  - 3 commits, 5 files, ~200 lines
  - Focus: setup-claude-code-env.sh, env template

PR #55b: "Fix Python 3.14 compatibility in CRDT sync"
  - 2 commits, 2 files, ~50 lines
  - Focus: crdt/sync.py annotation handling

PR #55c: "Optimize test performance with markers and fixtures"
  - 3 commits, 6 files, ~150 lines
  - Focus: conftest.py, pytest markers

PR #55d: "Add PDF export for Case Brief Tool"
  - 2 commits, 4 files, ~300 lines
  - Focus: WeasyPrint integration, CSS

PR #55e: "Add Course/Week models with RBAC"
  - 5 commits, 15 files, ~800 lines
  - Focus: models, endpoints, services

PR #55f: "Add Course management UI and navigation"
  - 3 commits, 8 files, ~400 lines
  - Focus: NiceGUI pages, feature flags
```

## Review Checklist for Maintainers

When reviewing PRs, verify:

- [ ] PR title accurately describes the change
- [ ] Summary explains the "why" not just the "what"
- [ ] Single concern (no bundled unrelated changes)
- [ ] Tests exist and pass
- [ ] No commented-out code or debugging statements
- [ ] No unrelated formatting changes

## Commit Message Format

```
<type>: <short description>

<optional body explaining why>

<optional footer with issue references>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`

Example:
```
feat: Add PDF export for Case Brief Tool

Implements two-column PDF layout using WeasyPrint with brief
content on left and annotations sidebar on right.

Closes #39
```
