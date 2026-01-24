# Code Review: Course/Week RBAC Feature

**Branch:** `claude/setup-async-development-8PY63`
**Reviewer:** Code Review Agent
**Date:** 2026-01-24
**Status:** CHANGES REQUIRED

---

## Executive Summary

This PR implements a Course/Week RBAC (Role-Based Access Control) system with the following components:
- Three new database models: `Course`, `CourseEnrollment`, `Week`
- CRUD service modules for courses and weeks
- NiceGUI pages for course management
- Migration adding three new tables
- Integration tests for the database layer

**Overall Assessment: NOT READY FOR MERGE**

The feature implements the core RBAC logic correctly, but contains several critical issues that must be resolved before merge:

1. **Data integrity vulnerability:** Missing unique constraint allows duplicate enrollments
2. **Race conditions:** Read-modify-write patterns without proper locking
3. **Session isolation issues:** Multi-call database operations can see stale data
4. **Missing model exports:** New models not exported from `db/__init__.py`

The code is well-structured and follows existing patterns, but the issues above could cause data corruption in production.

---

## Critical Issues (Must Fix Before Merge)

### CRIT-1: Missing Unique Constraint on CourseEnrollment

**File:** `alembic/versions/adb0f2ee06fa_add_course_week_enrollment_tables.py:40-61`
**File:** `src/promptgrimoire/db/models.py:222-243`

The `CourseEnrollment` table lacks a unique constraint on `(course_id, member_id)`. This allows duplicate enrollments, violating the invariant that each member has at most one enrollment per course.

**Current migration (lines 40-61):**
```python
op.create_table(
    "course_enrollment",
    sa.Column("id", sa.Uuid(), nullable=False),
    sa.Column("course_id", sa.Uuid(), nullable=False),
    sa.Column("member_id", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column("role", ..., nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(["course_id"], ["course.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id"),
)
```

**Required fix - add unique constraint:**
```python
op.create_table(
    "course_enrollment",
    sa.Column("id", sa.Uuid(), nullable=False),
    sa.Column("course_id", sa.Uuid(), nullable=False),
    sa.Column("member_id", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column("role", ..., nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(["course_id"], ["course.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("course_id", "member_id", name="uq_course_enrollment_course_member"),
)
```

**Model fix (`models.py`):**
```python
class CourseEnrollment(SQLModel, table=True):
    __tablename__ = "course_enrollment"
    __table_args__ = (
        UniqueConstraint("course_id", "member_id", name="uq_course_enrollment_course_member"),
    )
    # ... rest of fields
```

---

### CRIT-2: Race Conditions in Read-Modify-Write Operations

**Files:**
- `src/promptgrimoire/db/courses.py:87-102` (`archive_course`)
- `src/promptgrimoire/db/courses.py:216-244` (`update_member_role`)
- `src/promptgrimoire/db/weeks.py:78-93` (`publish_week`)
- `src/promptgrimoire/db/weeks.py:96-111` (`unpublish_week`)
- `src/promptgrimoire/db/weeks.py:114-135` (`schedule_week_visibility`)
- `src/promptgrimoire/db/weeks.py:138-153` (`clear_week_schedule`)
- `src/promptgrimoire/db/weeks.py:156-184` (`update_week`)

All these functions follow a dangerous pattern:
1. Read entity with `session.get()`
2. Modify in Python memory
3. Write back without checking if data changed

**Example - `archive_course()` (lines 87-102):**
```python
async def archive_course(course_id: UUID) -> bool:
    async with get_session() as session:
        course = await session.get(Course, course_id)  # Read
        if not course:
            return False
        course.is_archived = True  # Modify in memory
        session.add(course)  # Write (no version check)
        return True
```

**Issue:** If two requests try to archive the same course simultaneously, both succeed without conflict detection. While archiving is idempotent, this pattern is dangerous for `update_member_role` where concurrent updates could lead to lost updates.

**Recommended fix - use SELECT FOR UPDATE:**
```python
async def archive_course(course_id: UUID) -> bool:
    async with get_session() as session:
        result = await session.exec(
            select(Course)
            .where(Course.id == course_id)
            .with_for_update()
        )
        course = result.first()
        if not course:
            return False
        course.is_archived = True
        session.add(course)
        return True
```

---

### CRIT-3: Session Boundary Violation in `get_visible_weeks()`

**File:** `src/promptgrimoire/db/weeks.py:204-255`

The function makes two separate database calls with independent sessions:

```python
async def get_visible_weeks(
    course_id: UUID,
    member_id: str,
) -> list[Week]:
    # Call 1: Opens and closes session
    enrollment = await get_enrollment(course_id=course_id, member_id=member_id)
    if not enrollment:
        return []

    # Call 2: Opens new session
    async with get_session() as session:
        if enrollment.role in (...):
            # Use enrollment.role from CLOSED session
            result = await session.exec(...)
```

