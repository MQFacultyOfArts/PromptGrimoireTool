"""Load-test data generator for workspace navigator validation.

Creates courses, users, enrollments, weeks, activities, and student workspaces
at realistic scale (1100 students) for SQL query validation and FTS testing.

Usage:
    uv run load-test-data
"""

from __future__ import annotations

import asyncio
import random
import sys
from typing import TYPE_CHECKING

from rich.console import Console
from sqlmodel import select

from promptgrimoire.config import get_settings
from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.db.activities import create_activity
from promptgrimoire.db.courses import (
    DuplicateEnrollmentError,
    create_course,
    enroll_user,
)
from promptgrimoire.db.engine import get_session, init_db
from promptgrimoire.db.models import (
    Activity,
    Course,
    Tag,
    TagGroup,
    User,
    Week,
    Workspace,
)
from promptgrimoire.db.users import find_or_create_user
from promptgrimoire.db.weeks import create_week
from promptgrimoire.db.workspace_documents import add_document

if TYPE_CHECKING:
    from uuid import UUID

console = Console()

# ---------------------------------------------------------------------------
# Text content pools
# ---------------------------------------------------------------------------

DOCUMENT_PARAGRAPHS: list[str] = [
    (
        "<p>The plaintiff suffered injuries when a defective product malfunctioned "
        "during normal use. The manufacturer had been warned of the design flaw "
        "six months prior to the incident but failed to issue a recall or modify "
        "the production line. Expert testimony confirmed that the defect was "
        "present at the time of manufacture.</p>"
    ),
    (
        "<p>Under the duty of care analysis, the defendant owed a duty to take "
        "reasonable precautions to prevent foreseeable harm. The proximity "
        "between the parties and the foreseeability of the injury establish "
        "a prima facie case of negligence. The Caparo v Dickman three-stage "
        "test is directly applicable here.</p>"
    ),
    (
        "<p>The contract was formed on 14 March when the offeree posted their "
        "acceptance. Under the postal rule established in Adams v Lindsell, "
        "acceptance takes effect upon posting, not upon receipt. The revocation "
        "letter sent on 15 March arrived too late to void the agreement.</p>"
    ),
    (
        "<p>Statutory interpretation of the Work Health and Safety Act 2011 "
        "requires that employers provide a safe working environment so far as "
        "reasonably practicable. The phrase 'reasonably practicable' has been "
        "judicially considered in numerous decisions including Slivak v Lurgi.</p>"
    ),
    (
        "<p>The High Court in Donoghue v Stevenson established the neighbour "
        "principle, which holds that a person must take reasonable care to avoid "
        "acts or omissions that could reasonably foresee would injure their "
        "neighbour. This foundational tort law case remains binding authority "
        "across common law jurisdictions.</p>"
    ),
    (
        "<p>Causation in tort requires the plaintiff to demonstrate that the "
        "defendant's breach of duty was a necessary condition of the harm "
        "suffered. The 'but for' test remains the primary mechanism for "
        "establishing factual causation, subject to the modifications "
        "introduced by the Civil Liability Act 2002.</p>"
    ),
    (
        "<p>Vicarious liability arises where an employer is held responsible "
        "for the tortious acts of an employee committed in the course of "
        "employment. The close connection test from Mohamud v WM Morrison "
        "has expanded the boundaries of what constitutes 'course of employment' "
        "beyond traditional formulations.</p>"
    ),
    (
        "<p>The measure of damages in contract is governed by the expectation "
        "interest: the plaintiff is entitled to be placed in the position they "
        "would have occupied had the contract been performed. Remoteness of "
        "damage is assessed under the rule in Hadley v Baxendale, which limits "
        "recovery to losses within the reasonable contemplation of the parties.</p>"
    ),
    (
        "<p>Equitable estoppel prevents a party from resiling from a promise "
        "or representation where the other party has relied upon it to their "
        "detriment. The doctrine, as articulated in Waltons Stores v Maher, "
        "requires unconscionability in the departure from the assumed state "
        "of affairs.</p>"
    ),
    (
        "<p>The tort of trespass to the person encompasses battery, assault, "
        "and false imprisonment. Battery requires a direct and intentional "
        "application of force to another person without consent. The element "
        "of directness distinguishes trespass from negligence actions where "
        "the harm is consequential rather than immediate.</p>"
    ),
]

