# Design Plan Guidance for PromptGrimoire

**Last updated:** 2026-01-30

## Product Vision

PromptGrimoire is a **metacognition platform** for process management and reflection on both external and student-produced work. It enables deep learning through structured annotation and self-reflection.

**Core capabilities:**
- **Case Briefs** - Legal case analysis with structured annotation
- **Translation Annotation** - Language learning through marked-up translations
- **Prompt Grimoires** - Collaborative annotation of AI conversations for teaching prompt engineering

**Secondary capability:**
- **Roleplay** - SillyTavern-compatible character card execution (avoids tedious per-student deployment)

**Target:** Session 1 2026 (Feb 23) MVP launch

**Success looks like:** Students actively using the platform for metacognitive reflection, instructors able to observe and guide annotation patterns, exportable artifacts for assessment.

## Domain Terminology

| Term | Meaning |
|------|---------|
| **Workspace** | Student's personal instance of an Activity, containing their annotations and responses |
| **Activity** | Template created by instructor with source documents and tag configuration |
| **Course** | Top-level enrollment container |
| **Week** | Optional grouping within a Course |
| **Tag** | Categorization for highlights (e.g., "Issue", "Rule", "Application" for legal briefs) |
| **CRDT** | Conflict-free replicated data type - enables real-time collaboration without conflicts |
| **Seam** | A bounded integration point in the architecture (see Epic #92) |
| **Character Card** | SillyTavern chara_card_v3 JSON format for roleplay personas |
| **Lorebook** | Keyword-triggered context injection for roleplay scenarios |

## Architectural Constraints

### Required Patterns
- **CRDT-first for collaborative state** - All shared state uses pycrdt
- **Seam-based decomposition** - Follow Epic #92's 8 seams (A-H) for workspace platform
- **Database via Alembic only** - Never use `create_all()` outside migrations
- **UUID isolation in tests** - All test data must be collision-free

### Technology Stack (Decided)
| Layer | Technology | Status |
|-------|------------|--------|
| UI Framework | NiceGUI | **Decided** |
| ORM | SQLModel (Pydantic + SQLAlchemy) | **Decided** |
| Database | PostgreSQL | **Decided** |
| Real-time | pycrdt | **Decided** |
| Auth | Stytch (magic links, passkeys, RBAC) | **Decided** |
| PDF Export | TinyTeX + LuaLaTeX | **Decided** |
| Python | 3.14 (bleeding edge) | **Decided** |

**Do not propose alternatives** to decided technologies.

### Forbidden Approaches
- Direct DOM manipulation in E2E tests (use Playwright native APIs)
- `SQLModel.metadata.create_all()` in application code
- `drop_all()` or `truncate` in tests
- Skipping TDD (write failing test first, always)

## Active Domains & Issue Tracking

| Domain | Label | Key Issues |
|--------|-------|------------|
| Workspace Platform | `domain:workspace-platform` | Epic #92, Seams #93-#100 |
| PDF Export | `domain:pdf-export` | #66, #76, #83, #88, #89, #101 |
| Case Brief | `domain:case-brief` | #47, #50-#53 |
| Translation | `domain:translation` | PRD in docs/ |
| Roleplay | `domain:roleplay` | #36, #37 |

**Phase labels:**
- `phase:mvp` - Must ship for Feb 23
- `phase:post-mvp` - Nice to have, after launch

## Scope Defaults

**Typically IN scope:**
- Features tagged `phase:mvp`
- Bug fixes for existing functionality
- Test coverage for new code

**Typically OUT of scope (unless explicitly requested):**
- Admin dashboards
- Performance optimization beyond "works"
- Features tagged `phase:post-mvp`
- Documentation beyond docstrings

## Stakeholder Context

| Stakeholder | Cares About |
|-------------|-------------|
| Students | Intuitive annotation UX, works on their devices, exportable artifacts |
| Instructors | Visibility into student work, presentation mode, rubric alignment |
| Brian (Product Owner) | UAT-testable deliverables, maintainable code, Feb 23 deadline |

## Cross-Reference

- Full project rules: [project-reference.md](project-reference.md) (symlink to CLAUDE.md)
- Architecture: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- Epic #92: [GitHub](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/92)
