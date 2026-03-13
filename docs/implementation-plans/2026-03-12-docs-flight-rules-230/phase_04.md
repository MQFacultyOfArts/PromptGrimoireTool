# Documentation Flight Rules — Phase 4: Algolia DocSearch Configuration

**Goal:** Add `HelpConfig` sub-model to pydantic-settings configuration and document env vars for Algolia DocSearch integration.

**Architecture:** New `HelpConfig` sub-model following the existing `BaseModel` subclass pattern (like `StytchConfig`, `FeaturesConfig`). Two orthogonal settings: `help_enabled` (bool) controls whether the help button renders, `help_backend` (Literal) selects Algolia DocSearch or a docs-site link. Model validator ensures Algolia credentials are present when Algolia backend is enabled. Static docs site retains built-in MkDocs search — Algolia is for in-app help only.

**Tech Stack:** pydantic, pydantic-settings, Python

**Scope:** 4 of 5 phases from original design

**Codebase verified:** 2026-03-12

**Design divergence:** The original design proposed replacing MkDocs `- search` plugin with Algolia on the static site. Research found MkDocs Material has no native Algolia integration and MkDocs search cannot be embedded in NiceGUI. Revised approach: keep built-in search on docs site, use Algolia only for in-app help button (Phase 5). The `help_backend="mkdocs"` option opens a link to the docs site instead of embedding search.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### docs-flight-rules-230.AC4: Algolia DocSearch configured
- **docs-flight-rules-230.AC4.1 Success:** `HelpConfig` sub-model loads `help_enabled`, `help_backend`, `algolia_app_id`, `algolia_search_api_key`, `algolia_index_name` from env vars with `HELP__` prefix
- **docs-flight-rules-230.AC4.2 Success:** Default `help_enabled` is `False` (no help button when unconfigured)
- **docs-flight-rules-230.AC4.3 Failure:** Missing `algolia_app_id` when `help_enabled=True` and `help_backend="algolia"` raises validation error at startup
- **docs-flight-rules-230.AC4.4 Success:** Write API key is not referenced anywhere in application code or client-side assets

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create `HelpConfig` sub-model and register on `Settings`

**Verifies:** docs-flight-rules-230.AC4.1, docs-flight-rules-230.AC4.2, docs-flight-rules-230.AC4.3, docs-flight-rules-230.AC4.4

**Files:**
- Modify: `src/promptgrimoire/config.py` (add class after existing sub-models, register on Settings)
- Modify: `.env.example` (add HELP__ section)
- Modify: `docs/configuration.md` (add to sub-model reference table)

**Context:**

Read these files before starting:
- `src/promptgrimoire/config.py` — existing sub-model pattern (StytchConfig at ~line 37, Settings class at ~line 204, sub-model registration at ~line 227-233)
- `.env.example` — format with section headings and explanatory comments
- `docs/configuration.md` — sub-model reference table (lines 13-23)

**Implementation:**

**Step 1: Add `HelpConfig` class to `config.py`**

Add after the last existing sub-model class (before the `Settings` class). Follow the exact pattern used by `StytchConfig` and `FeaturesConfig`:

```python
class HelpConfig(BaseModel):
    """In-app help button and search configuration.

    Controls whether a help button renders in the application header
    and which search backend powers it.
    """

    help_enabled: bool = False
    help_backend: Literal["algolia", "mkdocs"] = "mkdocs"
    algolia_app_id: str = ""
    algolia_search_api_key: str = ""
    algolia_index_name: str = ""

    @model_validator(mode="after")
    def _validate_algolia_credentials(self) -> Self:
        """Require Algolia credentials when Algolia backend is enabled."""
        if self.help_enabled and self.help_backend == "algolia":
            missing = []
            if not self.algolia_app_id:
                missing.append("algolia_app_id")
            if not self.algolia_search_api_key:
                missing.append("algolia_search_api_key")
            if not self.algolia_index_name:
                missing.append("algolia_index_name")
            if missing:
                msg = (
                    f"Algolia backend requires: {', '.join(missing)}. "
                    "Set HELP__ALGOLIA_APP_ID, HELP__ALGOLIA_SEARCH_API_KEY, "
                    "and HELP__ALGOLIA_INDEX_NAME environment variables."
                )
                raise ValueError(msg)
        return self
```

Note: `Literal` import should already exist (used by other config fields). If not, add `from typing import Literal`. `Self` should already be imported (used by other validators). `model_validator` should already be imported from pydantic. Check existing imports at the top of `config.py`.

**Step 2: Register on `Settings` class**

Add to the `Settings` class alongside other sub-model fields (around line 233):

