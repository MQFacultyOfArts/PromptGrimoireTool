# Pydantic-Settings Migration -- Test Requirements

Maps each acceptance criterion from the `130-pydantic-settings` design plan to automated tests or documented human verification. Rationalized against implementation decisions made in phases 1--7.

---

## Automated Tests

### AC1: Type validation at startup

All AC1 tests live in `tests/unit/test_settings.py` class `TestTypeValidation` (Phase 2, Task 2). Every test constructs `Settings(_env_file=None, ...)` to avoid reading real `.env` files.

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC1.1 | Unit | `tests/unit/test_settings.py::TestTypeValidation::test_valid_typed_values_populate_all_fields` | Construct Settings with valid typed values for every sub-model field, verify all fields accessible and correctly typed. |
| AC1.2 | Unit | `tests/unit/test_settings.py::TestTypeValidation::test_bool_coercion_case_insensitive` | Parametrize over `"true"`, `"false"`, `"1"`, `"0"`, `"yes"`, `"no"`, `"True"`, `"FALSE"` -- construct `DevConfig(auth_mock=v)` for each, verify bool result. |
| AC1.3 | Unit | `tests/unit/test_settings.py::TestTypeValidation::test_int_coercion_from_string` | Construct `AppConfig(port="9090")`, `LlmConfig(thinking_budget="2048")`, `LlmConfig(lorebook_token_budget="500")` -- verify int coercion. |
| AC1.4 | Unit | `tests/unit/test_settings.py::TestTypeValidation::test_invalid_int_raises_validation_error` | Construct `AppConfig(port="not-a-number")` -- expect `ValidationError`. |
| AC1.5 | Unit | `tests/unit/test_settings.py::TestTypeValidation::test_missing_env_file_uses_defaults` | Construct `Settings(_env_file=None)` with no env vars set -- verify all defaults populated, no error raised. Verifies the design decision that all sub-model fields have defaults so the app boots without external services. |

### AC2: Startup validation for cross-field rules

AC2 tests cover the `StytchConfig.sso_requires_public_token` `@model_validator(mode="after")`. Split across two files: sub-model validation in `test_settings.py`, factory-level behavior in `test_auth_client.py`.

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC2.1 | Unit | `tests/unit/test_settings.py::TestCrossFieldValidation::test_sso_with_public_token_passes` | Construct `StytchConfig(sso_connection_id="test-id", public_token="test-token")` -- no error. |
| AC2.2 | Unit | `tests/unit/test_settings.py::TestCrossFieldValidation::test_sso_without_public_token_raises` | Construct `StytchConfig(sso_connection_id="test-id", public_token="")` -- expect `ValidationError` with message mentioning `STYTCH__PUBLIC_TOKEN`. |
| AC2.3 | Unit | `tests/unit/test_settings.py::TestCrossFieldValidation::test_neither_sso_nor_public_token_passes` | Construct `StytchConfig()` with defaults -- no error. Both fields are optional-or-empty. |

**Rationalization:** The design plan moved SSO cross-validation from the old `AuthConfig.validate()` method to a Pydantic `@model_validator`. This fires at construction time, so AC2 is fully testable via direct `StytchConfig()` construction without needing Settings or env vars.

### AC3: AuthConfig replacement

AC3 tests verify the factory migration from `AuthConfig` + `_get_config()` to `get_settings().stytch`. Tests in `test_auth_client.py` (Phase 3, Task 4).

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC3.1 | Unit | `tests/unit/test_auth_client.py::TestGetAuthClientFactory::test_returns_stytch_client_with_credentials` | Patch `get_settings` to return Settings with `stytch.project_id` and `stytch.secret` populated. Call `get_auth_client()`, verify `StytchB2BClient` returned with correct credentials. |
| AC3.2 | Unit | `tests/unit/test_auth_client.py::TestGetAuthClientFactory::test_returns_mock_client_when_auth_mock_enabled` | Patch `get_settings` to return Settings with `dev.auth_mock=True`. Call `get_auth_client()`, verify `MockAuthClient` returned. |
| AC3.3 | Unit | `tests/unit/test_auth_client.py::TestGetAuthClientFactory::test_raises_when_project_id_empty_and_mock_disabled` | Patch `get_settings` to return Settings with default (empty) `stytch.project_id` and `dev.auth_mock=False`. Call `get_auth_client()`, expect `ValueError` matching `"STYTCH__PROJECT_ID is required"`. |
| AC3.4 | Unit | `tests/unit/test_auth_client.py::TestStytchConfigValidation::test_auth_config_no_longer_importable` | Assert `from promptgrimoire.auth.config import AuthConfig` raises `ImportError` (file deleted in Phase 3, Task 1). Also verify `from_env` is not in `dir(promptgrimoire.auth)`. |

