# Issue #101 Unicode Robustness - Checkpoint 2026-02-03

## Current State

**Branch:** `101-cjk-blns`
**Related Issues:** #101 (main), #113 (blocker)

## Work Completed on This Branch

### Unicode Robustness (Issue #101)
- ✅ Phase 1-5 of unicode-robustness design complete
- ✅ `escape_unicode_latex()` with CJK/emoji wrapping
- ✅ `UNICODE_PREAMBLE` with comprehensive font fallback chain
- ✅ TinyTeX packages: emoji, luatexja, haranoaji
- ✅ Control char stripping moved AFTER marker insertion
- ⚠️ Phase 6-7 blocked by Issue #113

### Character-Based Tokenization (mid-stream pivot)
- ✅ All 5 phases implemented (cc358b2 → 7bd5d94)
- ✅ UI tokenizes by character, not word
- ✅ CJK text selectable character-by-character
- ✅ PDF export uses same character indexing
- ⚠️ UAT blocked by Issue #113

## Current Blockers

### Issue #113: HTML Entity-Like Strings Break LaTeX
**Root cause:** Character-based marker insertion breaks multi-char HTML entities.

Example:
```
Original: jav&#x0A;ascript
After marker at char N: jav&#x0HLSTART...A;ascript
After LaTeX: jav\&\#x0\highLight{A;ascript...  ← BROKEN
```

**Possible fixes (from issue):**
1. Post-process LaTeX - escape after marker replacement
2. Validate marker positions - don't break multi-char sequences
3. Sanitize BLNS content - strip/escape entities before storage

### Deseret Script Rendering
- Fonts installed via `fonts-noto`
- `luaotfload-tool --find` finds Noto Sans Deseret
- Still shows tofu in PDF output
- Lower priority than #113

## Design Plans Updated
- `docs/design-plans/2026-01-29-unicode-robustness.md` - status added
- `docs/design-plans/2026-02-02-character-tokenization.md` - status added

## Next Steps (Priority Order)

1. **Fix Issue #113** - LaTeX entity-like string breakage
2. **Complete UAT** - CJK fixtures + BLNS paste-in test
3. **Debug Deseret rendering** - why fonts not working despite being found
4. **Phase 7** - Visual validation demo route (optional for MVP)

## Key Files

- `src/promptgrimoire/export/unicode_latex.py` - UNICODE_PREAMBLE, escape functions
- `src/promptgrimoire/export/latex.py` - Marker insertion (now character-based)
- `src/promptgrimoire/pages/annotation.py` - Character tokenization UI
- `docs/design-plans/2026-01-29-unicode-robustness.md`
- `docs/design-plans/2026-02-02-character-tokenization.md`

## Commands

```bash
# Run app
uv run python -m promptgrimoire

# Test BLNS workspace (has Issue #113 repro)
# Workspace: f4270318-ca98-47fc-8527-9b772699a755

# Check font availability
fc-list | grep -i deseret
~/.TinyTeX/bin/x86_64-linux/luaotfload-tool --find="Noto Sans Deseret"
```
