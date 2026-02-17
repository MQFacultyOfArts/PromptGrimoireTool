# UAT Walkthrough — Workspace ACL (#96)

Interactive manual testing guide. Uses mock auth (`DEV__AUTH_MOCK=true`).
Two browser sessions needed: **Browser A** (student) and **Browser B** (instructor/admin).

Use Chrome + an Incognito window, or Chrome + Firefox — each needs its own session cookie.

## Prerequisites

```bash
# 1. Start the app (auto-creates DB, migrates, seeds)
uv run python -m promptgrimoire

# 2. Verify seed data users exist
uv run manage-users list --all
```

Expected: 4 users — instructor@uni.edu (coordinator), admin@example.com (coordinator),
student@uni.edu (student), test@example.com (student).

Expected: 1 course (LAWS1100), 2 weeks (Week 1 published, Week 2 draft),
1 activity ("Annotate Becky Bennett Interview") in Week 1.

---

## Test 1: Reference Tables (AC1) — Confirm

**In terminal:**
```bash
uv run python -c "
import asyncio
from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Permission, CourseRoleRef
from sqlmodel import select

async def check():
    async with get_session() as s:
        perms = (await s.exec(select(Permission).order_by(Permission.level))).all()
        roles = (await s.exec(select(CourseRoleRef).order_by(CourseRoleRef.level))).all()
        print('Permissions:')
        for p in perms: print(f'  {p.name}: level={p.level}')
        print('Roles:')
        for r in roles: print(f'  {r.name}: level={r.level}, is_staff={r.is_staff}')

asyncio.run(check())
"
```

**Expected:**
- Permissions: viewer(10), editor(20), owner(30)
- Roles: student(10, is_staff=False), tutor(20, is_staff=True), instructor(30, is_staff=True), coordinator(40, is_staff=True)

---

## Test 2: Student Cloning (AC7) — Confirm + Boundary

### 2a. Student clones workspace (happy path)

1. **Browser A:** Go to `/login`, click **"Student (student@uni.edu)"**
2. Navigate to `/courses` — should see LAWS1100
3. Click into the course — should see Week 1 with "Annotate Becky Bennett Interview"
4. Should show **"Start Activity"** button (not Resume)
5. Click **"Start Activity"**
6. Should redirect to `/annotation?workspace_id=<uuid>` — a new cloned workspace

**PAUSE** — Note the workspace UUID from the URL bar: `__________________________`

### 2b. Duplicate clone returns existing (AC7.4)

7. Go back to `/courses` → click into LAWS1100
8. Should now show **"Resume"** instead of "Start Activity"
9. Click **"Resume"** — should go to the SAME workspace UUID as step 6

### 2c. Draft week not visible to student (AC3.2)

