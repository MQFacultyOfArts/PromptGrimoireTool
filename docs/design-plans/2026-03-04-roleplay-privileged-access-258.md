# Roleplay Privileged Access Design

**GitHub Issue:** [#258](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/258)

## Summary

PromptGrimoire currently exposes `/roleplay` as a standalone authenticated page. That makes it visible in navigation to any logged-in user and reachable by hardcoded URL, which conflicts with the intended student access model. This design applies a narrow short-term containment fix: standalone roleplay remains available only to users who already satisfy `is_privileged_user()`, while non-privileged users lose both navigation visibility and direct-route access.

The implementation reuses existing patterns rather than introducing new auth or data concepts. Navigation filtering in `src/promptgrimoire/pages/registry.py` excludes the `Roleplay` entry for non-privileged users, and `src/promptgrimoire/pages/roleplay.py` adds a page-entry guard after authentication. If an authenticated non-privileged user opens `/roleplay`, the page shows a negative notification and stops before rendering upload or chat controls. No redirect occurs.

This design is intentionally smaller than the longer-term roleplay-activity model. It does not add activity typing, ACL extensions, persisted roleplay sessions, or CRDT-backed collaboration. Its purpose is to close the immediate brute-navigation hole while preserving a clean path to future activity-based access.

## Definition of Done

1. **Standalone roleplay access is limited to privileged users** -- `/roleplay` remains available for users who pass `is_privileged_user()`.
2. **Roleplay navigation is hidden from non-privileged users** -- authenticated students and other non-privileged users do not see the `Roleplay` page in app navigation.
3. **Direct URL access is denied without redirect** -- an authenticated non-privileged user who navigates directly to `/roleplay` sees a negative notification and the page stops before rendering the roleplay UI.

**Out of scope:** Activity-type wiring, student roleplay entry via activities, ACL expansion, persisted roleplay sessions, CRDT runner work.

## Acceptance Criteria

### roleplay-privileged-access-258.AC1: Privileged users retain standalone roleplay access
- **roleplay-privileged-access-258.AC1.1 Success:** Authenticated user where `is_privileged_user(auth_user)` returns `True` can open `/roleplay`
- **roleplay-privileged-access-258.AC1.2 Success:** Existing feature-flag guard still applies before the roleplay UI renders
- **roleplay-privileged-access-258.AC1.3 Success:** Existing unauthenticated behavior is unchanged; unauthenticated user is sent to `/login`

### roleplay-privileged-access-258.AC2: Non-privileged users do not see roleplay in navigation
- **roleplay-privileged-access-258.AC2.1 Success:** Authenticated non-privileged user does not see `Roleplay` in navigation
- **roleplay-privileged-access-258.AC2.2 Success:** Authenticated privileged user still sees `Roleplay` in navigation when the roleplay feature flag is enabled
- **roleplay-privileged-access-258.AC2.3 Edge:** Existing roleplay feature-flag filtering still hides `Roleplay` for all users when the feature is disabled

### roleplay-privileged-access-258.AC3: Non-privileged direct access is denied in place
- **roleplay-privileged-access-258.AC3.1 Failure:** Authenticated non-privileged user who opens `/roleplay` receives a negative notification
- **roleplay-privileged-access-258.AC3.2 Failure:** The page exits before rendering upload or chat controls for an authenticated non-privileged user
- **roleplay-privileged-access-258.AC3.3 Success:** Denial does not redirect the user away from `/roleplay`

## Glossary

- **`/roleplay` page**: The existing NiceGUI page in `src/promptgrimoire/pages/roleplay.py` that provides standalone roleplay chat with character-card upload and AI responses.
- **`is_privileged_user()`**: Existing helper in `src/promptgrimoire/auth/__init__.py` that returns `True` for org-level admins and the current privileged auth-role cohort. This design uses it as the sole access rule for standalone roleplay.
- **Navigation filtering**: The page-visibility logic in `src/promptgrimoire/pages/registry.py` that decides which registered pages appear in the app’s navigation UI for the current user.
- **Page-entry guard**: Early-return logic at the top of a NiceGUI page function that blocks access before the page’s main UI is constructed.
- **Negative notification**: A user-facing error/status message shown with `ui.notify(..., type="negative")`. In this design it is the visible denial response for non-privileged `/roleplay` access.
- **Privileged user**: For this design, a user whose `auth_user` session data passes `is_privileged_user()`. This is narrower than "any staff enrollment anywhere" and does not inspect unit enrollments.
- **Standalone roleplay**: The current global route-based roleplay feature, independent of any specific activity or workspace.
- **Roleplay activity model**: The future design direction where students reach roleplay through a distinct activity type rather than a global route. Explicitly out of scope here.

## Architecture

This design keeps `/roleplay` as a standalone page for the short term but narrows access to the existing privileged cohort. The access rule uses `is_privileged_user()` as the single source of truth for standalone roleplay. That keeps the change aligned with current authentication helpers and avoids introducing new schema, enrollment lookups, or ACL/resource modelling in the same slice.

Two layers enforce the same rule:

1. **Navigation filtering** removes the `Roleplay` page from visible navigation for authenticated users who do not pass `is_privileged_user()`.
2. **Page-entry guard** in `src/promptgrimoire/pages/roleplay.py` checks the authenticated user after the existing feature-flag and login guards. If the user is not privileged, the page shows a negative notification and returns before building the upload card or chat UI.

This is a containment fix, not the final activity-based design. Students are prevented from finding or brute-forcing standalone roleplay, but no roleplay activity route or persistence model is introduced here.

## Existing Patterns

Investigation found three existing patterns that this design follows:

- `is_privileged_user()` in `src/promptgrimoire/auth/__init__.py` is the existing app-level privilege helper. This design reuses it rather than introducing a new access rule.
- `roleplay_page()` in `src/promptgrimoire/pages/roleplay.py` already applies layered page guards: feature flag first, then login requirement. The new privilege check extends that same page-entry pattern.
- `get_visible_pages()` in `src/promptgrimoire/pages/registry.py` is the existing navigation filter for page visibility. This design adds a roleplay-specific privilege filter there rather than inventing a separate nav mechanism.

Investigation did not find an existing reusable helper for "has instructor privilege anywhere via enrollment". That is intentionally out of scope for this design; the short-term slice uses only the existing global `is_privileged_user()` helper.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Navigation Filtering

**Goal:** Hide the standalone `Roleplay` page from non-privileged users in app navigation.

**Components:**
- `src/promptgrimoire/pages/registry.py` -- extend page visibility filtering so `/roleplay` is excluded when the authenticated user does not satisfy `is_privileged_user()`
- Navigation-related unit tests in `tests/unit/` -- verify privileged and non-privileged visibility behavior without disturbing existing feature-flag coverage

**Dependencies:** None

**Done when:** Non-privileged authenticated users do not see `Roleplay` in navigation, privileged users still do, and tests cover `roleplay-privileged-access-258.AC2.*`
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Roleplay Page Guard

**Goal:** Deny direct `/roleplay` access to authenticated non-privileged users without redirecting them away.

**Components:**
- `src/promptgrimoire/pages/roleplay.py` -- add privileged-user guard after authentication check and before any roleplay UI is constructed
- Roleplay page tests in `tests/` -- verify denial path shows a negative notification and does not render the upload/chat UI for non-privileged users; verify privileged path remains accessible

**Dependencies:** Phase 1

**Done when:** Authenticated non-privileged direct access to `/roleplay` shows a negative notification and stops in place, privileged users still reach the page, and tests cover `roleplay-privileged-access-258.AC1.*` and `roleplay-privileged-access-258.AC3.*`
<!-- END_PHASE_2 -->

## Additional Considerations

**Scope boundary:** This design deliberately does not implement the longer-term "students access roleplay only as a distinct activity type" model. That remains a follow-up design involving activity typing, routing, and likely persisted roleplay state.

**UX trade-off:** Denial stays on the `/roleplay` route with a negative notification rather than redirecting elsewhere. This makes the restriction explicit and avoids hiding the fact that the route is privileged-only.
