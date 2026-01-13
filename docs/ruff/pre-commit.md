---
source: https://docs.astral.sh/ruff/integrations/#pre-commit
fetched: 2025-01-13
library: ruff
summary: Pre-commit integration guide for Ruff linter and formatter
---

# Using Ruff with pre-commit

To run Ruff's linter and formatter (available as of Ruff v0.0.289) via pre-commit, add the following to your `.pre-commit-config.yaml`:

```yaml
repos:
- repo: https://github.com/astral-sh/ruff-pre-commit
  # Ruff version.
  rev: v0.14.11
  hooks:
    # Run the linter.
    - id: ruff-check
    # Run the formatter.
    - id: ruff-format
```

## Enable lint fixes

To enable lint fixes, add the `--fix` argument to the lint hook:

```yaml
repos:
- repo: https://github.com/astral-sh/ruff-pre-commit
  # Ruff version.
  rev: v0.14.11
  hooks:
    # Run the linter.
    - id: ruff-check
      args: [ --fix ]
    # Run the formatter.
    - id: ruff-format
```

## Exclude Jupyter Notebooks

To avoid running on Jupyter Notebooks, remove jupyter from the list of allowed filetypes:

```yaml
repos:
- repo: https://github.com/astral-sh/ruff-pre-commit
  # Ruff version.
  rev: v0.14.11
  hooks:
    # Run the linter.
    - id: ruff-check
      types_or: [ python, pyi ]
      args: [ --fix ]
    # Run the formatter.
    - id: ruff-format
      types_or: [ python, pyi ]
```

## Hook ordering

When running with `--fix`, Ruff's lint hook should be placed:
- **Before** Ruff's formatter hook
- **Before** Black, isort, and other formatting tools

This is because Ruff's fix behavior can output code changes that require reformatting.

When running without `--fix`, Ruff's formatter hook can be placed before or after Ruff's lint hook.

As long as your Ruff configuration avoids any linter-formatter incompatibilities, `ruff format` should never introduce new lint errors, so it's safe to run Ruff's format hook after `ruff check --fix`.
