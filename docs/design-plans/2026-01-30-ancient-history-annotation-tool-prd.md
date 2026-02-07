# Ancient History AI Annotation Tool - Product Requirements Document

## Overview

AI Annotation Tool for Ancient History is an educational application for teaching AI literacy and critical evaluation of AI-generated content in the context of studying antiquity. Students annotate their AI conversations (Claude) and AI-generated summaries (ScienceOS) to develop metacognitive awareness of how AI assists—and sometimes misleads—their learning.

**Target:** Session 1 2025 (Feb 23)
**Deployment:** Single institution (Macquarie University)
**Unit:** AHIS1210 - Studying the Past: An Introduction to Ancient History in the 21st Century
**Cohort Size:** ~50-100 students (first-year undergraduates)
**Convenor:** Ray Laurence
**Relationship to PromptGrimoire:** Simplified annotation-only mode, shares core infrastructure (CRDT collaboration, annotation layer, PDF export)

## Pedagogical Framework

### AI-Assisted Learning in Ancient History

Students use AI tools as learning aids throughout the unit:

1. **Claude.ai** - Weekly learning prompts provided by instructor (e.g., "explain how Thucydides creates a narrative account of the plague")
2. **ScienceOS.ai** - Summarize Leganto readings before human reading

Students then **annotate these AI interactions** to:
- Identify useful explanations to remember
- Flag claims that need verification against ancient sources
- Note AI errors or hallucinations
- Connect AI responses to lecture content
- Reflect on what they learned vs. what needs human reading

### Learning Objectives

**Primary:** Critical AI literacy
- Evaluate AI-generated content for accuracy and usefulness
- Distinguish between helpful AI explanations and unsupported claims
- Understand AI limitations (cannot access paywalled readings, makes mistakes)
- Develop habits of verification against primary sources

**Secondary:** Ancient History content
- Understand historical narratives (pandemics, disability, Roman Republic)
- Engage with ancient sources (Thucydides, Appian, Suetonius, etc.)
- Develop blog writing skills for public history

## Tech Stack (Inherited from PromptGrimoire)

- **Python 3.14**
- **NiceGUI** - web UI framework
- **SQLModel** - ORM (Pydantic + SQLAlchemy)
- **PostgreSQL** - persistence
- **Stytch** - auth (magic links, passkeys, RBAC)
- **pycrdt** - CRDT for real-time collaboration

## User Roles

| Role | Permissions |
|------|-------------|
| Admin | Full system access, user management, all courses |
| Instructor | Create/manage weeks, define weekly tags, view student work |
| Student | Paste AI content, annotate documents, collaborate in tutorials, export PDF |

## User Stories

### Student - Weekly AI Annotation Workflow

**As a student**, I want to:
1. Use Claude.ai with the weekly prompt provided by Ray
2. Copy and paste my Claude conversation into the tool
3. Use ScienceOS to summarize a reading from the Leganto list
4. Paste the ScienceOS summary into the tool
5. Annotate both documents using the weekly tags Ray provided
6. Add my own tags if the provided ones don't fit
7. Add notes explaining my annotations (what I learned, what needs checking)
8. Export my annotated conversations as PDF
9. Use my annotations to inform my blog/essay writing (done externally)

**So that:** I develop critical AI literacy skills and have a record of my learning process.

### Student - Tutorial Collaboration

**As a student**, I want to:
1. Join a shared annotation session during tutorial
2. See my classmates' annotations in real-time
3. Collaboratively annotate a shared AI conversation
4. Discuss annotations with my group
5. Share my individual work anonymously with peers

**So that:** I learn from how others evaluate AI content and engage in collaborative critical thinking.

### Instructor (Ray) - Weekly Tag Management

**As an instructor**, I want to:
1. Define a set of tags for each week aligned with learning objectives
2. Have students use my tags but allow them to add their own
3. See student annotation work (optional - not for grading)
4. Facilitate in-class discussions using annotated AI conversations

**So that:** I guide students' critical evaluation while allowing flexibility.

## Information Architecture

```
Course (AHIS1210)
└── Week
    ├── Weekly Tags (instructor-defined)
    └── Student Work (per student)
        ├── Claude Conversation 1, 2, ... N
        ├── ScienceOS Summary 1, 2, ... N
        └── Annotations on all documents
```

## Data Model

Reuses existing PromptGrimoire models with simplified structure:

