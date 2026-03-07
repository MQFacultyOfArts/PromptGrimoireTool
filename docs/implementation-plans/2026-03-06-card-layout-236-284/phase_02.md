# Annotation Card Layout — Phase 2: E2E Card Helpers and Runner Shortcut

**Goal:** Build test infrastructure for card expand/collapse interactions and a CLI shortcut for running card-touching tests.

**Architecture:** Add `expand_card()` and `collapse_card()` helpers to `annotation_helpers.py` using test-audit wait patterns (state-based waits + animation frame, no sleeps). Update `add_comment_to_highlight()` to auto-expand before interacting. Add `cards` pytest marker and `uv run grimoire e2e cards` CLI subcommand.

**Tech Stack:** Playwright, pytest markers, Typer CLI

**Scope:** Phase 2 of 4 from original design (phases 1-4)

**Codebase verified:** 2026-03-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### card-layout-236-284.AC3: E2E card helpers and test updates
- **card-layout-236-284.AC3.1 Success:** `expand_card(page, card_index)` clicks `data-testid="card-expand-btn"` on the nth card and waits for detail section visible
- **card-layout-236-284.AC3.2 Success:** `collapse_card(page, card_index)` clicks chevron and waits for detail section hidden

### card-layout-236-284.AC4: `e2e cards` runner shortcut
- **card-layout-236-284.AC4.1 Success:** `uv run grimoire e2e cards` discovers and runs all `@pytest.mark.cards`-marked tests
- **card-layout-236-284.AC4.2 Success:** `cards` marker defined in `pyproject.toml` so pytest doesn't warn about unknown markers
- **card-layout-236-284.AC4.3 Edge:** Running `uv run grimoire e2e cards` with no marked tests exits cleanly (no error)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add `expand_card` and `collapse_card` helpers

**Verifies:** card-layout-236-284.AC3.1, card-layout-236-284.AC3.2

**Files:**
- Modify: `tests/e2e/annotation_helpers.py` (append after line 1005, before the "Sharing helpers" section comment at line 1006)

**Implementation:**

Add two helpers after the `count_comment_delete_buttons` function (line 999) and before the sharing helpers section comment (line 1002):

```python
def expand_card(page: Page, card_index: int = 0) -> None:
    """Expand an annotation card's detail section.

    Clicks the card's expand button and waits for the detail section
    to become visible, then waits one animation frame for
    ``positionCards()`` to re-run.

    Following test-audit patterns: state-based waits, no sleeps.

    Args:
        page: Playwright page with annotation workspace loaded.
        card_index: 0-based index of the annotation card.
    """
    card = page.locator("[data-testid='annotation-card']").nth(card_index)
    card.wait_for(state="visible", timeout=10000)

    detail = card.get_by_test_id("card-detail")
    if detail.is_visible():
        return  # already expanded

    expand_btn = card.get_by_test_id("card-expand-btn")
    expand_btn.click()

    detail.wait_for(state="visible", timeout=5000)
    # Wait one animation frame for positionCards() to re-run
    page.wait_for_function("new Promise(r => requestAnimationFrame(r))")


def collapse_card(page: Page, card_index: int = 0) -> None:
    """Collapse an annotation card's detail section.

    Clicks the card's expand button (toggles to collapse) and waits
    for the detail section to become hidden, then waits one animation
    frame for ``positionCards()`` to re-run.

    Following test-audit patterns: state-based waits, no sleeps.

    Args:
        page: Playwright page with annotation workspace loaded.
        card_index: 0-based index of the annotation card.
    """
    card = page.locator("[data-testid='annotation-card']").nth(card_index)
    card.wait_for(state="visible", timeout=10000)

    detail = card.get_by_test_id("card-detail")
    if not detail.is_visible():
        return  # already collapsed

    expand_btn = card.get_by_test_id("card-expand-btn")
    expand_btn.click()

    detail.wait_for(state="hidden", timeout=5000)
    # Wait one animation frame for positionCards() to re-run
    page.wait_for_function("new Promise(r => requestAnimationFrame(r))")
```

**Verification:**

These helpers are verified by Phase 3 tests and by the `add_comment_to_highlight` update in Task 2.

**Commit:** `feat(e2e): add expand_card and collapse_card helpers`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update `add_comment_to_highlight` to auto-expand

**Verifies:** card-layout-236-284.AC3.1 (implicitly — auto-expand uses `expand_card`)

**Files:**
- Modify: `tests/e2e/annotation_helpers.py:951-968` (`add_comment_to_highlight` function)

**Implementation:**

Update `add_comment_to_highlight` to call `expand_card` before interacting with comment input. The detail section (containing comment-input) is hidden by default in collapsed cards, so this helper must expand the card first.

Replace the existing function body (lines 951-968) with:

```python
def add_comment_to_highlight(page: Page, text: str, *, card_index: int = 0) -> None:
    """Add a comment to an annotation card via the Post button.

    Automatically expands the card if collapsed, since the comment
    input is inside the detail section.

    Args:
        page: Playwright page with an annotation workspace loaded.
        text: Comment text to post.
        card_index: 0-based index of the annotation card.
    """
    expand_card(page, card_index)

    card = page.locator("[data-testid='annotation-card']").nth(card_index)

    comment_input = card.get_by_test_id("comment-input")
    comment_input.fill(text)
    card.get_by_test_id("post-comment-btn").click()

    card.locator("[data-testid='comment']", has_text=text).wait_for(
        state="visible", timeout=10000
    )
```

This keeps existing tests working — they call `add_comment_to_highlight` and it handles expansion transparently.

