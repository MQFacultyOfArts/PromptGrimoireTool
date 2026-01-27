---
name: no-spec-weakening
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: tests?/.*\.(py|ts|js)$
  - field: new_text
    operator: regex_match
    pattern: pytest\.mark\.skip|@pytest\.mark\.xfail|\.skip\(|expect.*not.*toBe|assert.*!=|# TODO:?\s*(fix|skip|ignore)|\.toBeUndefined\(\)|\.toBeNull\(\)
action: warn
---

**Potential Test Spec Weakening Detected**

You may be weakening a test to make it pass instead of fixing the underlying issue.

**Red flags detected:**
- Skip/xfail markers
- Inverted assertions (`!=` instead of `==`)
- TODO comments suggesting deferred fixes
- Nullable/undefined assertions that may hide failures

**Before proceeding:**
1. Is this making the test pass by lowering expectations?
2. Should you fix the implementation instead?
3. If skipping is intentional, have you discussed with the user?

**TDD principle:** Fix the code to pass the test, not the test to pass the code.