COMMENT_POOL: list[str] = [
    "This establishes the duty of care owed by the defendant.",
    "Relevant to causation analysis \u2014 apply the 'but for' test here.",
    "Compare with Donoghue v Stevenson neighbour principle.",
    "Key statutory provision \u2014 note the 'reasonably practicable' standard.",
    "This paragraph identifies the legally relevant facts.",
    "The court's reasoning relies heavily on policy considerations.",
    "Note the procedural history \u2014 appeal from District Court.",
    "This is the ratio decidendi of the decision.",
    "Obiter dictum \u2014 persuasive but not binding authority.",
    "Consider whether this reasoning extends to economic loss claims.",
    "The damages assessment follows Hadley v Baxendale remoteness test.",
    "Vicarious liability analysis begins with the employment relationship.",
    "Contributory negligence may reduce damages under CLA s5R.",
    "The standard of care is that of a reasonable person in the defendant's position.",
    "Breach is established through the calculus of negligence factors.",
    "This evidence supports the plaintiff's case on factual causation.",
    "The defendant's expert contradicts this interpretation of the evidence.",
    "Jurisdictional issue \u2014 which court has original jurisdiction?",
    "The limitation period under s14 begins when the cause of action accrues.",
    "This passage illustrates the tension between corrective and distributive justice.",
]

RESPONSE_DRAFT_POOL: list[str] = [
    (
        "In this case, the plaintiff must establish that the defendant owed a "
        "duty of care, breached that duty, and that the breach caused the "
        "harm suffered. The analysis proceeds through each element sequentially."
    ),
    (
        "The key issue is whether reasonable foreseeability of harm was present "
        "at the time the defendant acted. If the type of harm was foreseeable, "
        "even if the precise manner was not, the duty of care is likely satisfied."
    ),
    (
        "Applying the Civil Liability Act 2002, the standard of care requires "
        "assessment of the probability of harm, the likely seriousness of the "
        "harm, the burden of taking precautions, and the social utility of the "
        "activity that created the risk."
    ),
    (
        "The contractual analysis turns on whether consideration was present. "
        "Past consideration is generally not valid consideration, but an "
        "exception may apply where the services were requested and payment "
        "was implicitly expected."
    ),
    (
        "Damages should be assessed under the expectation measure. The plaintiff "
        "is entitled to be put in the position they would have been in had the "
        "contract been performed. Loss of bargain damages are the primary remedy."
    ),
    (
        "The doctrine of vicarious liability applies because the employee was "
        "acting in the course of employment. The close connection test from "
        "recent authority supports a broad interpretation of this requirement."
    ),
    (
        "Contributory negligence is a partial defence that reduces the "
        "plaintiff's damages in proportion to their share of responsibility. "
        "The defendant bears the burden of establishing this defence."
    ),
    (
        "The equitable remedy of specific performance may be available where "
        "damages are inadequate. This is particularly relevant for contracts "
        "involving unique goods or interests in land."
    ),
]

LOOSE_WORKSPACE_TITLES: list[str] = [
    "My Prompt Notes",
    "Week 3 Reflections",
    "Legal Research Draft",
    "Tutorial Preparation",
    "Case Summary Notes",
    "Exam Revision Workspace",
    "Group Project Draft",
    "Practice Question Attempt",
]


# ---------------------------------------------------------------------------
# CRDT builder helper
# ---------------------------------------------------------------------------


