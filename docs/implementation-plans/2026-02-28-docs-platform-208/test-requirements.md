# Test Requirements: docs-platform-208

Generated from acceptance criteria in `docs/design-plans/2026-02-28-docs-platform-208.md`.

---

## AC1: Guide DSL produces structured markdown

| AC | Type | Test Description | Phase | Test Location |
|----|------|-----------------|-------|---------------|
| AC1.1 | Success | `Guide` context manager creates output directory and writes `.md` file on exit | 1 | `tests/unit/test_docs_guide.py` |
| AC1.2 | Success | `Step` context manager appends `## heading` to buffer on entry | 1 | `tests/unit/test_docs_guide.py` |
| AC1.3 | Success | `guide.note(text)` appends narrative paragraphs to buffer | 1 | `tests/unit/test_docs_guide.py` |
| AC1.4 | Success | `guide.screenshot()` captures PNG and appends `![caption](path)` to buffer | 1 | `tests/unit/test_docs_guide.py` |
| AC1.5 | Success | Step exit auto-captures screenshot without explicit call | 1 | `tests/unit/test_docs_guide.py` |
| AC1.6 | Edge | Multiple steps produce sequential headings and images in order | 1 | `tests/unit/test_docs_guide.py` |

## AC2: Screenshots are annotated with element highlights

| AC | Type | Test Description | Phase | Test Location |
|----|------|-----------------|-------|---------------|
| AC2.1 | Success | CSS injection adds visible outline to `data-testid` element before capture | 1 | `tests/unit/test_docs_screenshot.py` |
| AC2.2 | Success | Injected `<style>` element is removed after capture | 1 | `tests/unit/test_docs_screenshot.py` |
| AC2.3 | Success | Multiple elements can be highlighted simultaneously | 1 | `tests/unit/test_docs_screenshot.py` |
| AC2.4 | Edge | Highlighting non-existent `data-testid` is a no-op (no error) | 1 | `tests/unit/test_docs_screenshot.py` |

## AC3: Screenshots are trimmed of whitespace

| AC | Type | Test Description | Phase | Test Location |
|----|------|-----------------|-------|---------------|
| AC3.1 | Success | Pillow trimming removes empty margins from screenshots | 1 | `tests/unit/test_docs_screenshot.py` |
| AC3.2 | Success | Trimmed image retains all non-empty content (pixel data matches cropped original) | 1 | `tests/unit/test_docs_screenshot.py` |
| AC3.3 | Edge | Image with no whitespace margins is returned unchanged | 1 | `tests/unit/test_docs_screenshot.py` |
| AC3.4 | Success | Focused `locator.screenshot()` produces tightly-cropped element image | 3, 4 | Operational (via `uv run make-docs`) |

## AC4: make_docs() orchestrates the full pipeline

| AC | Type | Test Description | Phase | Test Location |
|----|------|-----------------|-------|---------------|
| AC4.1 | Success | `make-docs` starts server, launches Playwright, runs guides, stops both | 2 | `tests/unit/test_make_docs.py` |
| AC4.2 | Success | Instructor guide runs before student guide | 2 | `tests/unit/test_make_docs.py` |
| AC4.3 | Success | Pipeline produces both markdown files and screenshots | 2 | `tests/unit/test_make_docs.py` |
| AC4.4 | Failure | Guide exception causes `make_docs()` to exit non-zero | 2 | `tests/unit/test_make_docs.py` |
| AC4.5 | Failure | Missing pandoc causes clear error before server start | 2 | `tests/unit/test_make_docs.py` |

## AC5: Guide scripts produce correct output

| AC | Type | Test Description | Phase | Test Location |
|----|------|-----------------|-------|---------------|
| AC5.1 | Success | Instructor guide produces markdown with ~7 screenshots | 3 | Operational (`uv run make-docs`) |
| AC5.2 | Success | Student guide produces markdown with ~10 screenshots | 4 | Operational (`uv run make-docs`) |
| AC5.3 | Success | All screenshots show element highlights and are trimmed | 3, 4 | Operational (visual inspection) |

## AC6: MkDocs Material renders HTML site

| AC | Type | Test Description | Phase | Test Location |
|----|------|-----------------|-------|---------------|
| AC6.1 | Success | `mkdocs build` produces HTML site with landing page and both guides | 5 | `tests/unit/test_make_docs.py` (mock subprocess) + Operational |
| AC6.2 | Success | Navigation between landing page and guides works | 5 | Operational (`mkdocs serve`) |
| AC6.3 | Success | `mkdocs serve` starts local preview server | 5 | Operational (manual) |

## AC7: PDF export via Pandoc

| AC | Type | Test Description | Phase | Test Location |
|----|------|-----------------|-------|---------------|
| AC7.1 | Success | Pandoc produces PDF for each guide with embedded screenshots | 5 | `tests/unit/test_make_docs.py` (mock subprocess) + Operational |
| AC7.2 | Failure | Missing `--resource-path` causes image resolution failure | 5 | `tests/unit/test_make_docs.py` (verify flag in call args) |

## AC8: Old pipeline fully replaced

| AC | Type | Test Description | Phase | Test Location |
|----|------|-----------------|-------|---------------|
| AC8.1 | Success | No references to `rodney` or `showboat` in production code or `pyproject.toml` | 2, 6 | Operational (codebase search) |
| AC8.2 | Success | All bash guide scripts deleted | 3, 4, 6 | Operational (directory listing) |
| AC8.3 | Success | `CLAUDE.md` documents new `make-docs` pipeline accurately | 6 | Operational (manual review) |

## AC9: Zensical migration compatibility

| AC | Type | Test Description | Phase | Test Location |
|----|------|-----------------|-------|---------------|
| AC9.1 | Success | `mkdocs.yml` uses standard config with no blocking plugins | 5 | Operational (review `mkdocs.yml`) |

---

## Test Type Summary

| Type | Count | Notes |
|------|-------|-------|
| Unit tests (mocked) | 18 | AC1.1–AC1.6, AC2.1–AC2.4, AC3.1–AC3.3, AC4.1–AC4.5 |
| Operational (make-docs) | 9 | AC3.4, AC5.1–AC5.3, AC6.1–AC6.3, AC7.1, AC8.2 |
| Operational (search/review) | 4 | AC8.1, AC8.3, AC9.1, AC7.2 |

Unit tests live in `tests/unit/` and run via `uv run test-all`. Operational tests are verified by running `uv run make-docs` end-to-end and inspecting output.