**Issue:** The enrollment role is checked after the first session closes. In the time between:
1. An admin could change the user's role
2. The user could be unenrolled

The code would then use stale role information to determine visibility.

**Recommended fix - single session:**
```python
async def get_visible_weeks(
    course_id: UUID,
    member_id: str,
) -> list[Week]:
    async with get_session() as session:
        # Get enrollment within same session
        result = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.member_id == member_id)
        )
        enrollment = result.first()
        if not enrollment:
            return []

        # Now use the same session for weeks query
        if enrollment.role in (...):
            result = await session.exec(...)
```

---

### CRIT-4: Same Issue in `can_access_week()`

**File:** `src/promptgrimoire/db/weeks.py:258-293`

```python
async def can_access_week(
    week_id: UUID,
    member_id: str,
) -> bool:
    async with get_session() as session:
        week = await session.get(Week, week_id)
        if not week:
            return False

        # This opens a NEW session internally!
        enrollment = await get_enrollment(course_id=week.course_id, member_id=member_id)
```

The `get_enrollment()` call at line 276 opens a new session, breaking transaction isolation.

**Required fix:** Inline the enrollment query within the same session.

---

### CRIT-5: Missing Model Exports

**File:** `src/promptgrimoire/db/__init__.py`

The new models (`Course`, `CourseEnrollment`, `Week`, `CourseRole`) are not exported from the package's `__init__.py`, breaking the established pattern where all models are exported for external use.

**Current exports (lines 24-31):**
```python
from promptgrimoire.db.models import (
    AnnotationDocumentState,
    Class,
    Conversation,
    Highlight,
    HighlightComment,
    User,
)
```

**Required addition:**
```python
from promptgrimoire.db.models import (
    AnnotationDocumentState,
    Class,
    Conversation,
    Course,
    CourseEnrollment,
    CourseRole,
    Highlight,
    HighlightComment,
    User,
    Week,
)
```

Also update `__all__` to include the new exports.

---

## High Priority Issues

### HIGH-1: Duplicate Enrollment Not Prevented at Service Layer

**File:** `src/promptgrimoire/db/courses.py:105-129`

Even with the unique constraint (CRIT-1), the `enroll_member()` function doesn't check for existing enrollment before inserting. This will cause an `IntegrityError` exception to propagate to the caller.

**Current code:**
```python
async def enroll_member(
    course_id: UUID,
    member_id: str,
    role: CourseRole = CourseRole.student,
) -> CourseEnrollment:
    async with get_session() as session:
        enrollment = CourseEnrollment(...)
        session.add(enrollment)  # Will throw on duplicate
        await session.flush()
        await session.refresh(enrollment)
        return enrollment
```

**Recommended fix - use upsert or check-then-insert:**
```python
async def enroll_member(
    course_id: UUID,
    member_id: str,
    role: CourseRole = CourseRole.student,
) -> CourseEnrollment:
    async with get_session() as session:
        # Check for existing enrollment
        existing = await session.exec(
            select(CourseEnrollment)
            .where(CourseEnrollment.course_id == course_id)
            .where(CourseEnrollment.member_id == member_id)
        )
        if existing.first():
            raise ValueError(f"Member {member_id} is already enrolled in course {course_id}")

        enrollment = CourseEnrollment(...)
        session.add(enrollment)
        await session.flush()
        await session.refresh(enrollment)
        return enrollment
```

---

### HIGH-2: Inconsistent Role Authorization Checks

**Files:**
- `src/promptgrimoire/pages/courses.py:197-201` (tutors can see instructor UI)
- `src/promptgrimoire/pages/courses.py:309-314` (tutors cannot create weeks)

In `course_detail_page()`:
```python
is_instructor = enrollment.role in (
    CourseRole.coordinator,
    CourseRole.instructor,
    CourseRole.tutor,  # Tutors see "Add Week" button
)
```

But in `create_week_page()`:
```python
if not enrollment or enrollment.role not in (
    CourseRole.coordinator,
    CourseRole.instructor,  # Tutors EXCLUDED
):
    ui.label("Only instructors can add weeks")
```

**Issue:** Tutors see the "Add Week" button but get an error when clicking it. This is a poor UX and indicates inconsistent authorization logic.

**Recommended fix:** Create a centralized permission check:
```python
def can_manage_content(role: CourseRole) -> bool:
    """Check if role can manage course content (create/edit weeks)."""
    return role in (CourseRole.coordinator, CourseRole.instructor)

def can_view_all_content(role: CourseRole) -> bool:
    """Check if role can view unpublished content."""
    return role in (CourseRole.coordinator, CourseRole.instructor, CourseRole.tutor)
```

