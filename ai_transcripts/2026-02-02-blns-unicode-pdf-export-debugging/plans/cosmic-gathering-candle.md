# Plan: Session Statistics + Transcript Viewer (GitHub Issues #43 & #44)

## Summary
Create two connected pages:
1. `/admin/sessions` - Session statistics with timestamps and duration
2. `/admin/transcript/{run_id}` - Transcript viewer with IPA-to-text conversion

**Also fix:** Store original text alongside IPA in conversation history (currently lost).

## Data Model Understanding

**Key Tables:**
- `Run` - A lesson run (e.g., "day1" for a student+lesson combo)
- `GraphSnapshot` - Individual conversation states with `created_at` timestamps
- `state_data.conversation_history` - List of `{role, content}` messages

**Session Definition (Issue #43):**
A session = contiguous GraphSnapshots within a Run, delineated by 5+ minute gaps.

**Current Conversation History Format (PROBLEM):**
```python
# When IPA is present, original text is NOT stored:
{"role": "user", "content": "Student Response (IPA of their pronunciation): `[ɪ'vɪrənmənt]`"}
# Text is lost! Only IPA is stored.
```

**New Format (SOLUTION):**
```python
# Store BOTH text and IPA for AI evaluation:
{"role": "user", "content": "Student Response: `environment` (IPA: `[ɪ'vɪrənmənt]`)"}
# Display TEXT ONLY to users in transcript viewer
```

**Historical Data Migration:**
- `qa_recordings/run_{id}/*.json` files contain `normal` text alongside IPA!
- Match recordings to conversation by timestamp
- No AI inference needed - we have the original ASR text

**Audio Playback:**
- `qa_recordings/run_{id}/*.webm` files are saved for each student response
- Transcript viewer can include play buttons for audio playback

## Implementation Plan

### 0. Fix: Store original text alongside IPA
**File:** `app/graphs/vocab_learning/nodes.py`

**Current code (line 203-210):**
```python
content_for_eval = (
    f"Student Response (IPA of their pronunciation): `{student_ipa}`"
    if student_ipa
    else f"Student Input: `{student_text}`"
)
```

**New code:**
```python
content_for_eval = (
    f"Student Response: `{student_text}` (IPA: `{student_ipa}`)"
    if student_ipa
    else f"Student Input: `{student_text}`"
)
```

### 0b. Fix: Display clean text to students on session resume
**File:** `app/ui/components/conversation/message_display.py`

In `display_history()` (line 444-449), update to handle new format:

**Current code:**
```python
elif role == "user":
    match = re.search(r"Student Input: `([^`]+)`", content)
    if match:
        content = match.group(1)
    self.add_message("user", content)
```

**New code:**
```python
elif role == "user":
    # Handle new format: "Student Response: `text` (IPA: `...`)"
    match = re.search(r"Student Response: `([^`]+)`", content)
    if match:
        content = match.group(1)
    else:
        # Handle old format: "Student Input: `text`"
        match = re.search(r"Student Input: `([^`]+)`", content)
        if match:
            content = match.group(1)
    self.add_message("user", content)
```

This ensures students see only clean text like "environment" when resuming.

### 1. Create session calculation utility
**File:** `app/services/session_stats.py` (new)

```python
@dataclass
class SessionInfo:
    run_id: int
    session_index: int  # 1, 2, 3... within a run
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    round_count: int  # number of snapshots in this session
    student_name: str
    lesson_title: str
    user_email: str
    snapshot_ids: list[int]  # for transcript drill-down

def calculate_sessions_from_runs(runs: list[Run], gap_minutes: int = 5) -> list[SessionInfo]:
    """Split run snapshots into sessions based on time gaps."""
```

### 2. Create session statistics page (Issue #43)
**File:** `app/pages/admin_sessions.py` (new)

**Route:** `/admin/sessions`

**UI Elements:**
- Header: "Session Statistics"
- Subtitle with session definition explanation
- Table columns: Start, End, Duration, Rounds, Student, Lesson, User
- Clickable rows → navigate to `/admin/transcript/{run_id}?start={index}`
- Back button to admin

### 3. Parse user messages for display
**File:** `app/services/transcript_parser.py` (new)

```python
def parse_user_message(content: str) -> tuple[str | None, str | None]:
    """Extract text and IPA from user message.

    Returns: (text, ipa) - text is what we display to users
    """
    # New format: "Student Response: `text` (IPA: `ipa`)" → show text
    # Migrated format: same as above (after migration script runs)
    # Text-only: "Student Input: `text`" → show text
```

**Display shows TEXT only.**
- DB stores: `"Student Response: \`environment\` (IPA: \`[...]\`)"`
- Transcript UI shows: `"environment"` (just the text, nothing else)
- IPA is for AI evaluation, never shown to researchers in transcript

### 4. Create transcript viewer page (Issue #44)
**File:** `app/pages/admin_transcript.py` (new)

**Route:** `/admin/transcript/{run_id}`

**UI Elements:**
- Header with student name and lesson title
- Session selector (if multiple sessions in run)
- For each student message: play button to hear original audio
- Audio served from `qa_recordings/run_{run_id}/*.webm`
- Conversation display:
  - Teacher messages in blue bubbles
  - Student messages showing TEXT ONLY (e.g., "environment")
    - No IPA, no prefixes, just the spoken words
    - Play button to hear original audio
  - Evaluation messages in subtle gray
- Back button to sessions list

**Message Parsing Logic:**
```python
def parse_user_message(content: str) -> tuple[str | None, str | None]:
    """Extract IPA and/or text from user message.

    Returns: (ipa_text, original_text)

    Patterns:
    - "Student Response (IPA of their pronunciation): `[...]`" → IPA only
    - "Student Input: `...`" → text only
    """
```

### 5. Add navigation from admin page
**File:** `app/pages/admin.py` (modify)

Add button next to "View Student Progress":
```python
ui.button(
    "📋 Session Statistics",
    on_click=lambda: ui.navigate.to("/admin/sessions"),
)
```

### 6. Register pages in main.py
**File:** `app/main.py` (modify)

Add imports:
```python
from app.pages import admin_sessions  # noqa: F401
from app.pages import admin_transcript  # noqa: F401
```

### 7. Historical data migration script
**File:** `scripts/migrate_ipa_to_text.py` (new)

**Strategy:** Deterministic - use `qa_recordings/*.json` as source of truth.

```python
# For each run directory in qa_recordings/:
#   1. Read all *.json metadata files
#   2. For each, extract transcription.normal and timestamp
#   3. Find matching snapshot in DB by run_id + timestamp
#   4. Update conversation_history entries:
#      "Student Response (IPA...): `ipa`" → "Student Response: `normal` (IPA: `ipa`)"
#   5. Write updated state_data back to snapshot
```

**Run on server:** `uv run python scripts/migrate_ipa_to_text.py`

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `app/graphs/vocab_learning/nodes.py` | MODIFY | Store text+IPA in history |
| `app/ui/components/conversation/message_display.py` | MODIFY | Show clean text to students |
| `app/services/session_stats.py` | CREATE | Session calculation logic |
| `app/services/transcript_parser.py` | CREATE | Parse messages, extract text |
| `app/pages/admin_sessions.py` | CREATE | Session statistics list page |
| `app/pages/admin_transcript.py` | CREATE | Transcript viewer (text only) |
| `app/pages/admin.py` | MODIFY | Add navigation button |
| `app/main.py` | MODIFY | Import new pages |
| `scripts/migrate_ipa_to_text.py` | CREATE | Migration script for historical data |

## UI Flow

```
/admin
  ├── 📊 View Student Progress → /admin/progress
  └── 📋 Session Statistics → /admin/sessions
                                    │
                                    ▼ (click row)
                              /admin/transcript/{run_id}
```

## Transcript UI Mockup

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Back to Sessions                                              │
├─────────────────────────────────────────────────────────────────┤
│ Transcript: Anh - Science Week 1 (Day 1)                        │
│ Session 1 of 2 │ [Session 1 ▼]                                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 🤖 Teacher                                                │   │
│  │ Hi Anh! Today we're learning about 'environment'.        │   │
│  │ Can you say the word 'environment'?                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 👤 Student                                    [▶ Play]    │   │
│  │ environment                                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ ✓ Evaluation: success                                     │   │
│  │ Good pronunciation of 'environment'                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Technical Notes

### Message Parsing Strategy
1. Parse user message with regex to extract text and/or IPA
2. New format: `Student Response: \`text\` (IPA: \`ipa\`)` → both available
3. Old format: `Student Response (IPA...): \`ipa\`` → IPA only, show as-is
4. Text-only: `Student Input: \`text\`` → text only

### Session Calculation
1. Fetch all runs with snapshots (eager load)
2. For each run, sort snapshots by `created_at`
3. Split into sessions where gap > 5 minutes
4. Calculate stats for each session

### Performance Considerations
- Use `selectinload` for relationships to avoid N+1 queries
- Session calculation is O(n log n) per run (sorting snapshots)

## Verification

1. **Session Statistics Page:**
   - Navigate to `/admin` → click "Session Statistics"
   - Verify sessions are correctly split by 5-min gaps
   - Check timestamps, durations, and round counts
   - Click a row → should navigate to transcript

2. **Transcript Viewer:**
   - View conversation in readable format
   - Verify IPA is displayed with converted text
   - Test session selector if multiple sessions exist
   - Back button returns to sessions list

3. **Edge Cases:**
   - Run with no snapshots → skip in list
   - Run with single snapshot → one session
   - Empty conversation history → show "No messages"

4. **Data Migration Verification:**
   - After nodes.py fix: new sessions store text+IPA
   - After migration script: old sessions also have text+IPA
   - Transcript viewer shows text only (clean UX)

## Execution Order

1. **Phase 1 (can start now):**
   - Fix nodes.py to store text+IPA
   - Create session stats service
   - Create admin_sessions.py page
   - Add navigation button

2. **Phase 2 (can also start now):**
   - Create migration script `scripts/migrate_ipa_to_text.py`
   - Create transcript viewer page with audio playback
   - Test locally with existing `qa_recordings/` data

3. **Phase 3 (deployment):**
   - Deploy code changes to server
   - Run migration script: `uv run python scripts/migrate_ipa_to_text.py`
   - Verify transcript viewer works
