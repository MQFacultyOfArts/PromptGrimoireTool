# Plan: Remove Pause Functionality from Meeting Transcriber

## Summary
Remove the pause/resume workflow from the transcriber, simplifying it to just start and end (stop) operations. When the user clicks "End Meeting", the system will process diarization and save the transcript.

## Files to Modify

### 1. [app.py](src/meeting_transcriber/gui/app.py)
**Changes:**
- Remove `pause_and_process()` function (lines 172-291)
- Remove `resume_recording()` function (lines 293-320)
- Remove pause/resume buttons from UI (lines 472-473)
- Remove button event handlers for pause/resume (lines 551-558)
- Update `end_meeting()` to directly process diarization (instead of calling `pause_and_process()`)
- Update UI text/docstrings to remove pause/resume references
- Remove "⏸️ Paused" status indicator from `get_recording_status()`

### 2. [recorder.py](src/meeting_transcriber/audio/recorder.py)
**Changes:**
- Remove `pause()` method (lines 244-256)
- Remove `resume()` method (lines 258-276)
- Remove `is_paused` property (lines 88-90)
- Remove `_is_paused` state variable (line 58)
- Remove `_total_paused_time` and `_pause_start_time` tracking (lines 77-78)
- Simplify `elapsed_time` property (no pause time tracking)
- Simplify `is_recording` property (no pause check)
- Remove pause checks from thread loops (lines 190, 204)
- Update docstring to remove pause/resume references (line 45)

### 3. [round_manager.py](src/meeting_transcriber/output/round_manager.py)
**Changes:**
- Update docstring to remove pause/resume workflow references (lines 1, 25)
- The round management logic itself can remain since `end_meeting()` will create a single round

## Implementation Details

### Modified `end_meeting()` Flow
The new `end_meeting()` function will:
1. Stop the transcription thread
2. Process the final audio segment
3. Unload Granite model
4. Load diarizer and run on full audio
5. Create a single round with all segments
6. Save combined transcript
7. Stop recording and close audio file

### UI Changes
- Remove "Pause & Process" and "Resume" buttons
- Keep "Start Meeting" and "End Meeting" buttons
- Status will only show "🔴 RECORDING" or "⚫ Stopped" (no "⏸️ Paused")

## Verification
1. Run the transcriber: `uv run python -m meeting_transcriber`
2. Load models
3. Start a meeting recording
4. Verify recording status shows "🔴 RECORDING"
5. Click "End Meeting"
6. Verify diarization runs and transcript is saved
7. Check session directory for `transcript.json` and `transcript.txt`
