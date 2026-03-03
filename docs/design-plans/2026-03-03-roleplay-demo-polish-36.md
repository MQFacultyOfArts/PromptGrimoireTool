# Roleplay Demo Polish Design

**GitHub Issue:** #36

## Summary

This design adds visual polish and an export capability to the existing roleplay chat page. The roleplay page currently lets users upload a SillyTavern character card and hold a conversation with an AI-simulated client (Becky Bennett, a tort law claimant). The work here makes that experience look and feel like a SillyTavern session — background image, dark-themed chat bubbles with semi-transparent tinting, and round character avatars — and then bridges it to the annotation workflow by letting users export the completed conversation as an annotatable workspace.

The implementation is deliberately minimal and self-contained. Visual assets (background, avatars) are copied from an existing SillyTavern installation and served as static files. Styling is derived directly from SillyTavern's published CSS variables, so the colour and typography choices are grounded in an existing, validated theme. The export path converts the in-memory conversation to HTML in the format the annotation page already expects — the same `data-speaker` marker convention used when importing external AI conversations — meaning no changes are needed on the annotation side.

## Definition of Done

1. Roleplay page displays office conference room background image
2. Chat UI uses ST-inspired dark theme (semi-transparent bubbles, ivory text, orange quotes, grey italics, backdrop blur)
3. User messages show kangaroo lawyer avatar
4. AI messages show Becky Bennett portrait avatar
5. "Export to Workspace" button creates a loose workspace containing the conversation as a single `ai_conversation` document with `data-speaker`/`data-speaker-name` attributes
6. Exported workspace renders correctly in the annotation page with proper speaker labels

## Acceptance Criteria

### roleplay-demo-polish-36.AC1: Visual assets display correctly
- **roleplay-demo-polish-36.AC1.1 Success:** Background image covers the full roleplay page viewport with no tiling or distortion
- **roleplay-demo-polish-36.AC1.2 Success:** User messages display kangaroo lawyer avatar as 50px round image
- **roleplay-demo-polish-36.AC1.3 Success:** AI messages display Becky Bennett portrait as 50px round image

### roleplay-demo-polish-36.AC2: ST-inspired dark theme renders correctly
- **roleplay-demo-polish-36.AC2.1 Success:** Chat area has semi-transparent dark tint over the background image
- **roleplay-demo-polish-36.AC2.2 Success:** Message text renders in ivory/warm white, italics in grey, blockquotes with orange left border
- **roleplay-demo-polish-36.AC2.3 Edge:** Upload card (pre-session) remains readable against the dark background

### roleplay-demo-polish-36.AC3: Export creates annotatable workspace
- **roleplay-demo-polish-36.AC3.1 Success:** Clicking "Export to Workspace" creates a loose workspace with a single `ai_conversation` document containing all turns
- **roleplay-demo-polish-36.AC3.2 Success:** Each turn in the exported document has correct `data-speaker` ("user"/"assistant") and `data-speaker-name` (actual character/user names) attributes
- **roleplay-demo-polish-36.AC3.3 Success:** Exported workspace opens in annotation page with speaker labels rendered via CSS `::before`
- **roleplay-demo-polish-36.AC3.4 Failure:** Export button is disabled or hidden when no session is active (no character loaded)

## Glossary

