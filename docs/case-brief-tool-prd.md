# Case Brief Tool - Product Requirements Document

## Overview

Case Brief Tool is a legal education application for teaching students to read, annotate, and brief court cases. It enables instructors to assign cases, students to systematically analyze judgments through structured highlighting and annotation, and produces combined PDF deliverables of annotated cases with completed briefs.

**Target:** Session 1 2025 (Feb 23)
**Deployment:** Single institution
**Relationship to PromptGrimoire:** Shares infrastructure stack and authentication; domain-specific fork for legal education

## Tech Stack (Inherited from PromptGrimoire)

- **Python 3.14**
- **NiceGUI** - web UI framework
- **SQLModel** - ORM (Pydantic + SQLAlchemy)
- **PostgreSQL** - persistence
- **Stytch** - auth (magic links, passkeys, RBAC)
- **pycrdt** - CRDT for real-time collaboration (Phase 2)

### Additional Dependencies

- **PyMuPDF (fitz)** or **pdfplumber** - PDF text extraction and rendering
- **WeasyPrint** or **ReportLab** - PDF generation for exports

## User Roles

Reuses PromptGrimoire's Stytch RBAC configuration:

| Role | Permissions |
|------|-------------|
| Admin | Full system access, user management, all courses |
| Instructor | Create/manage courses, upload cases, view all student work |
| Student | View assigned cases, create briefs, annotate documents, export PDFs |

## Information Architecture

```
Course
└── Week
    └── Case (uploaded PDF)
        └── Brief (per student or per group)
            ├── Structured fields (11)
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
├── pdf_blob: bytes
├── extracted_text: str (for annotation layer)
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
└── fields: BriefFields (embedded)

BriefFields
├── jurisdiction: str
├── procedural_history: str
├── legally_relevant_facts: str
├── legal_issues: str
├── reasons: str
├── courts_reasoning: str
├── decision: str
├── order: str
├── domestic_sources: str (free-text: cases and legislation)
└── reflection: str

Highlight
├── id: UUID
├── case_id: FK → Case
├── brief_id: FK → Brief
├── student_id: FK → User
├── start_offset: int (character position in extracted_text)
├── end_offset: int
├── tagged_section: enum (jurisdiction | procedural_history | legally_relevant_facts | legal_issues | reasons | courts_reasoning | decision | order | domestic_sources | reflection)
├── note: str (optional annotation)
└── created_at: datetime
```

## Brief Fields Specification

| Field | Description | Guidance for Students |
|-------|-------------|----------------------|
| Court's Jurisdiction | Which court decided the case and its jurisdictional authority | Identify the court level and jurisdiction (e.g., High Court of Australia, NSW Supreme Court) |
| Procedural History | How the case arrived at this court | Prior proceedings, appeals, original jurisdiction |
| Legally Relevant Facts | Material facts that influenced the legal outcome | Facts the court relied upon; exclude background noise |
| Legal Issues | Questions of law the court addressed | Frame as questions the court needed to answer |
| Reasons | Legal principles and rules applied | Statutes, precedents, doctrines cited |
| Court's Reasoning | How the court applied law to facts | The analytical process connecting rules to outcome |
| Decision | The court's conclusion on each issue | Who won on each legal question |
| Court's Order | Formal orders made | Remedies granted, costs, any conditions |
| Domestic Sources | Cases and legislation cited | List key authorities relied upon |
| Reflection | Student's analysis and learning | Personal insight, connections to course themes, questions raised |

## Features

### MVP (Feb 2025)

#### 1. Case Upload and Viewing
- Instructor uploads PDF of court judgment
- System extracts text for annotation layer
- Students view PDF with side-by-side or overlay annotation capability
- Metadata: case title, citation, week assignment

#### 2. Document Annotation and Highlighting
- Select text passages in the case document
- Tag each highlight with one of the 11 brief sections
- Optional note/annotation on each highlight
- Visual differentiation of highlights by section (color-coding)
- Highlights persist and are visible when writing brief

