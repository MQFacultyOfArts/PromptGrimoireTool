# Course & Week RBAC Architecture

## Overview

PromptGrimoire uses a layered authorization model:
- **Stytch B2B** handles authentication and org-level roles
- **Our DB** handles course enrollment and week visibility

All users are members of the single MQ (Macquarie University) organization.

## Authorization Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Stytch B2B                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Organization: MQ                                                     │   │
│  │ Roles: admin, instructor, student                                    │   │
│  │ Provides: authentication, session management, org membership         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PromptGrimoire DB                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ CourseEnrollment: maps Stytch member_id → course + role             │   │
│  │ Week: visibility controlled by is_published + visible_from          │   │
│  │ Provides: course scoping, time-based visibility, fine-grained access │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Stytch Roles (Capability)

| Role | Description | Org-level Permissions |
|------|-------------|----------------------|
| `admin` | System administrator | Full org access, manage members |
| `instructor` | Course coordinator/lecturer | Can create courses, manage enrollments |
| `student` | Enrolled student | Can access enrolled courses |

These roles answer: **"What can this person do?"**

## Course Enrollment (Scope)

CourseEnrollment maps a Stytch member to a specific course with a course-level role:

| Course Role | Description |
|-------------|-------------|
| `coordinator` | Course owner, can manage all aspects |
| `instructor` | Can manage content, see all student work |
| `tutor` | Can see assigned tutorial groups |
| `student` | Can access published content |

This answers: **"Which courses can this person access, and with what permissions?"**

## Week Visibility

Weeks have two visibility controls:

```python
class Week:
    is_published: bool      # Master switch - False means hidden from students
    visible_from: datetime  # Optional - auto-publish at this time
```

### Visibility Rules

| Viewer | Sees Week When |
|--------|----------------|
| `coordinator` / `instructor` | Always (for their enrolled courses) |
| `tutor` | Always (for their enrolled courses) |
| `student` | `is_published AND (visible_from is None OR visible_from <= now())` |
| `admin` | Always (org-wide) |

## Data Model

### Course

```python
class Course(SQLModel, table=True):
    id: uuid.UUID
    code: str              # e.g., "LAWS1100"
    name: str              # e.g., "Contracts"
    semester: str          # e.g., "2025-S1"
    created_at: datetime
    is_archived: bool = False
```

### CourseEnrollment

```python
class CourseEnrollment(SQLModel, table=True):
    id: uuid.UUID
    course_id: uuid.UUID   # FK to Course
    member_id: str         # Stytch member_id
    role: CourseRole       # coordinator, instructor, tutor, student
    created_at: datetime
```

### Week

```python
class Week(SQLModel, table=True):
    id: uuid.UUID
    course_id: uuid.UUID   # FK to Course
    week_number: int       # 1-13 typically
    title: str             # e.g., "Introduction to Contract Law"
    is_published: bool = False
    visible_from: datetime | None = None
    created_at: datetime
```

## Authorization Flow

```
1. User authenticates via Stytch
   └─► Get session with member_id and org roles

2. User requests /course/{course_id}/week/{week_id}
   └─► Check CourseEnrollment for member_id + course_id
       └─► If not enrolled: 403 Forbidden
       └─► If enrolled as student: check week visibility
       └─► If enrolled as instructor+: allow access

3. Visibility check for students:
   └─► is_published == True?
       └─► visible_from is None OR visible_from <= now()?
           └─► Allow access
```

## Example Queries

### Get visible weeks for a student

```python
async def get_visible_weeks(
    session: AsyncSession,
    member_id: str,
    course_id: UUID,
) -> list[Week]:
    # First verify enrollment
    enrollment = await session.exec(
        select(CourseEnrollment)
        .where(CourseEnrollment.member_id == member_id)
        .where(CourseEnrollment.course_id == course_id)
    ).first()

    if not enrollment:
        raise HTTPException(403, "Not enrolled in course")

    # Instructors see all weeks
    if enrollment.role in (CourseRole.coordinator, CourseRole.instructor, CourseRole.tutor):
        return await session.exec(
            select(Week).where(Week.course_id == course_id)
        ).all()

    # Students see published weeks
    now = datetime.utcnow()
    return await session.exec(
        select(Week)
        .where(Week.course_id == course_id)
        .where(Week.is_published == True)
        .where(or_(Week.visible_from == None, Week.visible_from <= now))
    ).all()
```

### Check if user can access a week

```python
async def can_access_week(
    session: AsyncSession,
    member_id: str,
    week_id: UUID,
) -> bool:
    week = await session.get(Week, week_id)
    if not week:
        return False

    enrollment = await session.exec(
        select(CourseEnrollment)
        .where(CourseEnrollment.member_id == member_id)
        .where(CourseEnrollment.course_id == week.course_id)
    ).first()

    if not enrollment:
        return False

    # Instructors always have access
    if enrollment.role != CourseRole.student:
        return True

    # Students need published + visible
    if not week.is_published:
        return False

    if week.visible_from and week.visible_from > datetime.utcnow():
        return False

    return True
```

## Future Considerations

1. **Assignment-level visibility**: Same pattern as weeks
2. **Tutorial groups**: Tutors only see their assigned groups
3. **Cross-course sharing**: Instructors sharing resources across courses
4. **Audit logging**: Track who accessed what when
