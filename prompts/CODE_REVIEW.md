# Code Review Request

Please perform a maximally picky and professional code review of [SPIKE/FEATURE NAME].

## Scope

- All code added by this spike/PR
- All tests (unit, integration, E2E)
- Any modified configuration files

## MANDATORY: No Quick Hacks

**Quick hacks are absolutely forbidden.** Every fix must be a proper solution:

- No `# type: ignore` without documented justification
- No `time.sleep()` or arbitrary waits to "fix" race conditions
- No global mutable state as a workaround for proper dependency injection
- No suppressing exceptions without logging and proper handling
- No "temporary" workarounds that bypass security checks
- No commented-out code left "just in case"

If a proper fix requires significant refactoring, that refactoring must be done. The codebase must remain maintainable and correct, not just "working for now."

## Race Condition Audit Checklist

All code must be reviewed against these race condition patterns:

### Async/Await Race Conditions
- **State mutations during await:** Any `await` can yield control. Mutable state accessed before and after an `await` may have changed.
- **Concurrent page loads:** Multiple users hitting the same endpoint simultaneously must not share state.
- **Stream consumption:** Async generators must handle consumer disconnection gracefully.

### Module-Level State
- **Import-time initialization:** Code that runs at import time must be thread-safe.
- **Global singletons:** Any module-level state must use proper locking or be truly immutable.
- **sys.modules manipulation:** Never modify sys.modules without locks.

### Database Transactions
- **Read-modify-write:** SELECT followed by UPDATE must use proper locking or optimistic concurrency.
- **Session lifecycle:** Async sessions must not be shared across await boundaries without explicit management.
- **Connection pool exhaustion:** What happens when all connections are in use?

### UI State
- **Optimistic updates:** UI updated before backend confirms must handle rollback.
- **Multiple tabs:** Same user with multiple tabs must not corrupt shared state.
- **Page refresh mid-operation:** What happens if user refreshes during an async operation?

## Review Criteria

### Critical (Must Fix Before Merge)

- Thread safety / async safety issues
- State isolation problems (global mutable state affecting multiple users)
- Security vulnerabilities (XSS, injection, auth bypass)
- Data integrity issues
- Any code smells like imports inside functions or things commented out or automatic passes in tests
- Race conditions in any of the categories above

### High Priority

- Missing type hints
- Missing input validation
- Silent failures without logging
- Test coverage gaps for primary use cases

### Medium Priority

- Magic numbers without constants
- Hard-coded configuration values
- Code duplication
- Missing documentation for complex contracts

### Test Quality

- Are the primary use cases actually tested?
- Are there anti-patterns (arbitrary waits, weak assertions)?
- Is multi-user behavior tested?
- Are race conditions tested (concurrent operations, page refresh mid-stream)?

## Output Format

Provide a structured review document with:

1. Executive summary and overall assessment
2. Issues grouped by severity with file:line references
3. Specific code fixes (before/after)
4. Checklist of items to fix before merge vs before production
5. Verification steps to confirm fixes work
6. Notes for future related work

Be specific and critical. Consider whether this code enables future architectural goals.

When done, please give the absolute path to the code review document so that the programmers may read it.
