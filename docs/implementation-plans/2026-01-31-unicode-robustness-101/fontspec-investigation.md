# Fontspec Investigation Results

**Date:** 2026-01-31
**Decision:** Use detect-and-wrap approach

## Background

The design plan considered two approaches for unicode handling in LaTeX:
1. **Fontspec fallback chain** - Configure LuaLaTeX with font fallback sequence
2. **Detect-and-wrap** - Scan text for unicode ranges, wrap in explicit font commands

## Investigation

Prior experience with fontspec fallback chains showed:
- Configuration is environment-dependent
- Font resolution varies across systems
- Silent failures produce tofu (□) instead of useful errors
- Debugging font issues is time-consuming

## Decision

**Detect-and-wrap is the primary approach.**

Benefits:
- Explicit control over which fonts render which characters
- Clear error messages when fonts missing
- Consistent behavior across environments
- Easier to test and verify

## Implementation

- `src/promptgrimoire/export/unicode_latex.py` will detect CJK/emoji ranges
- Text will be wrapped in explicit `\setCJKfamily` or similar commands
- Phases 2-3 implement this approach