**Rationalization:** AC3.3 tests a new behavior introduced by the design: the old `AuthConfig.from_env()` would silently pass an empty `project_id` to `StytchB2BClient` (failing later at API call time). The new factory raises `ValueError` immediately. AC3.4 confirms the old module is fully removed, not just unused.

### AC4: SecretStr for sensitive fields

AC4 tests verify masking and unwrapping. Tests in `test_auth_client.py` class `TestSecretStrMasking` (Phase 3, Task 4).

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC4.1 | Unit | `tests/unit/test_auth_client.py::TestSecretStrMasking::test_str_masks_secrets` | Construct Settings with known secret values for `stytch.secret`, `llm.api_key`, `app.storage_secret`. Call `str(settings)`, assert none of the real values appear in the output. |
| AC4.2 | Unit | `tests/unit/test_auth_client.py::TestSecretStrMasking::test_get_secret_value_returns_actual_value` | Construct `StytchConfig(secret=SecretStr("my-real-secret"))`. Call `.get_secret_value()`, assert returns `"my-real-secret"`. |

**Rationalization:** AC4.2 also has indirect coverage in the factory (`get_auth_client()` calls `.get_secret_value()` to pass the real secret to `StytchB2BClient`) and the roleplay page (passes `settings.llm.api_key.get_secret_value()` to `ClaudeClient`). The unit test provides the direct assertion.

### AC5: .env.example sync

AC5 tests replace the old regex-scanning `test_env_vars.py` with Settings schema introspection. Tests in `tests/unit/test_env_vars.py` (Phase 2, Task 1).

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC5.1 | Unit | `tests/unit/test_env_vars.py::test_all_settings_fields_in_env_example` | Derive env var names from `Settings.model_fields` using `{SUB_MODEL}__{FIELD}` convention. Assert every derived name appears in `.env.example`. |
| AC5.2 | Unit | `tests/unit/test_env_vars.py::test_all_env_example_vars_in_settings` | Parse `.env.example` for variable names. Assert every name corresponds to a field in Settings. Catches orphaned entries in `.env.example` that have no backing field. |
| AC5.3 | Unit | `tests/unit/test_env_vars.py::test_env_var_names_use_double_underscore` | Assert all derived env var names for nested fields contain `__` separator. Guards against someone adding a flat env var name without nesting. |

**Rationalization:** The design plan replaced the old grep-based approach (scanning source for `os.environ.get()` patterns) with schema introspection because the source no longer contains `os.environ` calls. The new tests are more robust: they verify the bidirectional mapping between Settings model and `.env.example` structurally rather than textually.

### AC6: load_dotenv elimination

AC6 tests are **codebase-wide structural assertions** -- they verify the absence of patterns across the entire source tree. Tests in `tests/unit/test_env_vars.py` or a dedicated `tests/unit/test_no_dotenv.py` (Phase 6, Task 6; Phase 7, Tasks 2--3).

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC6.1 | Unit | `tests/unit/test_env_vars.py::test_no_load_dotenv_calls` | Scan all `.py` files under `src/`, `tests/`, and `alembic/` for `load_dotenv`. Assert zero matches. |
| AC6.2 | Unit | `tests/unit/test_env_vars.py::test_no_os_environ_get_in_app_code` | Scan all `.py` files under `src/promptgrimoire/` for `os.environ.get(` and `os.environ[`. Assert zero matches, with an allowlist for legitimate subprocess env operations: `cli.py` (`os.environ["DATABASE__URL"]` assignment), `bootstrap.py` (`dict(os.environ)` pass-through). |
| AC6.3 | Unit | `tests/unit/test_env_vars.py::test_no_direct_dotenv_imports` | Scan all `.py` files under `src/`, `tests/`, and `alembic/` for `from dotenv import` and `import dotenv`. Assert zero matches. Verifies that pydantic-settings handles `.env` reading natively. |

