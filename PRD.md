# PromptGrimoire - Product Requirements Document

## Vision

A collaborative "classroom grimoire" for prompt iteration, annotation, and sharing in educational contexts. Based on the pedagogical framework from ["Teaching the Unknown"](paper/20250603-BBS-JT-TeachingTheUnknown%20(1).pdf) (Ballsun-Stanton & Torrington).

**Timeline:** 6 weeks to Session 1 2025 (Feb 23)

A lightweight tool for educators and students to:
- Accept student prompts (copy-paste from multiple AI providers)
- Enable real-time collaborative annotation with structured tagging
- Support in-class "show me your prompts" discussions
- Build a shared grimoire of effective prompting patterns

---

## Core Features

### 1. Conversation Import & Parsing

- **Copy-paste only** (no API imports for v1)
- Multi-format parsers: Claude, ChatGPT, Chatcraft.org, ScienceOS
- Full conversation as atomic unit
- Parse into individual turns (human/assistant pairs)
- Plain text fallback with manual delimiters
- Heuristic detection of format from pasted content

### 2. Real-time Collaborative Annotation

- **Tech:** pycrdt (Yjs port) + PostgreSQL + NiceGUI websockets
- **Click-drag highlighting** on prompt/response text
- Structured tags (emergent folksonomy with seed defaults)
- Threaded comments on highlights
- Live cursors/presence indicators

### 3. Tag System

- Emergent folksonomy: users create tags freely
- Seed defaults: effective / ineffective / hallucination / good-structure
- Class-scoped tag namespacing
- Tag frequency surfacing for popular tags

### 4. Class Management

- Stytch magic links + passkeys for auth
- Stytch-managed invites per class
- Stytch RBAC for permissions (admin/instructor/student roles)
- Future: Okta SSO integration via Stytch

### 5. Sharing & Discovery

- Private by default (class-scoped)
- Explicit contribution to public grimoire
- **Attribution options:**
  - Attributed (full name/display name visible)
  - Anonymous presentation (no name shown publicly, but traceable by instructors for abuse cases)
- Search across accessible content

### 6. Course & Activity Structure

Prompts are organized hierarchically for classroom use:

```text
Course (e.g., "KI Sommercamp 2025")
  └── Day/Module (e.g., "Day 1: Can we control AI output?")
       └── Session (e.g., "Session 2: The Confident Assistant")
            └── Activity (e.g., "System Prompts and Copy Editing")
                 └── Prompts (individual student contributions)
```

- Instructors create course → day → session → activity structure
- Students submit prompts to specific activities
- Each activity has its own shared grimoire view
- "Show me your prompts" discussions scoped to activity
- Activities can be reused across course instances

### 7. Presentation Mode

- Fullscreen display optimized for projection
- Highlight active annotation
- Scroll control for instructor
- Surface recently shared/annotated prompts

---

## Tech Stack

- **Python 3.14** (bleeding edge)
- **NiceGUI** - web UI framework
- **SQLModel** - ORM (Pydantic + SQLAlchemy)
- **PostgreSQL** - persistence
- **pycrdt** - CRDT for real-time collaboration
- **Stytch** - auth (magic links, passkeys, invites)
- **Ruff** - linting + formatting
- **ty** - type checking
- **Playwright** - E2E testing
- **pytest** - unit/integration testing

---

## User Roles (Stytch RBAC)

| Role | Capabilities |
|------|-------------|
| **Admin** | Full system access, manage institutions |
| **Instructor** | Create classes, manage tags, invite students, projection view |
| **Student** | Import prompts, annotate, share to class/grimoire |

---

## Database Schema (Draft)

```text
# Users & Auth
User (id, email, display_name, created_at)

# Course Hierarchy
Course (id, name, owner_id, created_at)
CourseDay (id, course_id, name, sequence, created_at)
Session (id, day_id, name, sequence, created_at)
Activity (id, session_id, name, description, sequence, created_at)

# Class Management (enrollment instance of a course)
Class (id, course_id, name, owner_id, invite_code, created_at)
ClassMembership (user_id, class_id, role)  # role: admin/instructor/student

# Prompts & Annotations
Conversation (id, activity_id, class_id, owner_id, raw_text, parsed_turns, crdt_state,
              is_anonymous, shared_to_class, shared_to_grimoire, created_at)
Turn (id, conversation_id, role, content, sequence)
Annotation (id, conversation_id, user_id, turn_id, start_offset, end_offset,
            is_anonymous, crdt_state, created_at)
Tag (id, name, class_id, usage_count)
AnnotationTag (annotation_id, tag_id)
Comment (id, annotation_id, user_id, content, parent_id, is_anonymous, created_at)
```

**Note:** `is_anonymous` controls public display only. Instructors and admins can always see the real author for moderation.

---

## Open Questions

- **Stytch B2C vs B2B**: B2C is simpler (we manage classes), B2B has built-in RBAC/orgs
- Exact Stytch configuration (needs API keys)
- PostgreSQL hosting on NCI
- Parser specifications per AI provider
- UI/UX wireframes for annotation interface

---

## Milestones

### Week 1: Derisking Spikes

Technical validation of all integration points.

#### Spike 1: pycrdt + NiceGUI WebSocket

- Create Doc with Text type
- Two browser tabs connected
- Type in one, see update in other
- Validates: CRDT sync over NiceGUI WebSocket

#### Spike 2: Text Selection → Annotation

- Display static text in NiceGUI
- Click-drag to select
- Capture range via `ui.run_javascript()`
- Create visual highlight (CSS)
- Validates: Browser JS ↔ Python bridge

#### Spike 3: Stytch Magic Link Flow

- Send magic link email
- Handle callback URL
- Create/validate session
- Validates: Auth flow with NiceGUI

#### Spike 4: SQLModel Async + PostgreSQL

- Define User, Class, Conversation models
- Create tables via Alembic
- Async insert/query operations
- Validates: Async DB layer

#### Spike 5: Integration Test

- Combine spikes 1-4
- User logs in → sees conversation → selects text → annotation syncs
- Validates: End-to-end flow

### Week 2: Core Data Model

- Finalize SQLModel schemas (User, Class, Conversation, Turn, Annotation, Tag)
- Alembic migrations
- CRDT document structure for annotations
- Unit tests for all models

### Week 3: Conversation Import

- Plain text parser (manual delimiters)
- Claude format parser
- ChatGPT format parser
- Chatcraft.org parser
- ScienceOS parser
- Format auto-detection heuristics
- Tests for each parser

### Week 4: Annotation UI

- Text display component
- Click-drag selection capture
- Annotation highlight rendering
- Tag selector (create/select existing)
- Comment thread UI
- Real-time sync between users

### Week 5: Class Management & Auth

- Stytch integration (magic links)
- Class creation/invitation flow
- Role-based access (instructor/student)
- Class membership UI
- Session management

### Week 6: Polish & Presentation Mode

- Fullscreen presentation view
- Instructor scroll control
- Recent annotations feed
- Bug fixes and edge cases
- E2E test coverage
- Deployment to NCI

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed integration patterns.