```python
help: HelpConfig = HelpConfig()
```

**Step 3: Add to `.env.example`**

Add a new section (follow existing section heading convention):

```
# =============================================================================
# Help & Search (HELP__)
# =============================================================================

# Enable the in-app help button in the header
HELP__HELP_ENABLED=false

# Search backend: "algolia" for DocSearch, "mkdocs" for docs site link
HELP__HELP_BACKEND=mkdocs

# Algolia DocSearch credentials (required when HELP__HELP_BACKEND=algolia)
# Get these from https://docsearch.algolia.com/ — use the SEARCH-ONLY API key
HELP__ALGOLIA_APP_ID=
HELP__ALGOLIA_SEARCH_API_KEY=
HELP__ALGOLIA_INDEX_NAME=
```

**Step 4: Update `docs/configuration.md`**

Add a row to the sub-model reference table:

```markdown
| `HELP__` | `HelpConfig` | `help_enabled`, `help_backend`, `algolia_app_id`, `algolia_search_api_key`, `algolia_index_name` |
```

**AC4.4 compliance:** The configuration only references `algolia_search_api_key` (read-only, safe for client). No field named `write_api_key`, `admin_api_key`, or similar exists. The `.env.example` comment explicitly states "use the SEARCH-ONLY API key."

**Verification:**
```bash
uvx ty check src/promptgrimoire/config.py
# Expected: no errors

uv run ruff check src/promptgrimoire/config.py
# Expected: no errors

# Quick smoke test: verify defaults load
uv run python -c "from promptgrimoire.config import Settings; s = Settings(); print(s.help)"
# Expected: HelpConfig(help_enabled=False, help_backend='mkdocs', ...)

# Verify docs/configuration.md was updated
grep -q "HELP__" docs/configuration.md
# Expected: exit 0 (match found)

uv run complexipy src/promptgrimoire/config.py
# Expected: no functions > 15
```

**Commit:** `feat: add HelpConfig sub-model for in-app help (#281)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for `HelpConfig`

**Verifies:** docs-flight-rules-230.AC4.1, docs-flight-rules-230.AC4.2, docs-flight-rules-230.AC4.3

**Files:**
- Create: `tests/unit/test_help_config.py` (unit)

**Context:**

Read `src/promptgrimoire/config.py` to understand the HelpConfig class from Task 1.
Read existing config tests if any exist (check `tests/unit/` for `test_config*` files).

**Implementation:**

Tests for `HelpConfig` validation logic. These are pure unit tests — no database, no server.

**Testing:**

Tests must verify each AC listed:
- docs-flight-rules-230.AC4.1: `HelpConfig` fields load with correct defaults and types. Test that `HelpConfig(help_enabled=True, help_backend="algolia", algolia_app_id="X", algolia_search_api_key="Y", algolia_index_name="Z")` creates a valid config.
- docs-flight-rules-230.AC4.2: `HelpConfig()` has `help_enabled=False` by default.
- docs-flight-rules-230.AC4.3: `HelpConfig(help_enabled=True, help_backend="algolia")` raises `ValidationError` when `algolia_app_id` is empty. Test each missing field individually.

Additional tests:
- `help_enabled=True` with `help_backend="mkdocs"` does NOT require Algolia credentials
- `help_enabled=False` with `help_backend="algolia"` does NOT require Algolia credentials (disabled = no validation)
- Invalid `help_backend` value raises validation error

**Verification:**
```bash
uv run pytest tests/unit/test_help_config.py -v
# Expected: all tests pass

uvx ty check tests/unit/test_help_config.py
# Expected: no errors

uv run ruff check tests/unit/test_help_config.py
# Expected: no errors

uv run complexipy tests/unit/test_help_config.py
# Expected: no functions > 15
```

**UAT Steps (Phase 4 — after Tasks 1-2 complete):**
1. [ ] Run `uv run python -c "from promptgrimoire.config import Settings; s = Settings(); print(s.help)"` — verify defaults
2. [ ] Set `HELP__HELP_ENABLED=true` and `HELP__HELP_BACKEND=algolia` without credentials — verify startup fails with clear error naming the missing fields
3. [ ] Set `HELP__HELP_ENABLED=true`, `HELP__HELP_BACKEND=mkdocs` — verify startup succeeds without Algolia credentials
4. [ ] Verify `.env.example` has `HELP__` section with clear comments
5. [ ] Verify `docs/configuration.md` has `HELP__` row in sub-model reference table
6. [ ] Run `uv run pytest tests/unit/test_help_config.py -v` — all pass

**Commit:** `test: add HelpConfig unit tests (#281)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
