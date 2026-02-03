# EAL/D Vocabulary Learning Application - Technical Overview

## Executive Summary

This is a sophisticated AI-powered vocabulary learning prototype for English as an Additional Language/Dialect (EAL/D) students in Australian primary schools (Years 3-7). The application uses speech-based interactions to teach curriculum vocabulary through natural conversation with an AI tutor.

---

## Codebase Metrics

| Metric | Value |
|--------|-------|
| **Total Python Files** | 150 |
| **Lines of Code** | ~27,000 (including tests) |
| **Application Code** | ~9,100 lines in `/app/` |
| **Test Code** | ~3,900 lines, 255 test functions |
| **Database Models** | 6 SQLModel tables |
| **UI Components** | 15+ reusable NiceGUI components |
| **Service Modules** | 11 business logic services |
| **Pages/Routes** | 12 page files |

---

## Architecture Highlights

### 1. Graph-Based Conversation Engine
The core innovation is a **state machine conversation engine** built with `pydantic-graph`:

- **Resumable sessions**: Students can exit mid-lesson and return days later with full context preserved
- **Complete audit trail**: Every graph state saved as PostgreSQL JSONB snapshots
- **Four core nodes**: Init → StudentResponse → Evaluation → Instruction (loop)
- **Dependency injection**: Same graph code runs in CLI, web, and test environments

### 2. Multi-Provider AI Integration

| Service | Provider | Purpose |
|---------|----------|---------|
| Speech-to-Text | Google Gemini 2.5 | Transcription with IPA phonetic output |
| Instruction/Evaluation | Anthropic Claude | Conversational teaching responses |
| Text-to-Speech | ElevenLabs | Natural voice synthesis |

**Streaming TTS Architecture**: Parallel tasks for text generation and audio reception reduce latency from 2-3 seconds to 300-500ms for first audio.

### 3. Technology Stack

**Backend:**
- Python 3.12+ with `uv` package manager
- FastAPI + NiceGUI (reactive web UI)
- SQLModel (SQLAlchemy + Pydantic ORM)
- PostgreSQL with async connections
- Stytch magic link authentication

**AI/ML:**
- pydantic-ai for LLM orchestration
- pydantic-graph for conversation state machine
- Extended thinking configuration for ASR accuracy

**Observability:**
- Logfire distributed tracing
- OpenTelemetry compatible
- Full AI call instrumentation

### 4. Database Design

```
users (Stytch auth linking)
    └── student_details (profiles)
    └── lesson_plans (JSONB content)
            └── runs (session instances)
                    └── graph_snapshots (conversation state)
```

Each graph snapshot enables perfect session resumption with full conversation history.

---

## Code Quality & Testing

### Testing Infrastructure
- **pytest** with async support (pytest-asyncio)
- **255 test functions** across 9 categories
- Mock infrastructure for all AI services (no API calls in tests)
- Per-test database isolation with truncate/restart identity
- NiceGUI User fixture for fast UI component testing

### Development Tooling
- **ruff**: Ultra-fast linting and formatting
- **mypy**: Static type checking (Python 3.12 target)
- **vulture**: Dead code detection
- **pre-commit hooks**: 8 hooks (format, lint, type check, tests)

### Quality Patterns
- Type-safe throughout (no `Any` types)
- Google-style docstrings
- Test-driven development approach
- Example-driven integration testing

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Conversation engine | pydantic-graph | Type-safe, resumable, auditable |
| ORM | SQLModel | Type hints + SQL flexibility + validation |
| UI framework | NiceGUI | Rapid reactive UI, FastAPI integration |
| Auth | Stytch magic links | Passwordless, audit-friendly |
| Audio streaming | WebSocket + parallel tasks | 2.5s latency reduction |
| State persistence | PostgreSQL JSONB | Queryable, schema-flexible |
| Tracing | Logfire | Research-grade observability |

---

## Development Workflow

### Structure
```
/app/                    # Production code
├── models/              # Database models
├── services/            # Business logic
├── graphs/vocab_learning/  # Conversation engine
├── ui/components/       # Reusable UI components
├── pages/               # Route handlers
└── main.py              # Entry point

/examples/example9_audio_pipeline/  # Development harness
/tests/                  # Comprehensive test suite
/docs/                   # PRD, UX spec, architecture docs
```

### Workflow Pattern
1. Build features in standalone examples first
2. Extract reusable components to `/app/`
3. Development harness (example9) imports from `/app/`
4. Test-driven: write tests before implementation

---

## Complexity Assessment

**High Complexity Areas:**
- Graph-based conversation engine with resumable state
- Streaming TTS with parallel audio/text processing
- Multi-provider AI orchestration (3 different AI services)
- Async PostgreSQL persistence with JSONB snapshots

**Medium Complexity:**
- Stytch authentication middleware
- Role-based access control
- Reactive UI components with NiceGUI binding

**Standard Patterns:**
- FastAPI routing and middleware
- SQLModel CRUD operations
- pytest testing infrastructure

---

## Production Readiness

| Aspect | Status |
|--------|--------|
| Authentication | Production-grade (Stytch) |
| Database | Async SQLModel, ready for migrations |
| Logging | Distributed tracing (Logfire) |
| Error handling | Graceful fallbacks throughout |
| Testing | Comprehensive suite, pre-commit enforced |
| Documentation | PRD, UX spec, inline docstrings |

### Known Technical Debt
- Connection pool tuning needed for production scale
- Alembic migrations not yet configured (using create_all)
- Cache warming for agents (latency optimization)

---

## Summary for Software Development Firm

This is a **mature prototype** demonstrating:

1. **Sophisticated Architecture**: Graph-based state machine for resumable AI conversations, not just a simple chatbot wrapper

2. **Professional Code Quality**: Type-safe Python 3.12, comprehensive testing (255 tests), pre-commit hooks, distributed tracing

3. **Multi-Modal AI Integration**: Speech-to-text, LLM instruction, text-to-speech with streaming architecture for low latency

4. **Research-Ready**: Complete audit trails, JSONB state snapshots, session analytics

5. **Production Patterns**: Proper auth (Stytch), async database (PostgreSQL), observability (Logfire)

The codebase is well-structured for handoff or continued development, with clear separation of concerns, documented decisions, and example-driven development workflow.
