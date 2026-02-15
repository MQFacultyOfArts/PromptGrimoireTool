# Git Worktrees

*Last updated: 2026-02-15*

This project uses git worktrees for parallel feature development. Worktrees are located in `.worktrees/`.

## Worktree Setup

```bash
# Create a new worktree for a feature branch
git worktree add .worktrees/<branch-name> <branch-name>

# List all worktrees
git worktree list

# Remove a worktree when done
git worktree remove .worktrees/<branch-name>
```

## Serena Memory Management

Serena stores project memories in `.serena/memories/`. To ensure all worktrees share the same memories:

1. The main worktree (project root) holds the canonical memories directory
2. When creating a new worktree, symlink its memories to main:

```bash
# After creating a worktree, symlink memories to main
rm -rf .worktrees/<branch>/.serena/memories
ln -s /absolute/path/to/main/.serena/memories .worktrees/<branch>/.serena/memories
```

This ensures:
- All worktrees see the same project context
- Memory updates in any worktree are immediately visible to others
- No duplicate/divergent memories across branches

The `.serena/project.yml` uses `project_name: "PromptGrimoire"` (directory-based) rather than branch names for worktree compatibility.
