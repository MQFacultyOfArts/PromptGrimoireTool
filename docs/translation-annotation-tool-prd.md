# Translation Annotation & Iteration Tool - Product Requirements Document

## Overview

Translation Annotation & Iteration Tool is an educational application for teaching translation process, critical reasoning, and AI literacy in multilingual contexts. It enables students to systematically analyze source texts, document translation decisions, iterate on drafts, and critically evaluate AI-assisted workflows through structured annotation and proleptic reasoning.

**Target:** Session 1 2025 (Feb 23 student training - Week 2)
**Deployment:** Single institution (Macquarie University)
**Cohort Size:** ~25 students (Japanese, Korean, Chinese, Spanish language pairs)
**Relationship to PromptGrimoire:** Domain-specific extension for translation pedagogy, shares core infrastructure (CRDT collaboration, annotation layer, PDF export)

## Pedagogical Framework

### Proleptic Reasoning in Translation

Students engage in a three-stage predictive learning cycle:

**STAGE 1 - Source Text Analysis (Tab 1):**
- Predict translation challenges (idioms, cultural references, ambiguities)
- Anticipate required strategies (adaptation, modulation, transposition)
- Document predictions as annotations with reasoning

**STAGE 2 - Translation Drafting (Tab 3):**
- Make translation decisions WHILE translating
- Document rationale: "I'm choosing X BECAUSE I predict/anticipate Y"
- Capture decision log entries with predictive reasoning

**STAGE 3 - Post-Feedback Revision (Tab 1):**
- Verify predictions against AI feedback or peer review
- Annotate revised drafts: "My prediction was correct/incorrect because..."
- Demonstrate learning through adjusted reasoning

This creates a complete learning cycle: **Predict → Decide → Verify → Revise**

### Learning Objectives

**Primary:** Domain-specific translation reasoning
- Identify translation-rich points (challenges requiring strategic decisions)
- Apply translation strategies systematically
- Document and justify translation choices
- Iterate based on feedback (human or AI)

**Secondary:** AI literacy and prompt evaluation
- Critically evaluate prompting strategies (success/failure analysis with WHY)
- Assess AI-generated translations for quality and appropriateness
- Integrate AI feedback into iterative translation process
- Develop metacognitive awareness of AI as collaborative tool

## Tech Stack (Inherited from PromptGrimoire)

- **Python 3.14**
- **NiceGUI** - web UI framework
  - `ui.editor` - WYSIWYG for translation drafting
- **SQLModel** - ORM (Pydantic + SQLAlchemy)
- **PostgreSQL** - persistence
- **Stytch** - auth (magic links, passkeys, RBAC)
- **pycrdt** - CRDT for real-time collaboration (all screens)

### Additional Dependencies

- **striprtf** or similar - RTF text extraction for source documents
- **WeasyPrint** or **ReportLab** - PDF generation for exports
- **xeCJK LaTeX package** - CJK font support for PDF export

## User Roles

Reuses PromptGrimoire's Stytch RBAC configuration:

| Role | Permissions |
|------|-------------|
| Admin | Full system access, user management, all courses |
| Instructor | Create/manage courses, upload source texts, view all student work, export process reports |
| Student | View assigned tasks, annotate documents, create translations, iterate on drafts, export for iLearn |

## User Stories

### Student - Scenario 1 (Human-First Translation)

**As a student**, I want to:
1. View the instructor-provided source text in Tab 1
2. Annotate source text to identify translation challenges and predict strategies
3. Write my initial translation from scratch in Tab 3
4. Save my translation as Draft 1 (timestamped snapshot sent to Tab 1)
5. Use an external LLM to get feedback on my translation
6. Paste the AI conversation into Tab 1 as a new document
7. Annotate my prompts to explain WHY they succeeded or failed
8. Revise my translation in Tab 3 based on AI feedback
9. Document my decision-making in the decision log ("I changed X BECAUSE...")
10. Save as Draft 2 (sent to Tab 1)
11. Annotate Draft 2 to verify my predictions and show improvements
12. Iterate multiple times (Draft 3, 4, etc.) within the week
13. Organize my annotations by theme/priority in Tab 2
14. Select 4-5 key decisions and export final translation for iLearn submission

**So that:** I develop systematic translation reasoning, learn from AI feedback, and demonstrate my iterative process for grading.

### Student - Scenario 2 (AI-Assisted Translation)

**As a student**, I want to:
1. View the source text in Tab 1 and annotate predicted challenges
2. Use an external LLM to generate an initial translation
3. Paste the AI-generated translation directly into Tab 3 for revision
4. Paste the full AI conversation into Tab 1 for prompt analysis
5. Annotate my generation prompts (quality analysis with WHY)
6. Revise the AI output in Tab 3 (fixing errors, improving style)
7. Document what I kept/changed and why in the decision log
8. Save as Draft 1 (sent to Tab 1)
9. Annotate Draft 1 showing my reasoning for edits
10. Get additional AI feedback, iterate to Draft 2, 3, etc.
11. Organize annotations in Tab 2
12. Export final translation with curated decision notes for iLearn

**So that:** I learn to critically evaluate and improve AI-generated translations while maintaining accountability for final quality.