def build_crdt_state(
    document_id: str,
    tag_names: list[str],
    student_name: str,
    content_length: int,
) -> bytes:
    """Build a CRDT annotation state with highlights, comments, and a response draft.

    Args:
        document_id: UUID string of the workspace document to annotate.
        tag_names: Tag names from the activity template (for highlight tags).
        student_name: Display name of the student (highlight/comment author).
        content_length: Character length of the document content, used to
            position highlights within valid bounds.

    Returns:
        Serialized pycrdt state bytes.
    """
    doc = AnnotationDocument(doc_id=document_id)

    # 2-5 highlights
    num_highlights = random.randint(2, 5)  # nosec B311 — test fixture, not crypto
    highlight_ids: list[str] = []

    for _ in range(num_highlights):
        if content_length < 20:
            break
        start = random.randint(0, max(0, content_length - 20))  # nosec B311
        end = min(start + random.randint(10, 50), content_length)  # nosec B311
        tag = random.choice(tag_names) if tag_names else "General"  # nosec B311
        text = f"highlighted text by {student_name}"

        hl_id = doc.add_highlight(
            start_char=start,
            end_char=end,
            tag=tag,
            text=text,
            author=student_name,
            document_id=document_id,
        )
        highlight_ids.append(hl_id)

    # 0-3 comments per highlight
    for hl_id in highlight_ids:
        num_comments = random.randint(0, 3)  # nosec B311
        for _ in range(num_comments):
            doc.add_comment(
                highlight_id=hl_id,
                author=student_name,
                text=random.choice(COMMENT_POOL),  # nosec B311
            )

    # Response draft
    draft_text = random.choice(RESPONSE_DRAFT_POOL)  # nosec B311
    rdm = doc.response_draft_markdown
    rdm += draft_text

    return doc.get_full_state()


# ---------------------------------------------------------------------------
# Dice helper
# ---------------------------------------------------------------------------


def roll_1d6_minus_2() -> int:
    """Roll 1d6-2 (min 0, max 4) for loose workspace count per student."""
    return max(0, random.randint(1, 6) - 2)  # nosec B311


# ---------------------------------------------------------------------------
# Course / user / enrollment data definitions
# ---------------------------------------------------------------------------

COURSE_DEFS: list[dict[str, object]] = [
    {
        "code": "LT-LAWS1100",
        "name": "Introduction to Torts (Load Test)",
        "semester": "2026-LT",
        "student_count": 1100,
        "default_allow_sharing": True,
        "default_anonymous_sharing": True,
    },
    {
        "code": "LT-LAWS2200",
        "name": "Contract Law (Load Test)",
        "semester": "2026-LT",
        "student_count": 80,
        "default_allow_sharing": False,
        "default_anonymous_sharing": False,
    },
    {
        "code": "LT-ARTS1000",
        "name": "Academic Skills (Load Test)",
        "semester": "2026-LT",
        "student_count": 15,
        "default_allow_sharing": False,
        "default_anonymous_sharing": False,
    },
]

INSTRUCTOR_DEFS: list[dict[str, str]] = [
    {"email": "lt-instructor-torts@test.local", "name": "Prof. Tort (LT)"},
    {"email": "lt-instructor-contract@test.local", "name": "Prof. Contract (LT)"},
    {"email": "lt-instructor-skills@test.local", "name": "Prof. Skills (LT)"},
    {"email": "lt-admin@test.local", "name": "Admin LT User"},
]

# Week definitions per course: (week_number, title, is_published)
WEEK_DEFS: dict[str, list[tuple[int, str, bool]]] = {
    "LT-LAWS1100": [
        (1, "Negligence Foundations", True),
        (2, "Duty of Care", True),
        (3, "Breach and Causation", True),
        (4, "Defences and Damages", False),
    ],
    "LT-LAWS2200": [
        (1, "Formation of Contract", True),
        (2, "Terms and Performance", True),
        (3, "Remedies for Breach", False),
    ],
    "LT-ARTS1000": [
        (1, "Academic Writing Fundamentals", True),
        (2, "Research Methods", True),
        (3, "Critical Analysis Workshop", False),
    ],
}

# Activity definitions per course: dict mapping course_code -> list of
# (week_number, activity_title) for published weeks only.
ACTIVITY_DEFS: dict[str, list[tuple[int, str]]] = {
    "LT-LAWS1100": [
        (1, "Annotate Donoghue v Stevenson"),
        (1, "Identify Duty of Care Elements"),
        (2, "Analyse Caparo v Dickman"),
        (2, "Compare Proximity Tests"),
        (2, "Draft Duty of Care Argument"),
        (3, "Apply But-For Causation Test"),
        (3, "Evaluate Civil Liability Act Provisions"),
    ],
    "LT-LAWS2200": [
        (1, "Annotate Carlill v Carbolic Smoke Ball"),
        (1, "Identify Offer and Acceptance"),
        (2, "Analyse Contractual Terms"),
        (2, "Draft Performance Assessment"),
    ],
    "LT-ARTS1000": [
        (1, "Annotate Sample Essay"),
        (1, "Practice Paragraph Structure"),
        (2, "Evaluate Research Sources"),
    ],
}

