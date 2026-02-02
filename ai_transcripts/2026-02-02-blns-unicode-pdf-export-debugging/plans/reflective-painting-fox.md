# Case Brief Tool - PRD Revision Based on User Feedback

## Feedback Summary (from Amanda meeting)

### What's Working Well
- Live cursor sync and collaboration - "Oh my god. Fuck. We could do, um, feedback in this."
- Word-level highlighting with tag toolbar
- Scroll-synced annotation cards with "Go to text" functionality
- Top toolbar for tag selection (preferred over floating modal)
- Keyboard shortcuts [1-0] for tags

### Key Decisions from Feedback

#### 1. UI/UX Decisions
| Decision | Details |
|----------|---------|
| **Tag toolbar** | Top bar preferred over floating modal - "less steps for students" |
| **Mobile support** | DROP IT - "you can't do this on your phone" / "go to the library" |
| **Word-level highlighting** | Confirmed sufficient - "no" to mid-word highlighting |
| **Paragraph citations** | Word highlighting should reference containing paragraph number |

#### 2. Three-Screen Workflow (NEW)
Amanda described a **three-screen workflow** not in current PRD:

| Screen | Purpose | Details |
|--------|---------|---------|
| **Screen 1** | Document annotation | Current implementation - document with highlights |
| **Screen 2** | Card organization | NEW - Draggable reordering of annotation cards by category |
| **Screen 3** | Brief writing | WYSIWYG editor with organized cards as reference |

**Implementation: Single-page carousel** - All three views on one conceptual page with smooth transitions (reduces load times, maintains state). Not separate page navigations.

**Navigation**: Tab bar always visible - students can click to any screen: **Annotate | Organize | Write**

**Back navigation**: Full editing allowed - students can return to Screen 1 and add more annotations anytime (card ordering in Screen 2 updates accordingly)

**PDF Export**: From Screen 3 only - exports combined document (brief + organized annotations as appendix)

#### 3. Screen 2: Card Organization (NEW REQUIREMENT)
- Students can drag/reorder their annotation cards
- Cards grouped by tag category
- Supports non-contiguous themes in document
- **Toggle per case/assignment** - Amanda wants it for Remedies but NOT for Foundations initially
- Purpose: "extracts out what they've done... order it... use that to write"
- **CRDT-collaborative**: Group members see and manipulate same ordering in real-time
- **Implementation refs**:
  - Vue draggable Quasar: https://codesandbox.io/p/sandbox/vue-draggable-quasar-7cbcf
  - NiceGUI draggable extension: https://github.com/zigai/nicegui-extensions/blob/master/nicegui_ext/draggable.py

#### Tag Count Clarification
- **10 tags** (not 11 as PRD states): jurisdiction through reflection, no title tag
- PRD should be updated to reflect actual implementation

#### 4. Screen 3: Brief Writing Interface
- **NOT** 11 separate accordions with WYSIWYG per tag
- **Single WYSIWYG text box** - "just one" - completely freeform, students create own structure
- Sidebar on LEFT with:
  - Accordion of tag categories (collapsible)
  - Respects ordering from Screen 2
  - Full-text search across cards
  - Cards show paragraph number reference
- Students structure their own writing (no forced headers)
- Case document NOT visible in Screen 3 - "Period. Period. Yeah."
- Can navigate back to Screen 1 if needed
- **Word count display**: Below editor, using regex counter (sequences of letters)
- **Word limit**: Configurable hard limit per case - instructor sets max, enforced (prevents export/submission if exceeded)

#### 5. Paragraph Citation System
- Highlights should display containing paragraph number (e.g., "paragraph 48")
- **Detection algorithm**: Find topmost parent `<ol>` of selection and use its item number, OR find number at start of topmost `<p>`
- Sub-items within a paragraph (like "Order 6, 1") are still "paragraph 48"
- No AGLC4 citation formatting needed for Foundations
- Future: clicking card could insert hyperlink reference

