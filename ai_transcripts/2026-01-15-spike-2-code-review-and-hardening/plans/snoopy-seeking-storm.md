# Meeting Transcriber v2: Pause/Resume with Rounds

## Overview
Upgrade the existing meeting transcriber to support pause/resume workflow with consistent speaker diarization across rounds. Each "Pause & Process" creates a transcript chunk while maintaining speaker ID consistency.

## Current State
- Working: Granite Speech transcription, pyannote 4.x diarization, Gradio 6 UI
- Issue: Start/Stop creates separate sessions, no pause/resume, no round management

## New Architecture

### Workflow
1. **Start Meeting** → creates session, streams audio to `audio.opus`
2. **Pause & Process** → stops recording, runs cumulative diarization on full audio, transcribes new chunk, aligns, saves as Round N
3. **Resume** → continues appending to same opus file
4. **End Meeting** → final save, combines all rounds

### Key Design: Cumulative Diarization
- Each pause diarizes ALL audio from start (not just new chunk)
- Speaker IDs stay consistent because pyannote sees full context
- Trade-off: processing time grows with meeting length
- If too slow: user can "End Meeting" early, start new session

### Audio Format: Ogg Opus
- Crash-safe: each Ogg page is self-contained
- Survives program termination
- Good compression for speech
- `soundfile` supports streaming writes

## File Structure (per session)
```
meeting_transcripts/session_20260112_160000/
├── audio.opus              # Full meeting audio (streaming, crash-safe)
├── rounds/
│   ├── round_001.json      # {start, end, segments: [{speaker, start, end, text}]}
│   ├── round_001.txt       # Human-readable
│   ├── round_002.json
│   ├── round_002.txt
│   └── ...
├── transcript.json         # Combined final transcript
└── transcript.txt          # Full human-readable
```

## Implementation Changes

### 1. New StreamingAudioWriter (`audio/streaming_writer.py`)
```python
class StreamingAudioWriter:
    def __init__(self, path: Path, sample_rate: int = 16000):
        self._file = sf.SoundFile(path, mode='w', samplerate=sample_rate,
                                   channels=1, format='OGG', subtype='OPUS')
        self._samples_written = 0

    def write(self, audio: np.ndarray) -> None:
        self._file.write(audio)
        self._samples_written += len(audio)

    def close(self) -> None:
        self._file.close()

    @property
    def duration(self) -> float:
        return self._samples_written / self._sample_rate
```

### 2. Updated DualStreamRecorder (`audio/recorder.py`)
- Add `pause()` method: stops capture threads, keeps file handle open
- Add `resume()` method: restarts capture threads
- Track `_pause_time` for offset calculations
- Stream directly to `StreamingAudioWriter` instead of memory buffer

### 3. New RoundManager (`output/round_manager.py`)
```python
@dataclass
class Round:
    index: int
    start_time: float
    end_time: float
    segments: list[AlignedSegment]
    file_path: Path

class RoundManager:
    def __init__(self, session_dir: Path):
        self.rounds: list[Round] = []
        self._last_processed_time = 0.0

    def create_round(self, end_time: float, segments: list[AlignedSegment]) -> Round:
        # Filter segments to only those in this round's time range
        # Save to rounds/round_NNN.json and .txt
        # Return Round with absolute file path
```

### 4. Updated TranscriberState (`gui/app.py`)
```python
class TranscriberState:
    # ... existing ...

    # New fields
    audio_writer: StreamingAudioWriter | None = None
    round_manager: RoundManager | None = None
    is_paused: bool = False
    session_start_time: float = 0.0
    last_round_end_time: float = 0.0
```

### 5. Updated GUI (`gui/app.py`)
**New buttons:**
- "Start Meeting" (replaces "Start Recording")
- "Pause & Process" (new - runs diarization, creates round)
- "Resume" (new - continues recording)
- "End Meeting" (replaces "Stop Recording")

**New UI elements:**
- Round selector: tabs or dropdown `[Round 1] [Round 2] [Round 3]`
- Round display: shows selected round's transcript with timestamps
- Path display: shows absolute path to round file
- Copy button: copies current round's transcript

### 6. Pause & Process Logic
```python
def pause_and_process():
    # 1. Stop audio capture
    state.recorder.pause()
    current_time = state.audio_writer.duration

    # 2. Read full audio for diarization
    full_audio, sr = sf.read(state.session_dir / "audio.opus")

    # 3. Run diarization on FULL audio (cumulative)
    diarization = state.diarizer.diarize_array(full_audio, sr)

    # 4. Transcribe only NEW audio (since last pause)
    new_audio = full_audio[int(state.last_round_end_time * sr):]
    # ... segment and transcribe new_audio ...

    # 5. Align new transcriptions with full diarization
    # Filter diarization to segments in new time range

    # 6. Create round
    round = state.round_manager.create_round(current_time, aligned_segments)
    state.last_round_end_time = current_time

    # 7. Update UI with new round
    return round
```

## Files to Modify
- `src/meeting_transcriber/audio/recorder.py` - add pause/resume
- `src/meeting_transcriber/gui/app.py` - new UI, round management
- `src/meeting_transcriber/output/writer.py` - round file saving

## Files to Create
- `src/meeting_transcriber/audio/streaming_writer.py` - Ogg Opus streaming
- `src/meeting_transcriber/output/round_manager.py` - round tracking

## Optional: Transcript Cleanup via Ollama

### Purpose
Clean up speech artifacts without changing meaning:
- Remove repeated words ("the the" → "the")
- Remove filler sounds ("um", "uh", "like", "you know")
- Fix punctuation and capitalization
- **Do NOT correct mishearings** - preserve what was actually said

### Config
```python
@dataclass
class CleanupConfig:
    enabled: bool = True
    ollama_model: str = "qwen2.5:7b"
    ollama_host: str = "http://localhost:11434"
```

### New File: `transcription/cleanup.py`
```python
class OllamaCleanup:
    PROMPT = """Clean up this transcript. Remove:
- Repeated words (e.g., "the the" → "the")
- Filler sounds (um, uh, like, you know)
- Fix punctuation and capitalization

Do NOT correct mishearings - keep the exact words spoken.
Do NOT summarize or paraphrase.

Transcript:
{text}

Cleaned transcript:"""

    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host

    def cleanup(self, text: str) -> str:
        # Call Ollama API
        response = requests.post(
            f"{self.host}/api/generate",
            json={"model": self.model, "prompt": self.PROMPT.format(text=text), "stream": False}
        )
        return response.json()["response"].strip()
```

### Flow Integration
```
Granite transcribes → raw text
    ↓
Ollama cleans up → polished text (if enabled)
    ↓
Align with speakers → final output
```

## Files to Update
- `src/meeting_transcriber/config.py` - remove Canary 40s limit warning, add CleanupConfig

## Verification
1. `uv run meeting-transcriber`
2. Load models
3. Select mic + system audio
4. Click "Start Meeting"
5. Record for ~1 minute, click "Pause & Process"
6. Verify Round 1 appears with speaker labels
7. Click "Resume", record more
8. Click "Pause & Process" again
9. Verify Round 2 has consistent speaker IDs with Round 1
10. Check absolute paths are displayed and files exist
11. Click "End Meeting"
12. Check `meeting_transcripts/session_*/` for all files