**Rationalization:** AC6.2 requires an allowlist because the design explicitly retains `os.environ` for two legitimate purposes: (1) `cli.py` sets `DATABASE__URL` as an env var before spawning an Alembic subprocess so the subprocess inherits it, and (2) `bootstrap.py` passes `dict(os.environ)` to subprocess calls. These are subprocess communication, not configuration reading. The test must distinguish the two.

### AC7: Worktree .env fallback

AC7 tests verify the path resolution logic in `config.py` and the logging behavior. Tests in `tests/unit/test_settings.py` class `TestWorktreeEnvPaths` (Phase 2, Task 2).

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC7.1 | Unit | `tests/unit/test_settings.py::TestWorktreeEnvPaths::test_project_root_env_in_config` | Assert `_PROJECT_ROOT / ".env"` is present in `Settings.model_config["env_file"]` tuple. |
| AC7.2 | Unit | `tests/unit/test_settings.py::TestWorktreeEnvPaths::test_main_worktree_env_in_config` | Assert `_MAIN_WORKTREE_ENV` is present in `Settings.model_config["env_file"]` tuple. |
| AC7.3 | Unit | `tests/unit/test_settings.py::TestWorktreeEnvPaths::test_local_env_overrides_main_worktree` | Assert the local `.env` appears AFTER the main worktree `.env` in the tuple. pydantic-settings applies later files with higher precedence, so the local `.env` must be second. |
| AC7.4 | Unit | `tests/unit/test_settings.py::TestWorktreeEnvPaths::test_get_settings_logs_env_files` | Use `caplog` fixture. Call `get_settings()` (after `cache_clear()`). Assert INFO-level log message references `.env`. |

**Rationalization:** AC7.1--AC7.3 are structural assertions on the `model_config` tuple rather than functional tests that create temporary `.env` files. This is the approach chosen by the implementation plan: the worktree path resolution is computed from `__file__` at module load time, so the tuple values are deterministic and can be verified structurally. A functional test that creates `.env` files in temp directories would require monkeypatching `_PROJECT_ROOT` and `_MAIN_WORKTREE_ENV`, which tests the pydantic-settings `.env` loading machinery rather than our code.

AC7.4 tests the logging side-effect of `get_settings()`. The implementation logs at INFO level on first call and uses the `model_config["env_file"]` paths to determine which files exist.

### AC8: Test isolation

AC8 tests verify the isolation patterns that tests themselves will use. Tests in `tests/unit/test_settings.py` class `TestTestIsolation` (Phase 2, Task 2).

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC8.1 | Unit | `tests/unit/test_settings.py::TestTestIsolation::test_settings_construction_without_env` | Construct `Settings(_env_file=None, app=AppConfig(port=1234))`. Verify `port == 1234`. Demonstrates the pattern: tests pass explicit values, never read from `.env` or `os.environ`. |
| AC8.2 | Unit | `tests/unit/test_settings.py::TestTestIsolation::test_cache_clear_resets_singleton` | Call `get_settings()` twice -- same instance (identity check). Call `get_settings.cache_clear()`, call again -- different instance (identity check). |
| AC8.3 | Unit | `tests/unit/test_settings.py::TestTestIsolation::test_pure_function_no_settings_dependency` | Define a trivial pure function, call it with explicit args. This is a documentation test demonstrating the functional core pattern: pure functions never import or depend on Settings. |

**Rationalization:** AC8.3 is unusual as a test -- it demonstrates a coding pattern rather than testing specific behavior. The implementation plan includes it as a "documentation test" to codify the functional core / imperative shell convention. If this feels too synthetic, it could be replaced by a structural assertion (e.g., scanning `src/promptgrimoire/llm/prompt.py` for `get_settings` imports and asserting zero matches), but the plan specifies a demonstration test.

### AC9: Per-worktree database isolation