#### 3. Brief Creation
- Structured form with all 11 fields
- Each field shows linked highlights from case annotations
- Auto-save functionality
- Reflection field configurable per assignment (individual or collaborative)

#### 4. PDF Export
- Combined document containing:
  1. Case metadata (title, citation, court)
  2. Annotated excerpts organized by brief section
  3. Complete brief with all fields
- Clean, printable format suitable for submission

### Phase 2 (Post-MVP)

#### 5. Real-Time Collaboration
- Multiple students editing same brief simultaneously
- CRDT-based conflict resolution (pycrdt)
- Presence indicators showing who is editing
- Configurable: individual vs. group briefs per assignment

#### 6. Peer Review
- Inline annotations on peer briefs
- Rubric-based scoring:
  - Criteria per brief section
  - Numeric or qualitative ratings
  - Written feedback
- Anonymous or attributed (instructor choice)

## User Workflows

### Instructor Workflow

1. **Create Course** → Set course name, code
2. **Configure Weeks** → Add weekly modules with titles
3. **Upload Cases** → Attach PDFs to weeks, set metadata
4. **Configure Assignments** → Set reflection mode (individual/collaborative)
5. **Monitor Progress** → View student briefs and annotations
6. **Export/Grade** → Download student PDFs for assessment

### Student Workflow

1. **Access Course** → View weekly case assignments
2. **Open Case** → View PDF in annotation interface
3. **Read and Highlight** → Select passages, tag to brief sections
4. **Write Brief** → Complete structured fields, referencing highlights
5. **Add Reflection** → Personal analysis and learning
6. **Export PDF** → Download combined annotated case + brief

## UI/UX Considerations

### Case Viewer
- Split-pane or tabbed interface: PDF on left/top, brief form on right/bottom
- Highlight toolbar with section tags as color-coded buttons
- Minimap showing highlight density across document

### Brief Editor
- Accordion or tabbed sections for 11 fields
- Each section shows count of linked highlights
- "View highlights" expands to show tagged passages inline
- Character/word count per field (optional guidance)

### Export Preview
- Preview modal before download
- Option to include/exclude certain sections
- Watermark for draft vs. final submissions

## Technical Considerations

### PDF Processing
- Extract text maintaining approximate position mapping
- Handle multi-column layouts, footnotes, headers
- Store both original blob and extracted text
- Consider OCR fallback for scanned documents

### Highlight Storage
- Character offsets into extracted text
- Robust to minor text extraction variations
- Efficient queries: "all highlights for this brief section"

### Export Generation
- Template-based PDF generation
- Consistent styling with institution branding (configurable)
- Accessible PDF output (tagged, readable)

## Security and Privacy

- Student work visible only to: the student, instructors, assigned peer reviewers
- Case documents may be copyrighted: no public sharing
- Audit log of document access
- HTTPS, encrypted at rest

## Success Metrics

- Students complete briefs for assigned cases
- Students create highlights before/during brief writing (pedagogical goal)
- PDF exports successfully generated
- Instructor can view all student work per case

## Open Questions

1. **Copyright handling**: Should system watermark uploaded cases? Restrict downloads?
2. **LMS integration**: Future need to integrate with Moodle/Canvas gradebook?
3. **AI assistance**: Any plans to incorporate LLM-based feedback on briefs?
4. **Mobile support**: Is mobile/tablet annotation a requirement?

## Appendix: Comparison to PromptGrimoire

| Aspect | PromptGrimoire | Case Brief Tool |
|--------|----------------|-----------------|
| Domain | Prompt engineering | Legal education |
| Core content | Conversation transcripts | Court judgment PDFs |
| Annotation target | Prompts and responses | Case text passages |
| Structured output | Tags, comments | 11-field brief |
| Collaboration | CRDT prompts | Phase 2 |
| Export | - | Combined PDF |
| Organization | Class | Course > Week |
