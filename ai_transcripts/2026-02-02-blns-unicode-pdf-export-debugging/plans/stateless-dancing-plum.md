# Appian Civil Wars Audiobook Infrastructure - Plan

## Overview
Build infrastructure for an audiobook of Appian's Civil Wars, Book 1, Sections 1-21: from the beginning through Tiberius Gracchus's death and immediate aftermath.

## Source Material
- **Source**: Loeb Classical Library translation (user-provided paste)
- **Scope**: Book 1, Sections 1-21
- **Content**: English translation only (no Greek)

## Content Structure
- **Introduction (Sections 1-6)**: Overview of Roman civil strife from Gracchus to Augustus
- **Chapter I (Sections 7-13)**: Land crisis, Tiberius Gracchus's agrarian law, deposing Octavius
- **Chapter II (Sections 14-17)**: Election crisis, riot on Capitol, death of Gracchus
- **Chapter III (Sections 18-21)**: Aftermath - land commission troubles, Scipio's death, reform stalled

## Implementation

### Step 1: Create file structure
```
docs/appian_civil_wars/book1_tiberius_gracchus.txt
```

### Step 2: Extract and clean English text
Remove from pasted content:
- Navigation/UI elements
- Greek text (all of it)
- Page numbers, DOI references, copyright notices
- Footnote markers (superscript numbers)

Keep:
- Section numbers (1, 2, 3... 21)
- Chapter headers
- Marginal date annotations (b.c. 133, etc.)
- Topic headers (e.g., "The Agrarian Law of Tiberius Gracchus")

### Step 3: Format for narration
- Clean paragraph structure
- Readable flow without academic apparatus

## File to Create
- `docs/appian_civil_wars/book1_tiberius_gracchus.txt`

## Verification
- Confirm sections 1-21 present
- No Greek text
- Readable for audio narration