---

### HIGH-3: Week Number Not Unique Per Course

**File:** `src/promptgrimoire/db/models.py:246-272`

Multiple weeks can have the same `week_number` within a course. The model has no unique constraint:

```python
class Week(SQLModel, table=True):
    course_id: UUID = Field(sa_column=_cascade_fk_column("course.id"))
    week_number: int = Field(ge=1, le=52)
    # No UniqueConstraint on (course_id, week_number)
```

**Required fix:**
```python
class Week(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("course_id", "week_number", name="uq_week_course_number"),
    )
```

And a corresponding migration.

---

### HIGH-4: No Logging in Database Service Functions

**Files:**
- `src/promptgrimoire/db/courses.py` (entire file)
- `src/promptgrimoire/db/weeks.py` (entire file)

Neither file includes any logging. Failed operations, edge cases, and successful mutations should be logged for debugging and audit purposes.

**Example fix:**
```python
import logging

logger = logging.getLogger(__name__)

async def create_course(...) -> Course:
    async with get_session() as session:
        course = Course(...)
        session.add(course)
        await session.flush()
        await session.refresh(course)
        logger.info("Created course %s: %s (%s)", course.id, course.code, course.semester)
        return course
```

---

## Medium Priority Issues

### MED-1: HTML Not Escaped in PDF Export

**File:** `src/promptgrimoire/export/pdf.py:183-201`

The `_build_annotation_card()` function inserts user-controlled content directly into HTML:

```python
def _build_annotation_card(annotation: Annotation, include_para_ref: bool) -> str:
    parts = [f'<div class="annotation-card">']
    parts.append(f'<span class="tag {annotation.tag}">{annotation.tag}</span>')
    # ...
    parts.append(f'<div class="quoted-text">"{quoted}"</div>')

    if annotation.comment:
        parts.append(f'<div class="comment">{annotation.comment}</div>')  # XSS risk
```

While this is rendered to PDF (not displayed in browser), unescaped HTML could:
1. Break PDF layout with malformed HTML
2. Inject styles that hide content
3. Cause WeasyPrint parsing errors

**Recommended fix:**
```python
from html import escape

def _build_annotation_card(annotation: Annotation, include_para_ref: bool) -> str:
    parts = [f'<div class="annotation-card">']
    parts.append(f'<span class="tag {escape(annotation.tag)}">{escape(annotation.tag)}</span>')
    # ...
    if annotation.comment:
        parts.append(f'<div class="comment">{escape(annotation.comment)}</div>')
```

---

### MED-2: Magic Numbers in CSS Constants

**File:** `src/promptgrimoire/export/pdf.py:40-180`

The CSS contains many hardcoded values:
- `150` characters for text truncation (line 193)
- Various `cm`, `pt` sizes without constants

**Recommendation:** Extract these to named constants at the top of the file:
```python
MAX_QUOTED_TEXT_LENGTH = 150
SIDEBAR_MIN_WIDTH = "6cm"
SIDEBAR_MAX_WIDTH = "8cm"
```

---

### MED-3: Imports Inside Functions

**File:** `src/promptgrimoire/pages/courses.py` (multiple locations)

While lazy imports in NiceGUI page handlers are documented as necessary to avoid circular imports, they can mask import errors until runtime:

```python
@ui.page("/courses")
async def courses_list_page() -> None:
    # ...
    from promptgrimoire.db.courses import list_courses, list_member_enrollments  # Line 60
    from promptgrimoire.db.engine import init_db  # Line 61
    from promptgrimoire.db.models import CourseRole  # Line 62
```

**Recommendation:** Add an import test to ensure these imports don't fail:
```python
def test_courses_page_imports() -> None:
    """Verify all lazy imports in courses.py are valid."""
    from promptgrimoire.db.courses import list_courses, list_member_enrollments
    from promptgrimoire.db.engine import init_db
    from promptgrimoire.db.models import CourseRole
    from promptgrimoire.db.weeks import get_visible_weeks
    # etc.
```

---

### MED-4: No Input Validation on Course/Week Creation

**Files:**
- `src/promptgrimoire/pages/courses.py:132-153` (`submit()` in create_course_page)
- `src/promptgrimoire/pages/courses.py:329-341` (`submit()` in create_week_page)

The form validation only checks for empty values:
```python
if not code.value or not name.value or not semester.value:
    ui.notify("All fields are required", type="negative")
    return
```

Missing validations:
- Course code format (e.g., "LAWS" + 4 digits)
- Semester format (e.g., "YYYY-S[1-3]")
- Week title length
- SQL injection (handled by ORM, but explicit validation is better)

---

## Test Quality Issues

