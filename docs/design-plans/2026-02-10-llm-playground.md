# LLM Playground Design

## Summary

The LLM Playground is a transparent, pedagogical chat interface that exposes the full machinery of LLM interactions to students. Unlike production chat tools that hide complexity, this playground shows every parameter, token count, cost estimate, thinking block, and API request payload inline. Students configure temperature, max tokens, and extended thinking; switch models mid-conversation; and edit any message — all while seeing exactly what data is sent to the LLM provider.

The implementation uses pydantic-ai to abstract two provider paths: direct Anthropic API for native Claude thinking support, and OpenRouter for all other models (GPT-4, Gemini, DeepSeek, Llama, etc.). Instructors configure per-course model allowlists and provision per-student API keys (encrypted at rest, giving per-student budget control via provider billing). Conversations persist in PostgreSQL (canonical store) with an append-only JSONL archive preserving original content through edits. An "Annotate this conversation" button exports to the existing annotation workflow for critical examination. The architecture supports future CRDT-based real-time collaboration without requiring it for initial launch.

## Definition of Done

1. Students can chat with LLMs via the playground page with full transparency (system prompt, params, tokens, cost, thinking blocks, API JSON all visible and editable)
2. Instructors configure allowed models and provision per-student API keys per course; students select from the allowlist
3. Direct Anthropic + OpenRouter providers via pydantic-ai, with model switching per-message
4. Conversations persist in PostgreSQL (canonical store) with append-only JSONL audit archive
5. Export to annotation workflow ("Annotate this conversation" creates a WorkspaceDocument)
6. Every message (user and assistant) is editable in place; regenerate button on any assistant message re-runs that response
7. File attachments on messages
8. Architecture does not preclude CRDT sync or multi-student shared conversations

## Acceptance Criteria

### llm-playground.AC1: Full transparency of LLM interactions
- **AC1.1** System prompt is displayed as an always-visible editable textarea at the top of the conversation
- **AC1.2** Each assistant message displays: model name, input/output/thinking token counts, estimated cost, and active parameters (temperature, max_tokens, thinking on/off)
- **AC1.3** Thinking blocks display in collapsible expansion panels with streaming content during generation
- **AC1.4** "Copy API request JSON" button on each assistant message shows the exact request payload sent to the provider
- **AC1.5** Temperature slider is disabled when a thinking-capable model has thinking enabled
- **AC1.6** Token count updates on system prompt textarea as user edits

### llm-playground.AC2: Instructor model and key configuration
- **AC2.1** Instructor can add models to a course allowlist with display name, privacy notes, hosting region, and cost tier
- **AC2.2** Instructor can enable/disable individual models without deleting them
- **AC2.3** Instructor provisions per-student-per-unit API keys (one per provider per student per course); students cannot add their own keys
- **AC2.4** API keys are encrypted at rest and never exposed in any UI (including to students)
- **AC2.5** Per-student keys give instructor per-student budget control via the provider's own billing
- **AC2.6** Instructor can view student conversations read-only

### llm-playground.AC3: Provider abstraction via pydantic-ai
- **AC3.1** Direct Anthropic provider creates `AnthropicModel` agents with native thinking support
- **AC3.2** OpenRouter provider creates `OpenRouterModel` agents for non-Anthropic models
- **AC3.3** Both providers emit the same streaming event types (ThinkingPart, TextPart deltas) to the UI handler
- **AC3.4** Student can switch models between messages within the same conversation
- **AC3.5** Conversation `message_history` carries forward across model switches (pydantic-ai handles serialization)
- **AC3.6** Student model picker shows only models from the course allowlist

### llm-playground.AC4: Persistence and audit trail
- **AC4.1** Conversations persist in PostgreSQL (canonical store) and survive browser close/reopen
- **AC4.2** Student can browse conversation history and resume any previous conversation
- **AC4.3** Every API call is logged to append-only JSONL archive with full request, response, timing, cost, student ID, and course ID
- **AC4.4** JSONL archive is immutable even when students edit messages in the DB
- **AC4.5** Each conversation is linked to a Workspace

