# WIP: Issue #97 — Workspace Sharing & Visibility (Seam E)

**Branch:** `97-workspace-sharing`
**Date:** 2026-02-23

## Completed Phases

- **Phase 1:** Data Model & Migration — schema changes, peer permission, PlacementContext resolution
- **Phase 2:** Permission Resolution Extension — student peer access path, list_peer_workspaces query
- **Phase 3:** CRDT User Identity & Comments — user_id on highlights/comments, anonymisation utility (coolname), comment UI
- **Phase 4:** Permission-Aware Rendering — PageState.effective_permission, UI gating for viewer/peer/editor/owner
- **Phase 5:** Sharing UX — activity/course settings, "Share with class" toggle, per-user sharing dialog

Also completed: Issue #185 (workspace.py refactoring into header.py, placement.py, sharing.py submodules).

## Next Up

- **Phase 6:** Peer Discovery & Instructor View
  - Peer workspace list on activity page (courses.py) — gated by allow_sharing
  - Instructor view page at new route — activity selector, workspace roster, stats
  - Activity-level stats (started/enrolled, not-started list)
  - Dependencies all met: list_peer_workspaces (Phase 2), anonymisation (Phase 3), sharing config (Phase 5)

- **Phase 7:** PDF Export Anonymity
  - Anonymised author names in PDF export
  - Broadcast cursor/selection label anonymisation

## Untracked

- `alembic/versions/9e0deda2d47a_merge_tag_group_color_and_sharing_.py` — merge migration resolving two Alembic heads (tag_group_color + sharing columns)