### TEST-1: No E2E Tests for Course Pages

**Missing file:** `tests/e2e/test_courses.py`

The new routes have no end-to-end tests:
- `/courses`
- `/courses/new`
- `/courses/{id}`
- `/courses/{id}/weeks/new`
- `/courses/{id}/enrollments`

**Required:** Add Playwright tests for the happy path and key error cases.

---

### TEST-2: No Concurrent Operation Tests

**File:** `tests/integration/test_course_service.py`

All tests operate sequentially with a single user. Missing tests:
- Two users enrolling simultaneously
- Publish/unpublish race condition
- Concurrent role updates

**Example test to add:**
```python
@pytest.mark.asyncio
async def test_concurrent_enrollment_raises_on_duplicate(self) -> None:
    """Second concurrent enrollment should fail."""
    from promptgrimoire.db.courses import create_course, enroll_member

    course = await create_course(code="LAWS1234", name="Test", semester="2025-S1")
    member_id = f"member-{uuid4().hex[:8]}"

    # Simulate concurrent enrollment
    results = await asyncio.gather(
        enroll_member(course_id=course.id, member_id=member_id),
        enroll_member(course_id=course.id, member_id=member_id),
        return_exceptions=True,
    )

    # One should succeed, one should fail
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1
    assert len(failures) == 1
```

---

### TEST-3: Missing Negative Authorization Tests

**File:** `tests/integration/test_course_service.py`

The visibility tests are good, but missing:
- Test that students can't access unpublished weeks via `can_access_week()`
- Test that unenrolled users get empty list from `get_visible_weeks()`
- Test behavior when enrollment is deleted mid-session

---

### TEST-4: Test Assertions Could Be Stronger

**File:** `tests/integration/test_course_service.py:249-254`

```python
async def test_list_enrollments_for_member(self) -> None:
    # ...
    enrollments = await list_member_enrollments(member_id)

    assert len(enrollments) >= 2  # Weak assertion
```

The `>= 2` assertion doesn't catch if extra enrollments leak from other tests. Use exact counts with UUID-scoped test data.

---

## Checklist

### Before Merge (Blocking)

- [ ] Add unique constraint on `(course_id, member_id)` to CourseEnrollment
- [ ] Add unique constraint on `(course_id, week_number)` to Week
- [ ] Fix session boundary violation in `get_visible_weeks()`
- [ ] Fix session boundary violation in `can_access_week()`
- [ ] Export new models from `db/__init__.py`
- [ ] Add duplicate enrollment check in `enroll_member()`
- [ ] Fix inconsistent tutor authorization (remove "Add Week" button for tutors OR allow them to create weeks)

### Before Production (High Priority)

- [ ] Add SELECT FOR UPDATE to read-modify-write operations
- [ ] Add logging to service functions
- [ ] Add E2E tests for course pages
- [ ] Add concurrent operation tests
- [ ] Escape HTML in PDF export

### Nice to Have (Medium Priority)

- [ ] Extract CSS magic numbers to constants
- [ ] Add input validation for course/week forms
- [ ] Add import test for lazy imports
- [ ] Strengthen test assertions

---

## Verification Steps

After fixes are applied, verify with:

```bash
# 1. Run migrations on clean database
TEST_DATABASE_URL="..." uv run alembic upgrade head

# 2. Verify unique constraints exist
psql $TEST_DATABASE_URL -c "\d course_enrollment"
# Should show: uq_course_enrollment_course_member UNIQUE (course_id, member_id)

psql $TEST_DATABASE_URL -c "\d week"
# Should show: uq_week_course_number UNIQUE (course_id, week_number)

# 3. Run full test suite
uv run pytest tests/integration/test_course_service.py -v

# 4. Test duplicate enrollment fails
# (Add test and run it)

# 5. Verify exports
python -c "from promptgrimoire.db import Course, CourseEnrollment, Week, CourseRole; print('OK')"
```

---

## Notes for Future Work

1. **Audit logging:** Consider adding an audit log for enrollment changes and course modifications.

2. **Bulk operations:** The current API creates enrollments one at a time. For class imports, consider a bulk enrollment endpoint.

3. **Soft delete for enrollments:** Currently enrollments are hard-deleted. Consider soft delete for audit trail.

4. **Caching:** Week visibility queries could be cached since they're read-heavy. Consider Redis or in-memory caching with TTL.

5. **API layer:** The current implementation is UI-only. A REST/GraphQL API would enable mobile apps and integrations.

---

## Summary

| Category | Count |
|----------|-------|
| Critical | 5 |
| High | 4 |
| Medium | 4 |
| Test Issues | 4 |

**Recommendation:** Request changes. The critical issues must be addressed before this code can be safely merged to main.