### llm-playground.AC5: Export to annotation
- **AC5.1** "Annotate this conversation" creates a `WorkspaceDocument(source_type="playground")` that the annotation page can render
- **AC5.2** Exported HTML includes speaker labels and per-message metadata (model, tokens, cost)
- **AC5.3** Thinking blocks are included as collapsible sections in the exported HTML

### llm-playground.AC6: Message editing and regeneration
- **AC6.1** Student can edit any user message text in place
- **AC6.2** Student can edit any assistant message text in place
- **AC6.3** Regenerate button on any assistant message re-runs that response (replaces the message content)
- **AC6.4** Edits update the database record; original content is preserved in the JSONL archive

### llm-playground.AC7: File attachments
- **AC7.1** Student can attach files via upload button or drag-and-drop in the input area
- **AC7.2** Multiple files can be attached to a single message
- **AC7.3** Attached files display as reference chips (filename + size) on the message, not as image previews
- **AC7.4** Images are sent as base64 to vision-capable models
- **AC7.5** File attach button is disabled for models that don't support file/vision input
- **AC7.6** Attached files are stored in workspace file storage and referenced by message metadata

### llm-playground.AC8: Collaboration seams
- **AC8.1** Two students accessing the same workspace see the same conversation list
- **AC8.2** Two tabs/users in the same workspace can see the same AI stream arriving in real time
- **AC8.3** Each user in a shared workspace is identified by username; first name is passed to the AI so it can differentiate messages from different users
- **AC8.4** Instructor can share a conversation to the class (creates read-only copies for enrolled students)
- **AC8.5** CRDT integration points are documented for future implementation
- **AC8.6** Shared workspace access respects future ACL (architecture does not bypass Workspace-level access)

## Glossary

- **CRDT (Conflict-free Replicated Data Type)**: A data structure that allows multiple users to edit the same document concurrently without conflicts, automatically merging changes. Used in PromptGrimoire for real-time collaborative editing.
- **Extended thinking**: Anthropic's Claude feature where the model reasons through a problem step-by-step in a separate "thinking block" before generating the final response. Visible in the UI as collapsible amber panels.
- **JSONL (JSON Lines)**: A text format where each line is a valid JSON object. Used for append-only audit trails that can be processed line-by-line without loading the entire file.
- **OpenRouter**: A unified API gateway that provides access to multiple LLM providers (OpenAI, Google, Anthropic, Meta, etc.) through a single OpenAI-compatible endpoint.
- **pydantic-ai**: A Python framework for building LLM applications with structured outputs, type validation, and model-agnostic streaming. Abstracts differences between Anthropic, OpenAI, and other providers.
- **Thinking block**: A section of model output containing the reasoning process before the final answer. Claude's extended thinking, DeepSeek's `<think>` tags, and Gemini's reasoning_details all produce thinking blocks.
- **Token**: The atomic unit of text that LLMs process. A token is roughly 3-4 characters in English. Token counts determine API costs and context window usage.
- **Workspace**: A container for documents and collaboration state in PromptGrimoire. Conversations link to workspaces to enable annotation integration and future real-time sync.
- **Alembic**: A database migration tool for SQLAlchemy (and by extension SQLModel) that manages schema changes through versioned migration scripts.
- **LaTeX**: A document preparation system used in PromptGrimoire's export pipeline to generate high-quality PDFs with complex formatting (syntax highlighting, margin notes, nested structure).
- **NiceGUI**: A Python web framework for building reactive user interfaces. Used for all pages in PromptGrimoire, including the playground.
- **SQLModel**: An ORM (Object-Relational Mapping) library that combines Pydantic's validation with SQLAlchemy's database operations. Used for all database models in PromptGrimoire.
- **Stytch**: An authentication platform providing magic links, passkeys, and role-based access control (RBAC). Used for user login and course enrollment in PromptGrimoire.
- **ACL (Access Control List)**: A permission system that defines which users can access which resources. Referenced for future workspace sharing (not yet implemented).
- **Fork (conversation)**: Creating a new independent conversation branch from a point in an existing conversation. Changes in the fork do not affect the original.
- **Fernet**: A symmetric encryption algorithm from the cryptography library. Used for encrypting student API keys at rest in the database.

