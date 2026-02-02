# Spike 4: SillyTavern Scenario Import + Single-User Roleplay

## Goal

**Minimal vertical slice**: Drop in a SillyTavern character card, run a roleplay session at SillyTavern quality, emit JSONL log for later annotation.

### Data Flow

```
Input:  Becky Bennett (2).json (chara_card_v3 with embedded lorebook)
           ↓
        Parse & load character + lorebook entries
           ↓
        Roleplay session (NiceGUI chat UI + Claude API)
           ↓
Output: session_<timestamp>.jsonl (SillyTavern-compatible log for annotation)
```

### Scope for This Spike

- ✅ Parse SillyTavern chara_card_v3 format (character + embedded lorebook)
- ✅ Lorebook keyword activation (matching SillyTavern's logic)
- ✅ Claude API integration with streaming
- ✅ Basic NiceGUI roleplay UI (single user)
- ✅ Emit JSONL chat log (same format as SillyTavern)
- ❌ Multi-user CRDT sync (Spike 5)
- ❌ Annotation system (Spike 6)
- ❌ PostgreSQL persistence (defer - in-memory for now)

### Clarified Requirements

- **AI backend**: Direct Claude API integration
- **Lorebook visibility**: Hidden from students (realistic simulation)
- **Output**: JSONL log compatible with SillyTavern format for future annotation

---

## Data Formats (from SillyTavern)

### Lorebook (World Info) - `Negligence.json`
5 entries with keyword-triggered context injection:
- **Work Place Accident**: Core incident (horse riding injury, Feb 2023)
- **Pancreatitis**: Secondary complication (2024, alcohol self-medication)
- **Current Circumstances**: 2025 recovery status
- **Injury Details**: L2 fracture, surgical details
- **Employer**: Green Meadows Ranch context

Each entry has:
```json
{
  "key": ["accident", "injury", "horse", ...],  // trigger keywords
  "content": "Context text with {{char}} placeholders...",
  "order": 90,  // insertion priority
  "selective": true,
  "depth": 4  // how many messages back to scan
}
```

### Chat Format - JSONL
```jsonl
{"user_name":"Jordan","character_name":"Becky Bennett","create_date":"...","chat_metadata":{...}}
{"name":"Becky Bennett","is_user":false,"mes":"*walks in* Thanks for making time...","extra":{}}
{"name":"Jordan","is_user":true,"mes":"Hi, Welcome.","extra":{}}
{"name":"Becky Bennett","is_user":false,"mes":"*shifts weight* I'm not sure where to start...","extra":{"api":"claude","model":"claude-sonnet-4-5","reasoning":"..."}}
```

### Character Card - `Becky Bennett (2).json` (chara_card_v3 format)

```json
{
  "name": "Becky Bennett",
  "description": "##Appearance\n{{char}} is in her late 30s...",
  "personality": "{{char}} values community, hard work...",
  "scenario": "{{char}} is seeking legal advise from {{user}}...",
  "first_mes": "At the local offices of Wallaby, Wombat & Wattle...",
  "data": {
    "system_prompt": "# Legal Training Simulation\n...",
    "character_book": {
      "entries": [...],  // 5 lorebook entries embedded
      "name": "Negligence"
    },
    "extensions": {
      "talkativeness": "0.2",
      "world": "Negligence"
    }
  }
}
```

Key system prompt features:
- 30 word response limit
- Empathy-based trust mechanics (shares personal info only if treated well)
- 3-strike boundary escalation (irritation → warning → leaves + complaint)

---

## PromptGrimoire Current State

### Exists
- **Auth**: Stytch magic links + SSO + RBAC ✅
- **CRDT Sync**: `SharedDocument` with pycrdt ✅
- **Text Selection**: UI component for selecting text ✅

### Missing
- Domain models (Scenario, Character, Lorebook, Session, Turn)
- Parsers for SillyTavern formats
- PostgreSQL persistence
- LLM integration
- Roleplay UI

---

## Implementation Plan

### Phase 1: Data Models & Import

**1.1 SQLModel Entities** (`src/promptgrimoire/models/`)

```python
# scenario.py
class Character(SQLModel, table=True):
    id: uuid.UUID
    name: str
    system_prompt: str
    avatar_path: str | None

class LorebookEntry(SQLModel, table=True):
    id: uuid.UUID
    character_id: uuid.UUID  # FK
    keywords: list[str]  # JSON array
    content: str
    insertion_order: int
    scan_depth: int = 4

class Scenario(SQLModel, table=True):
    id: uuid.UUID
    name: str
    description: str
    character_id: uuid.UUID  # FK
    user_persona_name: str  # e.g., "Jordan"
    user_persona_prompt: str | None

class Session(SQLModel, table=True):
    id: uuid.UUID
    scenario_id: uuid.UUID  # FK
    created_at: datetime
    status: Literal["active", "completed", "archived"]

class Turn(SQLModel, table=True):
    id: uuid.UUID
    session_id: uuid.UUID  # FK
    speaker_type: Literal["character", "user", "system"]
    speaker_user_id: uuid.UUID | None  # FK to auth user, null for AI
    content: str
    created_at: datetime
    metadata: dict  # model info, reasoning, etc.
```

**1.2 SillyTavern Parser** (`src/promptgrimoire/parsers/sillytavern.py`)

```python
def parse_character_card(path: Path) -> tuple[Character, list[LorebookEntry]]:
    """Parse chara_card_v3 JSON -> (Character, embedded lorebook entries)

    The character card is self-contained with lorebook embedded in
    data.character_book.entries. No need for separate lorebook file.
    """
```

Key parsing tasks:
- Extract `system_prompt` from `data.system_prompt`
- Build full prompt from: description + personality + scenario + system_prompt
- Extract lorebook from `data.character_book.entries`
- Handle `{{char}}` / `{{user}}` placeholder substitution

### Phase 2: Lorebook Activation Engine

Based on SillyTavern's `world-info.js` implementation:

**2.1 Keyword Matching**

```python
def match_keys(text: str, keywords: list[str], case_sensitive: bool = False,
               match_whole_words: bool = False) -> bool:
    """Match keywords against conversation text.

    - Case insensitive by default
    - Supports regex patterns (if key starts with /)
    - match_whole_words: use word boundaries for single words
    - Returns True if ANY primary keyword matches
    """
```

**2.2 Scan Depth**

- `scan_depth` (default 4): how many recent messages to scan
- Build a "haystack" by joining the last N messages
- Substitute `{{char}}`/`{{user}}` in keywords before matching

**2.3 Selective Logic (secondary keywords)**

For entries with secondary keywords (`keysecondary`):

| selectiveLogic | Behavior |
|----------------|----------|
| 0 (AND_ANY) | Primary matches AND any secondary matches |
| 1 (NOT_ALL) | Primary matches AND any secondary does NOT match |
| 2 (NOT_ANY) | Primary matches AND NO secondary matches |
| 3 (AND_ALL) | Primary matches AND ALL secondary match |

**2.4 Insertion Order & Position**

- `insertion_order`: Higher values = higher priority (sorted descending)
- `position: "before_char"` (0): inject before character definition
- Activated entries prepended to system prompt in order

### Phase 3: LLM Integration

**3.1 Prompt Assembly**

```python
def build_prompt(character: Character, entries: list[LorebookEntry],
                 history: list[Turn], user_name: str) -> list[dict]:
    """
    1. Scan history for keywords → get activated entries
    2. Sort activated by insertion_order (descending)
    3. Build system prompt:
       [activated lorebook entries]
       [character description + personality + scenario]
       [system_prompt instructions]
    4. Substitute {{char}} → character.name, {{user}} → user_name
    5. Convert history to messages array
    """
```

**3.2 Claude API Client**

- Use `anthropic` Python SDK
- Stream responses for real-time UI update
- Store response as Turn, append to JSONL log file

### Phase 4: Roleplay UI (NiceGUI)

**4.1 Session View**

- Load character card via file picker or CLI arg
- Character name header + first_mes as opening
- Scrolling message list (user vs AI styled differently)
- Input area with "Send" button
- Streaming response display
- Auto-append each turn to JSONL log file

---

## Critical Files to Create

| Path | Purpose |
| ---- | ------- |
| `src/promptgrimoire/models/scenario.py` | Character, LorebookEntry, Session, Turn dataclasses |
| `src/promptgrimoire/parsers/sillytavern.py` | Parse chara_card_v3 JSON (character + embedded lorebook) |
| `src/promptgrimoire/llm/client.py` | Claude API wrapper with streaming |
| `src/promptgrimoire/llm/prompt.py` | Lorebook activation + prompt assembly |
| `src/promptgrimoire/pages/roleplay.py` | NiceGUI chat interface |
| `tests/unit/test_sillytavern_parser.py` | Parser tests against `Becky Bennett (2).json` |
| `tests/unit/test_lorebook_activation.py` | Keyword matching tests |
| `tests/integration/test_roleplay.py` | End-to-end with mocked Claude |

**Test data file:**
- Copy `Becky Bennett (2).json` to `tests/fixtures/` for parser tests

---

## Verification Plan

1. **Parser tests**: Import Becky Bennett character + Negligence lorebook, verify all fields parsed
2. **Lorebook activation test**: Given sample conversation, verify correct entries activate on keywords
3. **Prompt assembly test**: Verify system prompt + activated lorebook + history + user message ordering
4. **Integration test**: Mock Claude API, send message, verify response stored as Turn
5. **Manual test**: Run actual roleplay session, compare quality to existing SillyTavern chat logs

---

## Success Criteria

The spike is complete when:

1. Can import `Becky Bennett (2).json` (self-contained character card with embedded lorebook)
2. Can start a roleplay session and see `first_mes` as opening
3. Lorebook entries activate based on conversation keywords (verified via debug log)
4. Claude API generates responses matching SillyTavern quality (~30 words, conversational)
5. Session emits JSONL log file compatible with SillyTavern format
6. Basic chat UI displays streaming responses

### Acceptance Tests (manual)

| Test | Expected Behavior |
|------|-------------------|
| Empathetic opening | Becky responds warmly, willing to share details |
| Ask about "accident" | Lorebook entry activates, Becky describes horse incident |
| Ask about "pain" or "injury" | Medical details lorebook entry activates |
| Dismissive/cold tone | Becky shows irritation |
| Continue dismissive | Becky warns she'll find another lawyer |
| Third strike | Becky leaves, mentions Law Society complaint |
