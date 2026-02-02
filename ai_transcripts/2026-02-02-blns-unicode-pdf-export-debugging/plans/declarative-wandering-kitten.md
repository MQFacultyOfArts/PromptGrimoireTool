# dailyStandup Implementation Plan

## Overview

Two parallel deliverables:
1. **brian-python-template** - Reusable copier template extracted from PromptGrimoire patterns
2. **dailyStandup** - Personal task/standup system using the template

---

## Part 1: brian-python-template (copier)

### What gets templated

From PromptGrimoire, extract:

| File | Purpose |
|------|---------|
| `pyproject.toml` | uv config, ruff rules, pytest config, coverage settings |
| `.pre-commit-config.yaml` | ruff-check, ruff-format, ty-check hooks |
| `.python-version` | Pin to 3.14 |
| `.gitignore` | Python/uv patterns |
| `src/{{ project_name }}/__init__.py` | Package stub |
| `src/{{ project_name }}/__main__.py` | Entry point |
| `tests/conftest.py` | Pytest fixtures |
| `tests/unit/test_env_vars.py` | Environment variable sync test |
| `.env.example` | Template for required env vars |
| `CLAUDE.md` | Project context for Claude Code |
| `.claude/settings.json` | Claude Code hooks |

### Template variables

```yaml
project_name: "myproject"
description: "A short description"
author_name: "Brian Ballsun-Stanton"
author_email: "brian@example.com"
python_version: "3.14"
```

### Template structure

```
brian-python-template/
├── copier.yaml              # Template config and questions
├── {{ project_name }}/      # Generated project root
│   ├── pyproject.toml.jinja
│   ├── .pre-commit-config.yaml
│   ├── .python-version
│   ├── .gitignore
│   ├── .env.example
│   ├── CLAUDE.md.jinja
│   ├── README.md.jinja
│   ├── .claude/
│   │   └── settings.json
│   ├── src/
│   │   └── {{ project_name }}/
│   │       ├── __init__.py
│   │       └── __main__.py
│   └── tests/
│       ├── conftest.py
│       └── unit/
│           └── test_env_vars.py.jinja
└── README.md                # Template documentation
```

---

## Part 2: dailyStandup Application

### Core Requirements

1. **Structured standup check-in** via Claude Code chat
2. **Data sources**: Asana API, Outlook email (Selenium), CalDAV calendars, meeting transcripts
3. **Encryption**: YubiKey-backed (GPG or age) for sensitive data at rest
4. **Sync**: Git-based with encrypted blobs (GitHub repo as source of truth)
5. **Skills architecture**: Claude Code skills for different workflows

### Pain points being solved

- Cognitive fatigue from mental task tracking
- Reactive urgency-driven work vs importance-driven
- No evidence trail for academic promotion
- No visibility into actual capacity/time allocation

### Data Architecture

```
dailyStandup/
├── data/                    # Git-tracked, encrypted
│   ├── tasks/               # Task state (Asana-synced + local)
│   ├── emails/              # Encrypted email summaries
│   ├── calendar/            # Calendar event cache
│   ├── transcripts/         # Meeting transcript summaries
│   └── standups/            # Historical standup logs
├── config/                  # Not encrypted
│   ├── sources.yaml         # Data source configuration
│   └── categories.yaml      # Work categorization schema
└── .secrets/                # .gitignored, local-only
    ├── cookies/             # Selenium session cookies
    └── tokens/              # API tokens (backup)
```

### Encryption Strategy

**Tool: age + age-plugin-yubikey**
- Simple CLI, no GPG complexity
- Uses YubiKey PIV slot (not OpenPGP)
- `age -e -R recipient.pub -o file.age file` (encrypt)
- `age -d -i yubikey-identity.txt file.age` (decrypt, requires touch)

**Setup workflow:**
1. Install: `brew install age` / `apt install age` + `age-plugin-yubikey`
2. Generate identity: `age-plugin-yubikey` (creates identity tied to YubiKey)
3. Export public key: commit to repo for encryption
4. Decrypt requires physical YubiKey presence