## Architecture

### Design Principles

Inspired by ChatCraft.org's pedagogical philosophy: "show all the steps of the process... rather than collapsing this into one message, showing your work is a more powerful approach." Every parameter, token count, cost estimate, thinking block, and API request is visible and editable by students. The instructor's recourse is logging and the annotation pipeline, not hiding controls.

### Provider Layer

Two provider paths, unified by pydantic-ai's model-agnostic streaming interface:

**Direct Anthropic** (`AnthropicModel`): Used when instructor configures direct Claude access for a course. Full native thinking support via `AnthropicModelSettings` with `anthropic_thinking`. Adaptive thinking for Opus 4.6, `budget_tokens` for older Claude models. `ThinkingPart` arrives as first-class stream events with signature preservation for multi-turn continuity.

**OpenRouter** (`OpenRouterModel`): Used for all other providers (GPT-4, Gemini, Llama, DeepSeek, Mistral, etc.) and optionally for Claude models via OpenRouter. `OpenRouterStreamedResponse` handles thinking deltas from multiple providers (DeepSeek `<think>` tags, Gemini reasoning_details). Single OpenAI-compatible API contract.

Both paths emit the same pydantic-ai event types: `PartStartEvent(ThinkingPart)`, `PartDeltaEvent(DeltaThinkingPart)`, `PartStartEvent(TextPart)`, `PartDeltaEvent(TextPartDelta)`, `PartEndEvent`. The NiceGUI streaming handler does not need to know which provider is active.

Model selection is per-message. Students can switch models between turns. The conversation's `message_history` (pydantic-ai `ModelMessage` list) carries forward; pydantic-ai handles provider-specific serialization.

**Constraint**: When extended thinking is enabled for Claude, `temperature` cannot be set. The UI disables the temperature slider when a thinking-capable model is selected with thinking on.

### Data Model

**New SQLModel tables** (via Alembic migration):

**`CourseModelConfig`**: Per-course provider configuration.
- `course_id: UUID` (FK to Course)
- `provider: str` ("anthropic" | "openrouter")
- `model_id: str` (e.g., "anthropic/claude-opus-4-6", "openai/gpt-4o")
- `display_name: str` (human-readable label for the model picker)
- `enabled: bool` (instructor can disable without deleting)
- `privacy_notes: str | None` (instructor-visible notes on data handling)
- `hosting_region: str | None` (for regulatory filtering)
- `cost_tier: str | None` ("free" | "low" | "medium" | "high")

**`StudentAPIKey`**: Per-student-per-unit API key storage.
- `user_id: UUID` (FK to User)
- `course_id: UUID` (FK to Course)
- `provider: str` ("anthropic" | "openrouter")
- `api_key_encrypted: str` (encrypted at rest)
- Key provisioned by instructor only (no student self-service). Resolved server-side: student authenticates via Stytch, CourseEnrollment lookup, key retrieval. Keys never exposed in any UI. Per-student keys give instructor per-student budget control via the provider's own billing.

**`PlaygroundConversation`**: Conversation container.
- `id: UUID`
- `workspace_id: UUID` (FK to Workspace, for annotation integration and future CRDT sync)
- `course_id: UUID` (FK to Course)
- `user_id: UUID` (FK to User)
- `system_prompt: str` (editable, always visible)
- `title: str | None` (auto-generated or user-set)
- `created_at`, `updated_at: datetime`

**`PlaygroundMessage`**: Individual message with versioning.
- `id: UUID`
- `conversation_id: UUID` (FK to PlaygroundConversation)
- `role: str` ("user" | "assistant" | "system")
- `content: str` (text content)
- `thinking: str | None` (thinking block content, stored separately)
- `thinking_signature: str | None` (for multi-turn continuity)
- `model: str | None` (model ID that generated this message)
- `provider: str | None` ("anthropic" | "openrouter")
- `params: dict` (temperature, max_tokens, thinking config active at generation time)
- `token_count_input: int | None`
- `token_count_output: int | None`
- `token_count_thinking: int | None`
- `cost_estimate: float | None`
- `created_at: datetime`
- `file_refs: list[dict] | None` (name, size, content_type of attached files -- files stored in Workspace file storage)