# Tag group definitions for activity templates
TAG_GROUP_DEFS: list[tuple[str, str | None, list[tuple[str, str]]]] = [
    (
        "Case Elements",
        "#4a90d9",
        [
            ("Jurisdiction", "#1f77b4"),
            ("Procedural History", "#ff7f0e"),
            ("Decision", "#e377c2"),
        ],
    ),
    (
        "Legal Analysis",
        "#d9534f",
        [
            ("Legally Relevant Facts", "#2ca02c"),
            ("Legal Issues", "#d62728"),
            ("Reasons", "#9467bd"),
            ("Court's Reasoning", "#8c564b"),
        ],
    ),
]

# Flat list of tag names for CRDT highlight assignment
ALL_TAG_NAMES: list[str] = [
    tag_name for _, _, tags in TAG_GROUP_DEFS for tag_name, _ in tags
]


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


async def _find_or_create_course(
    code: str,
    name: str,
    semester: str,
    *,
    default_allow_sharing: bool = False,
    default_anonymous_sharing: bool = False,
) -> tuple[Course, bool]:
    """Find an existing course by code+semester or create a new one.

    Returns:
        (Course, created) where created is True if newly created.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Course).where(Course.code == code).where(Course.semester == semester)
        )
        existing = result.first()
        if existing:
            return existing, False

    course = await create_course(code=code, name=name, semester=semester)

    # Set sharing defaults
    async with get_session() as session:
        session.add(course)
        course.default_allow_sharing = default_allow_sharing
        course.default_anonymous_sharing = default_anonymous_sharing
        await session.flush()
        await session.refresh(course)

    return course, True


async def _seed_tags_for_template(workspace_id: UUID) -> None:
    """Seed tag groups and tags into an activity template workspace.

    Idempotent: skips if TagGroups already exist for the workspace.
    """
    async with get_session() as session:
        result = await session.exec(
            select(TagGroup).where(TagGroup.workspace_id == workspace_id)
        )
        if result.first() is not None:
            return  # Already seeded

    async with get_session() as session:
        tag_count = 0
        for group_idx, (group_name, group_color, tags) in enumerate(TAG_GROUP_DEFS):
            group = TagGroup(
                workspace_id=workspace_id,
                name=group_name,
                color=group_color,
                order_index=group_idx,
            )
            session.add(group)
            await session.flush()

            for tag_idx, (tag_name, color) in enumerate(tags):
                tag = Tag(
                    workspace_id=workspace_id,
                    group_id=group.id,
                    name=tag_name,
                    color=color,
                    locked=True,
                    order_index=tag_idx,
                )
                session.add(tag)
                tag_count += 1

        await session.flush()

        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            workspace.next_tag_order = tag_count
            workspace.next_group_order = len(TAG_GROUP_DEFS)
            session.add(workspace)
            await session.flush()


async def _ensure_weeks(code: str, course: Course) -> dict[int, Week]:
    """Create or retrieve weeks for a course. Returns week_number -> Week map."""
    week_defs = WEEK_DEFS.get(code, [])

    async with get_session() as session:
        existing = await session.exec(select(Week).where(Week.course_id == course.id))
        existing_weeks = {w.week_number: w for w in existing.all()}

    week_map: dict[int, Week] = {}
    for week_num, title, is_published in week_defs:
        if week_num in existing_weeks:
            week_map[week_num] = existing_weeks[week_num]
            continue
        week = await create_week(course_id=course.id, week_number=week_num, title=title)
        if is_published:
            async with get_session() as session:
                session.add(week)
                week.is_published = True
                await session.flush()
                await session.refresh(week)
        week_map[week_num] = week

    return week_map


async def _ensure_activities_for_course(
    code: str,
    week_map: dict[int, Week],
) -> list[tuple[Activity, UUID]]:
    """Create or retrieve activities for published weeks of a course."""
    activity_defs = ACTIVITY_DEFS.get(code, [])
    course_activities: list[tuple[Activity, UUID]] = []

    # Check existing activities
    async with get_session() as session:
        existing_acts = await session.exec(
            select(Activity).where(
                Activity.week_id.in_([w.id for w in week_map.values()])  # type: ignore[union-attr]
            )
        )
        existing_act_titles = {a.title for a in existing_acts.all()}

    for week_num, act_title in activity_defs:
        week = week_map.get(week_num)
        if week is None or not week.is_published:
            continue

        if act_title in existing_act_titles:
            async with get_session() as session:
                result = await session.exec(
                    select(Activity)
                    .where(Activity.week_id == week.id)
                    .where(Activity.title == act_title)
                )
                act = result.first()
                if act:
                    course_activities.append((act, act.template_workspace_id))
            continue

        activity = await create_activity(week_id=week.id, title=act_title)
        tmpl_id = activity.template_workspace_id

        # Add 2-3 documents to template workspace
        num_docs = random.randint(2, 3)  # nosec B311
        paragraphs = random.sample(  # nosec B311
            DOCUMENT_PARAGRAPHS, min(num_docs * 2, len(DOCUMENT_PARAGRAPHS))
        )
        for doc_idx in range(num_docs):
            start = doc_idx * 2
            content = "\n".join(paragraphs[start : start + 2])
            await add_document(
                workspace_id=tmpl_id,
                type="source",
                content=content,
                source_type="html",
                title=f"Document {doc_idx + 1}",
            )

        await _seed_tags_for_template(tmpl_id)
        course_activities.append((activity, tmpl_id))

    return course_activities


async def _create_weeks_and_activities(
    courses: dict[str, Course],
) -> dict[str, list[tuple[Activity, UUID]]]:
    """Create weeks and activities for all courses.

    Returns:
        Dict mapping course_code -> list of (Activity, template_workspace_id)
        for published-week activities only.
    """
    result_map: dict[str, list[tuple[Activity, UUID]]] = {}

    for code, course in courses.items():
        week_map = await _ensure_weeks(code, course)
        console.print(f"  [green]Weeks:[/] {len(week_map)} for {code}")

        course_activities = await _ensure_activities_for_course(code, week_map)
        result_map[code] = course_activities
        console.print(f"  [green]Activities:[/] {len(course_activities)} for {code}")

    return result_map


# ---------------------------------------------------------------------------
# Main async phases
# ---------------------------------------------------------------------------


async def _seed_courses() -> dict[str, Course]:
    """Phase 1: Create or find courses."""
    console.print("[bold cyan]Phase 1: Courses[/]")
    courses: dict[str, Course] = {}
    for cdef in COURSE_DEFS:
        course, created = await _find_or_create_course(
            code=str(cdef["code"]),
            name=str(cdef["name"]),
            semester=str(cdef["semester"]),
            default_allow_sharing=bool(cdef.get("default_allow_sharing", False)),
            default_anonymous_sharing=bool(
                cdef.get("default_anonymous_sharing", False)
            ),
        )
        courses[str(cdef["code"])] = course
        status = "[green]Created" if created else "[yellow]Exists"
        console.print(f"  {status}:[/] {cdef['code']} (id={course.id})")
    return courses


async def _seed_instructors(courses: dict[str, Course]) -> None:
    """Phase 2: Create instructors and enroll them."""
    console.print("\n[bold cyan]Phase 2: Instructors[/]")
    course_codes = list(courses.keys())

    for i, idef in enumerate(INSTRUCTOR_DEFS[:-1]):
        user, created = await find_or_create_user(
            email=idef["email"], display_name=idef["name"]
        )
        status = "[green]Created" if created else "[yellow]Exists"
        console.print(f"  {status}:[/] {idef['email']}")

        if i < len(course_codes):
            try:
                await enroll_user(
                    course_id=courses[course_codes[i]].id,
                    user_id=user.id,
                    role="coordinator",
                )
                console.print(
                    f"    [green]Enrolled:[/] coordinator in {course_codes[i]}"
                )
            except DuplicateEnrollmentError:
                console.print(f"    [yellow]Already enrolled:[/] {course_codes[i]}")

    # Admin user -- enrolled in all courses
    admin_def = INSTRUCTOR_DEFS[-1]
    admin_user, admin_created = await find_or_create_user(
        email=admin_def["email"], display_name=admin_def["name"]
    )
    if not admin_user.is_admin:
        admin_user.is_admin = True
        async with get_session() as session:
            session.add(admin_user)
            await session.commit()
    status = "[green]Created" if admin_created else "[yellow]Exists"
    console.print(f"  {status}:[/] {admin_def['email']} (admin)")

    for code, course in courses.items():
        try:
            await enroll_user(
                course_id=course.id,
                user_id=admin_user.id,
                role="coordinator",
            )
            console.print(f"    [green]Enrolled:[/] coordinator in {code}")
        except DuplicateEnrollmentError:
            console.print(f"    [yellow]Already enrolled:[/] {code}")


def _student_range_for_course(code: str, count: int) -> list[int] | range:
    """Compute student index range for a course code."""
    if code == "LT-LAWS1100":
        return range(1, count + 1)
    if code == "LT-LAWS2200":
        # Students 1-40 (overlap with LAWS1100) + 1101-1140 (unique)
        return list(range(1, 41)) + list(range(1101, 1101 + count - 40))
    if code == "LT-ARTS1000":
        return range(1141, 1141 + count)
    return []


async def _seed_students(
    courses: dict[str, Course],
) -> tuple[dict[str, User], dict[str, list[str]], int]:
    """Phase 3: Create students and enroll them.

    Returns:
        (all_students dict, student_courses dict, total_student_count)
    """
    console.print("\n[bold cyan]Phase 3: Students[/]")
    all_students: dict[str, User] = {}
    student_courses: dict[str, list[str]] = {}
    total_student_count = 0

    for cdef in COURSE_DEFS:
        code = str(cdef["code"])
        count = int(cdef["student_count"])  # type: ignore[arg-type]
        s_range = _student_range_for_course(code, count)

        enrolled_count = 0
        for i in s_range:
            email = f"loadtest-{i}@test.local"
            if email not in all_students:
                user, _ = await find_or_create_user(
                    email=email,
                    display_name=f"Load Test Student {i}",
                )
                all_students[email] = user
                student_courses[email] = []
                total_student_count += 1

            try:
                await enroll_user(
                    course_id=courses[code].id,
                    user_id=all_students[email].id,
                    role="student",
                )
                student_courses[email].append(code)
                enrolled_count += 1
            except DuplicateEnrollmentError:
                student_courses.setdefault(email, [])
                if code not in student_courses[email]:
                    student_courses[email].append(code)

        console.print(f"  [green]{code}:[/] {enrolled_count} students enrolled")

    console.print(f"  [green]Total unique students:[/] {total_student_count}")
    return all_students, student_courses, total_student_count


async def _async_load_test_data() -> None:
    """Main async entry point for load-test data generation."""
    await init_db()
    console.print("[bold]Creating load-test data...[/]\n")

    courses = await _seed_courses()
    await _seed_instructors(courses)
    _all_students, _student_courses, total_student_count = await _seed_students(courses)

    console.print("\n[bold cyan]Phase 4: Weeks & Activities[/]")
    course_activities = await _create_weeks_and_activities(courses)

    console.print("\n[bold green]Load-test courses, users, and enrollments created.[/]")
    console.print(f"  Courses: {len(courses)}")
    console.print(f"  Instructors: {len(INSTRUCTOR_DEFS)}")
    console.print(f"  Students: {total_student_count}")
    total_activities = sum(len(acts) for acts in course_activities.values())
    console.print(f"  Activities: {total_activities}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def load_test_data() -> None:
    """Generate load-test data for workspace navigator validation.

    Creates courses, users, enrollments, weeks, and activities at
    realistic scale (1100 students). Idempotent: safe to run repeatedly.

    Usage:
        uv run load-test-data
    """
    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    asyncio.run(_async_load_test_data())
