# Test Requirements: Roleplay Privileged Access (#258)

Maps each acceptance criterion to automated tests or verification commands.

## Conventions

- **Unit tests**: mock-driven tests for pure helpers and page-entry guard wiring
- **Integration tests**: existing suite-wide regression check via `uv run test-all`
- **Human verification**: not required for the accepted scope; all ACs are automatable

---

## AC1: Privileged users retain standalone roleplay access

### roleplay-privileged-access-258.AC1.1 — Authenticated privileged user can open `/roleplay`

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_roleplay_access.py::TestRoleplayAndLogsPageWiring::test_roleplay_page_enters_page_layout_for_privileged_user` |
| Description | Patch `require_roleplay_enabled()` to `True` and `require_privileged_roleplay_user()` to `True`, then assert `roleplay_page()` enters `page_layout("Roleplay")` |
| Phase | 2 |

### roleplay-privileged-access-258.AC1.2 — Existing feature-flag guard still applies before the roleplay UI renders

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_roleplay_access.py::TestRoleplayAndLogsPageWiring::test_roleplay_page_stops_before_access_guard_when_feature_flag_disabled` |
| Description | Patch `require_roleplay_enabled()` to `False`, call `roleplay_page()`, assert the privilege guard is never called and no roleplay UI is constructed |
| Phase | 2 |

### roleplay-privileged-access-258.AC1.3 — Existing unauthenticated behavior is unchanged; unauthenticated user is sent to `/login`

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_roleplay_access.py::TestRequirePrivilegedRoleplayUser::test_unauthenticated_user_redirects_to_login` |
| Description | Call the shared roleplay guard with no session user and assert it redirects to `/login` and returns `False` |
| Phase | 2 |

---

## AC2: Non-privileged users do not see roleplay in navigation

### roleplay-privileged-access-258.AC2.1 — Authenticated non-privileged user does not see `Roleplay` in navigation

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_settings.py::TestPageRegistryRoleplayFlag::test_roleplay_pages_hidden_for_non_privileged_user_when_enabled` |
| Description | Call `get_visible_pages()` with a non-privileged authenticated user and assert `/roleplay` and `/logs` are absent |
| Phase | 1 |

### roleplay-privileged-access-258.AC2.2 — Authenticated privileged user still sees `Roleplay` in navigation when the roleplay feature flag is enabled

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_settings.py::TestPageRegistryRoleplayFlag::test_roleplay_pages_shown_for_privileged_user_when_enabled` |
| Description | Call `get_visible_pages()` with a privileged authenticated user and assert `/roleplay` and `/logs` are present |
| Phase | 1 |

### roleplay-privileged-access-258.AC2.3 — Existing roleplay feature-flag filtering still hides `Roleplay` for all users when the feature is disabled

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_settings.py::TestPageRegistryRoleplayFlag::test_roleplay_page_hidden_when_disabled` |
| Description | Assert all `requires_roleplay=True` pages remain hidden when `roleplay_enabled=False`, regardless of user privilege |
| Phase | 1 |

---

## AC3: Non-privileged direct access is denied in place

### roleplay-privileged-access-258.AC3.1 — Authenticated non-privileged user who opens `/roleplay` receives a negative notification

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_roleplay_access.py::TestRequirePrivilegedRoleplayUser::test_non_privileged_user_gets_negative_notification_without_redirect` |
| Description | Call the shared roleplay guard with a non-privileged authenticated user and assert `ui.notify(..., type="negative")` is called |
| Phase | 2 |

### roleplay-privileged-access-258.AC3.2 — The page exits before rendering upload or chat controls for an authenticated non-privileged user

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_roleplay_access.py::TestRoleplayAndLogsPageWiring::test_roleplay_page_stops_before_page_layout_for_denied_user` |
| Description | Patch the roleplay page guard to deny access, call `roleplay_page()`, and assert `page_layout()` is never entered |
| Phase | 2 |

### roleplay-privileged-access-258.AC3.3 — Denial does not redirect the user away from `/roleplay`

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_roleplay_access.py::TestRequirePrivilegedRoleplayUser::test_non_privileged_user_gets_negative_notification_without_redirect` |
| Description | Assert the non-privileged denial path calls `ui.notify` but does not call `ui.navigate.to` |
| Phase | 2 |

---

## Additional Coverage From Codebase Verification

These checks are not separate accepted ACs, but they lock in the verified codebase risk uncovered during implementation planning.

### Shared guard also protects `/logs`

| Aspect | Value |
|--------|-------|
| Test type | unit |
| Test file | `tests/unit/test_roleplay_access.py::TestRoleplayAndLogsPageWiring::test_logs_page_stops_before_label_render_for_denied_user` |
| Description | Patch `require_privileged_roleplay_user()` to deny access, call `logs_page()`, and assert the log viewer does not render labels or controls |
| Phase | 2 |

### Full-suite regression check

| Aspect | Value |
|--------|-------|
| Test type | integration |
| Test file | `uv run test-all` |
| Description | Run the standard unit/integration suite after both phases to ensure the new registry filter and shared page guard do not regress unrelated behavior |
| Phase | 2 |

---

## Test Execution Commands

```bash
# Phase 1: navigation filtering
uv run pytest tests/unit/test_settings.py -v

# Phase 2: shared helper + page-wiring guard tests
uv run pytest tests/unit/test_roleplay_access.py -v

# Lint and format checks for touched files
uv run ruff check src/promptgrimoire/pages/registry.py src/promptgrimoire/pages/layout.py src/promptgrimoire/pages/roleplay.py src/promptgrimoire/pages/logviewer.py tests/unit/test_settings.py tests/unit/test_roleplay_access.py
uv run ruff format src/promptgrimoire/pages/registry.py src/promptgrimoire/pages/layout.py src/promptgrimoire/pages/roleplay.py src/promptgrimoire/pages/logviewer.py tests/unit/test_settings.py tests/unit/test_roleplay_access.py --check

# Type checking
uvx ty check

# Standard regression gate
uv run test-all
```