10. Still as student — Week 2 ("Client Interviews") should NOT appear (it's unpublished)

### 2d. Non-enrolled user cannot clone (AC7.6) — Boundary

11. **Browser A:** Log out → log in as **"Test User (test@example.com)"**
12. Navigate to `/courses` — test@example.com is enrolled as student too, so they CAN see the course
13. Click "Start Activity" — should work (they're enrolled)

Now test a truly non-enrolled user:
14. Open a **new terminal** and remove test@example.com's enrollment:
```bash
uv run manage-users unenroll test@example.com LAWS1100 S1-2026
```
15. **Browser A:** Refresh `/courses` — LAWS1100 should no longer appear (or the activity should not be accessible)

16. **Restore enrollment for later tests:**
```bash
uv run manage-users enroll test@example.com LAWS1100 S1-2026 --role student
```

---

## Test 3: Permission Resolution (AC6) — Boundary

### 3a. Instructor gets enrollment-derived access

17. **Browser B:** Go to `/login`, click **"Instructor (instructor@uni.edu)"**
18. Navigate to the student's workspace URL directly:
    `/annotation?workspace_id=<UUID from step 6>`
19. Should load successfully — instructor has enrollment-derived access

### 3b. Unauthenticated user denied (AC10.1)

20. Open a **fresh incognito window** (not logged in)
21. Paste the workspace URL: `/annotation?workspace_id=<UUID from step 6>`
22. Should redirect to `/login`

### 3c. Unauthorised user denied (AC10.2)

This tests a user with NO enrollment and NO ACL entry. You need a 5th user not in the course:

```bash
# Create an outsider user
uv run python -c "
import asyncio
from promptgrimoire.db.users import find_or_create_user
async def main():
    u, created = await find_or_create_user(email='outsider@example.com', display_name='Outsider')
    print(f'id={u.id} created={created}')
asyncio.run(main())
"
```

23. **Browser B:** Log out → go to `/login`
24. In the magic link email field, type `outsider@example.com` and submit
25. Use token `mock-valid-token` (or navigate directly to `/auth/callback?token=mock-token-outsider@example.com`)
26. Navigate to the student's workspace URL
27. **Should see:** Redirect to `/courses` with notification "You do not have access to this workspace"

---

## Test 4: Admin Override (AC6.6) — Confirm

28. **Browser B:** Log out → log in as **"Admin (admin@example.com)"**
29. Navigate to the student's workspace URL: `/annotation?workspace_id=<UUID from step 6>`
30. **Should load successfully** — admin gets owner-level access regardless of ACL

---

## Test 5: Sharing Controls (AC8) — Confirm + Boundary

### 5a. Enable sharing on the activity

31. **Browser B:** Log in as **"Instructor (instructor@uni.edu)"**
32. Go to `/courses` → LAWS1100 → click the gear icon on the activity
33. Set "Allow Sharing" to **"On"**

### 5b. Owner shares workspace

There's no sharing UI yet (that's a future feature), so test via Python:

```bash
uv run python -c "
import asyncio
from promptgrimoire.db.acl import grant_share
from promptgrimoire.db.users import get_user_by_email

async def main():
    student = await get_user_by_email('student@uni.edu')
    test_user = await get_user_by_email('test@example.com')
    # Get student's workspace
    from promptgrimoire.db.acl import list_entries_for_user
    entries = await list_entries_for_user(student.id)
    ws_entry = [e for e in entries if e.permission == 'owner'][0]

    # Student (owner) shares with test_user as viewer
    result = await grant_share(
        workspace_id=ws_entry.workspace_id,
        grantor_id=student.id,
        recipient_id=test_user.id,
        permission='viewer',
    )
    print(f'Shared: {result}')

asyncio.run(main())
"
```

### 5c. Non-owner cannot share (AC8.7) — Boundary

```bash
uv run python -c "
import asyncio
from promptgrimoire.db.acl import grant_share
from promptgrimoire.db.users import get_user_by_email

async def main():
    test_user = await get_user_by_email('test@example.com')
    student = await get_user_by_email('student@uni.edu')
    # Get test_user's VIEWER entry
    from promptgrimoire.db.acl import list_entries_for_user
    entries = await list_entries_for_user(test_user.id)
    ws = [e for e in entries if e.permission == 'viewer'][0]

    # test_user (viewer) tries to share — should fail
    try:
        await grant_share(
            workspace_id=ws.workspace_id,
            grantor_id=test_user.id,
            recipient_id=student.id,
            permission='viewer',
        )
        print('ERROR: Should have been rejected!')
    except Exception as e:
        print(f'Correctly rejected: {e}')

asyncio.run(main())
"
```

**Should see:** Rejection (not an owner).

---

## Test 6: Real-Time Revocation (AC10.5, AC10.6) — Boundary

This is the most interesting test. Requires the app to be running.

34. **Browser A:** Log in as **test@example.com**
35. Navigate to student@uni.edu's shared workspace (the one shared in Test 5b)
    — It should load (test_user has viewer access)
36. **Keep Browser A open on the workspace page**

37. **In a new terminal** — revoke access while test_user is connected:
```bash
uv run python -c "
import asyncio
from promptgrimoire.db.acl import revoke_permission
from promptgrimoire.db.users import get_user_by_email
from promptgrimoire.pages.annotation.broadcast import revoke_and_redirect

async def main():
    test_user = await get_user_by_email('test@example.com')
    from promptgrimoire.db.acl import list_entries_for_user
    entries = await list_entries_for_user(test_user.id)
    viewer_entry = [e for e in entries if e.permission == 'viewer'][0]

    deleted = await revoke_permission(
        viewer_entry.workspace_id,
        test_user.id,
        on_revoke=revoke_and_redirect,
    )
    print(f'Revoked: {deleted}')

asyncio.run(main())
"
```

**IMPORTANT:** This script runs in a **separate process** from the NiceGUI server,
so `revoke_and_redirect` won't find the client in the in-process presence registry.
The revocation will succeed in the DB but the push notification won't fire cross-process.

**To test the live push**, you'd need to call `revoke_permission(..., on_revoke=revoke_and_redirect)`
from within the running server process (e.g. from an instructor's UI action). Since there's
no revocation UI yet, the cross-process limitation means:

- **DB revocation works** — verified by automated tests
- **Push redirect works** — verified by integration test with mocked client registry
- **Next page load denied** — verify manually:

38. **Browser A:** After running the revoke script, **refresh the page**
39. **Should see:** Redirect to `/courses` with "You do not have access to this workspace"

---

## Test 7: Course Settings UI (AC8.3–AC8.5) — Confirm

40. **Browser B:** Log in as instructor
41. `/courses` → LAWS1100 → click course settings (gear icon on course card)
42. Toggle **"Allow Sharing"** (course default) — should be a switch
43. Click the activity gear → "Allow Sharing" should show tri-state: "Inherit from course" / "On" / "Off"
44. Set activity to "Inherit from course", course to Off → sharing should be off
45. Set activity to "On", course to Off → sharing should be on (override)

---

## Test 8: Week Visibility for Staff (AC3.2) — Confirm

46. **Browser B:** As instructor, navigate to LAWS1100
47. Should see **both** Week 1 and Week 2 (staff sees draft weeks)
48. **Browser A:** As student, navigate to LAWS1100
49. Should see **only** Week 1 (students don't see unpublished weeks)

---

## Summary

| # | Test | Type | Result |
|---|------|------|--------|
| 1 | Reference tables seed data | Confirm | |
| 2a | Student clones workspace | Confirm | |
| 2b | Duplicate clone returns existing | Boundary | |
| 2c | Draft week hidden from student | Confirm | |
| 2d | Non-enrolled user denied | Boundary | |
| 3a | Instructor enrollment-derived access | Confirm | |
| 3b | Unauthenticated → /login | Boundary | |
| 3c | Unauthorised → /courses with notification | Boundary | |
| 4 | Admin override | Confirm | |
| 5a | Enable sharing on activity | Confirm | |
| 5b | Owner shares workspace | Confirm | |
| 5c | Non-owner share rejected | Boundary | |
| 6 | Revocation (next page load) | Boundary | |
| 7 | Course/activity sharing tri-state UI | Confirm | |
| 8 | Week visibility by role | Confirm | |

**Deferred (not testable yet):**
- Live push revocation (needs in-process trigger — no UI for instructor revoke yet, #171)
- Viewer read-only UI (#172)
- Roleplay page enforcement (#171)