```
Course (existing)
├── id: UUID
├── name: str (e.g., "AHIS1210")
├── instructor_id: FK → User
└── semester: str

Week (existing)
├── id: UUID
├── course_id: FK → Course
├── week_number: int (1-13)
├── title: str (e.g., "Week 2: Plague of Athens")
└── is_published: bool

WeeklyTagSet (new)
├── id: UUID
├── week_id: FK → Week
├── tags: JSON array of tag definitions
│   └── [{name: str, description: str, color: str}, ...]
└── created_at: datetime

Document (simplified from translation tool)
├── id: UUID
├── week_id: FK → Week
├── student_id: FK → User
├── type: enum (claude_conversation | scienceos_summary)
├── content: str (pasted text, wrapped in word-level spans)
├── title: str (student-provided, e.g., "Thucydides plague prompt")
└── created_at: datetime

Tag (existing, student custom tags)
├── id: UUID
├── week_id: FK → Week
├── student_id: FK → User
├── name: str
├── description: str
├── color: str
└── is_from_weekly_set: bool (true if copied from WeeklyTagSet)

Highlight (existing)
├── id: UUID
├── document_id: FK → Document
├── student_id: FK → User
├── start_word: int
├── end_word: int
├── tag_id: FK → Tag
├── note: str (required - critical reflection)
└── created_at: datetime
```

## Weekly Tag Examples

**Week 2: Plague of Athens**
- `useful_explanation` - AI provided helpful context
- `needs_verification` - Claim should be checked against Thucydides
- `narrative_technique` - AI identified a storytelling method
- `modern_comparison` - Connection to COVID-19
- `ai_error` - AI made a factual mistake

**Week 5-7: Disability History**
- `terminology_issue` - AI used problematic language
- `ableist_framing` - AI presented disability negatively
- `good_source` - AI suggested useful reading
- `retrospective_diagnosis` - AI imposed modern medical terms
- `needs_primary_source` - Should check ancient text directly

**Week 9-12: Roman Republic**
- `constitutional_point` - AI explained how Republic worked
- `appian_reference` - Connects to this week's reading
- `modern_relevance` - Connection to contemporary democracies
- `causation_claim` - AI's explanation of why Republic failed
- `oversimplification` - AI glossed over complexity

## Features

### MVP (Feb 2025)

#### Single-Screen Annotation Interface

Unlike the translation tool's three-tab interface, this tool uses a **single annotation screen**:

- **Document list** (left sidebar): All pasted AI content for this week
- **Document viewer** (center): Current document with word-level annotation
- **Annotation cards** (right sidebar): Highlights with notes and comments

#### Document Paste & Import

- **"Add Claude Conversation"** button: Opens dialog to paste conversation text
- **"Add ScienceOS Summary"** button: Opens dialog to paste summary text
- Student provides a title for each document
- System wraps content in word-level spans for annotation

#### Annotation Layer (CRDT-synced)

- **Word-level highlighting** across all documents
- **Weekly tag palette**: Instructor-defined tags loaded automatically
- **Custom tag creation**: Students can add their own tags
- **Annotation notes**: Required reflection explaining each highlight
- **Annotation cards** in sidebar:
  - Tag name and color
  - Highlighted text preview
  - Note content
  - Timestamp
  - "Go to text" button

#### Collaboration Modes

**Individual mode (default):**
- Student sees only their own documents and annotations
- Standard workflow for weekly preparation

**Tutorial collaboration mode:**
- Real-time CRDT sync for groupwork
- Live cursor/selection sharing
- Two sub-modes:
  - **Shared document**: Group annotates same AI conversation together
  - **Peer sharing**: View classmates' individual work (anonymized optional)

#### PDF Export

- Standard PDF export of annotated documents
- Highlights rendered with colors
- Notes included as margin annotations or inline
- Used as reference for blog/essay writing (done externally)

### Phase 2 (Post-MVP)

#### Anonymous Peer Sharing
- Students opt-in to share annotated work anonymously
- Browse peer annotations for same week
- Learn from how others evaluate AI content

#### Instructor Dashboard
- View student annotation activity (not for grading)
- See which tags are used most frequently
- Identify common AI errors students are catching

#### Claude Prompt Integration
- Pre-load Ray's weekly Claude prompts into the tool
- Students can launch Claude conversation from within tool
- Automatic paste-back of conversation (if technically feasible)

## User Workflow

### Weekly Student Workflow

**Before Tutorial (Preparation):**

