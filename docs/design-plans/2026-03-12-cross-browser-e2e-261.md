# Cross-Browser E2E Testing Design

**GitHub Issue:** #261

## Summary

The application's E2E test suite currently runs only against Chromium via Playwright's bundled browser engine. This design extends cross-browser coverage to two tiers: Playwright's bundled Firefox engine (for local development and CI), and real browsers via BrowserStack's cloud testing service (as a final PR gate). A third BrowserStack tier targets deliberately unsupported older browser versions to verify that the CSS Custom Highlight API feature gate correctly rejects them.

WebKit/Safari testing is handled exclusively through BrowserStack. Playwright's bundled WebKit was evaluated and rejected — on Linux it has documented HSTS bugs, headless failures, and codec issues (2024-2025, unresolved), and the Playwright team explicitly recommends macOS for "closest-to-Safari experience". Since both the dev machine and CI run Ubuntu, Playwright WebKit provides no useful signal.

The implementation reuses the existing CLI subcommand pattern, lane abstraction, and per-file worker subprocess model with minimal changes. For Firefox, the only difference from `e2e run` is a prepended `--browser firefox` flag. For BrowserStack, the worker swaps the subprocess prefix from `python -m pytest` to `browserstack-sdk pytest`, which transparently intercepts Playwright's browser launch and routes it through a CDP WebSocket to real cloud browsers. A local tunnel managed by the BrowserStack SDK proxies remote traffic back to the locally running NiceGUI server.

## Definition of Done

1. New CLI subcommand `uv run grimoire e2e firefox` runs the E2E test suite against Playwright's bundled Firefox engine
2. New CLI subcommand `uv run grimoire e2e all-browsers` runs Chromium then Firefox sequentially, reporting per-browser results. Continues to next browser on failure by default; `--fail-fast` stops on first browser failure.
3. New CLI subcommand `uv run grimoire e2e browserstack [profile]` runs the E2E suite against real browsers on BrowserStack, supporting the same test selection patterns as other subcommands. Optional profile argument selects a specific browser (e.g., `safari`, `firefox`)
4. `uv run grimoire e2e run` remains Chromium-only
5. CI runs Chromium + Firefox as a matrix; BrowserStack runs as a final gate on PRs after all other checks pass
6. BrowserStack unsupported-browser tier runs gate-only tests against older browser versions to verify the feature gate rejects them
7. Browser gate minimum versions validated against caniuse data for CSS Custom Highlight API

## Acceptance Criteria

### cross-browser-e2e-261.AC1: Firefox CLI subcommand
- **cross-browser-e2e-261.AC1.1 Success:** `uv run grimoire e2e firefox` runs the full E2E suite and reports results
- **cross-browser-e2e-261.AC1.2 Success:** Pytest passthrough args (`-k`, `-x`, `--ff`) work with `e2e firefox`
- **cross-browser-e2e-261.AC1.3 Success:** Parallel mode works (multiple Firefox workers with isolated DBs and ports)
- **cross-browser-e2e-261.AC1.4 Failure:** Missing Firefox install produces a clear error message (not a stack trace)

### cross-browser-e2e-261.AC2: All-browsers convenience command
- **cross-browser-e2e-261.AC2.1 Success:** `uv run grimoire e2e all-browsers` runs Chromium then Firefox sequentially
- **cross-browser-e2e-261.AC2.2 Success:** Reports per-browser pass/fail summary
- **cross-browser-e2e-261.AC2.3 Success:** By default, continues to next browser even if previous browser fails (diagnostic mode)
- **cross-browser-e2e-261.AC2.4 Success:** `--fail-fast` flag stops on first browser failure

### cross-browser-e2e-261.AC3: BrowserStack integration
- **cross-browser-e2e-261.AC3.1 Success:** `uv run grimoire e2e browserstack` runs E2E suite against all configured BrowserStack platforms
- **cross-browser-e2e-261.AC3.2 Success:** `uv run grimoire e2e browserstack safari` runs against Safari-only config
- **cross-browser-e2e-261.AC3.3 Success:** `uv run grimoire e2e browserstack firefox` runs against Firefox-only config
- **cross-browser-e2e-261.AC3.4 Success:** BrowserStack Local tunnel proxies remote browsers to localhost NiceGUI server
- **cross-browser-e2e-261.AC3.5 Failure:** Missing `BROWSERSTACK_USERNAME` or `BROWSERSTACK_ACCESS_KEY` produces a clear error before attempting any test
- **cross-browser-e2e-261.AC3.6 Failure:** BrowserStack connection failure does not leave orphaned local server processes