- **SillyTavern (ST)**: An open-source chat UI for running AI roleplay scenarios. Defines a character card format, lorebook system, and CSS theming system that this project borrows from.
- **Character card (chara_card_v3)**: A JSON schema used by SillyTavern to describe an AI persona — name, description, system prompt, and an embedded lorebook. Cards are typically distributed as PNG files with JSON embedded in the metadata.
- **Lorebook**: A lookup table of keyword-triggered context snippets attached to a character card. When a keyword appears in the conversation, the associated entry is injected into the AI prompt.
- **Session / Turn**: In-memory data structures representing a roleplay session (`Session`) and a single exchange (`Turn`) within it. Transient in this design — full persistence is out of scope.
- **Loose workspace**: A workspace with no parent week or activity. Used here to hold exported roleplay conversations outside any structured course hierarchy.
- **`ai_conversation` document type**: A document sub-type in the annotation system for AI-generated conversations. The annotation page applies special CSS rendering (speaker labels via `::before` pseudo-elements) to documents of this type.
- **`data-speaker` / `data-speaker-name`**: HTML data attributes placed on turn-boundary `<div>` elements to identify who spoke each turn. The annotation page's CSS reads these to render speaker labels without modifying document text.
- **ACL / `grant_permission`**: Access Control List entry. `grant_permission(workspace_id, user_id, "owner")` gives the exporting user full control of the newly created workspace.
- **NiceGUI**: The Python web UI framework used throughout the application. Wraps Quasar components; `ui.chat_message()` is its chat bubble component.
- **Quasar**: The Vue-based component library underlying NiceGUI. CSS overrides target Quasar's `.q-message` classes to restyle chat bubbles.
- **ST theme variables**: CSS custom properties defined by SillyTavern's theming system (e.g. `--SmartThemeBodyColor`, `--SmartThemeQuoteColor`). This design reads those variable values as a colour specification, not as runtime variables.
- **`markdown` library**: Python package that converts Markdown-formatted text to HTML. Used to render turn content (italics, bold, blockquotes) before writing it into the exported workspace document.

## Architecture

### Visual Layer

Three static image assets copied from the SillyTavern data directory at `/home/brian/people/Amanda/ST-2025-10-24-TORTS/SillyTavern/data/default-user/` into `src/promptgrimoire/static/roleplay/`:

| Asset | Source | Destination |
|-------|--------|-------------|
| Background | `backgrounds/pjqhsrifzuynmcmq9cpn.png` | `static/roleplay/background.png` |
| AI avatar | `characters/Becky Bennett.png` | `static/roleplay/becky-bennett.png` |
| User avatar | `User Avatars/user-default.png` | `static/roleplay/user-default.png` |

Static files served via `app.add_static_files('/static/roleplay', ...)` in the roleplay page module.

A new CSS file `src/promptgrimoire/static/roleplay.css` provides ST-inspired styling derived from SillyTavern's default theme variables:

| Property | ST Variable | Value |
|----------|-------------|-------|
| Text colour | `--SmartThemeBodyColor` | `rgb(220, 220, 210)` |
| Italics/em | `--SmartThemeEmColor` | `rgb(145, 145, 145)` |
| Quotes | `--SmartThemeQuoteColor` | `rgb(225, 138, 36)` |
| Chat tint | `--SmartThemeChatTintColor` | `rgba(23, 23, 23, 0.85)` |
| User msg tint | `--SmartThemeUserMesBlurTintColor` | `rgba(0, 0, 0, 0.3)` |
| AI msg tint | `--SmartThemeBotMesBlurTintColor` | `rgba(60, 60, 60, 0.3)` |
| Font | `--mainFontFamily` | `"Noto Sans", sans-serif` |
| Font size | `--mainFontSize` | `15px` |
| Avatar size | `--avatar-base-width/height` | `50px` |
| Avatar shape | `--avatar-base-border-radius-round` | `50%` |

Background image applied to the page container with `background-size: cover; background-attachment: fixed`. Chat area gets semi-transparent dark tint with `backdrop-filter: blur(10px)`.

NiceGUI's `ui.chat_message()` accepts an `avatar` parameter (URL string). User messages get `/static/roleplay/user-default.png`, AI messages get `/static/roleplay/becky-bennett.png`. CSS overrides target Quasar's `.q-message` classes for bubble colouring and text styling.

### Export Layer

The export converts in-memory `Session.turns` directly to annotation-ready HTML:

1. For each `Turn` in `Session.turns`, render markdown content to HTML (using Python `markdown` library)
2. Prepend an empty speaker marker div as a **sibling** before the turn content (not wrapping it): `<div data-speaker="{role}" data-speaker-name="{name}"></div>` followed by the rendered HTML
   - `role` is `"user"` for user turns, `"assistant"` for AI turns (system turns, if any, map to `"system"`)
   - `name` is `session.user_name` or `session.character.name`
3. Concatenate all turns into a single HTML string — each turn is a marker div followed by its content as siblings

This HTML is passed directly to `add_document()` with `type="ai_conversation"` and `source_type="html"`. No input pipeline processing needed — we are the source and produce clean HTML with no chrome to strip.

