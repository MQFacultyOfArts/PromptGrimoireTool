"""Shared helper functions for annotation E2E tests.

This module has been decomposed into focused helper modules:

- tag_helpers.py: Tag seeding, deterministic UUIDs, tag locking
- db_fixtures.py: Direct-SQL workspace creation
- highlight_tools.py: Highlight creation, text selection, CSS highlight waits
- fixture_loaders.py: UI-based workspace setup and fixture loading
- page_interactions.py: Navigation, drag-and-drop, sharing helpers
- export_tools.py: PDF/LaTeX export helpers

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/design-plans/2026-01-30-workspace-model.md
- Test consolidation: docs/design-plans/2026-01-31-test-suite-consolidation.md
"""
