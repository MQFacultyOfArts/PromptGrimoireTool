# Plan: Close Completed GitHub Issues

## Task
Close GitHub issues #43, #44, and #47 which have been verified as implemented.

## Verification Summary

### #43 - Session Statistics Page
- **Implemented in**: `app/pages/admin_sessions.py`
- **Features**: Session list with timestamps, duration, rounds, 5+ min gap detection, clickable drill-down

### #44 - Transcript Viewer with IPA-to-Text
- **Implemented in**: `app/pages/admin_transcript.py` + `app/services/transcript_parser.py`
- **Features**: Full transcript display, IPA-to-text conversion, audio playback

### #47 - Show English Text in Student Logs Instead of IPA
- **Implemented in**: `app/ui/components/conversation/message_display.py` (lines 443-455)
- **Features**: `display_history` extracts English text from formatted messages; live messages use `text` not IPA

## Action
Close all three issues using `gh issue close`.
