# AISummercamp Transcription Pipeline Plan

## Summary of Investigation

### 1. What .zprj Files Are
**NOT CLO 3D or Marvelous Designer files** - they are **Zoom H8 portable recorder project directories**.

Each `.zprj` directory contains:
- `.h8prj` - Zoom H8 project metadata file (header: "ZOOM H8 ProjectFile v001")
- `TrA.mp3` - Main track audio (stereo mix or Track A)
- `Mic12.mp3` - Microphone channels 1+2 combined
- `Mic12_BU.mp3` - Backup of mic channels

The MP3 files are already extracted audio - **no conversion needed**. They're 48kHz mono MP3s encoded by the H8.

**Week 2 recordings:**
- `F190925_001.zprj/TrA.mp3` - 2h43m recording (~150MB)
- `F190925_002.zprj/TrA.mp3` - ~1h recording (~63MB)

### 2. Transcription Infrastructure
Located at `/home/brian/people/Jodie/ai-literacy-training-phase-1`

**Command:** `uv run process-recording <audio_file> [-o output_dir]`

**Pipeline:**
1. Loads audio, resamples to 16kHz mono
2. Segments into 30-second overlapping chunks
3. Transcribes via IBM Granite Speech 3.3 8B
4. Diarizes speakers via pyannote
5. Aligns transcripts with speaker labels
6. Outputs: `transcript.json`, `transcript.txt`, `full_audio.wav`

**Optional cleanup:** Uses local Ollama with qwen2.5 (if running) to remove filler words/artifacts.

### 3. Student's Work on Remote
Remote: `kisummercamp:` contains organized structure with:
- Summaries (day0-day5.txt) - AI-generated topic summaries
- ReadMe_Week1.md - Content assessment and editing notes
- Day folders with renamed/organized videos
- Transcript docx for Day 1