### Instructor (Vanessa) - Process Grading

**As an instructor**, I want to:
1. Upload source texts (RTF, HTML, or plain text) to weekly assignments
2. Optionally provide suggested tags to help students get started
3. View any student's complete annotation workspace (all tabs)
4. See all documents in their Tab 1 (source, AI conversations, all drafts)
5. Read their decision log entries (visible as sidebar when viewing drafts)
6. Review their annotation patterns across source text and drafts
7. See timestamps on all drafts to track iteration frequency
8. Export comprehensive process reports for learning portfolio grading (20%)
9. Facilitate in-class discussions using students' annotated work

**So that:** I can grade students' translation reasoning process, critical thinking about AI, and iterative improvement—independent of target language quality.

### Language Tutors - Quality Grading

**As a language tutor**, I want to:
1. Receive student-exported translation PDFs via iLearn
2. See the final translation text with 4-5 selected decision notes
3. Understand student reasoning for major translation choices
4. Grade translation quality in target language (accuracy, fluency, style)

**So that:** I can assess linguistic quality and appropriateness without needing to review extensive annotation work (which Vanessa handles).

## Information Architecture

```
Course
└── Week
    └── TranslationAssignment
        ├── Source Document (instructor-uploaded)
        └── Student Work (per student)
            ├── Documents in Tab 1:
            │   ├── Source Text (read-only)
            │   ├── AI Conversation 1, 2, ... N (student-pasted)
            │   └── Draft 1, 2, ... N (timestamped from Tab 3)
            ├── Annotations (on all documents)
            │   └── Custom Tags (student-created)
            ├── Card Organization (Tab 2 state)
            └── Active Translation Workspace (Tab 3)
                ├── Translation text (auto-saved)
                └── Decision Log (saved with snapshots)
```

## Data Model

### Core Entities

```
Course
├── id: UUID
├── name: str
├── code: str (e.g., "TRAN1000")
├── instructor_id: FK → User
├── semester: str (e.g., "2025-S1")
├── is_archived: bool
└── created_at: datetime

Week
├── id: UUID
├── course_id: FK → Course
├── week_number: int (1-13)
├── title: str (e.g., "Week 3: Business Translation")
├── is_published: bool
└── visible_from: datetime | None

TranslationAssignment
├── id: UUID
├── week_id: FK → Week
├── title: str (e.g., "Business Email Translation EN→JA")
├── source_document_id: FK → Document
├── instructions: str (HTML - instructor guidance)
├── due_date: datetime | None
└── created_at: datetime

Document
├── id: UUID
├── assignment_id: FK → TranslationAssignment
├── student_id: FK → User (nullable for instructor source docs)
├── type: enum (source_text | ai_conversation | translation_draft)
├── content: str (HTML with word-level spans for annotation)
├── raw_content: str (original pasted/uploaded text)
├── order_index: int (display order in Tab 1)
├── metadata: JSON
│   ├── decision_log: List[DecisionLogEntry] (for translation_draft only)
│   │   ├── timestamp: datetime
│   │   ├── text_span: (start_word, end_word)
│   │   └── reasoning: str
│   ├── conversation_metadata: {...} (for ai_conversation if needed)
│   └── language_pair: str (e.g., "en-ja")
├── timestamp: datetime (for drafts: when saved from Tab 3)
└── created_at: datetime

Tag
├── id: UUID
├── assignment_id: FK → TranslationAssignment (or null for global)
├── student_id: FK → User (custom tags) or null (suggested system tags)
├── name: str (e.g., "predicted_challenge", "strategy_adaptation")
├── description: str (what this tag means)
├── color: str (hex, auto-assigned from accessible palette)
├── is_system_tag: bool (suggested starter vs student-created)
├── category: str | None (e.g., "source_analysis", "prompt_quality", "draft_revision")
└── created_at: datetime

Highlight
├── id: UUID
├── document_id: FK → Document
├── student_id: FK → User
├── start_word: int (word-level indexing)
├── end_word: int (exclusive)
├── tag_id: FK → Tag
├── note: str (required - critical reflection explaining annotation)
├── paragraph_num: int | None (auto-detected from document structure)
└── created_at: datetime

HighlightComment
├── id: UUID
├── highlight_id: FK → Highlight
├── author_id: FK → User
├── text: str
└── created_at: datetime

AnnotationCardOrder (Tab 2 organization state)
├── id: UUID
├── assignment_id: FK → TranslationAssignment
├── student_id: FK → User
├── tag_id: FK → Tag
├── ordered_highlight_ids: List[UUID] (JSON array)
└── updated_at: datetime

TranslationWorkspace (Tab 3 persistent state)
├── id: UUID
├── assignment_id: FK → TranslationAssignment
├── student_id: FK → User
├── translation_content: str (current work-in-progress)
├── decision_log_draft: List[DecisionLogEntry] (not yet saved to Tab 1)
├── auto_saved_at: datetime (periodic DB sync)
└── updated_at: datetime
```

### Suggested Starter Tags (Optional System Tags)

