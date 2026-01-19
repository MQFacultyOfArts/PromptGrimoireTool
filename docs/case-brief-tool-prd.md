# Case Brief Tool - Product Requirements Document

## Overview

Case Brief Tool is a legal education application for teaching students to read, annotate, and brief court cases. It enables instructors to assign cases, students to systematically analyze judgments through structured highlighting and annotation, and produces combined PDF deliverables of annotated cases with completed briefs.

**Target:** Session 1 2025 (Feb 23)
**Deployment:** Single institution
**Relationship to PromptGrimoire:** Shares infrastructure stack and authentication; domain-specific fork for legal education

## Tech Stack (Inherited from PromptGrimoire)

- **Python 3.14**
- **NiceGUI** - web UI framework
  - `ui.editor` - Quill-based WYSIWYG for brief fields
- **SQLModel** - ORM (Pydantic + SQLAlchemy)
- **PostgreSQL** - persistence
- **Stytch** - auth (magic links, passkeys, RBAC)
- **pycrdt** - CRDT for real-time collaboration (Phase 2)

### Additional Dependencies

- **striprtf** or similar - RTF text extraction
- **WeasyPrint** or **ReportLab** - PDF generation for exports

## User Roles

Reuses PromptGrimoire's Stytch RBAC configuration:

| Role | Permissions |
|------|-------------|
| Admin | Full system access, user management, all courses |
| Instructor | Create/manage courses, upload cases, view all student work, export on behalf of students |
| Student | View assigned cases, create briefs, annotate documents, export PDFs |

## Information Architecture

```
Course
└── Week
    └── Case (uploaded RTF)
        └── Brief (per student or per group)
            ├── Brief tags (11)
            └── Linked highlights (from case annotations)
```

## Data Model

### Core Entities

```
Course
├── id: UUID
├── name: str
├── code: str (e.g., "LAW2001")
├── instructor_id: FK → User
├── created_at: datetime
└── weeks: List[Week]

Week
├── id: UUID
├── course_id: FK → Course
├── number: int
├── title: str (e.g., "Week 3: Contract Formation")
└── cases: List[Case]

Case
├── id: UUID
├── week_id: FK → Week
├── title: str (case name, e.g., "Carlill v Carbolic Smoke Ball Co")
├── citation: str
├── rtf_blob: bytes (original RTF file)
├── extracted_text: str (plain text for annotation layer)
├── uploaded_by: FK → User
└── uploaded_at: datetime

Brief
├── id: UUID
├── case_id: FK → Case
├── student_id: FK → User
├── group_id: FK → Group (nullable, for collaborative briefs - Phase 2)
├── reflection_mode: enum (individual | collaborative)
├── created_at: datetime
├── updated_at: datetime
└── tags: BriefTags (embedded, HTML content from WYSIWYG)

BriefTags
├── jurisdiction: str (HTML)
├── procedural_history: str (HTML)
├── legally_relevant_facts: str (HTML)
├── legal_issues: str (HTML)
├── reasons: str (HTML)
├── courts_reasoning: str (HTML)
├── decision: str (HTML)
├── order: str (HTML)
├── domestic_sources: str (HTML, free-text: cases and legislation)
└── reflection: str (HTML)

Highlight
├── id: UUID
├── case_id: FK → Case
├── brief_id: FK → Brief
├── student_id: FK → User
├── start_offset: int (character position in extracted_text)
├── end_offset: int
├── tag: enum (jurisdiction | procedural_history | legally_relevant_facts | legal_issues | reasons | courts_reasoning | decision | order | domestic_sources | reflection)
├── note: str (optional annotation)
└── created_at: datetime
```

## Brief Tags Specification

The 11 brief tags are used to categorize both highlights (on the case) and sections (in the brief form). Terminology: use "tag" consistently throughout.