### cross-browser-e2e-261.AC4: Default behaviour unchanged
- **cross-browser-e2e-261.AC4.1 Success:** `uv run grimoire e2e run` still runs Chromium-only (no change to existing behaviour)
- **cross-browser-e2e-261.AC4.2 Success:** Existing CI workflow produces identical results for the Chromium job

### cross-browser-e2e-261.AC5: CI pipeline
- **cross-browser-e2e-261.AC5.1 Success:** CI E2E job runs Chromium and Firefox as separate matrix entries
- **cross-browser-e2e-261.AC5.2 Success:** BrowserStack CI job runs only on PRs
- **cross-browser-e2e-261.AC5.3 Success:** BrowserStack CI job depends on all other jobs passing (does not run if unit/E2E fails)
- **cross-browser-e2e-261.AC5.4 Success:** BrowserStack failure blocks PR merge

### cross-browser-e2e-261.AC6: Browser gate validation
- **cross-browser-e2e-261.AC6.1 Success:** Supported real browsers (current Safari, current Firefox) pass the CSS Highlight API gate and see the login UI
- **cross-browser-e2e-261.AC6.2 Success:** Unsupported real browsers (old Safari, old Firefox) see the upgrade overlay
- **cross-browser-e2e-261.AC6.3 Success:** Gate minimum versions match caniuse data for CSS Custom Highlight API
- **cross-browser-e2e-261.AC6.4 Success:** Unsupported tier runs only `browser_gate`-marked tests (not the full suite)

## Glossary

- **BrowserStack**: A commercial cloud testing service that provides access to real browsers and devices. The BrowserStack SDK intercepts Playwright's browser launch and routes it to BrowserStack's infrastructure instead of a local binary.
- **BrowserStack Local tunnel**: A secure proxy process (managed by the BrowserStack SDK) that allows remote browsers running in BrowserStack's cloud to reach a server running on localhost.
- **`browserstack-sdk`**: The BrowserStack Python SDK. When used as a subprocess prefix (`browserstack-sdk pytest ...`), it intercepts Playwright and reroutes browser sessions to BrowserStack's cloud without requiring changes to test code.
- **CDP (Chrome DevTools Protocol)**: The wire protocol Playwright uses to control browser instances. BrowserStack uses a CDP WebSocket endpoint to present a remote real browser as if it were a local one.
- **CSS Custom Highlight API**: A browser API (`CSS.highlights`) that the application uses to render annotation highlights without DOM mutation. Browsers that lack it cannot render the annotation interface. Safari's implementation only supports `StaticRange` (not `LiveRange`) — the application already uses `StaticRange` exclusively.
- **browser gate**: A client-side JavaScript check on page load that verifies the browser supports required APIs. Browsers that fail are shown an upgrade overlay.
- **`browser_gate` pytest marker**: A pytest mark applied to tests that verify the gate itself. Used to restrict the unsupported-browser BrowserStack tier to only these tests.
- **caniuse**: A reference database (caniuse.com) documenting browser API support by version. Used to validate the browser gate's minimum version thresholds.
- **lane / `LaneSpec`**: Internal abstraction in the E2E CLI that groups test paths, markers, and configuration under a named profile. Firefox reuses the existing `PLAYWRIGHT_LANE`.
- **pytest-playwright**: A pytest plugin that integrates Playwright's browser automation into pytest. Exposes the `--browser` flag to select between Chromium, Firefox, and WebKit.
- **upgrade overlay**: A full-page UI element shown to users whose browser does not support the required APIs. Tested in Tier 3 (unsupported browsers).

## Architecture

Two tiers of cross-browser coverage, each catching different categories of bugs:

**Tier 1 — Playwright bundled Firefox (local + CI).** `e2e firefox` passes `--browser firefox` to pytest-playwright via the existing worker subprocess model. Same test paths, same lane discovery, same parallel orchestration. The only difference from `e2e run` is the prepended `--browser` flag. CI runs Chromium + Firefox as a matrix.

**Tier 2 — BrowserStack real browsers (CI gate on PRs).** `e2e browserstack` replaces the subprocess command from `[sys.executable, "-m", "pytest"]` to `["browserstack-sdk", "pytest"]`. The BrowserStack SDK transparently intercepts Playwright's browser launch and routes it through a CDP WebSocket to real browsers in BrowserStack's cloud. BrowserStack Local tunnel (managed by the SDK via `browserstackLocal: true` in YAML config) proxies remote browser traffic to the local NiceGUI server.

