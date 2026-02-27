"""Load-test data generator for workspace navigator validation.

Creates courses, users, enrollments, weeks, activities, and student workspaces
at realistic scale (1100 students) for SQL query validation and FTS testing.

Usage:
    uv run load-test-data              # full 1100-student dataset
    uv run load-test-data --validate   # 1 of each entity for smoke test
"""

from __future__ import annotations

import asyncio
import random
import sys
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from rich.console import Console
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from promptgrimoire.auth.mock import _email_to_member_id
from promptgrimoire.config import get_settings
from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.db.acl import grant_permission
from promptgrimoire.db.activities import create_activity
from promptgrimoire.db.courses import (
    DuplicateEnrollmentError,
    create_course,
    enroll_user,
)
from promptgrimoire.db.engine import get_session, init_db
from promptgrimoire.db.models import (
    ACLEntry,
    Activity,
    Course,
    CourseEnrollment,
    Tag,
    TagGroup,
    User,
    Week,
    Workspace,
    WorkspaceDocument,
)
from promptgrimoire.db.users import find_or_create_user
from promptgrimoire.db.weeks import create_week
from promptgrimoire.db.workspace_documents import add_document, list_documents
from promptgrimoire.db.workspaces import (
    create_workspace,
    place_workspace_in_activity,
    place_workspace_in_course,
    save_workspace_crdt_state,
)

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
    tag_ids: list[str],
    student_name: str,
    content_length: int,
    user_id: str | None = None,
) -> bytes:
    """Build a CRDT annotation state with highlights, comments, and a response draft.

    Args:
        document_id: UUID string of the workspace document to annotate.
        tag_ids: Tag UUID strings from the workspace (for highlight tag values).
            These must be Tag.id UUID strings, not tag names, because the
            annotation UI resolves tag display info via ``tag_options`` which
            maps ``str(tag.id)`` -> ``tag.name``.
        student_name: Display name of the student (highlight/comment author).
        content_length: Character length of the document content, used to
            position highlights within valid bounds.
        user_id: Stytch-style member ID for the student. Without this, the
            annotation page shows "Unknown" for all highlights and comments
            because ``anonymise_author`` treats missing user_id as legacy data.

    Returns:
        Serialized pycrdt state bytes.
    """
    doc = AnnotationDocument(doc_id=document_id)

    # 2-5 highlights
    num_highlights = random.randint(2, 5)  # nosec B311 -- test fixture, not crypto
    highlight_ids: list[str] = []

    for _ in range(num_highlights):
        if content_length < 20:
            break
        start = random.randint(0, max(0, content_length - 20))  # nosec B311
        end = min(start + random.randint(10, 50), content_length)  # nosec B311
        tag = random.choice(tag_ids) if tag_ids else ""  # nosec B311
        text = f"highlighted text by {student_name}"

        hl_id = doc.add_highlight(
            start_char=start,
            end_char=end,
            tag=tag,
            text=text,
            author=student_name,
            document_id=document_id,
            user_id=user_id,
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
                user_id=user_id,
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

    Sequential-only assumption: this function is always called from
    _seed_courses(), which iterates courses one at a time in a single
    async task. Concurrent callers could both see no existing course and
    both attempt create_course(), producing a unique-constraint violation.
    If that ever happens the IntegrityError is caught and the existing
    row is re-fetched so the caller still gets a valid Course object.

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

    try:
        course = await create_course(code=code, name=name, semester=semester)
    except IntegrityError:
        # Lost the race — another caller created it between our check and our
        # insert.  Re-fetch the row that won.
        async with get_session() as session:
            result = await session.exec(
                select(Course)
                .where(Course.code == code)
                .where(Course.semester == semester)
            )
            existing = result.first()
            if existing is None:
                raise  # Unexpected — re-raise so the error is visible.
            return existing, False

    # Set sharing defaults
    async with get_session() as session:
        session.add(course)
        course.default_allow_sharing = default_allow_sharing
        course.default_anonymous_sharing = default_anonymous_sharing
        await session.flush()
        await session.refresh(course)

    return course, True


async def _seed_tags_for_template(workspace_id: UUID) -> list[str]:
    """Seed tag groups and tags into a workspace and return Tag UUID strings.

    Idempotent: if TagGroups already exist for the workspace, fetches and
    returns the existing Tag UUIDs instead of inserting duplicates.

    Returns:
        List of Tag UUID strings (str(tag.id)) for use in CRDT highlights.
    """
    async with get_session() as session:
        result = await session.exec(
            select(TagGroup).where(TagGroup.workspace_id == workspace_id)
        )
        if result.first() is not None:
            # Already seeded — fetch and return existing Tag UUIDs
            tag_result = await session.exec(
                select(Tag).where(Tag.workspace_id == workspace_id)
            )
            return [str(t.id) for t in tag_result.all()]

    async with get_session() as session:
        tag_ids: list[str] = []
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
                await session.flush()
                tag_ids.append(str(tag.id))

        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            workspace.next_tag_order = len(tag_ids)
            workspace.next_group_order = len(TAG_GROUP_DEFS)
            session.add(workspace)
            await session.flush()

    return tag_ids


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

    # Check existing activities.
    # Key on (week_id, title) so the same title in two different weeks is not
    # incorrectly treated as already-existing.
    async with get_session() as session:
        existing_acts = await session.exec(
            select(Activity).where(
                Activity.week_id.in_([w.id for w in week_map.values()])  # type: ignore[union-attr]  # SQLAlchemy column expression
            )
        )
        existing_act_keys = {(a.week_id, a.title) for a in existing_acts.all()}

    for week_num, act_title in activity_defs:
        week = week_map.get(week_num)
        if week is None or not week.is_published:
            continue

        if (week.id, act_title) in existing_act_keys:
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
# Workspace generation helpers (Task 3)
# ---------------------------------------------------------------------------


async def _check_workspace_exists(activity_id: UUID, user_id: UUID) -> bool:
    """Check if a workspace already exists for a student+activity pair.

    Looks for a workspace with the given activity_id that has an owner
    ACL entry for the given user.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Workspace.id)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)  # type: ignore[arg-type]  # SQLAlchemy join expression, not a plain column
            .where(
                Workspace.activity_id == activity_id,
                ACLEntry.user_id == user_id,
                ACLEntry.permission == "owner",
            )
        )
        return result.first() is not None


async def _get_template_documents(
    template_workspace_id: UUID,
) -> list[WorkspaceDocument]:
    """Retrieve documents from a template workspace for cloning."""
    return await list_documents(template_workspace_id)


async def _seed_tags_and_crdt_state(
    workspace_id: UUID,
    user: User,
    first_doc_id: str | None,
    first_doc_content_len: int,
) -> None:
    """Seed tags into a workspace and build+save CRDT annotation state.

    Shared finalisation step for both activity and loose workspaces.
    Skipped when no document was created (first_doc_id is None).
    """
    tag_ids = await _seed_tags_for_template(workspace_id)

    if first_doc_id and first_doc_content_len > 0:
        crdt_bytes = build_crdt_state(
            document_id=first_doc_id,
            tag_ids=tag_ids,
            student_name=user.display_name or user.email,
            content_length=first_doc_content_len,
            user_id=_email_to_member_id(user.email),
        )
        await save_workspace_crdt_state(workspace_id, crdt_bytes)


async def _create_student_activity_workspace(
    activity: Activity,
    user: User,
    template_docs: list[WorkspaceDocument],
) -> tuple[UUID, int, bool]:
    """Create a student workspace for an activity, cloning template documents.

    Returns:
        (workspace_id, document_count, shared_with_class) for the created workspace.
    """
    workspace = await create_workspace()
    ws_id = workspace.id

    # Place in activity and set title
    await place_workspace_in_activity(ws_id, activity.id)
    shared_with_class = random.random() < 0.2  # nosec B311 -- ~20% chance
    async with get_session() as session:
        ws = await session.get(Workspace, ws_id)
        if ws:
            ws.title = activity.title
            ws.shared_with_class = shared_with_class
            session.add(ws)
            await session.flush()

    # Owner ACL
    await grant_permission(ws_id, user.id, "owner")

    # Clone documents with slight variation
    doc_count = 0
    first_doc_id: str | None = None
    first_doc_content_len = 0

    for tmpl_doc in template_docs:
        # Swap one paragraph from the pool for variation
        content = tmpl_doc.content
        if random.random() < 0.3:  # nosec B311 -- 30% chance of variation
            extra_para = random.choice(DOCUMENT_PARAGRAPHS)  # nosec B311
            content = content + "\n" + extra_para

        new_doc = await add_document(
            workspace_id=ws_id,
            type=tmpl_doc.type,
            content=content,
            source_type=tmpl_doc.source_type,
            title=tmpl_doc.title,
        )
        doc_count += 1

        if first_doc_id is None:
            first_doc_id = str(new_doc.id)
            first_doc_content_len = len(content)

    await _seed_tags_and_crdt_state(ws_id, user, first_doc_id, first_doc_content_len)

    return ws_id, doc_count, shared_with_class


async def _create_loose_workspace(
    user: User,
    course_id: UUID,
) -> tuple[UUID, int]:
    """Create a loose workspace (no activity) for a student in a course.

    Returns:
        (workspace_id, document_count) for the created workspace.
    """
    workspace = await create_workspace()
    ws_id = workspace.id

    # Place in course (loose -- no activity)
    await place_workspace_in_course(ws_id, course_id)

    # Set title from pool
    title = random.choice(LOOSE_WORKSPACE_TITLES)  # nosec B311
    async with get_session() as session:
        ws = await session.get(Workspace, ws_id)
        if ws:
            ws.title = title
            session.add(ws)
            await session.flush()

    # Owner ACL
    await grant_permission(ws_id, user.id, "owner")

    # Add 1-2 documents
    num_docs = random.randint(1, 2)  # nosec B311
    paragraphs = random.sample(  # nosec B311
        DOCUMENT_PARAGRAPHS, min(num_docs * 2, len(DOCUMENT_PARAGRAPHS))
    )

    first_doc_id: str | None = None
    first_doc_content_len = 0

    for doc_idx in range(num_docs):
        start = doc_idx * 2
        content = "\n".join(paragraphs[start : start + 2])
        new_doc = await add_document(
            workspace_id=ws_id,
            type="source",
            content=content,
            source_type="html",
            title=f"Notes {doc_idx + 1}",
        )

        if first_doc_id is None:
            first_doc_id = str(new_doc.id)
            first_doc_content_len = len(content)

    await _seed_tags_and_crdt_state(ws_id, user, first_doc_id, first_doc_content_len)

    return ws_id, num_docs


# Cache of course_code -> course_id resolved via the activity hierarchy.
# The Activity->Week->Course mapping is static during a load-test run, so
# there is no need to hit the database more than once per course code.
_course_id_cache: dict[str, UUID | None] = {}


async def _resolve_course_id_for_code(
    course_code: str,
    course_activities: dict[str, list[tuple[Activity, UUID]]],
) -> UUID | None:
    """Resolve a course_id from a course code via the activity hierarchy.

    Uses the first activity in the course to traverse Activity -> Week -> Course
    in a single JOIN query.  Results are cached so repeated calls for the same
    course_code cost zero additional round-trips (the mapping is static during
    a load-test run).

    Returns None if the course has no activities or the hierarchy is broken.
    """
    if course_code in _course_id_cache:
        return _course_id_cache[course_code]

    acts = course_activities.get(course_code, [])
    if not acts:
        _course_id_cache[course_code] = None
        return None

    activity_for_course = acts[0][0]
    async with get_session() as session:
        result = await session.exec(
            select(Week.course_id)
            .join(Activity, Activity.week_id == Week.id)  # type: ignore[arg-type]  # SQLAlchemy join expression, not a plain column
            .where(Activity.id == activity_for_course.id)
        )
        course_id = result.first()

    _course_id_cache[course_code] = course_id
    return course_id


async def _create_loose_workspaces_for_student(
    user: User,
    enrolled_codes: list[str],
    course_activities: dict[str, list[tuple[Activity, UUID]]],
) -> tuple[int, int]:
    """Create loose workspaces for a single student.

    Rolls 1d6-2 for count, picks random enrolled courses for placement.

    Returns:
        (loose_workspace_count, document_count)
    """
    loose_count = roll_1d6_minus_2()
    if loose_count == 0 or not enrolled_codes:
        return 0, 0

    ws_count = 0
    doc_count = 0

    for _ in range(loose_count):
        course_code = random.choice(enrolled_codes)  # nosec B311
        course_id = await _resolve_course_id_for_code(course_code, course_activities)
        if course_id is None:
            continue

        _, docs = await _create_loose_workspace(user, course_id)
        ws_count += 1
        doc_count += docs

    return ws_count, doc_count


async def _seed_student_workspaces(
    all_students: dict[str, User],
    student_courses: dict[str, list[str]],
    course_activities: dict[str, list[tuple[Activity, UUID]]],
) -> tuple[int, int, int, int]:
    """Phase 5: Create student activity workspaces and loose workspaces.

    Returns:
        (activity_workspace_count, loose_workspace_count,
         total_document_count, shared_with_class_count)
    """
    console.print("\n[bold cyan]Phase 5: Student Workspaces[/]")

    activity_ws_count = 0
    loose_ws_count = 0
    total_doc_count = 0
    shared_count = 0

    # Pre-fetch template documents for each activity to avoid repeated queries
    template_doc_cache: dict[UUID, list[WorkspaceDocument]] = {}
    for acts in course_activities.values():
        for _activity, tmpl_id in acts:
            if tmpl_id not in template_doc_cache:
                template_doc_cache[tmpl_id] = await _get_template_documents(tmpl_id)

    student_list = list(all_students.items())
    total_students = len(student_list)

    for idx, (email, user) in enumerate(student_list):
        enrolled_codes = student_courses.get(email, [])

        # Activity workspaces
        for code in enrolled_codes:
            activities = course_activities.get(code, [])
            for activity, tmpl_id in activities:
                # 70% chance of creating a workspace
                if random.random() > 0.7:  # nosec B311
                    continue

                # Idempotency check
                if await _check_workspace_exists(activity.id, user.id):
                    continue

                _ws_id, doc_count, is_shared = await _create_student_activity_workspace(
                    activity=activity,
                    user=user,
                    template_docs=template_doc_cache[tmpl_id],
                )
                activity_ws_count += 1
                total_doc_count += doc_count
                if is_shared:
                    shared_count += 1

        # Loose workspaces
        loose, docs = await _create_loose_workspaces_for_student(
            user, enrolled_codes, course_activities
        )
        loose_ws_count += loose
        total_doc_count += docs

        # Progress reporting every 100 students
        if (idx + 1) % 100 == 0 or idx + 1 == total_students:
            console.print(
                f"  [green]Progress:[/] {idx + 1}/{total_students} students "
                f"({activity_ws_count} activity ws, {loose_ws_count} loose ws)"
            )

    console.print(
        f"  [green]Activity workspaces:[/] {activity_ws_count}\n"
        f"  [green]Loose workspaces:[/] {loose_ws_count}\n"
        f"  [green]Documents:[/] {total_doc_count}\n"
        f"  [green]Shared with class:[/] {shared_count}"
    )

    return activity_ws_count, loose_ws_count, total_doc_count, shared_count


# ---------------------------------------------------------------------------
# ACL shares (Task 4)
# ---------------------------------------------------------------------------


async def _seed_acl_shares(
    all_students: dict[str, User],
    student_courses: dict[str, list[str]],
    courses: dict[str, Course],
) -> int:
    """Phase 6: Add explicit ACL shares between students.

    Selects ~50 random student workspaces and grants editor/viewer
    permission to 1-2 other students in the same course.

    Returns:
        Number of ACL shares created.
    """
    console.print("\n[bold cyan]Phase 6: ACL Shares[/]")

    share_count = 0

    # Build course_id -> list of student Users mapping
    course_students: dict[UUID, list[User]] = {}
    for email, codes in student_courses.items():
        user = all_students[email]
        for code in codes:
            if code in courses:
                cid = courses[code].id
                course_students.setdefault(cid, []).append(user)

    # Collect activity-linked student workspaces (not templates, not loose)
    candidate_workspaces: list[
        tuple[UUID, UUID, UUID]
    ] = []  # (workspace_id, owner_user_id, course_id)

    for _course_code, course in courses.items():
        async with get_session() as session:
            # Find non-template activity workspaces in this course
            result = await session.exec(
                select(Workspace.id, ACLEntry.user_id, Week.course_id)
                .join(Activity, Workspace.activity_id == Activity.id)  # type: ignore[arg-type]  # SQLAlchemy join expression, not a plain column
                .join(Week, Activity.week_id == Week.id)  # type: ignore[arg-type]  # SQLAlchemy join expression, not a plain column
                .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)  # type: ignore[arg-type]  # SQLAlchemy join expression, not a plain column
                .where(
                    Week.course_id == course.id,
                    ACLEntry.permission == "owner",
                    Workspace.id != Activity.template_workspace_id,
                )
            )
            for ws_id, owner_id, cid in result.all():
                candidate_workspaces.append((ws_id, owner_id, cid))

    if not candidate_workspaces:
        console.print("  [yellow]No candidate workspaces for sharing[/]")
        return 0

    # Select ~50 random workspaces
    sample_size = min(50, len(candidate_workspaces))
    selected = random.sample(candidate_workspaces, sample_size)  # nosec B311

    for ws_id, owner_id, course_id in selected:
        students_in_course = course_students.get(course_id, [])
        # Filter out the owner
        eligible = [s for s in students_in_course if s.id != owner_id]
        if not eligible:
            continue

        # Grant to 1-2 other students
        num_shares = random.randint(1, min(2, len(eligible)))  # nosec B311
        recipients = random.sample(eligible, num_shares)  # nosec B311

        for recipient in recipients:
            perm = random.choice(["editor", "viewer"])  # nosec B311
            await grant_permission(ws_id, recipient.id, perm)
            share_count += 1

    console.print(f"  [green]ACL shares created:[/] {share_count}")
    return share_count


# ---------------------------------------------------------------------------
# Summary (Task 4)
# ---------------------------------------------------------------------------


async def _print_summary(
    courses: dict[str, Course],
    course_activities: dict[str, list[tuple[Activity, UUID]]],
    activity_ws_count: int,
    loose_ws_count: int,
    total_doc_count: int,
    share_count: int,
    shared_with_class_count: int,
) -> None:
    """Print final load-test data summary with counts from the database."""
    console.print("\n[bold green]Load test data summary:[/]")

    # Count from database for accuracy
    async with get_session() as session:
        # All load-test users share @test.local domain (students: loadtest-*,
        # instructors: lt-instructor-*, admin: lt-admin). Seed data uses
        # @uni.edu and @example.com, so this won't over-count.
        user_result = await session.exec(
            select(User.id).where(User.email.like("%@test.local"))  # type: ignore[union-attr]  # SQLAlchemy column expression
        )
        db_user_count = len(user_result.all())

        enrollment_result = await session.exec(
            select(CourseEnrollment.id).where(
                CourseEnrollment.course_id.in_(  # type: ignore[union-attr]  # SQLAlchemy column expression
                    [c.id for c in courses.values()]
                )
            )
        )
        db_enrollment_count = len(enrollment_result.all())

    total_activities = sum(len(acts) for acts in course_activities.values())

    console.print(f"  Users (load-test, incl. instructors/admin): {db_user_count}")
    console.print(f"  Courses: {len(courses)}")
    console.print(f"  Enrollments: {db_enrollment_count}")
    console.print(f"  Activities: {total_activities}")
    console.print(f"  Workspaces (activity): {activity_ws_count}")
    console.print(f"  Workspaces (loose): {loose_ws_count}")
    console.print(f"  Documents: {total_doc_count}")
    console.print(f"  ACL shares: {share_count}")
    console.print(f"  Workspaces with shared_with_class: {shared_with_class_count}")


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
        count = int(cdef["student_count"])  # type: ignore[arg-type]  # dict value is typed as object; int() is safe here
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


async def _validate_ensure_week(course: Course) -> Week:
    """Ensure a single published week exists for the validation course.

    Idempotent: returns the existing week if one is already present.
    """
    async with get_session() as session:
        result = await session.exec(select(Week).where(Week.course_id == course.id))
        existing = result.first()
    if existing:
        return existing

    week = await create_week(
        course_id=course.id, week_number=1, title="Validation Week"
    )
    async with get_session() as session:
        session.add(week)
        week.is_published = True
        await session.flush()
        await session.refresh(week)
    return week


async def _validate_ensure_activity(week: Week) -> tuple[Activity, UUID]:
    """Ensure a single activity with template docs+tags exists for validation.

    Returns:
        (Activity, template_workspace_id)
    """
    async with get_session() as session:
        result = await session.exec(select(Activity).where(Activity.week_id == week.id))
        existing_activity = result.first()

    if existing_activity:
        console.print(
            f"  [yellow]Exists:[/] Activity '{existing_activity.title}' "
            f"(tmpl={existing_activity.template_workspace_id})"
        )
        return existing_activity, existing_activity.template_workspace_id

    activity = await create_activity(week_id=week.id, title="Validate Annotation")
    tmpl_id = activity.template_workspace_id

    content = DOCUMENT_PARAGRAPHS[0] + "\n" + DOCUMENT_PARAGRAPHS[1]
    await add_document(
        workspace_id=tmpl_id,
        type="source",
        content=content,
        source_type="html",
        title="Validation Document",
    )
    await _seed_tags_for_template(tmpl_id)
    console.print(f"  [green]Created:[/] Activity '{activity.title}' (tmpl={tmpl_id})")
    return activity, tmpl_id


async def _validate_ensure_student_workspace(
    activity: Activity,
    tmpl_id: UUID,
    student: User,
) -> UUID | None:
    """Ensure a student workspace exists for the validation activity.

    Returns:
        The workspace UUID (existing or newly created).
    """
    if await _check_workspace_exists(activity.id, student.id):
        async with get_session() as session:
            result = await session.exec(
                select(Workspace.id)
                .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)  # type: ignore[arg-type]  # SQLAlchemy join expression, not a plain column
                .where(
                    Workspace.activity_id == activity.id,
                    ACLEntry.user_id == student.id,
                    ACLEntry.permission == "owner",
                )
            )
            ws_id = result.first()
        console.print(f"  [yellow]Exists:[/] Student workspace (id={ws_id})")
        return ws_id

    template_docs = await _get_template_documents(tmpl_id)
    ws_id, doc_count, _shared = await _create_student_activity_workspace(
        activity=activity,
        user=student,
        template_docs=template_docs,
    )
    console.print(
        f"  [green]Created:[/] Student workspace (id={ws_id}, {doc_count} docs)"
    )
    return ws_id


async def _validate_enroll(
    email: str,
    display_name: str,
    course: Course,
    role: str,
) -> User:
    """Find-or-create a user and enroll them in the validation course."""
    user, created = await find_or_create_user(email=email, display_name=display_name)
    status = "[green]Created" if created else "[yellow]Exists"
    console.print(f"  {status}:[/] {email}")
    try:
        await enroll_user(course_id=course.id, user_id=user.id, role=role)
        console.print(f"    [green]Enrolled:[/] {role}")
    except DuplicateEnrollmentError:
        console.print("    [yellow]Already enrolled[/]")
    return user


async def _async_validate() -> None:
    """Create a minimal dataset (1 of each entity) for quick smoke testing.

    Idempotent: reuses existing entities if the validation course already
    exists. Prints the annotation URL and login email at the end.
    """
    await init_db()
    console.print("[bold]Creating validation dataset...[/]\n")

    course, course_created = await _find_or_create_course(
        code="LT-VALIDATE",
        name="Validation Course (Load Test)",
        semester="2026-LT",
        default_allow_sharing=True,
        default_anonymous_sharing=True,
    )
    status = "[green]Created" if course_created else "[yellow]Exists"
    console.print(f"  {status}:[/] LT-VALIDATE (id={course.id})")

    await _validate_enroll(
        "loadtest-validate-instructor@test.local",
        "Prof. Validate (LT)",
        course,
        "coordinator",
    )
    student = await _validate_enroll(
        "loadtest-validate@test.local",
        "Validate Student (LT)",
        course,
        "student",
    )

    week = await _validate_ensure_week(course)
    console.print(f"  [green]Week:[/] {week.title} (id={week.id})")

    activity, tmpl_id = await _validate_ensure_activity(week)
    ws_id = await _validate_ensure_student_workspace(activity, tmpl_id, student)

    url = f"http://127.0.0.1:8080/annotation?{urlencode({'workspace_id': str(ws_id)})}"
    console.print(
        f"\n[bold green]Validation workspace created. Open in browser:[/]"
        f"\n  {url}"
        f"\n\n  Log in as: [bold]loadtest-validate@test.local[/]"
    )


async def _async_load_test_data() -> None:
    """Main async entry point for load-test data generation."""
    await init_db()
    console.print("[bold]Creating load-test data...[/]\n")

    courses = await _seed_courses()
    await _seed_instructors(courses)
    all_students, student_courses, _total_student_count = await _seed_students(courses)

    console.print("\n[bold cyan]Phase 4: Weeks & Activities[/]")
    course_activities = await _create_weeks_and_activities(courses)

    # Phase 5: Student workspaces
    (
        activity_ws_count,
        loose_ws_count,
        total_doc_count,
        shared_with_class_count,
    ) = await _seed_student_workspaces(all_students, student_courses, course_activities)

    # Phase 6: ACL shares
    share_count = await _seed_acl_shares(all_students, student_courses, courses)

    # Summary
    await _print_summary(
        courses=courses,
        course_activities=course_activities,
        activity_ws_count=activity_ws_count,
        loose_ws_count=loose_ws_count,
        total_doc_count=total_doc_count,
        share_count=share_count,
        shared_with_class_count=shared_with_class_count,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def load_test_data() -> None:
    """Generate load-test data for workspace navigator validation.

    Creates courses, users, enrollments, weeks, and activities at
    realistic scale (1100 students). Idempotent: safe to run repeatedly.

    Usage:
        uv run load-test-data              # full 1100-student dataset
        uv run load-test-data --validate   # 1 of each entity for smoke test
    """
    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    if "--validate" in sys.argv:
        asyncio.run(_async_validate())
    else:
        asyncio.run(_async_load_test_data())