The annotation page's existing CSS in `src/promptgrimoire/pages/annotation/css.py` (lines 157–222) renders speaker labels via `::before` pseudo-elements keyed on `data-speaker` and `data-speaker-name` attributes. No annotation-side changes needed.

**Data flow:**

```
Session.turns (in-memory)
  → markdown.markdown(turn.content) per turn
  → wrap in <div data-speaker="..." data-speaker-name="..."></div> + HTML
  → concatenate all turns
  → create_workspace() → loose workspace, no parent
  → add_document(workspace_id, type="ai_conversation", content=html, source_type="html", title="Roleplay: {char} — {date}")
  → grant_permission(workspace_id, user_id, "owner")
  → navigate to /annotation/{workspace_id}
```

## Existing Patterns

### Workspace creation

`db/workspaces.py` provides `create_workspace()` which returns a bare `Workspace` with no parent (loose). `make_workspace_loose()` is the explicit version but `create_workspace()` already produces this state.

### Document addition

`db/workspace_documents.py` provides `add_document()` accepting `workspace_id`, `type`, `content` (HTML string), `source_type`, and optional `title`. The `type="ai_conversation"` value is already used by the annotation page for conversation imports.

### Speaker markers

The platform handler system in `src/promptgrimoire/export/platforms/__init__.py` injects `<div data-speaker="{role}" class="speaker-turn"></div>` before turn boundaries (line 166). Our export follows the same marker format but generates them directly rather than via regex substitution.

### ACL grants

`db/acl.py` provides `grant_permission(workspace_id, user_id, permission)` for setting workspace access. The roleplay page already has `auth_user` in `app.storage.user`.

### Static file serving

NiceGUI serves static files via `app.add_static_files(url_path, local_path)`. No existing pattern for per-page static directories, but the annotation page's `annotations.css` in `static/` provides precedent for page-specific CSS.

### No divergence from existing patterns

This design follows all existing patterns. No new patterns introduced.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Static Assets and CSS

**Goal:** Copy image assets and create ST-inspired stylesheet

**Components:**
- `src/promptgrimoire/static/roleplay/` directory — background, AI avatar, user avatar images
- `src/promptgrimoire/static/roleplay.css` — ST-inspired dark theme styles targeting Quasar chat components

**Dependencies:** None

**Done when:** Static files exist at expected paths, CSS file contains ST-derived theme variables and chat styling rules
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Roleplay Page Visual Integration

**Goal:** Apply background, avatars, and dark theme to the roleplay chat UI

**Components:**
- `src/promptgrimoire/pages/roleplay.py` — register static files, add CSS link, pass avatar URLs to `ui.chat_message()`, apply background to page container

**Dependencies:** Phase 1 (static assets exist)

**Done when:** Roleplay page renders with office background, dark-themed chat bubbles, round avatars beside messages. Covers DoD items 1–4.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Export to Workspace

**Goal:** Convert in-memory roleplay session to annotation-ready workspace

**Components:**
- Export function in `src/promptgrimoire/pages/roleplay.py` — converts `Session.turns` to HTML with `data-speaker`/`data-speaker-name` markers, creates loose workspace via `create_workspace()`, adds document via `add_document()`, grants owner ACL, navigates to annotation page
- "Export to Workspace" button in chat UI — visible once session is active, triggers export

**Dependencies:** Phase 2 (roleplay page changes), existing `db/workspaces.py`, `db/workspace_documents.py`, `db/acl.py`

**Done when:** Clicking export creates a workspace with correctly formatted `ai_conversation` document, user has owner access, annotation page displays conversation with proper speaker labels. Covers DoD items 5–6.
<!-- END_PHASE_3 -->

## Additional Considerations

**Markdown rendering:** The `markdown` library is already a transitive dependency (NiceGUI uses it). If not directly available, `markdown-it-py` or a minimal renderer suffices — roleplay text uses basic formatting (italics, bold, quotes, paragraphs).

**Character card coupling:** Background, avatars, and character name are currently hardcoded for the Becky Bennett demo. A future design could extract avatar images from character card PNGs (SillyTavern embeds JSON in PNG metadata) and select backgrounds per-character. Out of scope for this demo.

**Session resumption:** Issue #36's full scope includes SQLModel persistence, session queries, and resumption. This design addresses the annotation use case only. Full persistence remains future work.