1. Access Week N in the tool
2. Open Claude.ai, use Ray's provided prompt
3. Have conversation with Claude about the week's topic
4. Copy entire conversation
5. In tool: Click "Add Claude Conversation", paste, give title
6. Open ScienceOS, upload PDF from Leganto reading list
7. Copy the AI-generated summary
8. In tool: Click "Add ScienceOS Summary", paste, give title
9. Annotate both documents using weekly tags:
   - Highlight useful explanations
   - Flag claims needing verification
   - Note AI errors
   - Add reflective notes
10. Read the actual Leganto articles (human brain!)
11. Add more annotations based on what you learned from reading

**During Tutorial:**

12. Join tutorial collaboration session (if Ray enables it)
13. Discuss annotations with group
14. Collaboratively annotate shared example (optional)

**For Assessment:**

15. Export annotated documents as PDF
16. Use annotations as reference when writing blog/essay
17. Submit blog/essay via Turnitin (external to this tool)

## Technical Considerations

### Text Processing
- **Paste workflow**: Students copy-paste from Claude/ScienceOS
- Clipboard paste preserves plain text; formatting stripped
- Word-level span wrapping for annotation layer

### CRDT Sync (pycrdt)
- Document content: CRDT Text type
- Annotations: CRDT Map type
- Real-time collaboration during tutorials

### Multi-Language Support
- **Not required** for Ray's unit (English-only content)
- Ancient Greek/Latin terms appear in discussions but don't require special input

## UI/UX Considerations

### Platform Support
- **Desktop only** - same as translation tool
- Minimum screen resolution: 1366x768

### Layout
- **Single-page interface** (no tabs)
- Document list sidebar (collapsible)
- Main document viewer with annotation layer
- Annotation cards sidebar

### Tag Palette
- Weekly tags displayed prominently
- "Create custom tag" button
- Color-coded, keyboard shortcuts [1-9]

## Success Metrics

**For Students:**
- Paste AI conversations and summaries weekly
- Create annotations identifying useful content and AI errors
- Participate in tutorial collaboration
- Export PDFs to support blog/essay writing

**For Ray:**
- Students develop critical AI literacy
- Annotations show evidence of verification habits
- Tutorial discussions enriched by shared annotations

**For System:**
- Paste workflow is frictionless
- Real-time collaboration works during tutorials
- PDF export generates successfully

## Timeline

### Pre-Launch (Jan 2025)
- Development (Brian)
- Internal testing

### Week 1 (Feb 17, 2025) - Soft Launch
- Course created in system
- Week 1 tags configured

### Week 2 (Feb 24, 2025) - Student Training
- Brian guest lecture: Tool demonstration
- Students practice annotation workflow

### Weeks 3-13 - Production Use
- Weekly tag sets configured by Ray
- Students annotate AI content weekly
- Tutorial collaboration as needed

## Relationship to Translation Annotation Tool

This tool is a **simplified subset** of the Translation Annotation Tool:

| Feature | Translation Tool | Ancient History Tool |
|---------|-----------------|---------------------|
| Tabs | 3 (Annotate, Organize, Write) | 1 (Annotate only) |
| Content types | Source text, AI convos, drafts | AI convos, AI summaries |
| Translation drafting | Yes (Tab 3) | No |
| Decision log | Yes | No |
| Tag management | Suggested starters + student-created | Weekly instructor-defined + student amendments |
| Instructor grading view | Yes (process grading) | No (not for grading) |
| Multi-language | Yes (CJK, Spanish, French) | No (English only) |
| CRDT collaboration | Yes | Yes |
| PDF export | Curated + comprehensive | Standard |

**Implementation note:** This can be built as a "simplified mode" of the translation tool, hiding Tabs 2-3 and the translation-specific features.

## Open Questions

1. **Prompt library**: Should Ray's weekly Claude prompts be stored in the tool for easy access?
2. **ScienceOS integration**: Any possibility of direct integration vs. copy-paste?
3. **Turnitin**: Any value in direct submission to Turnitin from the tool?

## Resolved Questions

1. **Content to annotate**: Claude conversations AND ScienceOS summaries (both)
2. **Tag management**: Instructor pre-defines weekly, students can amend
3. **Organization**: By week
4. **Collaboration**: Individual + tutorial groupwork + anonymous peer sharing
5. **Export**: Standard PDF
6. **Grading integration**: Not needed (annotations support learning, not grading)