| Tag | Description | Guidance for Students |
|-----|-------------|----------------------|
| jurisdiction | Which court decided the case and its jurisdictional authority | Identify the court level and jurisdiction (e.g., High Court of Australia, NSW Supreme Court) |
| procedural_history | How the case arrived at this court | Prior proceedings, appeals, original jurisdiction |
| legally_relevant_facts | Material facts that influenced the legal outcome | Facts the court relied upon; exclude background noise |
| legal_issues | Questions of law the court addressed | Frame as questions the court needed to answer |
| reasons | Legal principles and rules applied | Statutes, precedents, doctrines cited |
| courts_reasoning | How the court applied law to facts | The analytical process connecting rules to outcome |
| decision | The court's conclusion on each issue | Who won on each legal question |
| order | Formal orders made | Remedies granted, costs, any conditions |
| domestic_sources | Cases and legislation cited | List key authorities relied upon |
| reflection | Student's analysis and learning | Personal insight, connections to course themes, questions raised |

## Features

### MVP (Feb 2025)

#### 1. Case Upload and Viewing
- Instructor uploads RTF file of court judgment (paragraph numbers should be included in the RTF by instructor)
- System extracts plain text for annotation layer
- Students view case text in annotation interface
- Metadata: case title, citation, week assignment
- **Copy-paste prevention**: CSS `user-select: none` + disabled right-click context menu (basic friction, not security)

#### 2. Document Annotation and Highlighting
- Select text passages in the case document
- Tag each highlight with one of the 11 brief tags (dropdown selection)
- Optional free-text note on each highlight
- Visual differentiation of highlights by tag (color-coding, must be colorblind accessible)
- Highlights persist and are visible when writing brief
- Clicking a highlight shows its note only - does NOT insert text into brief (students must type themselves)

#### 3. Brief Creation
- Structured form with all 11 tag sections
- **WYSIWYG editor** for each field (NiceGUI `ui.editor` - supports bold, italic, underline, lists)
- Each section shows linked highlights from case annotations (view only, no auto-insert)
- **Auto-save** functionality via CRDT
- Reflection tag configurable per assignment (individual or collaborative)
- **Word count display**: regex-based (series of letters delimited by non-letters), excludes footnotes
- **Copy-paste prevention**: Same as case viewer (basic friction)
- Students cite passages using paragraph numbers in brackets, e.g., [42]

#### 4. PDF Export
- Combined document containing:
  1. Case metadata (title, citation, court)
  2. Annotated excerpts organized by brief tag
  3. Complete brief with all tags
- Clean, printable format suitable for submission to iLearn
- Students export their own work
- **Instructors can export on behalf of any student** (for grading, troubleshooting)

#### 5. Instructor Student View
- Instructors can navigate to any student's work for a given case
- Read-only view of student's annotations and brief in progress
- Export PDF on behalf of student
- No inline commenting for MVP

#### 6. Responsive Layout
- **Desktop**: Split-pane view (case left, brief right)
- **Tablet/Mobile**: Tabbed interface (switch between case view and brief view)

### Phase 2 (Post-MVP)

#### 7. Highlight Minimap
- Scrolling heat map showing highlight density across document
- Visual indicator of current position

#### 8. Real-Time Collaboration
- Multiple students editing same brief simultaneously
- CRDT-based conflict resolution (pycrdt)
- Presence indicators showing who is editing
- Configurable: individual vs. group briefs per assignment

#### 9. Peer Review
- Inline annotations on peer briefs
- Rubric-based scoring:
  - Criteria per brief tag
  - Numeric or qualitative ratings
  - Written feedback
- Anonymous or attributed (instructor choice)

#### 10. Instructor Comments
- Optional inline comments on student work
- Feedback visible to student

#### 11. Encryption at Rest
- Database-level encryption for stored content

## User Workflows

### Instructor Workflow

