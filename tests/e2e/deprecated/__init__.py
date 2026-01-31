"""Deprecated E2E tests pending deletion.

These tests depend on /demo/* routes that are being removed.
Coverage has been migrated to:
- tests/e2e/test_annotation_basics.py
- tests/e2e/test_annotation_cards.py
- tests/e2e/test_annotation_highlights.py
- tests/e2e/test_annotation_workflows.py
- tests/e2e/test_annotation_sync.py
- tests/e2e/test_annotation_collab.py
- tests/e2e/test_auth_pages.py (pre-existing, covers isolation)

See docs/implementation-plans/2026-01-31-test-suite-consolidation/coverage-mapping.md
for the full coverage analysis.

These files will be deleted after verification period.
"""