### UI Layout

NiceGUI-native page at `/playground`. Every gear visible inline.

**System prompt**: First card in the chat, always-visible editable textarea with token count and "reset to course default" button.

**User messages**: Displayed with edit button. Edit modifies the message text in place (updates DB, original preserved in JSONL archive). File attachments shown as reference chips (filename + size).

**Assistant messages**: Each shows:
- Thinking block as `ui.expansion()` panel (collapsed by default, amber background, streams live during generation)
- Text content rendered via `ui.markdown()`
- Metadata byline: model name, token counts (input/output/thinking separately), estimated cost, parameters active at generation (temp, max_tokens, thinking on/off)
- Action buttons: edit (modifies text in place), regenerate (re-runs this response with current model/params)
- "Copy API request JSON" button showing exactly what was sent

**Input area**: `ui.textarea()` for prompt, inline model picker (filtered to course allowlist), parameter controls (temperature slider, max_tokens input, thinking toggle), file attach button via `ui.upload(multiple=True)`, send button with loading state.

**Streaming**: While streaming, the assistant message card builds live. Thinking expansion appears first with streaming content, then text streams below. Auto-scroll follows. Cancel via ESC or button aborts the pydantic-ai agent.

**NiceGUI patterns**: Each message is a `@ui.refreshable` component for individual re-rendering on edit/version-switch. Conversation state held in a page-level dataclass.

### Persistence and Logging

**Canonical store: Database** -- PostgreSQL via SQLModel. Conversations and messages persist. Students can resume, browse history. Instructors can view student conversations. Edits update records in place.

**Append-only archive: JSONL** -- Extending `llm/log.py`. Every API call logged with full request (system prompt, messages, params), full response (thinking + text + metadata), timing, cost, student ID, course ID. Immutable record preserving original content even after students edit messages in DB.

### Export Path

**Playground to Annotation**: "Annotate this conversation" button. Renders conversation as structured HTML with speaker labels, thinking blocks as collapsible sections, per-message metadata as data attributes. Creates `WorkspaceDocument(source_type="playground")` in the same workspace. Existing annotation page renders it through the input pipeline. JSON, Markdown, and PDF export are future additions.

### Collaboration Seams

Architecture does not preclude future CRDT sync or multi-student shared conversations:

- Conversations live in Workspaces, which already support multi-user access via future ACL
- `PlaygroundConversation` links to a Workspace; two students sharing a workspace share conversations
- Two users viewing the same workspace see the same active stream arriving in real time via NiceGUI data binding (shared server-side state automatically pushes updates to all bound clients)
- Each user in a shared workspace is identified by username; the user's first name is injected into the system prompt context so the AI can differentiate messages from different users
- pycrdt infrastructure already exists in the codebase for real-time sync
- For Phase 1, shared viewing works via DB-backed state and server-push. Full CRDT sync is a future enhancement.

## Existing Patterns

Investigation found the following relevant patterns in the codebase:

**LLM client**: `src/promptgrimoire/llm/client.py` has `ClaudeClient` with async streaming, extended thinking capture (currently hidden from UI), and metadata tracking. The playground replaces this with pydantic-ai's `Agent` but follows the same async streaming pattern.

**Data models**: `src/promptgrimoire/models/scenario.py` has `Turn` and `Session` dataclasses. The playground introduces richer SQLModel-backed equivalents (`PlaygroundMessage`, `PlaygroundConversation`) but follows the same metadata-per-turn pattern.

**NiceGUI streaming**: `src/promptgrimoire/pages/roleplay.py` streams via `streaming_label.text = full_response` with auto-scroll. The playground follows this pattern but adds per-block rendering (thinking vs text).

**JSONL logging**: `src/promptgrimoire/llm/log.py` has `JSONLLogger` writing SillyTavern-compatible format. The playground extends this with richer metadata (params, cost, provider details).

**Page registration**: `src/promptgrimoire/pages/registry.py` with `@page_route()` decorator. The playground registers at `/playground`.

