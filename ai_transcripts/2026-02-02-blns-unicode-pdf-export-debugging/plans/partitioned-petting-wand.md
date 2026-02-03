# ABC Recording Form - Claude Code Skill Implementation Plan

## Overview

Create a Claude Code skill that:
1. Reads a PDF template (ABC Recording Form from NSW Department of Education)
2. Conducts interactive Q&A asking one question at a time
3. Provides a readback for user confirmation
4. Generates a filled Word document (and optionally PDF)

## Required Skills/Dependencies

### Python Libraries (add to pyproject.toml)
```toml
dependencies = [
    "python-docx>=1.1.0",    # Word document generation
    "pypdf>=4.0.0",          # PDF reading (to extract template structure)
]
```

### Claude Code Skill Structure
```
.claude/
└── skills/
    └── abc-form/
        ├── SKILL.md              # Skill definition with Q&A flow
        └── scripts/
            └── generate_docx.py  # Word document generator
```

## Implementation Steps

### Step 1: Update pyproject.toml
Add `python-docx` and `pypdf` dependencies.

### Step 2: Create Skill Directory Structure
```bash
mkdir -p .claude/skills/abc-form/scripts
```

### Step 3: Create SKILL.md
The skill file instructs Claude to:
- Introduce the ABC form purpose
- Ask questions ONE AT A TIME in sequence:
  1. Child's name
  2. Focus behaviour
  3. Educator(s) name(s)
  4. For each observation: Date/Time, Setting/Context, Antecedent, Behaviour, Consequence
  5. "Add another observation?" loop
- Provide formatted readback for confirmation
- Generate filled document on confirmation

### Step 4: Create generate_docx.py
Python script that:
- Accepts JSON data via stdin or file
- Creates Word document matching NSW Education template structure:
  - Header with NSW Department of Education branding
  - Title: "Antecedent, Behaviour, Consequences (ABC) recording"
  - Explanatory paragraphs
  - Header table (Child's name, Focus behaviour, Educator names)
  - Observations table with 5 columns
- Uses proper styling (NSW blue #002664 for headings)

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| [pyproject.toml](pyproject.toml) | Modify | Add python-docx, pypdf dependencies |
| .claude/skills/abc-form/SKILL.md | Create | Skill definition with interview flow |
| .claude/skills/abc-form/scripts/generate_docx.py | Create | Word document generator |

## Data Structure

```json
{
  "child_name": "string",
  "focus_behaviour": "string",
  "educator_names": "string",
  "observations": [
    {
      "date_time": "string",
      "setting_context": "string",
      "antecedent": "string",
      "behaviour": "string",
      "consequence": "string"
    }
  ]
}
```

## Verification

1. **Test skill invocation**: Run `/abc-form` in Claude Code
2. **Complete Q&A flow**: Answer all questions through the interview
3. **Check readback**: Verify summary is accurate
4. **Verify output**: Open generated .docx and compare to original template
5. **Test multi-row**: Add 3+ observations to verify table expands correctly
