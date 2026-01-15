# Code Review Request

Please perform a maximally picky and professional code review of [SPIKE/FEATURE NAME].

## Scope

- All code added by this spike/PR
- All tests (unit, integration, E2E)
- Any modified configuration files

## Review Criteria

### Critical (Must Fix Before Merge)

- Thread safety / async safety issues
- State isolation problems (global mutable state affecting multiple users)
- Security vulnerabilities (XSS, injection, auth bypass)
- Data integrity issues
- Any code smells like imports inside functions or things commented out or automatic passes in tests

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

## Output Format

Provide a structured review document with:

1. Executive summary and overall assessment
2. Issues grouped by severity with file:line references
3. Specific code fixes (before/after)
4. Checklist of items to fix before merge vs before production
5. Verification steps to confirm fixes work
6. Notes for future related work

Be specific and critical. Consider whether this code enables future architectural goals.