**Key new content not in local:**
- Summary/*.txt files
- ReadMe_Week1.md
- OBS/Day 1-5 subfolders with organized MP4s
- Transcript Day One Course 2025.docx

---

## Implementation Plan

### Task 1: Sync Student's Work (rclone)
Pull down organized content without clobbering raw files:

```bash
# Sync only the new organized content (summaries, readme, transcripts)
rclone copy "kisummercamp:Raw Video/AI Week Raw/Week 1/Summary" \
    "/home/brian/people/Brian/AISummercamp/AI Week Raw/Week 1/Summary"

rclone copy "kisummercamp:Raw Video/AI Week Raw/Week 1/ReadMe_Week1.md" \
    "/home/brian/people/Brian/AISummercamp/AI Week Raw/Week 1/"

# Optionally sync the Day folders (contains renamed/converted versions)
rclone copy "kisummercamp:Raw Video/AI Week Raw/Week 1/OBS/Day 1" \
    "/home/brian/people/Brian/AISummercamp/AI Week Raw/Week 1/OBS/Day 1"
# (repeat for Day 2-5)
```

### Task 2: Create Transcript Directory Structure
Mirror source hierarchy:
```
AISummercamp/
├── transcripts/
│   ├── Week 1/
│   │   ├── OBS/
│   │   │   ├── 2025-09-08_09-14-22/
│   │   │   │   ├── transcript.json
│   │   │   │   └── transcript.txt
│   │   │   └── ...
│   │   └── Screen Records/
│   └── Week 2/
│       ├── F190925_001/
│       └── F190925_002/
└── Opener Raw/
```

### Task 3: Batch Transcription Script
Create script to process all recordings:

```bash
#!/bin/bash
# process-all-recordings.sh

INFRA_DIR="/home/brian/people/Jodie/ai-literacy-training-phase-1"
SOURCE_DIR="/home/brian/people/Brian/AISummercamp"
OUTPUT_BASE="$SOURCE_DIR/transcripts"

# Week 1 OBS recordings (MKV)
for f in "$SOURCE_DIR/AI Week Raw/Week 1/OBS/"*.mkv; do
    basename=$(basename "$f" .mkv)
    outdir="$OUTPUT_BASE/Week 1/OBS/$basename"
    mkdir -p "$outdir"
    cd "$INFRA_DIR" && uv run process-recording "$f" -o "$outdir"
done

# Week 1 Screen Records (MP4)
for f in "$SOURCE_DIR/AI Week Raw/Week 1/Screen Records/"*.mp4; do
    basename=$(basename "$f" .mp4)
    outdir="$OUTPUT_BASE/Week 1/Screen Records/$basename"
    mkdir -p "$outdir"
    cd "$INFRA_DIR" && uv run process-recording "$f" -o "$outdir"
done

# Week 2 Zoom H8 recordings (already MP3, use TrA.mp3)
for zprj in "$SOURCE_DIR/AI Week Raw/Week 2/"*.zprj; do
    basename=$(basename "$zprj" .zprj)
    outdir="$OUTPUT_BASE/Week 2/$basename"
    mkdir -p "$outdir"
    cd "$INFRA_DIR" && uv run process-recording "$zprj/TrA.mp3" -o "$outdir"
done

# Opener
for f in "$SOURCE_DIR/Opener Raw/"*.mkv; do
    basename=$(basename "$f" .mkv)
    outdir="$OUTPUT_BASE/Opener/$basename"
    mkdir -p "$outdir"
    cd "$INFRA_DIR" && uv run process-recording "$f" -o "$outdir"
done
```

### Task 4: Post-Processing with Qwen 2.5
The transcription infra already has optional Ollama cleanup built-in. Ensure Ollama is running with qwen2.5:

```bash
# Start Ollama if not running
ollama serve &

# Pull model if needed
ollama pull qwen2.5:7b

# The process-recording tool will auto-detect and use it
```

If you want additional cleanup beyond the built-in:
```bash
# Manual cleanup pass on transcript.txt files
for txt in "$OUTPUT_BASE"/**/transcript.txt; do
    ollama run qwen2.5:7b "Clean up this transcript by removing filler words, repeated phrases, and obvious speech artifacts. Preserve the speaker labels and timestamps. Do not change the meaning or correct mishearings:\n\n$(cat "$txt")" > "${txt%.txt}_cleaned.txt"
done
```

---

## Files to Process

| Location | Files | Format | Duration Est. |
|----------|-------|--------|---------------|
| Week 1/OBS | 12 MKV files | Video+Audio | ~18GB total |
| Week 1/Screen Records | 6 MP4 files | Video+Audio | ~7.8GB total |
| Week 2/F190925_001.zprj | TrA.mp3 | Audio only | 2h43m |
| Week 2/F190925_002.zprj | TrA.mp3 | Audio only | ~1h |
| Opener Raw | 1 MKV file | Video+Audio | ~1.4GB |

---

## Verification Steps

1. **After rclone sync:** Check that Summary folder and ReadMe exist locally
2. **After transcription:** Verify each output folder has transcript.json and transcript.txt
3. **Spot-check accuracy:** Compare a few transcript segments against the actual audio
4. **Check speaker diarization:** Verify speaker labels make sense in multi-speaker recordings

---

## User Decisions (Resolved)

1. **Week 2 audio tracks:** Process ALL tracks (TrA.mp3, Mic12.mp3, Mic12_BU.mp3)
2. **Sync:** DONE - Day folders synced via rclone
3. **Execution:** Sequential (safer, one at a time)

---

## Execution Order

1. ~~Sync student's work from kisummercamp remote~~ DONE
2. Process Week 2 Zoom H8 recordings (all 3 tracks × 2 sessions = 6 transcriptions)
3. Process Week 1 OBS recordings (14 MKV files)
4. Process Week 1 Screen Records (6 MP4 files)
5. Process Opener Raw (1 MKV file)
6. Run Qwen 2.5 cleanup pass on all transcripts
