# Meeting Transcriber Bug Fixes

## Issues to Fix

### Critical
1. **Recording indicator accuracy** - Must not show "recording" when not actually recording (false positive)
2. **OOM detection** - Wrap transcription calls in try/except for `torch.cuda.OutOfMemoryError`, `MemoryError`, `RuntimeError` with "out of memory"
3. **Session nesting bug** - Sessions creating inside other sessions (`session_X/meeting_transcripts/session_Y/`)

### High Priority
4. **Dropdown state bug** - Round dropdown choices empty when setting value; update choices before setting value
5. **Round 3 reliability** - Likely OOM-related, should improve with #2

### Medium Priority
6. **Round naming** - Make rounds globally unique (include session timestamp in round name or use UUIDs)
7. **Data fragility** - Save state more frequently / implement recovery mechanism

### Lower Priority (Note in TODO)
8. **Diarization not working** - Needs deeper investigation
9. **Clearer recording indicator** - UI enhancement

## Files to Modify
- `src/meeting_transcriber/gui/app.py` - Recording state, OOM handling, dropdown fix
- `src/meeting_transcriber/transcription/granite.py` - OOM handling
- `src/meeting_transcriber/output/round_manager.py` - Round naming
- `src/meeting_transcriber/output/writer.py` - Session path fix

## Quick Fixes Plan
1. Add try/except around transcription calls with OOM detection
2. Fix recording indicator state management
3. Fix session directory creation to use absolute base path
4. Update dropdown choices before setting value
5. Add session prefix to round names for uniqueness