AC9 tests cover branch detection, suffix derivation, URL suffixing, and the Settings model validator. Tests in `tests/unit/test_settings.py` class `TestBranchDbIsolation` (Phase 2, Task 2). Branch detection tests use `tmp_path` to create fake `.git` structures. Validator tests use `unittest.mock.patch` on `_current_branch`.

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC9.1 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_main_branch_no_suffix` | `_branch_db_suffix("main")` returns `""`. Also test `"master"` and `None`. Patch `_current_branch` to return `"main"`, construct Settings, verify URL unchanged. |
| AC9.2 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_feature_branch_suffixed` | `_branch_db_suffix("130-pydantic-settings")` returns `"130_pydantic_settings"`. Patch `_current_branch`, construct Settings with `database.url`, verify suffix appended. |
| AC9.3 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_both_urls_suffixed` | Patch `_current_branch` to return `"feature"`. Construct Settings with both `database.url` and `dev.test_database_url`. Verify BOTH are suffixed. |
| AC9.4 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_branch_detection_worktree` | Create fake `.git` file (worktree) + gitdir path with HEAD containing `ref: refs/heads/feature`. Verify `_current_branch()` returns `"feature"`. Uses `tmp_path` + monkeypatch on `_PROJECT_ROOT`. |
| AC9.5 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_detached_head_no_suffix` | Create fake `.git/HEAD` containing a raw SHA. Verify `_current_branch()` returns `None`. |
| AC9.6 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_special_chars_sanitised` | `_branch_db_suffix("feature/my.branch-name")` returns `"feature_my_branch_name"`. |
| AC9.7 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_long_branch_truncated_with_hash` | `_branch_db_suffix("a" * 60)` returns a string <= 40 chars with a deterministic hash suffix. |
| AC9.8 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_idempotent_suffix` | `_suffix_db_url("postgresql://u:p@h/mydb_feature", "feature")` returns unchanged. |
| AC9.9 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_query_params_preserved` | `_suffix_db_url("postgresql://u:p@h/mydb?host=/tmp", "feature")` preserves `?host=/tmp`. |
| AC9.10 | Unit | `tests/unit/test_settings.py::TestBranchDbIsolation::test_opt_out_branch_db_suffix` | Patch `_current_branch` to return `"feature"`. Construct Settings with `dev.branch_db_suffix=False`. Verify URL unchanged. |

**Rationalization:** AC9.4 uses `tmp_path` to create a fake `.git` file structure rather than mocking Path methods, making the test more realistic. AC9.8 idempotency is critical because `_pre_test_db_cleanup()` sets `DATABASE__URL` in the environment and then the Alembic subprocess reads it — if the subprocess triggers Settings construction, the validator must not double-suffix. AC9.10 validates the opt-out mechanism for developers who want to share databases across worktrees.

### AC10: Branch-specific database auto-creation

AC10 tests cover `ensure_database_exists()`. The function itself is tested in `tests/unit/test_settings.py` class `TestEnsureDatabaseExists` (Phase 2, Task 2). Tests require a real PostgreSQL connection and are skipped if no database is available. Integration with `run_alembic_upgrade()` is tested indirectly through Phase 4 Task 2.

| Criterion | Type | Test File | Description |
|-----------|------|-----------|-------------|
| AC10.1 | Integration | `tests/unit/test_settings.py::TestEnsureDatabaseExists::test_creates_missing_database` | Generate unique DB name, call `ensure_database_exists()`, verify DB exists in `pg_database`, drop afterwards. Requires PostgreSQL. |
| AC10.2 | Integration | `tests/unit/test_settings.py::TestEnsureDatabaseExists::test_idempotent_existing_database` | Call `ensure_database_exists()` twice. No error on second call. |
| AC10.3 | Unit | `tests/unit/test_settings.py::TestEnsureDatabaseExists::test_noop_on_none_url` | `ensure_database_exists(None)` returns without error. `ensure_database_exists("")` returns without error. No database connection needed. |

**Rationalization:** AC10.1 and AC10.2 are integration-grade tests because they require a real PostgreSQL connection. They are placed in the unit test file for co-location with the Settings tests but are skipped when `TEST_DATABASE_URL` is not set. AC10.3 is a pure unit test for the guard clauses.

---

## Summary: Test File Inventory

| Test File | New/Modified | Criteria Covered | Phase |
|-----------|-------------|------------------|-------|
| `tests/unit/test_settings.py` | New | AC1.1--AC1.5, AC2.1--AC2.3, AC7.1--AC7.4, AC8.1--AC8.3, AC9.1--AC9.10, AC10.1--AC10.3 | 2 |
| `tests/unit/test_env_vars.py` | Modified (rewrite) | AC5.1--AC5.3, AC6.1--AC6.3 | 2, 7 |
| `tests/unit/test_auth_client.py` | Modified (replace `TestAuthConfigValidation`) | AC3.1--AC3.4, AC4.1--AC4.2 | 3 |

Total: 40 sub-criteria across 3 test files. All criteria are covered by automated tests (AC10.1--AC10.2 are integration-grade, skipped without PostgreSQL).

---

## Human Verification

All 27 sub-criteria have automated test coverage. No criterion requires human-only verification.

However, the following items warrant manual smoke-testing during UAT because they exercise integration paths that unit tests cover only indirectly:

### 1. Application boots with new env var names

**Criteria touched:** AC1.1, AC6.3, AC7.1

**Why not fully automatable in unit tests:** Unit tests construct `Settings(_env_file=None, ...)` by design (AC8.1). This means no unit test actually exercises the real `.env` file loading path with the renamed variables. The pydantic-settings `.env` parsing is library code we trust, but a typo in `.env.example` or a mismatch between documented names and `SettingsConfigDict(env_nested_delimiter="__")` would only surface at runtime.

**Verification approach:**
1. Copy `.env.example` to `.env`, fill in values
2. Run `uv run python -m promptgrimoire`
3. Verify app starts, database connects (if configured), auth works

### 2. Alembic migrations work standalone and via CLI

**Criteria touched:** AC6.1, AC6.3

**Why not fully automatable in unit tests:** Alembic runs as a subprocess (via `cli.py`) or standalone (`alembic upgrade head`). The subprocess env var inheritance chain (`cli.py` sets `DATABASE__URL` -> subprocess inherits -> `alembic/env.py` calls `get_settings()` -> reads inherited env var) involves process boundaries that unit tests mock away.

**Verification approach:**
1. With `.env` configured: `alembic upgrade head` (standalone)
2. With `.env` configured: `uv run test-debug` (exercises `_pre_test_db_cleanup` -> Alembic subprocess)
3. Verify both paths succeed without `load_dotenv` errors

### 3. Worktree .env fallback in practice

**Criteria touched:** AC7.2, AC7.3

**Why not fully automatable in unit tests:** Unit tests verify the tuple structure of `model_config["env_file"]` but do not create actual `.env` files in worktree directories and verify precedence. This is by design -- the unit test verifies our code's path computation, and pydantic-settings' file reading is trusted library behavior.

**Verification approach:**
1. In main worktree: create `.env` with `APP__PORT=9000`
2. In `.worktrees/130-pydantic-settings/`: verify no local `.env` exists
3. Run `uv run python -c "from promptgrimoire.config import Settings; print(Settings().app.port)"` from worktree
4. Verify port is `9000` (fallback to main worktree)
5. Create local `.env` in worktree with `APP__PORT=9001`
6. Repeat command, verify port is `9001` (local override)
7. Delete local `.env`, verify fallback resumes

### 4. SecretStr masking in production logs

**Criteria touched:** AC4.1

**Why not fully automatable in unit tests:** `test_str_masks_secrets` verifies `str(settings)` output. But production may log settings objects through logging frameworks, exception tracebacks, or debugger representations. These paths are not covered by the unit test.

**Verification approach:**
1. Set `STYTCH__SECRET=real-credential` in `.env`
2. Start app, trigger an auth error (e.g., invalid credentials)
3. Check logs for `real-credential` -- must not appear
4. Check that `**********` or similar masking appears in its place

### 5. Per-worktree database isolation in practice

**Criteria touched:** AC9.2, AC9.3, AC10.1

**Why not fully automatable in unit tests:** Unit tests mock `_current_branch()` for isolation. The end-to-end flow — Settings reads real `.git/HEAD`, derives branch suffix, auto-creates database, Alembic migrates it, tests run against it — involves multiple process boundaries and real filesystem state.

**Verification approach:**
1. `uv run test-debug` on branch `130-pydantic-settings` — auto-creates `promptgrimoire_test_130_pydantic_settings`, runs migrations, tests pass
2. `uv run test-debug` on `main` — uses original `promptgrimoire_test`, no suffix
3. Switch between branches — each uses its own DB, no migration conflicts
4. Set `DEV__BRANCH_DB_SUFFIX=false` in local `.env` — uses unsuffixed DB