BrowserStack runs are split into two sub-tiers:
- **Supported tier:** Full E2E suite against current Safari on macOS and current Firefox on Windows.
- **Unsupported tier:** Gate-only tests (`-m browser_gate`) against older browser versions (e.g., Safari 16, Firefox 130) that lack CSS Custom Highlight API. Verifies the upgrade overlay appears on real browsers, not just via the `delete CSS.highlights` simulation.

**WebKit exclusion rationale:** Playwright's bundled WebKit on Linux has documented HSTS bugs (#35293), headless mode failures (#32429), and missing codec libraries (#31615) — all unresolved as of 2025. The Playwright team recommends macOS for faithful WebKit testing. Since dev and CI both run Ubuntu, Playwright WebKit provides no useful signal. Safari testing is handled entirely by BrowserStack.

**Data flow:**

```
CLI subcommand
  → select browser flag (--browser firefox) or SDK command (browserstack-sdk)
  → select browserstack config YAML (if BrowserStack)
  → existing lane/worker infrastructure
  → per-file subprocess with isolated DB + port
  → pytest-playwright (local engine or BrowserStack CDP)
```

**BrowserStack SDK concurrency note:** The existing per-file subprocess model spawns multiple short-lived `browserstack-sdk pytest` processes. This must be validated during Phase 2 — the SDK may expect a single invocation managing its own session pool. If per-file fan-out is incompatible, the BrowserStack command will need to run pytest as a single process across all test files rather than using the per-file worker model.

## Existing Patterns

**CLI subcommand pattern** (`src/promptgrimoire/cli/e2e/__init__.py`): All 7 existing subcommands follow the same structure — `@e2e_app.command()` with `typer.Context` for extra args passthrough, delegating to lane runner functions. New browser commands follow this exactly.

**Lane abstraction** (`src/promptgrimoire/cli/e2e/_lanes.py`): `LaneSpec` frozen dataclass defines `name`, `test_paths`, `marker_expr`, `needs_server`, `artifact_subdir`. Firefox reuses `PLAYWRIGHT_LANE` (same test paths and markers) — no new lane definition needed. The difference is in pytest args, not lane config.

**Worker subprocess model** (`src/promptgrimoire/cli/e2e/_workers.py`): `run_playwright_file()` builds a `cmd` list starting with `[sys.executable, "-m", "pytest", ...]`. BrowserStack changes this prefix to `["browserstack-sdk", "pytest", ...]`. The rest of the command (test file, markers, junit path, user args) is identical.

**StaticRange usage** (`src/promptgrimoire/static/annotation-highlight.js`): The `charOffsetToRange()` function (line 167) constructs all CSS Highlight API ranges via `new StaticRange(...)`. This is compatible with Safari's CSS Highlight API, which only supports `StaticRange`. The few `document.createRange()` calls (lines 224, 236) are for `getBoundingClientRect()` lookups, not for highlight registration.

**Divergence:** BrowserStack introduces a new dependency (`browserstack-sdk`) and external configuration files (`browserstack/*.yml`). This is a new pattern — no external test service integration exists in the codebase today.

## Implementation Phases

<!-- START_PHASE_0 -->
### Phase 0: Browser Gate Caniuse Audit

**Goal:** Validate browser gate minimum versions against caniuse data before writing any BrowserStack configs.

**Components:**
- Caniuse lookup for CSS Custom Highlight API — verify minimum Safari, Firefox, Chrome, Edge versions
- Update login page JS if gate thresholds don't match caniuse data
- Document the validated thresholds for use in Phase 2 unsupported tier config

**Dependencies:** None (pre-work)

**Done when:** Gate minimum versions match caniuse data. Thresholds documented for BrowserStack config.

**Validated thresholds (caniuse `mdn-api_highlight`, verified 2026-03-12):**

| Browser | Minimum Version | caniuse First Support |
|---------|-----------------|----------------------|
| Chrome  | 105+            | 105                  |
| Edge    | 105+            | 105                  |
| Firefox | 140+            | 140                  |
| Safari  | 17.2+           | 17.2                 |

Gate JS in `auth.py:79-81` matches. No changes needed.