#### 6. Configuration Toggles
- **Card organization (Screen 2)**: Toggle at **case/assignment level**, not course-wide
- Instructors can enable/disable for individual cases

#### 7. Brief WYSIWYG Sync
- **CRDT real-time collaboration** for brief content (Screen 3)
- Same infrastructure as annotation sync
- Multiple users can edit same brief simultaneously

#### 6. Keystroke Logging for Academic Integrity
- System inherently has mouse/cursor tracking
- Can be positioned as deterrent: "online tools that record your keystrokes do so in this way"
- Not actively analyzing - just telling students it exists

### Deferred/Future Features
- AGLC4 citation automation - "not essential" for Foundations
- Click-to-insert paragraph references - "maybe as we move along"
- Secondary source database - "not this semester"
- LMS integration - still open

## Current Implementation Status

### Already Built
- [x] Word-level CSS highlighting with CRDT sync
- [x] 10-tag system with colorblind-accessible palette
- [x] Real-time cursor/selection sharing
- [x] Comment threading on highlights
- [x] Scroll-synced annotation cards
- [x] Database persistence with debouncing
- [x] "Go to text" button with scroll + highlight
- [x] RTF parsing to word spans

### Not Yet Built
- [ ] Screen 2: Card organization/reordering view
- [ ] Screen 3: Brief writing interface
- [ ] Paragraph number extraction from RTF
- [ ] Per-class toggle for card organization feature
- [ ] Full-text search across annotation cards
- [ ] Navigation between screens

## PRD Changes Required

### Remove
1. Mobile/tablet support via tabbed interface - explicitly dropped
2. 11 separate WYSIWYG accordions - replaced with single editor

### Add
1. **Three-screen workflow** description
2. **Screen 2: Card Organization View**
   - Drag-and-drop reordering within categories
   - Toggle: enable/disable per class
3. **Screen 3: Brief Writing Interface**
   - Single WYSIWYG editor (right side)
   - Collapsible accordion sidebar (left) with search
   - Cards respect user ordering from Screen 2
   - No case document visible
   - Back navigation to Screen 1
4. **Paragraph number extraction** from RTF ordered lists
5. **Class-level feature toggles** for card organization

### Modify
1. Brief Editor section - update to single WYSIWYG model
2. Responsive Layout section - remove tablet/mobile, desktop only
3. UI/UX Considerations - update to three-screen workflow

## GitHub Issues to Create (after PRD revision)

### High Priority (MVP)

1. **Three-Screen Tab Navigation** - Single-page carousel with Annotate | Organize | Write tabs
2. **Screen 2: Card Organization View** - CRDT-collaborative drag/drop reordering by tag category
3. **Screen 3: Brief Writing Interface** - Single freeform WYSIWYG with accordion sidebar
4. **Paragraph Number Extraction** - Detect from topmost `<ol>` parent or `<p>` leading number
5. **Brief CRDT Sync** - Real-time collaboration on brief content (pycrdt Text)
6. **Word Count with Hard Limits** - Display + instructor-configurable max (enforced)

### Medium Priority

7. **Full-text Search for Cards** - Search across annotation text in Screen 3 sidebar
8. **Case-Level Feature Toggles** - Enable/disable card organization per case
9. **PDF Export Combined Document** - Brief + organized annotations as appendix

### Lower Priority / Future

10. **Click-to-Insert Paragraph References** - Insert `[48]` from card click
11. **AGLC4 Citation Support** - Optional citation formatting
12. **Secondary Source Database** - Multi-document annotation (Remedies use case)

## Action Plan

1. **Revise PRD** (`docs/case-brief-tool-prd.md`)
   - Update tag count: 10 not 11
   - Remove mobile/tablet support
   - Replace Brief Editor section with three-screen workflow
   - Add Screen 2 and Screen 3 specifications
   - Add paragraph number detection algorithm
   - Add word count hard limit configuration
   - Update data model for card ordering + brief content CRDT

2. **Create GitHub Issues** from revised PRD sections

3. **Implementation** (future sessions)
