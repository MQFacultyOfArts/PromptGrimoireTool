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
- **pycrdt** - CRDT for real-time collaboration (MVP - all screens)

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
            ├── Highlights with tags (10 categories)
            ├── Card ordering (user-defined per tag)
            └── Brief content (freeform WYSIWYG)
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
├── group_id: FK → Group (nullable, for collaborative briefs)
├── content: str (HTML from freeform WYSIWYG - CRDT synced)
├── card_ordering: JSON (tag → ordered list of highlight IDs - CRDT synced)
├── word_limit: int | None (instructor-configured max, nullable)
├── created_at: datetime
└── updated_at: datetime

Highlight
├── id: UUID
├── case_id: FK → Case
├── brief_id: FK → Brief
├── student_id: FK → User
├── start_word: int (word index - word-level, not character)
├── end_word: int
├── paragraph_num: int | None (auto-detected from document structure)
├── tag: enum (jurisdiction | procedural_history | legally_relevant_facts | legal_issues | reasons | courts_reasoning | decision | order | domestic_sources | reflection)
├── text: str (highlighted text content)
├── note: str (optional annotation)
├── comments: List[Comment] (threaded discussion)
└── created_at: datetime

Case (additional fields)
├── enable_card_organization: bool (instructor toggle per case)
└── word_limit: int | None (max words for brief, enforced)
```

## Brief Tags Specification

The **10 brief tags** are used to categorize highlights on the case document. Students use these tags to organize their annotations before writing their freeform brief.

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

#### Three-Screen Workflow

The application uses a **single-page carousel** with three screens. All screens are CRDT-synced for real-time collaboration. Navigation via **always-visible tab bar**: Annotate | Organize | Write.

Students can navigate freely between screens at any time (no validation gates).

#### Screen 1: Document Annotation (Annotate Tab)

- Instructor uploads RTF file of court judgment (paragraph numbers in ordered lists or at paragraph start)
- System extracts HTML with word-level spans for CSS-based highlighting
- **Word-level highlighting**: Select words, tag with one of 10 categories via toolbar or keyboard shortcuts [1-0]
- **Paragraph number detection**: System auto-detects containing paragraph from topmost `<ol>` parent or leading number in `<p>`
- Color-coded highlights by tag (colorblind-accessible palette)
- Optional free-text comments on each highlight (threaded discussion, CRDT-synced)
- Annotation cards in sidebar, scroll-synced to document position
- "Go to text" button scrolls and temporarily highlights source passage
- **Real-time collaboration**: Live cursor/selection sharing, presence indicators
- **Copy-paste prevention**: CSS `user-select: none` + disabled right-click (pedagogical friction, not security)

#### Screen 2: Card Organization (Organize Tab)

- View all annotation cards grouped by tag category
- **Drag-and-drop reordering** within each category
- Supports organizing non-contiguous document themes
- **CRDT-collaborative**: Group members see and manipulate same ordering in real-time
- **Per-case toggle**: Instructor can enable/disable this screen per case assignment
- When disabled, students skip directly from Screen 1 to Screen 3

#### Screen 3: Brief Writing (Write Tab)

- **Single freeform WYSIWYG editor** - students create their own structure (no forced tag sections)
- **Left sidebar** with:
  - Collapsible accordion of tag categories
  - Cards ordered per user's Screen 2 arrangement
  - Full-text search across all annotation cards
  - Cards show paragraph number reference (e.g., "[48]")
- Case document NOT visible - forces students to synthesize from their annotations
- **Word count display** below editor (regex-based: sequences of letters)
- **Word limit enforcement**: Instructor-configurable max per case; prevents export if exceeded
- **CRDT real-time collaboration** on brief content
- Students cite passages using paragraph numbers in brackets, e.g., [42]

#### PDF Export

- Accessed from Screen 3 only
- Combined document containing:
  1. Case metadata (title, citation, court)
  2. Organized annotations (respecting Screen 2 ordering)
  3. Complete brief content
- Clean, printable format suitable for submission to iLearn
- Students export their own work
- **Instructors can export on behalf of any student** (for grading, troubleshooting)
- Export blocked if word count exceeds configured limit

#### Case Upload and Management

- Instructor uploads RTF file with paragraph numbers (in ordered lists or paragraph-leading)
- Metadata: case title, citation, week assignment
- **Per-case configuration**:
  - Enable/disable card organization (Screen 2)
  - Word limit for brief (optional)

#### Instructor Student View

- Instructors can navigate to any student's work for a given case
- Read-only view of student's annotations, card ordering, and brief in progress
- Export PDF on behalf of student
- No inline commenting for MVP

### Phase 2 (Post-MVP)

#### Highlight Minimap
- Scrolling heat map showing highlight density across document
- Visual indicator of current position

#### Peer Review
- Inline annotations on peer briefs
- Rubric-based scoring:
  - Criteria per brief tag
  - Numeric or qualitative ratings
  - Written feedback
- Anonymous or attributed (instructor choice)

#### Instructor Comments
- Optional inline comments on student work
- Feedback visible to student

#### Click-to-Insert References
- Clicking a card in Screen 3 inserts paragraph reference (e.g., `[48]`) at cursor
- Card content becomes footnote in PDF export

#### AGLC4 Citation Support
- Optional formal citation formatting
- Auto-generate citation strings from case metadata

#### Encryption at Rest
- Database-level encryption for stored content

#### Secondary Source Database
- Support for multiple documents per assignment
- Cross-document annotation and organization
- Use case: Remedies course with scholarly sources

## User Workflows

### Instructor Workflow

1. **Create Course** → Set course name, code
2. **Configure Weeks** → Add weekly modules with titles
3. **Upload Cases** → Attach RTF files to weeks, set metadata (ensure paragraph numbers in ordered lists or paragraph-leading)
4. **Configure Per-Case Settings**:
   - Enable/disable card organization (Screen 2)
   - Set word limit for brief (optional)
5. **Monitor Progress** → View individual student briefs and annotations (read-only)
6. **Export for Grading** → Generate PDF on behalf of any student

### Student Workflow

1. **Access Course** → View weekly case assignments
2. **Open Case** → Enter three-screen workflow
3. **Screen 1 - Annotate** → Read case, highlight passages with tags, add comments
4. **Screen 2 - Organize** → Drag/drop cards to arrange by theme within each tag (if enabled)
5. **Screen 3 - Write** → Compose freeform brief using organized annotations as reference
6. **Export PDF** → Download combined document for iLearn submission (blocked if over word limit)

## UI/UX Considerations

### Platform Support

- **Desktop only** - no tablet/mobile support
- Students without computers should use library facilities

### Navigation

- **Tab bar** always visible at top: Annotate | Organize | Write
- Single-page carousel with smooth transitions between screens
- All state maintained in-page (no page reloads)

### Screen 1: Annotate

- Document on left (70%), annotation cards on right (30%)
- Tag toolbar in header with 10 color-coded buttons + keyboard shortcuts [1-0]
- Scroll-synced annotation cards with "Go to text" navigation
- Real-time cursor/selection indicators for collaborators
- Colorblind-accessible palette (tested with deuteranopia)

### Screen 2: Organize

- Cards grouped by tag category in collapsible sections
- Drag handles for reordering within each category
- Visual feedback during drag operations
- CRDT sync shows other users' reordering in real-time

### Screen 3: Write

- Sidebar on left (30%) with accordion of tag categories
- Full-text search box at top of sidebar
- Cards show: tag color, paragraph reference, truncated text
- WYSIWYG editor on right (70%)
- Word count display below editor
- Warning/block when approaching/exceeding word limit
- WYSIWYG formatting: bold, italic, underline, bullets, numbered lists

### Export Preview

- Preview modal before download
- Shows combined document structure
- Blocked if word count exceeds limit

## Technical Considerations

### RTF Processing
- Extract plain text from RTF maintaining paragraph structure
- Paragraph numbers expected to be in source document
- Store both original RTF blob and extracted text

### Highlight Storage

- **Word-level indexing** (not character offsets) - simplifies selection handling
- CRDT Map storing highlights by UUID
- Comments stored as array within each highlight
- Efficient queries: "all highlights for this tag"

### Paragraph Number Detection

Algorithm for detecting containing paragraph number:

1. Find the word span element for the highlight start
2. Walk up DOM tree looking for:
   - Topmost `<ol>` ancestor → use `<li>` position as paragraph number
   - OR `<p>` with leading number pattern (e.g., "48." or "[48]") → extract number
3. Store detected paragraph number with highlight
4. Display as "[48]" in annotation cards

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

### Word Limit Enforcement

- Instructor sets optional word limit per case
- Word count displayed in real-time below editor
- Visual warning when approaching limit (e.g., 90%)
- **Hard enforcement**: Export blocked if count exceeds limit
- Error message explains limit and current count

### Export Generation
- Template-based PDF generation (WeasyPrint)
- Consistent styling with institution branding (configurable)
- Accessible PDF output (tagged, readable)

## Security and Privacy

### Access Control

- Student work visible only to: the student, instructors, assigned peer reviewers (Phase 2)
- Case documents may be copyrighted: no public sharing, copy-paste prevention
- Audit log of document access

### Authentication Requirements

- **Server-side session validation**: Do not trust client-side storage for auth state. Validate session tokens against Stytch on every protected request.
- **Session expiration**: Validate that session tokens are still valid, not just present.
- **Token validation**: Validate format and length of auth tokens before processing.

### Input Validation

- **RTF upload size limit**: Maximum 10MB per file to prevent DoS
- **Text field length limits**: All user-input fields (notes, brief content, course names) must have reasonable length limits
- **HTML sanitization**: WYSIWYG editor output must be sanitized before storage/display to prevent XSS

### Infrastructure

- HTTPS required
- Encryption at rest: Phase 2
- Rate limiting on auth endpoints (before public deployment)

## Success Metrics

- Students complete briefs for assigned cases
- Students create highlights before/during brief writing (pedagogical goal)
- Students use card organization to structure their analysis
- PDF exports successfully generated
- Instructor can view all student work per case
- Real-time collaboration works smoothly for group work

## Resolved Questions

1. **Input format**: RTF only (not PDF) - simpler processing, instructor prepares with paragraph numbers
2. **Copyright/copy protection**: Basic CSS + right-click prevention; acknowledged as friction not security
3. **Mobile support**: No - desktop only, students use library if needed
4. **AI assistance**: No - tool intentionally avoids doing work for students
5. **Citation automation**: No for MVP - clicking highlights shows notes only, students type their own text (Phase 2: click-to-insert)
6. **Encryption at rest**: Phase 2
7. **Brief structure**: Freeform single WYSIWYG - students create their own structure, no forced tag sections
8. **Tag count**: 10 tags (jurisdiction through reflection)
9. **Highlight granularity**: Word-level (not character or mid-word)
10. **Card organization**: Optional per-case toggle, CRDT-collaborative when enabled
11. **Real-time collaboration**: MVP for all screens (annotations, card ordering, brief content)

## Open Questions

1. **LMS integration**: Future need to integrate with Moodle/Canvas gradebook?
2. **Bulk operations**: Should instructors be able to bulk-export all student PDFs for a case?

## Appendix: Comparison to PromptGrimoire

| Aspect | PromptGrimoire | Case Brief Tool |
|--------|----------------|-----------------|
| Domain | Prompt engineering | Legal education |
| Core content | Conversation transcripts | Court judgment RTFs |
| Annotation target | Prompts and responses | Case text passages (word-level) |
| Structured output | Tags, comments | 10 brief tags + freeform brief |
| Collaboration | CRDT prompts | CRDT all screens (MVP) |
| Export | - | Combined PDF |
| Organization | Class | Course > Week > Case |
| Workflow | Linear | Three-screen carousel |