**Source Text Analysis:**
- `predicted_challenge` - Translation-rich point identified proactively
- `cultural_reference` - Culture-specific element requiring strategy
- `ambiguity` - Multiple valid interpretations
- `audience_consideration` - Target reader expectations
- `strategy_literal` - Direct translation predicted
- `strategy_adaptation` - Cultural adaptation predicted
- `strategy_modulation` - Perspective shift predicted

**AI Conversation Analysis:**
- `prompt_success` - Effective prompt with WHY explanation
- `prompt_failure` - Ineffective prompt with WHY explanation
- `learned_pattern` - Prompting insight or pattern discovered

**Draft Revision:**
- `prediction_verified` - Stage 1 prediction was correct
- `prediction_incorrect` - Stage 1 prediction was wrong, revised approach
- `improvement_made` - Change between drafts with rationale
- `quality_issue` - Error or weakness identified

Students can use, modify, or ignore these suggestions and create fully custom tags with their own names and descriptions.

## Features

### MVP (Feb 2025)

#### Three-Screen Workflow

The application uses a **single-page interface** with three tabs. All screens are CRDT-synced for real-time collaboration. Navigation via **always-visible tab bar**: Annotate | Organize | Write.

Students can navigate freely between tabs at any time (no validation gates).

#### Tab 1: Document Collection & Annotation

**Multi-Document Viewer:**
- Document list/switcher showing all documents for this assignment
- Document types displayed:
  1. **Source Text** (instructor-uploaded, read-only for students)
  2. **AI Conversation Documents** (student-pasted, shown as continuous text)
  3. **Translation Drafts** (auto-created from Tab 3 snapshots)
- Current document displayed with word-level spans for annotation
- Order preserved: source text first, then conversations, then drafts by timestamp

**Document Upload/Import:**
- **Instructor**: Upload source text (RTF, HTML, or plain text)
  - System parses into word-level spans for annotation
  - Optionally provide suggested starter tags for this assignment
- **Students**: "Add AI Conversation" button
  - Opens dialog to paste conversation text
  - System creates new document in Tab 1 as continuous text (no turn parsing)
  - Students manually select text spans to annotate prompts vs responses
- **System**: Auto-add timestamped drafts from Tab 3 "Save & Send" action

**Annotation Layer (CRDT-synced):**
- **Word-level highlighting** across all document types
- **Tag system**:
  - Optional suggested starter tags (instructor can provide, students can use/ignore)
  - **Custom tag creation** dialog:
    - Name (e.g., "metaphor_challenge")
    - Description (e.g., "Metaphors requiring cultural adaptation")
    - Color auto-assigned from accessible palette
    - Category (optional grouping)
  - **Tag management**:
    - Edit tag descriptions
    - Change tag colors
    - Delete unused tags (with confirmation if highlights exist)
  - Students have full freedom to create their own analytical vocabulary
- **Annotation workflow**:
  1. Select text span (words)
  2. Choose tag from palette or create new tag
  3. Write required note explaining the annotation (critical reflection)
  4. Optional: Add paragraph/sentence reference
- **Annotation cards** in scrollable sidebar:
  - Tag name and color
  - Author name
  - Timestamp
  - Paragraph/segment reference (if detected)
  - Highlighted text preview (truncated)
  - Note content (critical reflection)
  - Threaded comments (CRDT-synced for collaboration)
  - "Go to text" button (scrolls and temporarily highlights source)
  - Delete button (removes highlight)