Note: Firefox 140 is the first version with **full** CSS Custom Highlight API support (the `Highlight` interface and `CSS.highlights` registry). Earlier Firefox versions had partial implementations behind flags. The gate checks `CSS.highlights` availability, so 140 is the correct minimum.
<!-- END_PHASE_0 -->

<!-- START_PHASE_1 -->
### Phase 1: Playwright Firefox CLI Commands

**Goal:** Add `e2e firefox` and `e2e all-browsers` subcommands that run the existing E2E suite against Playwright's bundled Firefox engine.

**Components:**
- CLI subcommands in `src/promptgrimoire/cli/e2e/__init__.py` — two new `@e2e_app.command()` functions following the existing pattern
- `_workers.py` modification — accept an optional `browser` parameter that prepends `--browser {name}` to the pytest command
- `playwright install` step — CI workflow updated to install `firefox` alongside `chromium`
- `pytest.ini` marker — `browser_gate` marker for gate-specific tests
- `all-browsers` runs Chromium then Firefox, reporting per-browser results; `--fail-fast` opt-in

**Dependencies:** None

**Done when:** `uv run grimoire e2e firefox` runs the full E2E suite on Firefox, `uv run grimoire e2e all-browsers` runs Chromium then Firefox sequentially with per-browser summary. CI matrix runs Chromium + Firefox.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: BrowserStack Integration

**Goal:** Add `e2e browserstack [profile]` subcommand that runs E2E tests against real browsers via BrowserStack.

**Components:**
- `browserstack-sdk` dependency in `pyproject.toml` (dev dependency)
- BrowserStack YAML configs in `browserstack/` directory — `supported.yml`, `unsupported.yml`, `safari.yml`, `firefox.yml`
- CLI subcommand in `src/promptgrimoire/cli/e2e/__init__.py` — `browserstack` command with optional profile argument, selecting YAML config via `--browserstack.config`
- Worker modification in `_workers.py` — swap subprocess command prefix to `["browserstack-sdk", "pytest"]` when BrowserStack mode is active
- Credentials via `BROWSERSTACK_USERNAME` and `BROWSERSTACK_ACCESS_KEY` env vars (never in repo)
- Validate SDK concurrency model — test per-file fan-out vs single-process invocation

**Dependencies:** Phase 0 (caniuse thresholds inform unsupported.yml versions), Phase 1 (browser_gate marker exists)

**Done when:** `uv run grimoire e2e browserstack` runs full suite against supported real browsers, `uv run grimoire e2e browserstack safari` targets Safari only, unsupported tier runs gate-only tests against older browsers.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: CI Pipeline Integration

**Goal:** GitHub Actions runs Firefox in the E2E matrix and BrowserStack as a final PR gate.

**Components:**
- `.github/workflows/ci.yml` — E2E job becomes matrix strategy (`browser: [chromium, firefox]`), `playwright install --with-deps` installs selected browser
- New BrowserStack CI job — depends on all other jobs passing, runs only on PRs, uses GitHub Secrets for credentials
- BrowserStack job runs `uv run grimoire e2e browserstack` (supported tier full suite + unsupported tier gate-only)

**Dependencies:** Phase 2 (BrowserStack commands work locally)

**Done when:** PRs trigger Chromium + Firefox E2E matrix, BrowserStack job runs after all checks pass, BrowserStack failures block merge.
<!-- END_PHASE_3 -->

## Additional Considerations

**BrowserStack SDK concurrency model:** The per-file subprocess worker model may be incompatible with BrowserStack SDK's session management. The SDK may expect a single invocation managing its own parallelism and Local tunnel lifecycle. Phase 2 must validate this early — if per-file fan-out is incompatible, the BrowserStack command will need to bypass the worker model and run pytest as a single process.

**BrowserStack costs:** BrowserStack runs consume plan minutes. The CI job only triggers on PRs after all other checks pass, minimising spend. If costs become a concern, the job can be further restricted to specific PR labels.

**Race condition sensitivity:** NiceGUI's async task reordering may manifest differently across browser engines. The existing value-capture (`on_submit_with_value`) and rebuild-epoch patterns should handle this, but Firefox/Safari may surface new timing-dependent failures. These are genuine cross-browser bugs to investigate, not tests to skip.

**Safari StaticRange compatibility:** Verified that `annotation-highlight.js` uses `new StaticRange(...)` exclusively for CSS Highlight API ranges (line 183). Safari's implementation requires StaticRange — no code changes needed.
