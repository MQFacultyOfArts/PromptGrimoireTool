# Speaker Profile Management Plan

## Goal

Add speaker profile creation and matching using pyannote embeddings:
1. After diarization, let user label speakers (SPEAKER_00 → "Brian")
2. Extract embeddings from labeled segments → save as profiles
3. Future meetings: auto-match speakers against saved profiles
4. **Uncertain matches stay as SPEAKER_XX** (don't guess wrong)

## Architecture

### New Module: `src/meeting_transcriber/speaker_profiles/`

```
speaker_profiles/
├── __init__.py
├── extractor.py      # SpeakerEmbeddingExtractor - wraps pyannote/embedding
├── manager.py        # ProfileManager - load/save/list profiles
└── matcher.py        # ProfileMatcher - cosine similarity matching
```

### Storage Structure

```
speaker_profiles/                    # Global profile database
├── profiles.json                    # Index of all profiles
├── brian/
│   ├── profile.json                 # Metadata + settings
│   └── embedding.npy                # 512-dim average embedding
├── jodie/
│   └── ...
```

## Implementation Steps

### Step 1: SpeakerEmbeddingExtractor

**File:** `src/meeting_transcriber/speaker_profiles/extractor.py`

```python
from pyannote.audio import Inference

class SpeakerEmbeddingExtractor:
    """Extract 512-dim speaker embeddings using pyannote."""

    def __init__(self, model_name="pyannote/embedding", use_gpu=True):
        self._inference = None
        self._loaded = False

    def load_model(self): ...
    def unload_model(self): ...

    def extract_from_segment(self, audio_path: Path, start: float, end: float) -> np.ndarray:
        """Extract embedding from audio segment by timestamps."""
        ...

    def extract_from_segments(self, audio_path: Path, segments: list[DiarizationSegment]) -> np.ndarray:
        """Extract and average embeddings from multiple segments."""
        embeddings = [self.extract_from_segment(audio_path, s.start, s.end) for s in segments]
        return np.mean(embeddings, axis=0)  # Average for robustness
```

### Step 2: ProfileManager

**File:** `src/meeting_transcriber/speaker_profiles/manager.py`

```python
@dataclass
class SpeakerProfile:
    name: str                    # "brian"
    display_name: str            # "Brian Ballsun-Stanton"
    embedding: np.ndarray        # 512-dim vector
    created_at: datetime
    segment_count: int           # How many segments trained on
    source_sessions: list[str]   # Which recordings contributed

class ProfileManager:
    def __init__(self, profiles_dir: Path): ...

    def list_profiles(self) -> list[SpeakerProfile]: ...
    def get_profile(self, name: str) -> SpeakerProfile | None: ...
    def save_profile(self, profile: SpeakerProfile): ...
    def delete_profile(self, name: str): ...

    def create_profile_from_segments(
        self,
        name: str,
        display_name: str,
        audio_path: Path,
        segments: list[DiarizationSegment],
        extractor: SpeakerEmbeddingExtractor,
    ) -> SpeakerProfile:
        """Create profile from diarized segments."""
        ...
```

### Step 3: ProfileMatcher

**File:** `src/meeting_transcriber/speaker_profiles/matcher.py`

```python
class ProfileMatcher:
    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold  # Below this, keep SPEAKER_XX

    def match_speaker(
        self,
        embedding: np.ndarray,
        profiles: list[SpeakerProfile],
    ) -> tuple[str | None, float]:
        """Match embedding against profiles.

        Returns:
            (matched_name, confidence) or (None, best_score) if below threshold
        """
        best_match = None
        best_score = 0.0

        for profile in profiles:
            score = cosine_similarity(embedding, profile.embedding)
            if score > best_score:
                best_score = score
                best_match = profile.display_name

        if best_score >= self.threshold:
            return (best_match, best_score)
        return (None, best_score)  # Uncertain - keep original label
```

### Step 4: Config Addition

**File:** `src/meeting_transcriber/config.py`

```python
@dataclass
class SpeakerProfileConfig:
    profiles_dir: Path = field(default_factory=lambda: Path("speaker_profiles"))
    embedding_model: str = "pyannote/embedding"
    match_threshold: float = 0.7  # Below this, mark as uncertain
    min_segment_duration: float = 2.0  # Minimum seconds for reliable embedding
    use_gpu: bool = True
```

### Step 5: GUI Integration

**File:** `src/meeting_transcriber/gui/app.py`

Add to UI after speaker rename section:

```python
# Profile Creation Section
gr.Markdown("### Create Speaker Profiles")
gr.Markdown("Label speakers below to save their voice profiles for future recognition.")

with gr.Row():
    profile_speaker_dropdown = gr.Dropdown(
        choices=[],  # Populated after diarization: [("SPEAKER_00 (5 segments)", "SPEAKER_00"), ...]
        label="Select Speaker to Profile",
    )
    profile_name_input = gr.Textbox(
        label="Profile Name",
        placeholder="e.g., brian",
    )
    profile_display_name = gr.Textbox(
        label="Display Name",
        placeholder="e.g., Brian Ballsun-Stanton",
    )

create_profile_btn = gr.Button("Create Profile from This Speaker")
profile_status = gr.Textbox(label="Profile Status", interactive=False)
```

**New function in app.py:**

```python
def create_speaker_profile(speaker_id: str, name: str, display_name: str):
    """Create profile from diarized speaker segments."""
    if not speaker_id or not name:
        return "Please select a speaker and enter a name"

    # Get segments for this speaker from current diarization
    speaker_segments = [s for s in state.current_diarization if s.speaker == speaker_id]

    if len(speaker_segments) < 3:
        return f"Need at least 3 segments, found {len(speaker_segments)}"

    # Filter by minimum duration
    valid_segments = [s for s in speaker_segments if (s.end - s.start) >= 2.0]

    profile = state.profile_manager.create_profile_from_segments(
        name=name,
        display_name=display_name or name,
        audio_path=state.session_dir / "audio.opus",
        segments=valid_segments,
        extractor=state.embedding_extractor,
    )

    return f"Created profile '{display_name}' from {len(valid_segments)} segments"
```

### Step 6: Auto-Matching in end_meeting()

Add after diarization completes:

```python
# === PHASE 6.5: Match speakers to profiles ===
if diarization_succeeded and state.profile_manager:
    progress(0.55, desc="Matching speakers to profiles...")
    profiles = state.profile_manager.list_profiles()

    if profiles:
        # Get unique speakers from diarization
        unique_speakers = set(s.speaker for s in diarization)

        for speaker_id in unique_speakers:
            # Get segments for this speaker
            speaker_segs = [s for s in diarization if s.speaker == speaker_id]
            valid_segs = [s for s in speaker_segs if (s.end - s.start) >= 2.0]

            if valid_segs:
                # Extract embedding
                embedding = state.embedding_extractor.extract_from_segments(
                    audio_path, valid_segs
                )

                # Match against profiles
                matched_name, confidence = state.profile_matcher.match_speaker(
                    embedding, profiles
                )

                if matched_name:
                    state.speaker_names[speaker_id] = matched_name
                    logger.info(f"Matched {speaker_id} → {matched_name} ({confidence:.2f})")
                else:
                    # Keep original label - uncertain match
                    logger.info(f"No confident match for {speaker_id} (best: {confidence:.2f})")
```

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/meeting_transcriber/speaker_profiles/__init__.py` | Create |
| `src/meeting_transcriber/speaker_profiles/extractor.py` | Create |
| `src/meeting_transcriber/speaker_profiles/manager.py` | Create |
| `src/meeting_transcriber/speaker_profiles/matcher.py` | Create |
| `src/meeting_transcriber/config.py` | Add `SpeakerProfileConfig` |
| `src/meeting_transcriber/gui/app.py` | Add profile UI, auto-matching, state fields |

## Key Design Decisions

1. **Threshold-based matching** - Below 0.7 cosine similarity, keep SPEAKER_XX (don't guess)
2. **Minimum segment duration** - 2 seconds minimum for reliable embeddings
3. **Average embeddings** - Multiple segments averaged for robustness
4. **Separate from diarization** - Embedding extraction is optional, diarization still works without it
5. **VRAM management** - Unload embedding model after use (like diarizer)

## Verification

1. **Profile creation**: Record meeting, label SPEAKER_00 as "Brian", verify profile saved
2. **Profile matching**: New recording, verify "Brian" auto-recognized (if confident)
3. **Uncertain handling**: New unknown speaker stays as SPEAKER_XX
4. **Threshold tuning**: Adjust 0.7 threshold based on real-world testing