**Verification:**
Run: `uv run grimoire test changed`
Expected: Existing unit/integration tests still pass (no E2E yet — those need Phase 3).

**Commit:** `feat(e2e): auto-expand card in add_comment_to_highlight`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Export new helpers from annotation_helpers

**Verifies:** card-layout-236-284.AC3.1, card-layout-236-284.AC3.2

**Files:**
- Verify: `tests/e2e/annotation_helpers.py` — confirm `expand_card` and `collapse_card` are importable (module-level functions, no `__all__` restriction)

**Implementation:**

No code change needed — `annotation_helpers.py` does not use `__all__`, so all module-level functions are importable. Verify by checking that the functions are at module level (not nested).

**Verification:**
Run: `python -c "from tests.e2e.annotation_helpers import expand_card, collapse_card; print('OK')"`
Expected: Prints `OK`

**Commit:** No separate commit needed — covered by Task 1 commit.

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->

<!-- START_TASK_4 -->
### Task 4: Add `cards` pytest marker to pyproject.toml

**Verifies:** card-layout-236-284.AC4.2

**Files:**
- Modify: `pyproject.toml:198-205` (markers list in `[tool.pytest.ini_options]`)

**Implementation:**

Add `cards` marker to the markers list. Insert after the `latex` marker line (line 204), before the closing `]` (line 205):

```toml
    "cards: marks card-touching annotation E2E tests (run with 'uv run grimoire e2e cards')",
```

The full markers list becomes:
```toml
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "e2e: marks end-to-end tests requiring Playwright browsers",
    "nicegui_ui: marks in-process NiceGUI user_simulation UI tests",
    "blns: marks Big List of Naughty Strings tests (opt-in with '-m blns')",
    "perf: marks performance baseline tests (skip with '-m \"not perf\"')",
    "latex: marks tests requiring TinyTeX and system fonts (skip with '-m \"not latex\"')",
    "cards: marks card-touching annotation E2E tests (run with 'uv run grimoire e2e cards')",
]
```

**Verification:**
Run: `uv run pytest --markers | grep cards`
Expected: Shows the `cards` marker with its description.

**Commit:** `chore: add cards pytest marker`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add `e2e cards` CLI subcommand

**Verifies:** card-layout-236-284.AC4.1, card-layout-236-284.AC4.3

**Files:**
- Modify: `src/promptgrimoire/cli/e2e/__init__.py` (add `cards` command after the `changed` command, around line 327)

**Implementation:**

Add a `cards` command that runs Playwright tests filtered to `-m cards`. Follow the pattern of the existing `noretry` command (serial, single server, no retries) but with `-m "e2e and cards"` marker filter.

Insert after the `run_playwright_changed_lane` function (after line 326):

```python
@e2e_app.command(
    "cards",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    },
)
def cards(
    ctx: typer.Context,
    filter_expr: str | None = typer.Option(
        None, "-k", "--filter", help="Pytest keyword filter expression"
    ),
) -> None:
    """Run card-touching E2E tests (marked with @pytest.mark.cards)."""
    args = _prepend_filter(ctx.args, filter_expr)
    sys.exit(run_playwright_cards_lane(args))


def run_playwright_cards_lane(user_args: list[str]) -> int:
    """Run card-touching Playwright tests in serial mode."""
    from promptgrimoire.config import get_settings

    get_settings()
    _pre_test_db_cleanup()

    port = _allocate_ports(1)[0]

    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    os.environ["E2E_BASE_URL"] = url

    default_args = [
        "-m",
        "e2e and cards",
        "-v",
        "--tb=short",
        "--log-cli-level=WARNING",
    ]
    if not _has_test_path(user_args):
        default_args.insert(0, _PLAYWRIGHT_TEST_PATH)

    try:
        exit_code = _run_pytest(
            title=f"Playwright Card Tests (-m cards) — server {url}",
            log_path=Path("test-e2e.log"),
            default_args=default_args,
            extra_args=user_args,
        )
    finally:
        _stop_e2e_server(server_process)
    return exit_code
```

**Verification:**
Run: `uv run grimoire e2e cards --help`
Expected: Shows help text for the cards subcommand.

Run: `uv run grimoire e2e cards` (with no marked tests yet)
Expected: Exits cleanly with exit code 5 (no tests collected) — this is pytest's standard "no tests" exit code, not an error. Verifies AC4.3. Note: exit code 5 passes through `sys.exit()` directly. This is the same behaviour as the existing `noretry` and `changed` commands — pytest exit code 5 means "no tests matched the filter," which is expected when no tests are marked yet. CI systems that treat exit code 5 as failure should use `uv run grimoire e2e run` instead.

**Design note — no `--fail-fast` (`-x`):** The `cards` runner intentionally omits `-x` (fail-fast). During card UI development, seeing all failures at once is more useful than stopping at the first one. This matches the `changed` command's behaviour. Developers who want fail-fast can pass `-x` as an extra arg: `uv run grimoire e2e cards -- -x`.

**Commit:** `feat(cli): add e2e cards subcommand for card-touching tests`

<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

---

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Run: `uv run grimoire e2e cards --help` — verify the subcommand exists and shows help
3. [ ] Run: `uv run grimoire e2e cards` (with no marked tests) — verify exit code 5 (no tests collected), no crash
4. [ ] In a Python REPL: `from tests.e2e.annotation_helpers import expand_card, collapse_card` — verify imports succeed
5. [ ] Read `pyproject.toml` markers section — verify `cards` marker is present

## Evidence Required
- [ ] `uv run grimoire e2e cards --help` output
- [ ] `uv run pytest --markers | grep cards` shows the marker