- **Multi-language input support**:
  - Full Unicode support for Japanese, Korean, Chinese, Spanish, French
  - Test against [Big List of Naughty Strings](https://github.com/minimaxir/big-list-of-naughty-strings)
  - Proper font rendering for CJK characters
  - No special keyboard switching required (native OS input methods)

**Translation Draft Documents (Special Display):**
- Draft document shows translation text with standard annotation layer
- **Collapsible Decision Log Sidebar**:
  - Appears when viewing a translation_draft document
  - Shows decision log entries from Tab 3 (read-only)
  - Each entry displays:
    - Timestamp
    - Referenced text span (click to highlight in document)
    - Reasoning note
  - Provides context for verification annotations
  - NOT directly annotatable (students annotate the translation text itself)
- Students annotate the draft text to evaluate their decisions:
  - "My Draft 1 prediction about domestication was wrong because..."
  - "Changed to adaptation here - AI feedback revealed cultural gap I didn't anticipate"

**Real-time Collaboration:**
- Live cursor/selection sharing (Google Docs style)
- Presence indicators ("3 users online")
- Annotation changes sync immediately
- Comment threads update in real-time

#### Tab 2: Organize Annotations

(Inherited from case brief tool design, adapted for translation workflow)

- **Kanban-style card view** (Trello-like layout)
- **Columns** = tag categories (one column per tag)
- **Cards** = annotations from Tab 1
  - Show tag, highlighted text preview, note preview
  - Click card → navigates to Tab 1 and highlights source
- **Drag-and-drop reordering**:
  - **Within columns**: Prioritize annotations by importance/theme
  - **Between columns**: Re-tag annotations (change tag assignment)
- **CRDT-synced** for collaborative organization
- **Collapsible columns** for focus
- **Purpose**:
  - Identify patterns across source text and draft annotations
  - Group related challenges (e.g., all metaphors, all cultural references)
  - Prioritize issues for next revision
  - Prepare for in-class discussion

#### Tab 3: Translation Workspace

**Parallel Text Layout:**
- **Left panel (30%)**: Source text display
  - Read-only view of instructor-provided source text
  - Same content as Tab 1, but shown for reference while translating
  - Synchronized scrolling (optional toggle)
- **Right panel (70%)**: Translation editor
  - WYSIWYG editor or plain text mode (student choice)
  - **Persistent workspace**: Content auto-saves to localStorage + periodic DB sync
  - Does NOT clear after "Save & Send to Tab 1"
  - Students continue editing same workspace toward next draft

**Translator's Decision Log:**
- **Separate panel** below or beside parallel text
- **Purpose**: Capture proleptic reasoning WHILE translating
- **Log entry creation**:
  1. Select text span in translation (right panel)
  2. Click "Add Decision Note" button
  3. Write reasoning (e.g., "Using adaptation here BECAUSE I predict cultural frame mismatch with [specific reason]")
  4. Timestamp auto-added
  5. Entry appears in list below
- **Entry display**:
  - Chronological list with timestamps
  - Each entry shows: text span reference, reasoning note
  - Click entry → highlights referenced text in translation
  - Editable during current session
  - Becomes read-only after "Save & Send to Tab 1"
- **Entry management**:
  - Edit or delete entries before saving to Tab 1
  - After save, entries become part of draft metadata (read-only)

**Actions:**

1. **"Save & Send to Tab 1"** button:
   - Creates timestamped snapshot of:
     - Translation text (right panel content)
     - Decision log entries (as metadata)
   - Adds new document to Tab 1 as "Draft N (YYYY-MM-DD HH:MM)"
   - Decision log appears as collapsible sidebar when viewing draft in Tab 1
   - **Does NOT clear Tab 3 workspace** - students continue editing
   - Use case: Student saves Draft 1, gets feedback, continues editing in Tab 3, saves Draft 2, etc.

2. **"Export Final Translation for iLearn"** button (MVP: basic export):
   - Opens dialog showing:
     - Translation text
     - List of all decision log entries and Tab 1 annotations on drafts
   - **Student selects 4-5 key decisions** to include via checkboxes
   - Generates downloadable PDF or Word document:
     - Full translation text
     - Selected reasoning notes (embedded or appended)
   - **Purpose**: Curated submission for language tutors (quality grading)
   - **Note**: Does NOT export all annotation work (Vanessa reviews that in-tool)

**Auto-Save Behavior:**
- Tab 3 content (translation + decision log draft) saves to:
  - Browser localStorage (immediate, survives page refresh)
  - PostgreSQL TranslationWorkspace table (periodic sync every 30 seconds)
- On return to Tab 3:
  - Load most recent auto-saved content
  - Students never lose work if they switch tabs or close browser

**Version Control (MVP):**
- Tab 3 is single-workspace (not multi-document)
- Students can't have multiple drafts open simultaneously in Tab 3
- Tab 3 = whatever they're currently working on
- All saved drafts live in Tab 1 where students view/annotate them
- **Phase 2**: "Load Draft N to Tab 3" button to copy previous draft back for editing

#### Tag Management

**Tag Creation Dialog:**
- Accessible from all tabs (global action button)
- Fields:
  - Name (required, e.g., "metaphor_gap")
  - Description (optional, e.g., "Metaphors with no target language equivalent")
  - Category (optional dropdown: source_analysis, prompt_quality, draft_revision, custom)
- Color auto-assigned from colorblind-accessible palette
- Tag immediately available in annotation palette

**Tag Editor:**
- List view of all tags (system suggested + student custom)
- Edit: Change name, description, category
- Delete: Shows warning if highlights exist with this tag
  - Option: Delete tag only (highlights remain untagged)
  - Option: Delete tag + all highlights with this tag
- Reorder: Drag to change palette display order

**Tag Visibility:**
- System suggested tags marked with icon (students can hide/ignore)
- Student custom tags marked with creator name (in collaborative scenarios)
- Filter view: Show only tags I created / Show all tags

#### Export & Grading Integration

**For Vanessa (Process Grading):**
- View any student's complete workspace in-tool
- See all documents in Tab 1 (source, conversations, all drafts)
- Read decision logs (sidebar when viewing drafts)
- Review annotation patterns and critical reflections
- See timestamps on all drafts (iteration frequency)
- **Phase 2**: Export comprehensive process report PDF
  - Source text + all drafts + all annotations + decision logs
  - For learning portfolio grading (20% of grade)

**For Language Tutors (Quality Grading via iLearn):**
- Students export via "Export for iLearn" button
- Curated PDF/Word document:
  - Final translation text
  - 4-5 selected decision notes (student-chosen)
- Tutors grade translation quality (accuracy, fluency, style)
- Tutors do NOT see extensive annotation work (that's Vanessa's domain)

**For Students (Submission):**
- "Export for iLearn" creates downloadable file
- Students upload to iLearn for tutor grading
- Separate from in-tool annotation work (which persists for Vanessa's review)

#### Course/Week/Assignment Structure

Inherited from existing PromptGrimoire structure:

- **Courses**: Instructor creates courses with code, name, semester
- **Weeks**: Within courses, weekly modules (1-13)
- **Assignments**: Within weeks, translation tasks
  - Each assignment has one source document
  - Students have independent workspaces per assignment
  - All student work persists in assignment workspace

**Weekly Workflow:**
- Week N published → students see new translation assignment
- One translation task per week
- Multiple iterations (drafts) within the week
- In-class discussion (Week N+1) using annotated work from Week N

### Phase 2 (Post-MVP)

#### Load Previous Draft to Tab 3
- Button on draft documents in Tab 1: "Load to Tab 3"
- Copies draft content back to Tab 3 translation editor
- Allows branching: Draft 2 → edit → becomes Draft 3 or 2.1
- Decision log from original draft stays in Tab 1 (read-only)
- Student creates NEW decision log entries in Tab 3 for this revision

#### Anonymous Peer Sharing
- Students opt-in to share annotated work anonymously
- Peers can view (read-only) and add comments
- Vanessa and admins see true authorship
- Respects cultural comfort with public critique
- Use case: In-class peer review sessions

#### Comprehensive Process Export
- "Export Process Report" button for instructors
- Generates PDF with:
  - Source text
  - All student drafts (chronological)
  - All annotations with notes
  - All decision log entries
  - Iteration timeline visualization
- For Vanessa's learning portfolio grading

#### Advanced Tag Analytics
- Tag frequency heatmaps (which challenges most common?)
- Correlation analysis (which tags co-occur?)
- Student vs cohort comparison (am I identifying same challenges as peers?)

#### SillyTavern Roleplay Integration
- Character card: Professional client scenarios
- Students practice justifying translation choices
- Roleplay: Client asks "Why did you translate it this way?"
- Student defends decisions using their annotations/decision log
- Use case: Communication skills training (second half of semester)

#### Instructor Annotations
- Vanessa can add inline comments on student work
- Feedback visible to student
- Does NOT replace numerical grading (which happens in iLearn)

## User Workflows

### Instructor Workflow (Vanessa)

1. **Create Course** → Set name "TRAN1000", semester "2025-S1"
2. **Configure Weeks** → Add weekly modules (Week 1 through Week 13)
3. **Create Translation Assignment** (Week N):
   - Upload source text (RTF or plain text)
   - Set title (e.g., "Business Email EN→JA")
   - Write instructions (HTML editor)
   - Optionally provide suggested starter tags
4. **Publish Assignment** → Students see task in their course view
5. **Monitor Progress** (during week):
   - View individual student workspaces (all tabs)
   - See draft timestamps (are they iterating early or last-minute?)
   - Read annotations and decision logs (in-tool review)
6. **Facilitate In-Class Discussion** (Week N+1):
   - Project student work (anonymized if needed)
   - Discuss annotation patterns, strategies, AI interactions
7. **Grade Process Work** (end of semester):
   - Review all student annotation work in-tool
   - Export process reports (Phase 2) for records
   - Assign learning portfolio grade (20% of course)

### Student Workflow - Scenario 1 (Human-First Translation)

**Week N (Before Class):**

1. **Tab 1 - Source Analysis**:
   - Open Week N assignment
   - Read source text
   - Annotate predicted challenges with custom tags:
     - "This idiom has no direct Japanese equivalent - predict I'll need adaptation strategy"
     - "Formal register - predict I'll need honorific forms in Japanese"
   - Document proleptic reasoning in annotation notes

2. **Tab 3 - Initial Translation**:
   - View source text (left panel)
   - Type translation from scratch (right panel)
   - Add decision log entries while working:
     - "Using keigo (honorific speech) here BECAUSE source uses formal register and I predict Japanese reader expects formality in business context"
   - Click "Save & Send to Tab 1" → creates Draft 1

3. **External - AI Feedback**:
   - Copy Draft 1 from Tab 1
   - Paste into ChatGPT with prompt: "Review this Japanese translation for accuracy and naturalness"
   - Receive AI feedback

4. **Tab 1 - Analyze AI Feedback**:
   - Click "Add AI Conversation"
   - Paste full conversation
   - Annotate prompts:
     - Tag: `prompt_success`, Note: "This prompt worked BECAUSE I specified 'naturalness' not just accuracy - AI gave cultural feedback"
     - Tag: `prompt_failure`, Note: "Should have specified business context - AI gave casual suggestions"

5. **Tab 1 - Annotate Draft 1**:
   - Switch to Draft 1 document
   - Read decision log (sidebar) to recall my reasoning
   - Annotate areas where AI found issues:
     - "My prediction about keigo was CORRECT - AI confirmed appropriateness"
     - "WRONG prediction - this metaphor doesn't work in Japanese (AI explained why)"

6. **Tab 3 - Revise Translation**:
   - Continue editing in Tab 3 (Draft 1 is still there)
   - Make changes based on AI feedback
   - Add NEW decision log entries:
     - "Changed metaphor to direct description BECAUSE AI feedback revealed cultural gap I didn't anticipate in Stage 1"
   - Click "Save & Send to Tab 1" → creates Draft 2

7. **Iterate** (optional):
   - Get more feedback (AI or peer)
   - Annotate Draft 2 in Tab 1
   - Revise in Tab 3 → Draft 3
   - Repeat as needed before class

8. **Tab 2 - Organize**:
   - Review all annotations (source + conversations + drafts)
   - Drag cards to group by theme (all metaphor challenges, all keigo decisions)
   - Prioritize for class discussion

9. **Export for Submission**:
   - Tab 3: Click "Export for iLearn"
   - Select 4-5 key decision notes (major challenges)
   - Download PDF
   - Upload to iLearn for language tutor grading

**Week N+1 (In Class):**
- Vanessa projects anonymized student work
- Discuss annotation patterns (what challenges did everyone identify?)
- Compare strategies (how did different students solve same problem?)
- Reflect on AI interactions (which prompts were effective?)

### Student Workflow - Scenario 2 (AI-Assisted Translation)

**Week N (Before Class):**

1. **Tab 1 - Source Analysis**:
   - Annotate source text with predicted challenges (same as Scenario 1)

2. **External - AI Translation**:
   - Copy source text
   - Prompt ChatGPT: "Translate this business email from English to Japanese using formal keigo register"
   - Receive AI-generated translation

3. **Tab 3 - Initial Revision**:
   - Paste AI translation into right panel (direct paste, no parsing)
   - Add decision log entries while reviewing:
     - "AI used 敬語 form correctly - keeping this BECAUSE appropriate for business context"
     - "AI translated idiom literally - changing to natural Japanese expression BECAUSE literal version sounds unnatural"
   - Click "Save & Send to Tab 1" → creates Draft 1 (revised AI output)

4. **Tab 1 - Analyze Generation Prompt**:
   - Click "Add AI Conversation"
   - Paste full conversation (source text + prompt + AI translation)
   - Annotate prompt quality:
     - Tag: `prompt_success`, Note: "Specified 'formal keigo' WORKED - AI used appropriate register throughout"
     - Tag: `prompt_failure`, Note: "Should have warned about idioms - AI translated literally without cultural adaptation"

5. **Tab 1 - Annotate Draft 1**:
   - Switch to Draft 1 (my revised version of AI output)
   - Annotate changes I made:
     - "Kept AI's keigo forms - prediction about formality was correct"
     - "Changed idiom - my prediction about this needing adaptation was correct, AI failed here"

6. **Iterate** (same as Scenario 1):
   - Get more AI feedback on Draft 1
   - Paste conversation to Tab 1, annotate prompts
   - Revise in Tab 3 → Draft 2
   - Repeat as needed

7. **Tab 2 - Organize** (same as Scenario 1)

8. **Export for Submission** (same as Scenario 1)

**Key Difference from Scenario 1:**
- Translation starts from AI output, not from scratch
- More emphasis on critical evaluation of AI generation quality
- Students accountable for ALL final translation decisions (even if AI made initial choice)

## Technical Considerations

### RTF/Text Processing
- Reuse existing `parse_rtf()` from case brief tool
- Support plain text and HTML upload for source texts
- Word-level span wrapping for annotation layer
  - Each word wrapped in `<span class="w" data-w="N">word</span>`
  - Preserves whitespace and HTML entities
  - Paragraph detection for reference numbers

### CRDT Sync (pycrdt)
- All tabs CRDT-synced for real-time collaboration
- Document content: CRDT Text type
- Annotations (highlights): CRDT Map type (highlight_id → highlight data)
- Decision log in Tab 3: CRDT Array type (for collaborative drafting)
- Card ordering in Tab 2: CRDT Map type (tag_id → ordered highlight IDs)
- Live cursor/selection sharing: Ephemeral WebSocket state (not persisted)

### Multi-Language Storage & Display
- PostgreSQL UTF-8 encoding (already configured)
- No special storage requirements for CJK/Spanish text
- Test character limits on text fields (avoid truncation of multi-byte characters)
- **Font rendering**:
  - Web: System fonts with CJK fallbacks (Noto Sans CJK, etc.)
  - CSS: `font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans CJK JP", "Noto Sans CJK KR", sans-serif;`
- **Input handling**:
  - Native browser IME support (no custom keyboard logic)
  - Test with Japanese IME (hiragana → kanji conversion)
  - Test with Korean IME (jamo → syllable composition)
  - Test with Chinese IME (pinyin input)

### Input Validation (Security)
- **Text field length limits**:
  - Annotation notes: 5000 characters (allow detailed reflection)
  - Decision log entries: 2000 characters
  - Tag names: 50 characters
  - Tag descriptions: 200 characters
- **HTML sanitization**:
  - WYSIWYG editor output sanitized before storage (XSS prevention)
  - Allowed tags: `<p>, <strong>, <em>, <ul>, <ol>, <li>, <br>`
  - Strip `<script>, <iframe>, <object>` tags
- **Upload size limits**:
  - Source document: 5MB max (reasonable for RTF/text files)
  - AI conversation paste: 50,000 characters max (prevent DoS)

### Tab 3 Persistence Architecture
- **Auto-save strategy**:
  - LocalStorage: Immediate save on every change (debounced 500ms)
  - PostgreSQL: Background sync every 30 seconds
  - Key: `translation_workspace_${assignment_id}_${student_id}`
- **Conflict resolution**:
  - If Tab 3 open in multiple browser tabs/devices: last-write-wins (acceptable for single-user workspace)
  - On load: Check DB timestamp vs localStorage timestamp, use newer
- **Data stored**:
  - Translation content (HTML from WYSIWYG)
  - Decision log draft (JSON array)
  - Last saved timestamp
- **Recovery**:
  - If browser crash: localStorage survives, loads on return
  - If localStorage cleared: DB backup loads (may be up to 30 seconds stale)

### PDF Export (LaTeX via TinyTeX)
- Reuse existing export infrastructure from case brief tool
- **New templates needed**:
  - **Curated export** (for iLearn submission):
    - Translation text (full)
    - Selected decision notes (4-5 entries, student-chosen)
    - Clean, professional format for tutor grading
  - **Comprehensive export** (Phase 2, for Vanessa):
    - Source text
    - All drafts (chronological with timestamps)
    - All annotations with notes
    - All decision log entries
    - Iteration timeline
- **CJK font support**:
  - Use xeCJK LaTeX package
  - System fonts: Noto Sans CJK, Noto Serif CJK (open-source, bundled)
  - Test rendering: Japanese kanji, Korean hangul, Chinese hanzi, Spanish tildes

### Database Indexes (Performance)
- `Document.assignment_id` + `Document.student_id` (query student's documents)
- `Document.type` (filter by document type)
- `Highlight.document_id` (query annotations for document)
- `Highlight.tag_id` (query by tag)
- `Tag.assignment_id` + `Tag.student_id` (query student's custom tags)
- `AnnotationCardOrder.assignment_id` + `AnnotationCardOrder.student_id` (load Tab 2 state)

## UI/UX Considerations

### Platform Support
- **Desktop only** - no tablet/mobile support
- Students without computers use university lab facilities
- Minimum screen resolution: 1366x768 (standard laptop)

### Navigation
- **Tab bar** always visible at top: Annotate | Organize | Write
- Single-page interface with smooth transitions between tabs
- No page reloads (state maintained client-side + CRDT sync)
- Active tab highlighted

### Tab 1: Annotate
- **Layout**: Document viewer (70%) + annotation cards sidebar (30%)
- **Document switcher**: Dropdown or tabs showing all documents
  - Source text (icon: 📄)
  - AI conversations (icon: 💬)
  - Drafts (icon: ✏️ with timestamp)
- **Tag toolbar** in header:
  - Color-coded tag buttons with keyboard shortcuts [1-9, 0]
  - "Create New Tag" button
  - Tag filter dropdown (show annotations by tag)
- **Annotation cards**:
  - Scroll-synced to document position (optional, can be disabled)
  - "Go to text" button scrolls document and temporarily highlights (yellow outline for 1.5 seconds)
  - Delete button (with confirmation)
  - Comment input below each card
- **Decision log sidebar** (when viewing draft documents):
  - Collapsible panel on right (overlays annotation cards when open)
  - Header: "Decision Log - Draft N"
  - Entries show timestamp, text reference, reasoning
  - Click entry → highlights text in document
  - Close button returns to annotation cards view

### Tab 2: Organize
- **Kanban layout**: Horizontal columns, one per tag
- **Column headers**: Tag name, color, annotation count
- **Cards**: Compact view with tag color, text preview (50 chars), note preview (80 chars)
- **Drag handles**: Visual feedback during drag (card transparency, drop zone highlights)
- **Collapsible columns**: Click header to collapse (shows only header + count)
- **Empty state**: "No annotations with this tag yet"

### Tab 3: Write
- **Parallel text**:
  - Left panel: Source text (read-only, light gray background)
  - Right panel: Translation editor (white background)
  - Synchronized scrolling toggle (icon button between panels)
- **Decision log panel** (below or beside parallel text):
  - Header: "Decision Log" + entry count
  - "Add Decision Note" button (opens modal)
  - Entry list: chronological, each with timestamp, text reference, reasoning
  - Edit/delete icons on each entry (before saving to Tab 1)
- **Action buttons** (bottom right):
  - "Save & Send to Tab 1" (primary button, blue)
  - "Export for iLearn" (secondary button, gray)
- **Auto-save indicator**: Small icon showing "Saved 30 seconds ago" or "Saving..."

### Accessibility
- **Colorblind-accessible tag palette**: Use ColorBrewer qualitative schemes + patterns/icons
- **Keyboard shortcuts**:
  - Tab navigation: Ctrl+1 (Tab 1), Ctrl+2 (Tab 2), Ctrl+3 (Tab 3)
  - Tag application: Number keys [1-0] when text selected
  - Save snapshot: Ctrl+S in Tab 3
- **Screen reader support**:
  - ARIA labels on all interactive elements
  - Semantic HTML (`<nav>`, `<main>`, `<aside>`)
  - Focus management (when switching tabs, focus moves to main content)

## Success Metrics

**For Students:**
- Complete weekly translation tasks (1 task per week, multiple drafts)
- Create highlights on source text BEFORE drafting (proleptic reasoning)
- Document decision-making in decision logs (capture "BECAUSE I predict..." reasoning)
- Iterate on drafts (minimum 2 drafts per task, goal 3-4)
- Critically annotate AI prompts (explain WHY success/failure)
- Annotate own drafts to verify predictions (Stage 3 reflection)
- Successfully export final translations for iLearn submission

**For Vanessa (Process Grading):**
- View all student annotation work per assignment
- Track iteration frequency (draft timestamps)
- Assess critical thinking in annotation notes
- Review proleptic reasoning quality (prediction → decision → verification cycle)
- Grade learning portfolio (20% of course) based on process work
- Facilitate in-class discussions using student work

**For Language Tutors (Quality Grading):**
- Receive curated exports with translation + key decisions
- Grade translation quality (accuracy, fluency, style) based on linguistic criteria
- Understand student reasoning for major choices (via 4-5 selected notes)

**For System:**
- Real-time collaboration works smoothly (CRDT sync, live cursors)
- Multi-language input functions correctly (Japanese, Korean, Chinese, Spanish)
- Auto-save prevents data loss (Tab 3 persistence)
- PDF exports generate successfully (curated format for tutors)

## Timeline & Phasing

### Pre-Launch (Jan 2025)
- Development (Brian)
- Testing with Big List of Naughty Strings (multi-language validation)
- Internal testing (Brian + Vanessa)

### Week 1 (Feb 17, 2025) - Soft Launch
- Course created in system
- Vanessa uploads Week 1 source text (simple task for onboarding)
- Suggested starter tags configured

### Week 2 (Feb 24, 2025) - Student Training
- Brian guest lecture: Tool demonstration + AI pedagogy overview
- Students create accounts, access Week 1 assignment
- Practice: Annotate source text, paste AI conversation, save draft
- Week 2 assignment released (first graded task)

### Weeks 3-13 (Mar-May 2025) - Production Use
- Weekly translation tasks (one per week)
- Students iterate on drafts before in-class discussion
- Vanessa monitors progress, facilitates discussions
- Ongoing bug fixes and minor improvements

### End of Semester (June 2025)
- Final translation submissions via iLearn (language tutors grade quality)
- Vanessa grades learning portfolios (process work, 20%)
- Retrospective: What worked, what needs improvement

### Phase 2 (Semester 2 2025) - Enhancements
- Anonymous peer sharing
- Comprehensive process export for Vanessa
- Load previous draft to Tab 3
- SillyTavern roleplay integration (client communication scenarios)
- Advanced tag analytics

## Open Questions

1. **LMS Integration**: Future need to auto-sync grades from iLearn to tool (or vice versa)?
2. **Bulk Operations**: Should Vanessa be able to bulk-export all student PDFs for a given assignment?
3. **Group Work**: Support for collaborative translation (team of 2-3 students sharing same workspace)?
4. **Language Pair Flexibility**: Should students be able to select language pair per assignment (or is it fixed per course)?
5. **Offline Mode**: Progressive Web App support for working without internet (sync on reconnect)?

## Resolved Questions

1. **AI conversation parsing**: Continuous text block (Option A) - no turn parsing needed
2. **Decision log integration**: Metadata sidebar (Option C) - read-only reference, not annotatable
3. **AI translation workflow**: Direct paste to Tab 3 (Option C/D hybrid) - no "Load to Tab 3" button needed
4. **Tab 3 persistence**: Auto-save to localStorage + DB - never loses work
5. **Tag system**: Optional starters + full student control - no mandatory system tags
6. **Export scope**: Two types - curated for tutors (4-5 notes), comprehensive for Vanessa (Phase 2)
7. **Multi-language support**: Native OS IME, Unicode storage, CJK fonts in PDF - no special input widgets
8. **Real-time collaboration**: MVP for all tabs (inherited from case brief tool CRDT architecture)
9. **Version control**: Simple snapshot model (MVP), branching in Phase 2
10. **Document order**: Source first, then conversations, then drafts by timestamp (fixed, not user-reorderable)

## Appendix: Comparison to Case Brief Tool

| Aspect | Case Brief Tool | Translation Annotation Tool |
|--------|-----------------|----------------------------|
| Domain | Legal education | Translation pedagogy |
| Core content | Court judgment RTFs | Source texts + AI conversations + drafts |
| Annotation target | Case text (word-level) | Source, conversations, drafts (all word-level) |
| Structured output | 10 brief tags + freeform brief | Custom tags + translation drafts + decision logs |
| Collaboration | CRDT all screens (MVP) | CRDT all screens (MVP) |
| Export | Combined PDF (case + annotations + brief) | Curated PDF (translation + 4-5 notes) |
| Organization | Course > Week > Case | Course > Week > TranslationAssignment |
| Workflow | Three-screen carousel (annotate → organize → write) | Three-tab interface (annotate → organize → write) |
| Proleptic reasoning | Implicit (students predict issues in brief) | Explicit (Stage 1 predict → Stage 2 decide → Stage 3 verify) |
| Multi-language | English only | Japanese, Korean, Chinese, Spanish, French |
| Iteration | Single brief per case | Multiple drafts per task (timestamped snapshots) |
| Decision log | Not present | Core feature (Tab 3 panel + Tab 1 sidebar metadata) |
| AI integration | No direct AI interaction | Central to workflow (both scenarios) |
