# Claude Code Plugin & MCP Checklist

**Last updated:** 2026-01-30
**Purpose:** Ensure consistent Claude Code setup across machines

## Required Plugins (user scope)

Check these are enabled in `~/.claude/settings.json` under `enabledPlugins`:

### denubis-plugins (workflow - REQUIRED)

| Plugin | Enabled | Notes |
|--------|---------|-------|
| `denubis-00-getting-started@denubis-plugins` | `true` | README and intro |
| `denubis-hook-skill-reinforcement@denubis-plugins` | `true` | Skill reminder hooks |
| `denubis-basic-agents@denubis-plugins` | `true` | Generic subagents |
| `denubis-research-agents@denubis-plugins` | `true` | Internet/codebase research |
| `denubis-extending-claude@denubis-plugins` | `true` | Skills, transcripts |
| `denubis-hook-claudemd-reminder@denubis-plugins` | `true` | CLAUDE.md context |
| `denubis-plan-and-execute@denubis-plugins` | `true` | Design/implementation workflow |
| `denubis-hook-shortcut-detection@denubis-plugins` | `true` | Slash command detection |

### claude-plugins-official (tools - REQUIRED)

| Plugin | Enabled | Notes |
|--------|---------|-------|
| `context7@claude-plugins-official` | `true` | Library docs lookup |
| `playwright@claude-plugins-official` | `true` | Browser automation MCP |
| `serena@claude-plugins-official` | `true` | Semantic code nav MCP |
| `pr-review-toolkit@claude-plugins-official` | `true` | PR review agents |
| `code-review@claude-plugins-official` | `true` | Code review |
| `commit-commands@claude-plugins-official` | `true` | Git helpers |
| `hookify@claude-plugins-official` | `true` | Hook management |
| `claude-md-management@claude-plugins-official` | `true` | CLAUDE.md tools |
| `claude-code-setup@claude-plugins-official` | `true` | Setup recommendations |
| `feature-dev@claude-plugins-official` | `true` | Feature development |
| `code-simplifier@claude-plugins-official` | `true` | Code cleanup |
| `frontend-design@claude-plugins-official` | `true` | UI generation |

### Disabled (by choice)

| Plugin | Enabled | Reason |
|--------|---------|--------|
| `github@claude-plugins-official` | `false` | Using gh CLI instead |
| `agent-sdk-dev@claude-plugins-official` | `false` | Not building SDK agents |
| `greptile@claude-plugins-official` | `false` | Not using Greptile |
| `linear@claude-plugins-official` | `false` | Not using Linear |
| `pyright-lsp@claude-plugins-official` | `true` | Optional - LSP support |
| `security-guidance@claude-plugins-official` | `true` | Optional - security tips |

## Global Settings

In `~/.claude/settings.json`:

```json
{
  "enabledPlugins": { ... },
  "alwaysThinkingEnabled": true
}
```

## Project-Level Settings

In `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{ "type": "command", "command": "...", "timeout": 120 }]
      }
    ],
    "Stop": [...]
  }
}
```

## Verification Script

Run this to compare your setup against this checklist:

```bash
# Show enabled plugins
cat ~/.claude/settings.json | jq '.enabledPlugins | to_entries | map(select(.value == true)) | .[].key' | sort

# Show disabled plugins
cat ~/.claude/settings.json | jq '.enabledPlugins | to_entries | map(select(.value == false)) | .[].key' | sort

# Check installed plugin versions
cat ~/.claude/plugins/installed_plugins.json | jq '.plugins | keys'
```

## Sync Procedure

When setting up a new machine or syncing:

1. Export settings from working machine:
   ```bash
   cp ~/.claude/settings.json ~/claude-settings-backup.json
   ```

2. On new machine, restore:
   ```bash
   cp ~/claude-settings-backup.json ~/.claude/settings.json
   ```

3. Install plugins (Claude Code will auto-install on first run if in settings)

4. Verify with commands above

## MCP Servers

MCP servers are provided by plugins. Current active MCPs:

| MCP | Plugin | Purpose |
|-----|--------|---------|
| `plugin:serena:serena` | serena | Semantic code navigation |
| `plugin:playwright:playwright` | playwright | Browser automation |
| `plugin:context7:context7` | context7 | Library documentation |

## Troubleshooting

**Plugin not loading:**
1. Check `~/.claude/settings.json` has it enabled
2. Check `~/.claude/plugins/installed_plugins.json` has it installed
3. Try: `/plugins update`

**MCP not available:**
1. Check plugin providing MCP is enabled
2. Restart Claude Code
3. Check `~/.claude/plugins/cache/` for the plugin

**Hooks not firing:**
1. Check `.claude/settings.json` in project root
2. Verify hook scripts are executable
3. Check `$CLAUDE_PROJECT_DIR` is set correctly
