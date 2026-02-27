# Test Requirements — Bottom-Anchored Tag Bar

Generated from acceptance criteria in `docs/design-plans/2026-02-27-bottom-tag-bar.md`.

---

## Coverage Matrix

| AC | Description | Phase | Verification Method |
|----|-------------|-------|-------------------|
| bottom-tag-bar.AC1.1 | Toolbar `position: fixed; bottom: 0` | 1 | E2E (Phase 5: `test_structural_css_properties`) + Human UAT |
| bottom-tag-bar.AC1.2 | Box-shadow above toolbar | 1 | E2E (Phase 5: `test_structural_css_properties`) + Human UAT |
| bottom-tag-bar.AC1.3 | Content not hidden behind toolbar | 1 | E2E (Phase 5: `test_layout_correctness`) + Human UAT |
| bottom-tag-bar.AC1.4 | Padding adjusts when toolbar wraps | 1 | Human UAT (requires many tags to force wrapping) |
| bottom-tag-bar.AC2.1 | No inline title | 2 | E2E (Phase 5: `test_layout_correctness`) + Human UAT |
| bottom-tag-bar.AC2.2 | No UUID label | 2 | E2E (Phase 5: `test_layout_correctness`) + Human UAT |
| bottom-tag-bar.AC2.3 | Header row renders correctly | 2 | E2E (Phase 5: `test_layout_correctness`) + Human UAT |
| bottom-tag-bar.AC3.1 | Menu below selection (default) | 4 | Human UAT |
| bottom-tag-bar.AC3.2 | Menu left edge aligns with selection end | 4 | Human UAT |
| bottom-tag-bar.AC3.3 | Menu flips above when near bottom | 4 | Human UAT |
| bottom-tag-bar.AC3.4 | Menu never overlaps toolbar | 4 | Human UAT |
| bottom-tag-bar.AC3.5 | Menu z-index above toolbar | 4 | E2E (Phase 5: `test_structural_css_properties`) + Human UAT |
| bottom-tag-bar.AC3.6 | Menu stays below at very top | 4 | Human UAT |
| bottom-tag-bar.AC4.1 | Compact button padding | 1 | E2E (Phase 5: `test_structural_css_properties`) |
| bottom-tag-bar.AC5.1 | E2E verifies computed CSS | 5 | E2E (self-verifying) |
| bottom-tag-bar.AC5.2 | Test fails on mismatch | 5 | E2E (self-verifying) |

### Operational Verification Targets

| ID | Description | Phase |
|----|-------------|-------|
| OP1 | Annotation cards near viewport bottom visible above toolbar, not hidden behind it | 3 |

---

## Automated E2E Tests (Phase 5)

All automated tests live in `tests/e2e/test_css_audit.py`.

### `test_structural_css_properties`

Quasar regression guard. Asserts computed CSS on key elements:

| Element | Locator | Property | Expected | AC |
|---------|---------|----------|----------|----|
| Toolbar wrapper | `#tag-toolbar-wrapper` | `position` | `fixed` | AC1.1 |
| Toolbar wrapper | `#tag-toolbar-wrapper` | `bottom` | `0px` | AC1.1 |
| Toolbar wrapper | `#tag-toolbar-wrapper` | `box-shadow` | `rgba(0, 0, 0, 0.1) 0px -2px 4px 0px` | AC1.2 |
| Compact button | `.q-btn.compact-btn >> nth=0` | `padding` | `0px 6px` | AC4.1 |
| Highlight menu | `#highlight-menu` | `z-index` | `110` | AC3.5 |

### `test_layout_correctness`

Behavioural layout assertions:

| Check | Method | AC |
|-------|--------|----|
| Toolbar at viewport bottom | `bounding_box()`: `toolbar.y + toolbar.height ≈ viewport.height` (±1px) | AC1.1, AC1.3 |
| Content not obscured | `bounding_box()`: `content.y + content.height <= toolbar.y` | AC1.3 |
| No inline title | `expect(page.locator(".text-2xl.font-bold")).to_have_count(0)` | AC2.1 |
| No UUID label | `expect(page.locator("text=/Workspace: [0-9a-f-]+/")).not_to_be_visible()` | AC2.2 |
| Header row visible | Single committed locator (executor inspects `render_workspace_header()`) | AC2.3 |

---

## Human UAT Requirements

These ACs require manual verification because they depend on visual appearance, user interaction (text selection), or dynamic resizing that cannot be reliably automated:

### Phase 1 UAT

1. **AC1.1**: Toolbar at bottom of viewport, not top
2. **AC1.2**: Shadow above toolbar (subtle upward shadow), not below
3. **AC1.3**: Scroll to bottom — last paragraph fully visible above toolbar
4. **AC1.4**: Resize window narrower to force tag wrapping — padding adjusts, content not obscured

### Phase 2 UAT

5. **AC2.1**: No "Annotation Workspace" heading in page content area (navigator title is fine)
6. **AC2.2**: No "Workspace: \<uuid\>" text on page
7. **AC2.3**: Header row (save status, user count, export, sharing) visible and correctly positioned

### Phase 3 UAT (Operational Verification)

8. **OP1**: Scroll to bottom — annotation cards near viewport bottom visible above toolbar
9. **OP1**: Scroll to top — cards visible without 60px dead zone

### Phase 4 UAT

10. **AC3.1**: Select text in middle of page — menu appears below selection
11. **AC3.2**: Menu left edge aligns with end of selection
12. **AC3.3**: Select text near bottom — menu flips above selection
13. **AC3.4**: Menu does not overlap or render behind toolbar
14. **AC3.5**: In DevTools, highlight menu `z-index: 110` > toolbar `z-index: 100`
15. **AC3.6**: Select text at very top — menu stays below (z-index handles any overlap)

---

## Test Infrastructure

- **E2E fixture**: `authenticated_page` (from `tests/e2e/conftest.py`)
- **Workspace creation**: `_create_workspace_via_db()` with simple HTML content
- **Render wait**: `wait_for_text_walker(page, timeout=15000)`
- **Run command**: `uv run test-e2e -k test_css_audit`
- **Changed-only**: `uv run test-e2e-changed`