**Database models**: `src/promptgrimoire/db/models.py` has Workspace and WorkspaceDocument. The playground links to Workspace for annotation integration.

**Export pipeline**: `src/promptgrimoire/export/` has the full HTML to Pandoc to LaTeX to PDF chain. The playground adds a new serializer for conversation-to-HTML but reuses the existing pipeline.

**Divergence from existing patterns**: The existing `ClaudeClient` is replaced by pydantic-ai rather than extended. This is justified because pydantic-ai provides model-agnostic streaming, OpenRouter support, and thinking block handling across providers -- capabilities that would require significant custom code to add to `ClaudeClient`. The existing roleplay page continues to use `ClaudeClient` for SillyTavern character card scenarios.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Data Model and Provider Foundation

**Goal:** Database schema for conversations, messages, course model config, and student API keys. Provider abstraction via pydantic-ai with streaming.

**Components:**
- Alembic migration for `CourseModelConfig`, `StudentAPIKey`, `PlaygroundConversation`, `PlaygroundMessage` tables in `src/promptgrimoire/db/`
- SQLModel classes in `src/promptgrimoire/db/models.py`
- Provider factory in `src/promptgrimoire/llm/playground_provider.py` -- resolves model ID + API key to pydantic-ai `Agent`, handles `AnthropicModel` vs `OpenRouterModel` routing
- Streaming handler that consumes `run_stream_events()` and yields structured events (thinking chunks, text chunks, metadata)
- CRUD operations for course model config and student API keys

**Dependencies:** None (first phase)

**Done when:** Provider factory creates agents for both Anthropic and OpenRouter, streaming produces thinking and text events, database tables exist and accept data. Tests cover: provider routing, streaming event parsing, model creation, CRUD operations.

**Covers:** llm-playground.AC3 (provider abstraction), llm-playground.AC2 (model config CRUD)
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Core Chat UI

**Goal:** Functional playground page where students can send messages and receive streaming responses with full transparency.

**Components:**
- Page route at `/playground` in `src/promptgrimoire/pages/playground.py`
- System prompt card (editable textarea, token count, reset button)
- Message rendering: user messages, assistant messages with streaming, thinking expansion panels
- Input area: textarea, model picker (from course allowlist), parameter controls (temperature, max_tokens, thinking toggle), send button
- Streaming display: live thinking block + text rendering, auto-scroll, cancel support
- Metadata display on each assistant message: model, tokens (input/output/thinking), cost, params, "copy API request JSON"

**Dependencies:** Phase 1 (data model, provider factory)

**Done when:** Student can select a model, type a prompt, see streaming response with thinking blocks, view all metadata inline, edit system prompt, and copy API request JSON. Tests cover: page renders, streaming updates UI, metadata displays correctly, model picker shows only allowed models.

**Covers:** llm-playground.AC1 (transparency), llm-playground.AC3 (model switching)
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Message Editing and Regeneration

**Goal:** Every message (user and assistant) is editable in place. Regenerate button on assistant messages.

**Components:**
- Edit button on user messages (modifies text in place, updates DB)
- Edit button on assistant messages (modifies text in place, updates DB)
- Regenerate button on assistant messages (re-runs response with current model/params, replaces content)
- `@ui.refreshable` per-message components for individual re-rendering on edit

**Dependencies:** Phase 2 (chat UI)

**Done when:** Student can edit any message in place and regenerate any assistant response. Original content preserved in JSONL archive. Tests cover: edit updates DB, regenerate calls provider, JSONL preserves pre-edit content.

**Covers:** llm-playground.AC6 (editing, regeneration)
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Persistence and Logging

**Goal:** Conversations persist in PostgreSQL. JSONL audit trail captures all API interactions.

**Components:**
- Conversation save/load in `src/promptgrimoire/db/` -- auto-save on each message send/receive
- Conversation list UI (sidebar or top bar) -- browse, resume, create new
- JSONL logger extension in `src/promptgrimoire/llm/` -- logs full request/response/timing/cost per API call
- Conversation links to Workspace (created automatically)

