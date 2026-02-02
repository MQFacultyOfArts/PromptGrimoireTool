# Plan: Pass Conversation Context to ASR

## Goal
Improve ASR transcription accuracy by providing the last teacher message, so Gemini knows what the student is responding to.

## Current State
- ASR is called in `lesson.py` line 628 with only audio and optional `system_prompt`
- `session_manager.session.state.conversation_history` contains all messages
- Each message is `{"role": "assistant"|"user"|..., "content": str}`

## Approach
Append the last teacher message to the existing `system_prompt` parameter - no changes to `asr_service.py` needed.

### Context to include:
- **Last teacher message only** - what the student is responding to

This avoids biasing the ASR toward specific vocabulary words while still providing helpful context.

### Format:
```
<context>
Teacher just said: Can you say the word "environment"?
</context>
```

## Implementation

### File: `examples/example9_audio_pipeline/pages/lesson.py`

**1. Add helper function** (around line 165, after `get_asr_prompt_for_session`):

```python
def build_asr_context(session_manager: LessonSessionManager) -> str:
    """Build minimal context for ASR: last teacher message."""
    if not session_manager.session or not session_manager.session.state:
        return ""

    state = session_manager.session.state

    # Get last teacher message
    for msg in reversed(state.conversation_history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if len(content) > 300:
                content = content[:300] + "..."
            return f"<context>\nTeacher just said: {content}\n</context>"

    return ""
```

**2. Modify `handle_recording_complete`** (around line 628):

```python
# Build context-enhanced system prompt
context = build_asr_context(session_manager)
enhanced_prompt = asr_system_prompt or ""
if context:
    enhanced_prompt = f"{enhanced_prompt}\n\n{context}" if enhanced_prompt else context

result = await asr_service.transcribe_audio(
    audio_bytes,
    mime_type=mime_type,
    get_both_formats=True,
    system_prompt=enhanced_prompt if enhanced_prompt else None,
)
```

## Files Modified

- `examples/example9_audio_pipeline/pages/lesson.py` (~20 lines added/changed)

## Verification

1. Run the app and start a lesson
2. Check Logfire traces to see the ASR system prompt includes the context
3. Verify transcription still works correctly