1. **Create Course** → Set course name, code
2. **Configure Weeks** → Add weekly modules with titles
3. **Upload Cases** → Attach RTF files to weeks, set metadata (ensure paragraph numbers are in the RTF)
4. **Configure Assignments** → Set reflection mode (individual/collaborative)
5. **Monitor Progress** → View individual student briefs and annotations (read-only)
6. **Export for Grading** → Generate PDF on behalf of any student

### Student Workflow

1. **Access Course** → View weekly case assignments
2. **Open Case** → View case text in annotation interface
3. **Read and Highlight** → Select passages, tag to brief sections, add notes
4. **Write Brief** → Type content in WYSIWYG editor for each tag (reference highlights but type manually)
5. **Add Reflection** → Personal analysis and learning
6. **Export PDF** → Download combined annotated case + brief for iLearn submission

## UI/UX Considerations

### Case Viewer
- Split-pane (desktop) or tabbed (mobile) interface
- Highlight toolbar with 11 tags as color-coded buttons
- Colorblind-accessible palette (test with deuteranopia)
- Minimap showing highlight density (Phase 2)

### Brief Editor
- Accordion or tabbed sections for 11 tags
- Each section shows count of linked highlights
- "View highlights" expands to show tagged passages (read-only reference)
- Word count per field (letters-only regex, excludes any footnotes)
- WYSIWYG formatting: bold, italic, underline, bullets, numbered lists

### Export Preview
- Preview modal before download
- Option to include/exclude certain sections
- Watermark for draft vs. final submissions

## Technical Considerations

### RTF Processing
- Extract plain text from RTF maintaining paragraph structure
- Paragraph numbers expected to be in source document
- Store both original RTF blob and extracted text

### Highlight Storage
- Character offsets into extracted text
- Efficient queries: "all highlights for this tag"

### Copy-Paste Prevention
- CSS: `user-select: none` on case text and brief content
- JavaScript: disable context menu (right-click)
- Note: This is pedagogical friction, not security. Determined students can bypass.

### Word Count Algorithm
```python
import re
def word_count(text: str) -> int:
    """Count words as sequences of letters."""
    return len(re.findall(r'[a-zA-Z]+', text))
```

### Export Generation
- Template-based PDF generation (WeasyPrint)
- Consistent styling with institution branding (configurable)
- Accessible PDF output (tagged, readable)

## Security and Privacy

- Student work visible only to: the student, instructors, assigned peer reviewers (Phase 2)
- Case documents may be copyrighted: no public sharing, copy-paste prevention
- Audit log of document access
- HTTPS required
- Encryption at rest: Phase 2

## Success Metrics

- Students complete briefs for assigned cases
- Students create highlights before/during brief writing (pedagogical goal)
- PDF exports successfully generated
- Instructor can view all student work per case
- Tablet/mobile users can complete workflow via tabbed interface

## Resolved Questions

1. **Input format**: RTF only (not PDF) - simpler processing, instructor prepares with paragraph numbers
2. **Copyright/copy protection**: Basic CSS + right-click prevention; acknowledged as friction not security
3. **Mobile support**: Yes, via tabbed interface instead of split pane
4. **AI assistance**: No - tool intentionally avoids doing work for students
5. **Citation automation**: No - clicking highlights shows notes only, students type their own text
6. **Encryption at rest**: Phase 2

## Open Questions

1. **LMS integration**: Future need to integrate with Moodle/Canvas gradebook?
2. **Bulk operations**: Should instructors be able to bulk-export all student PDFs for a case?

## Appendix: Comparison to PromptGrimoire

| Aspect | PromptGrimoire | Case Brief Tool |
|--------|----------------|-----------------|
| Domain | Prompt engineering | Legal education |
| Core content | Conversation transcripts | Court judgment RTFs |
| Annotation target | Prompts and responses | Case text passages |
| Structured output | Tags, comments | 11 brief tags |
| Collaboration | CRDT prompts | Phase 2 |
| Export | - | Combined PDF |
| Organization | Class | Course > Week |
