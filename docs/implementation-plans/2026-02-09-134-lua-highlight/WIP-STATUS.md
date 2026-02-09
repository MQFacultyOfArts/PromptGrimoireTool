# WIP Status: 134-lua-highlight Implementation

**Last updated:** 2026-02-10
**Branch:** 134-lua-highlight

## Completed

### Phase 1: Extract preamble and Pandoc modules
- **Status:** COMPLETE (code review approved, zero issues)
- **Commits:** 46d5f72, a49dbd2, a181ddf, d430d1b
- Split `latex.py` into `preamble.py` (188 lines) and `pandoc.py` (194 lines)
- Updated all imports, re-exports, 13 AC3 validation tests pass

### Phase 2: Pre-Pandoc highlight span insertion
- **Status:** CODE REVIEW FIXES NEEDED
- **Commits:** 4b40a87, 40ed6ea
- Created `highlight_spans.py` with region computation + block splitting
- 15 AC1 tests written
- Code review found 6 issues (2 Critical, 2 Important, 2 Minor)

#### Outstanding Review Issues

| ID | Severity | Summary |
|----|----------|---------|
| C1 | Critical | `_char_to_byte_pos` maps region start to wrong text node at block boundaries |
| C2 | Critical | AC1.1/AC1.5 tests don't verify span text content (mask C1 bug) |
| I1 | Important | Missing CRLF edge case test (explicitly required by plan) |
| I2 | Important | Redundant `find_text_node_offsets` call (perf waste) |
| M1 | Minor | Stale docstring references selectolax in `_detect_block_boundaries` |
| M2 | Minor | Stale `_find_text_node_offsets` reference in test docstring |

## Not Started

### Phase 3: Pandoc Lua filter
### Phase 4: Wire pipeline + delete old code
