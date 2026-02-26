# AAF OIDC Authentication — Phase 4: Magic Link Domain Enforcement

**Goal:** Restrict magic link login to MQ email domains

**Architecture:** UI-level domain validation in `_build_magic_link_section()` using a pure function and hardcoded domain set. Auth client unchanged. Stytch's `email_allowed_domains` provides server-side backstop (dashboard config).

**Tech Stack:** Python 3.14, NiceGUI

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-02-26

---

## Acceptance Criteria Coverage

This phase implements and tests:

### aaf-oidc-auth-188-189.AC7: Magic link domain enforcement
- **aaf-oidc-auth-188-189.AC7.1 Success:** Magic link with @mq.edu.au email sends successfully
- **aaf-oidc-auth-188-189.AC7.2 Success:** Magic link with @students.mq.edu.au email sends successfully
- **aaf-oidc-auth-188-189.AC7.3 Failure:** Magic link with @gmail.com (or any non-MQ domain) shows error message, does not send
- **aaf-oidc-auth-188-189.AC7.4 Success:** Error message tells user to use their Macquarie University email

---

## Key Files Reference

| File | Role |
|------|------|
| `src/promptgrimoire/pages/auth.py:224-273` | `_build_magic_link_section()` — add domain validation |
| `tests/unit/` | New test file or extend existing for domain validation |
| `tests/e2e/test_auth_pages.py:70-72` | Existing test verifying arbitrary domain acceptance — **must update** |
| `CLAUDE.md` | Project conventions |

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create domain validation function and add to magic link form

**Verifies:** aaf-oidc-auth-188-189.AC7.1, aaf-oidc-auth-188-189.AC7.2, aaf-oidc-auth-188-189.AC7.3, aaf-oidc-auth-188-189.AC7.4

**Files:**
- Modify: `src/promptgrimoire/pages/auth.py` — add constant and validation, modify `_build_magic_link_section()`
- Test: `tests/unit/test_magic_link_domain.py` (new file, unit)

**Implementation:**

**Part A: Add domain constant and validation function**

Near the top of `src/promptgrimoire/pages/auth.py` (with other module-level constants):

```python
_ALLOWED_MAGIC_LINK_DOMAINS: frozenset[str] = frozenset({"mq.edu.au", "students.mq.edu.au"})


def _is_allowed_magic_link_domain(email: str) -> bool:
    """Check if email domain is in the allowed set for magic links.

    Args:
        email: Email address to validate.

    Returns:
        True if domain is allowed, False otherwise.
    """
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].lower().strip()
    return domain in _ALLOWED_MAGIC_LINK_DOMAINS
```

**Part B: Add validation to `_build_magic_link_section()`**

In the `send_magic_link()` inner function (lines 243-268), after the empty-email check and before the logger.info call, add:

```python
async def send_magic_link() -> None:
    email = email_input.value
    if not email:
        ui.notify("Please enter an email address", type="warning")
        return

    if not _is_allowed_magic_link_domain(email):
        ui.notify(
            "Please use your Macquarie University email address (@mq.edu.au or @students.mq.edu.au)",
            type="warning",
        )
        return

    logger.info("Magic link requested for email=%s", email)
    # ... rest of existing code unchanged
```

**Testing:**

New test file `tests/unit/test_magic_link_domain.py`:

Tests must verify each AC:
- aaf-oidc-auth-188-189.AC7.1: `_is_allowed_magic_link_domain("user@mq.edu.au")` → True
- aaf-oidc-auth-188-189.AC7.2: `_is_allowed_magic_link_domain("student@students.mq.edu.au")` → True
- aaf-oidc-auth-188-189.AC7.3: `_is_allowed_magic_link_domain("user@gmail.com")` → False
- Additional cases: empty string → False, no @ → False, subdomain `@sub.mq.edu.au` → False, case insensitivity `@MQ.EDU.AU` → True

**Verification:**

```bash
uv run pytest tests/unit/test_magic_link_domain.py -v
uv run test-all
```

Expected: New tests pass, all existing tests pass.

**Commit:** `feat(auth): add magic link domain enforcement for MQ emails`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update E2E test for domain enforcement

**Verifies:** aaf-oidc-auth-188-189.AC7.3, aaf-oidc-auth-188-189.AC7.4

**Files:**
- Modify: `tests/e2e/test_auth_pages.py:70-72` — update test that verifies arbitrary domain acceptance

**Implementation:**

The existing E2E test at lines 70-72 explicitly verifies that `"arbitrary@anywhere.com"` is accepted:
```python
fresh_page.get_by_test_id("email-input").fill("arbitrary@anywhere.com")
fresh_page.get_by_test_id("send-magic-link-btn").click()
expect(fresh_page.get_by_text("Magic link sent")).to_be_visible()
```

This needs to be updated to:
1. Verify that `"arbitrary@anywhere.com"` is now **rejected** with the Macquarie University email message
2. Verify that `"test@mq.edu.au"` is **accepted** and sends the magic link

**Testing:**

The E2E test itself IS the test. Update the assertion:
- Fill `"arbitrary@anywhere.com"`, click send → expect warning message about Macquarie University email
- Fill `"test@mq.edu.au"`, click send → expect "Magic link sent" success message

**Verification:**

```bash
uv run test-e2e -k test_login_page
```

Expected: Updated E2E test passes.

**Commit:** `test(auth): update E2E test for magic link domain enforcement`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## Phase Completion Criteria

Phase 4 is complete when:
1. Non-MQ emails rejected with clear error message (Task 1)
2. MQ emails (@mq.edu.au, @students.mq.edu.au) accepted (Task 1)
3. Unit tests for domain validation pass (Task 1)
4. E2E test updated and passing (Task 2)
5. `uv run test-all` passes with zero failures
