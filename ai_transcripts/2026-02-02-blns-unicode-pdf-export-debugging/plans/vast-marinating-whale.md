# Roleplay Page Improvements Plan

## Reference: SillyTavern Data Location

SillyTavern installation with example data:
`/home/brian/people/Amanda/ST-2025-10-24-TORTS/SillyTavern/data/default-user/`

---

## Scope

This plan covers two phases:

**Phase A (This PR):** Fix immediate UI bugs in roleplay page
**Phase B (Future):** Scenario setup page with persona management

---

## Phase A: Immediate UI Fixes

### A1. Initial Message Not Showing (Critical)

**Root Cause:** `_render_messages()` creates `ui.chat_message()` elements outside the `chat_container` context.

**Fix:** Pass `chat_container` to `_render_messages()` and wrap in context manager.

**File:** [roleplay.py](src/promptgrimoire/pages/roleplay.py)

---

### A2. Markdown Rendering (High Priority)

**Root Cause:** `ui.chat_message(text=...)` renders plain text.

**Fix:** Use `ui.markdown()` inside chat_message:

```python
def _create_chat_message(content: str, name: str, sent: bool) -> None:
    msg = ui.chat_message(name=name, sent=sent)
    with msg:
        ui.markdown(content).classes("text-base")
```

Update 3 locations: `_render_messages()`, user message in `_handle_send()`, AI response.

---

### A3. Chat Styling

**Fix:** Add gap classes: `chat_container = ui.column().classes("w-full gap-3")`

---

### A4. User Name from Stytch

**Decision:** Extract Stytch `name` field, fall back to parsed email prefix.

**Files:**

1. [auth/models.py](src/promptgrimoire/auth/models.py) - Add `name: str | None = None`
2. [auth/client.py](src/promptgrimoire/auth/client.py) - Extract `response.member.name`
3. [auth/mock.py](src/promptgrimoire/auth/mock.py) - Add name to mocks
4. [pages/auth.py](src/promptgrimoire/pages/auth.py) - Store in session
5. [pages/roleplay.py](src/promptgrimoire/pages/roleplay.py) - Pre-populate input

---

## Phase B: Scenario Setup & Personas (Future Work)

Based on SillyTavern's persona system (from `settings.json`):

### SillyTavern Persona Structure

```json
{
  "personas": { "user-default.png": "Jordan" },
  "persona_descriptions": {
    "user-default.png": {
      "description": "{{user}} is a graduate lawyer at Wallaby, Wombat & Wattle...",
      "position": 0,
      "connections": [{ "type": "character", "id": "Becky Bennett.png" }]
    }
  }
}
```

### Key Concepts

- **Persona name**: Display name for `{{user}}` (e.g., "Jordan")
- **Persona description**: Role/context injected into prompt (e.g., "graduate lawyer...")
- **Connections**: Bind personas to specific characters
- **Position**: Where in prompt to inject (story string has `{{persona}}` placeholder)

### Planned Features

1. **Scenario Setup Page** (`/scenario-setup`)
   - Upload/select character card
   - Define multiple user personas for the scenario
   - Each persona has: name, description, optional character binding
   - Pre-load character cards (no upload each time)

2. **Persona Model**

   ```python
   @dataclass
   class UserPersona:
       name: str  # "Jordan"
       description: str  # "{{user}} is a graduate lawyer..."
       character_bindings: list[str] = field(default_factory=list)
   ```

3. **Prompt Integration**
   - Add `{{persona}}` to story_string template
   - Inject persona description at configurable position

4. **Database Storage**
   - Store personas per class/course
   - Instructors can create personas for students to use

---

## Files to Modify (Phase A)

| File | Changes |
| ---- | ------- |
| [roleplay.py](src/promptgrimoire/pages/roleplay.py) | Fix context, markdown, styling |
| [auth/models.py](src/promptgrimoire/auth/models.py) | Add `name` field |
| [auth/client.py](src/promptgrimoire/auth/client.py) | Extract member.name |
| [auth/mock.py](src/promptgrimoire/auth/mock.py) | Add name to mocks |
| [pages/auth.py](src/promptgrimoire/pages/auth.py) | Store name in session |

---

## Verification (Phase A)

1. Load character card → Initial message displays
2. Messages render markdown (bold, italic, code)
3. User messages right-aligned with spacing
4. Logged-in users see their name pre-populated
5. `uv run pytest` passes