### Data Source Integrations

#### 1. Asana API (deferred - spike later)

- Python SDK: `asana` package
- OAuth or Personal Access Token
- Read tasks, projects, due dates
- Write: Update task status, add comments from standup notes

#### 2. Outlook Email (Playwright)
- Playwright (not Selenium - better async support, matches PromptGrimoire)
- Persistent browser context with saved cookies
- Extract: sender, subject, date, snippet
- Store encrypted summaries, not full content

#### 3. Calendars

- Personal calendar: CalDAV via `caldav` Python package
- Work calendar: ICS feed (available, no auth issues)

#### 4. Meeting Transcripts
- Drop files into `data/transcripts/`
- Parse various formats (Teams VTT, Otter.ai, plain text)
- Extract action items, decisions, commitments

### Claude Code Skills (MVP)

#### `/standup` - Daily check-in
```
1. Load current task state from all sources
2. Walk through each project/area
3. For each: status update, blockers, next actions
4. Capture new commitments
5. Update Asana with standup notes
6. Log standup to history
```

#### `/ingest` - Pull fresh data
```
1. Sync Asana tasks
2. Pull recent emails via Playwright
3. Fetch calendar events
4. Encrypt and store
```

#### `/review [period]` - Query history
```
- "What did I do last week?"
- "What did I promise Sarah?"
- "Show me all blocked items"
```

---

## Implementation Phases (MVP)

**MVP Scope: Template + Encryption Infrastructure Only**

### Phase 1: Template Creation

1. Create `brian-python-template` directory (or separate repo)
2. Write `copier.yaml` with prompts for project_name, description, author
3. Extract and templatize from PromptGrimoire:
   - `pyproject.toml.jinja` (ruff, pytest, uv config)
   - `.pre-commit-config.yaml` (ruff-check, ruff-format, ty-check)
   - `.python-version`
   - `.gitignore`
   - `src/{{ project_name }}/` structure
   - `tests/` structure with env var sync test
   - `CLAUDE.md.jinja`
   - `.claude/settings.json` (hooks)
4. Test: `copier copy . /tmp/test-project && cd /tmp/test-project && uv sync && uv run pre-commit run --all-files`

### Phase 2: Initialize dailyStandup from Template

1. Run `copier copy brian-python-template ./dailyStandup`
2. Verify tooling: `uv sync`, pre-commit, pytest

### Phase 3: Encryption Infrastructure

1. Add `age` wrapper module (`src/dailystandup/crypto.py`)
2. Implement: `encrypt_file()`, `decrypt_file()`, `encrypt_string()`, `decrypt_string()`
3. YubiKey identity management (detect, prompt for setup)
4. Test encryption round-trip

### Phase 4: Data Schema

1. Define dataclasses for core entities:
   - `Task`, `Email`, `CalendarEvent`, `Transcript`, `StandupEntry`
2. JSON serialization/deserialization
3. Encrypted storage helpers

### Future Phases (not in MVP)

- Data source integrations (calendar, email, Asana)
- `/standup`, `/ingest`, `/review` skills
- Promotion reporting

---

## Verification

### Template verification
```bash
# Generate test project
copier copy ./brian-python-template /tmp/test-project

# Verify tooling works
cd /tmp/test-project
uv sync
uv run pre-commit run --all-files
uv run pytest
```

### dailyStandup verification
```bash
# Encryption round-trip
echo "test" | gpg --encrypt --armor | gpg --decrypt

# Asana connection
uv run python -c "import asana; print('OK')"

# Skill invocation
# In Claude Code: /ingest, /standup
```

---

## Decisions Made

- **Encryption**: age + age-plugin-yubikey (not GPG)
- **Asana**: Deferred to spike - evaluate Python SDK later
- **Work calendar**: ICS feed available
- **Template tool**: copier (supports updating existing projects)
