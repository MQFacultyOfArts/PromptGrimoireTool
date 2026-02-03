# Fix: ASR Returning Only One Word Instead of Full Sentence

## Problem

When a student says "predators are animals that hunt and eat other animals", the ASR is only returning "predators" as the transcription.

## Root Cause

The `asr_system_prompt` in **[lesson_plan.json](lesson_plans/test_student/lesson_plan.json):10** contains:

```
"Render the text output with phonetic spelling, rather than trying to create accurate words."
```

This tells Gemini to extract vocabulary words rather than transcribe verbatim.

## Change Required

**File**: `lesson_plans/test_student/lesson_plan.json` line 10

**Current** (problematic):
```json
"asr_system_prompt": "Transcribe the user's audio into normal_transcription.\n\nFor ipa_transcription: Provide an IPA transcription of the ACTUAL SOUNDS the speaker produced - not the dictionary/standard pronunciation of the words. Capture their exact pronunciation including any accent, mispronunciation, unusual stress patterns, or non-standard speech. The IPA should reflect what was acoustically present in the audio, not what the words \"should\" sound like. Render the text output with phonetic spelling, rather than trying to create accurate words."
```

**Replace with**:
```json
"asr_system_prompt": "Transcribe the user's audio into normal_transcription.\n\nFor normal_transcription: Transcribe EXACTLY what the speaker says, word for word. Include all words spoken, not just vocabulary words. Do not summarize or extract keywords.\n\nFor ipa_transcription: Provide an IPA transcription of the ACTUAL SOUNDS the speaker produced - not the dictionary/standard pronunciation of the words. Capture their exact pronunciation including any accent, mispronunciation, unusual stress patterns, or non-standard speech. The IPA should reflect what was acoustically present in the audio, not what the words \"should\" sound like."
```

## Key Changes

1. **Removed**: "Render the text output with phonetic spelling, rather than trying to create accurate words."
2. **Added**: Explicit instruction for `normal_transcription` to transcribe verbatim

## Verification

1. Run the app, go to a lesson
2. Say a full sentence like "Predators are animals that hunt and eat other animals"
3. Check transcript shows the full sentence
4. Confirm in Logfire that `normal_transcription` contains complete spoken text
