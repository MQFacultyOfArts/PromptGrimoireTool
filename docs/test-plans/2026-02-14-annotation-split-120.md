# Test Plan: Annotation Module Split (#120)

## Prerequisites

- Development environment configured with `.env` file
- PostgreSQL running and accessible
- `uv sync` completed
- `uv run test-all` passing (2494 tests)
- Seeded database (`uv run seed-data`)
- Browser supporting CSS Custom Highlight API (Chrome 105+ / Edge 105+)

## Phase 1: Scroll-Sync Card Positioning (AC2.3)

| Step | Action | Expected |
|------|--------|----------|
| 1.1 | Start app (`uv run python -m promptgrimoire`), navigate to `/annotation` | Page loads without errors |
| 1.2 | Create workspace, paste multi-paragraph HTML | Document renders in Annotate tab |
| 1.3 | Create 3+ highlights across different parts of the document | Highlights render with coloured underlines, cards appear in sidebar |
| 1.4 | Scroll document up and down | Cards track highlight positions smoothly |
| 1.5 | Hover over a sidebar card | Corresponding text region glows/highlights |

## Phase 2: Copy Protection (AC2.4)

| Step | Action | Expected |
|------|--------|----------|
| 2.1 | Navigate to `/courses`, create course with copy protection enabled | Toggle saves |
| 2.2 | Create Week and Activity (inherits copy protection) | Activity shows "Inherit from course" |
| 2.3 | Open template workspace, paste content | Content loads |
| 2.4 | Open student workspace (incognito/unauthenticated) | Amber "Protected" lock chip visible |
| 2.5 | Select text, press Ctrl+C | Copy blocked, toast notification |
| 2.6 | Right-click selected text | Context menu blocked, toast notification |
| 2.7 | Drag selected text | Drag blocked, toast notification |
| 2.8 | Press Ctrl+P | Print intercepted, toast notification |

## Phase 3: Import Structure (AC3.1, AC3.2)

| Step | Action | Expected |
|------|--------|----------|
| 3.1 | Inspect `pages/annotation/*.py` imports | All cross-module imports use `from promptgrimoire.pages.annotation.<module> import ...` |
| 3.2 | Read `__init__.py` | All imports at module level, no function-scoped late imports |

## Phase 4: Documentation (AC5.1-5.3)

| Step | Action | Expected |
|------|--------|----------|
| 4.1 | Read CLAUDE.md project structure | `annotation/` listed as 12-module package, no stale `annotation.py` ref |
| 4.2 | Read `annotation-perf.md` Phase 1 | Module names match actual package structure |
| 4.3 | `gh issue list --search "paste handler JS"` | Issue #167 exists |

## Traceability

| AC | Automated Test | Manual Step |
|----|----------------|-------------|
| AC1.1-AC1.6 | `test_annotation_package_structure.py` (8 tests) | -- |
| AC2.1-AC2.2 | `test_annotation_js_extraction.py` (4 tests) | -- |
| AC2.3 | -- | 1.3-1.5 |
| AC2.4 | -- | 2.4-2.8 |
| AC2.5 | `test_annotation_js_extraction.py` (1 test) | -- |
| AC3.1 | `test_annotation_package_structure.py::test_no_imports_from_old_satellite_paths` | 3.1 |
| AC3.2 | -- | 3.2 |
| AC3.3-AC3.4 | `test_annotation_package_structure.py` | -- |
| AC4.1 | `uv run test-all` (2494 passed) | -- |
| AC4.3 | Updated test files pass | -- |
| AC5.1-AC5.3 | -- | 4.1-4.3 |