**Dependencies:** Phase 3 (editing -- need version-aware persistence)

**Done when:** Student can close browser, return, and resume a conversation. All API calls logged to JSONL. Conversation list shows history. Tests cover: save/load round-trip, JSONL log completeness, workspace creation.

**Covers:** llm-playground.AC4 (persistence, audit trail)
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: File Attachments

**Goal:** Students can attach files (images, text, PDFs) to messages.

**Components:**
- File upload via `ui.upload(multiple=True)` with drag-and-drop in the input area
- Attached files shown as chips on user messages (filename + size, no image preview)
- Files stored in workspace file storage, referenced by `PlaygroundMessage.file_refs`
- File content sent to LLM API: images as base64 for vision-capable models, text files as content, PDFs as extracted text
- Model capability detection: disable file attach for models that don't support vision/files

**Dependencies:** Phase 4 (persistence -- files need workspace storage)

**Done when:** Student can attach files to messages, files display as references, vision-capable models receive image content. Tests cover: upload flow, file storage, file reference on message, capability gating.

**Covers:** llm-playground.AC7 (file attachments)
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Export to Annotation

**Goal:** Export playground conversations to the annotation workflow.

**Components:**
- "Annotate this conversation" button: serializes conversation to structured HTML with speaker labels, thinking blocks as collapsible sections, per-message metadata as data attributes
- Creates `WorkspaceDocument(source_type="playground")` in the same workspace
- Annotation page renders the exported document through the existing input pipeline

**Dependencies:** Phase 4 (persistence), existing input pipeline in `src/promptgrimoire/input_pipeline/`

**Done when:** Exported conversation renders correctly on the annotation page with speaker labels and metadata. Tests cover: HTML serialization, WorkspaceDocument creation, annotation page rendering.

**Covers:** llm-playground.AC5 (export to annotation)
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Course Configuration and Admin

**Goal:** Instructors configure allowed models, API keys, and view student conversations.

**Components:**
- Course model config UI on the courses page: add/remove/enable models, set default, privacy/region/cost metadata
- Student API key management: instructor provisions keys per student per unit
- Instructor conversation view: read-only list of student conversations per course
- Usage dashboard: per-student token usage, cost, model distribution

**Dependencies:** Phase 6 (export), existing courses page at `src/promptgrimoire/pages/courses.py`

**Done when:** Instructor can configure models for a course, provision student keys, view student conversations read-only, see usage stats. Tests cover: model config CRUD via UI, key provisioning, read-only view, usage aggregation.

**Covers:** llm-playground.AC2 (instructor configuration)
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Collaboration Seams

**Goal:** Ensure architecture supports future CRDT sync and multi-student shared conversations without blocking Phase 1 launch.

**Components:**
- Verify Workspace linkage works for shared access (two students, one workspace, shared conversation list)
- Add `shared_with: list[UUID] | None` field to `PlaygroundConversation` for explicit sharing
- Instructor "share conversation to class" action (creates read-only copies for all enrolled students)
- Document CRDT integration points for future implementation

**Dependencies:** Phase 7 (admin -- sharing needs course enrollment context)

**Done when:** Two students accessing the same workspace see the same conversations. Instructor can share a conversation to the class. CRDT integration points documented. Tests cover: shared workspace access, instructor sharing, conversation visibility.

**Covers:** llm-playground.AC8 (collaboration seams)
<!-- END_PHASE_8 -->

## Additional Considerations

**Key encryption:** Student API keys must be encrypted at rest in PostgreSQL. Use Fernet symmetric encryption with a server-side key from environment variable. Keys are decrypted only in memory for API calls.

**Rate limiting:** Per-student rate limiting should be considered for OpenRouter calls to prevent accidental cost overruns. This can be implemented as a simple token-bucket in the provider factory.

**Model capability detection:** Not all models support vision, thinking, or tool calling. The provider factory should query model capabilities (available from OpenRouter's model metadata API) and the UI should disable unsupported features per model.

**Implementation scoping:** This design has 8 phases. If Phase 8 (collaboration seams) proves too complex for the initial delivery, it can be deferred -- the architecture supports it without requiring upfront implementation.
