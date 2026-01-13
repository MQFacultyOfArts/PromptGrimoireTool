---
source: https://code.claude.com/docs/en/skills
fetched: 2025-01-13
library: claude-code
summary: How to create and configure Claude Code skills (markdown files that teach Claude specialized knowledge)
---

# Claude Code Skills

Skills are markdown files that teach Claude specialized knowledge about how to accomplish specific tasks. They extend Claude's capabilities by encoding domain-specific instructions, standards, or patterns.

## What Skills Are

When your request matches a Skill's purpose, Claude automatically applies it. Skills are stored as `SKILL.md` files in specific directories.

## How to Create Them

1. **Create a directory** for your Skill
2. **Write a `SKILL.md` file** with YAML metadata and markdown instructions
3. **Skills load automatically** when created or modified

Example structure:

```
~/.claude/skills/explaining-code/
└── SKILL.md
```

## File Format

Skills use a simple markdown format with YAML frontmatter:

```yaml
---
name: skill-name
description: What the Skill does and when to use it
---

# Skill Instructions

Clear, step-by-step guidance for Claude...
```

### Required fields

- `name` - Lowercase letters, numbers, hyphens only (max 64 chars)
- `description` - What it does and when to use it (max 1024 chars). This is critical—Claude uses it to decide when to apply the Skill

### Optional fields

- `allowed-tools` - Restrict which tools Claude can use (e.g., `Read, Grep, Glob`)
- `model` - Specific Claude model to use
- `context: fork` - Run in isolated sub-agent context
- `hooks` - Define lifecycle hooks (PreToolUse, PostToolUse, Stop)
- `user-invocable: false` - Hide from slash menu but Claude can still use it

## Where Skills Are Stored

Storage location determines scope:

| Location   | Path                    | Access Level              |
|:-----------|:------------------------|:--------------------------|
| Personal   | `~/.claude/skills/`     | You, all projects         |
| Project    | `.claude/skills/`       | Your team in this repo    |
| Plugin     | Bundled with plugins    | Anyone with plugin        |
| Enterprise | Managed by admin        | Entire organization       |

## How Skills Are Triggered

**Model-invoked**: Claude decides when to use them automatically based on your request:

1. **Discovery** - Claude loads Skill names and descriptions at startup
2. **Activation** - When your request matches a Skill's description, Claude asks permission
3. **Execution** - Claude follows the Skill's instructions

You can also manually invoke with `/skill-name` or programmatically via the `Skill` tool.

## Tips

- Write detailed descriptions with trigger keywords users would naturally say
- Vague descriptions like "helps with documents" won't trigger reliably
- Keep `SKILL.md` under 500 lines; put detailed docs in supporting files
- Include utility scripts that execute without consuming context tokens
