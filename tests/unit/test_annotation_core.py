"""Guard: the annotation functional core must be importable without NiceGUI.

The snapshot delivery worker (and any future standalone process) builds
sidebar items and tag metadata from this module.  Standalone workers follow
the export-worker discipline of never importing NiceGUI, so the core must
not pull it in transitively.  A same-process assertion would be vacuous
(the test suite imports NiceGUI elsewhere), so the check runs in a fresh
interpreter.
"""

from __future__ import annotations

import subprocess
import sys

_PROBE = """
import sys
import promptgrimoire.annotation_core
import promptgrimoire.input_pipeline.paragraph_map
import promptgrimoire.crdt.annotation_doc
import promptgrimoire.snapshot
banned = sorted(m for m in sys.modules if m == "nicegui" or m.startswith("nicegui."))
if banned:
    print("NiceGUI imported transitively: " + ", ".join(banned))
    sys.exit(1)
print("ok")
"""


def test_annotation_core_imports_without_nicegui() -> None:
    """Importing the core in a fresh interpreter must not load nicegui."""
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"


def test_old_import_paths_still_resolve() -> None:
    """The pages.annotation shims must keep exporting the relocated names."""
    from promptgrimoire.annotation_core import (
        TagInfo,
        author_initials,
        group_highlights_by_tag,
        serialise_items,
        workspace_tags_from_crdt,
    )
    from promptgrimoire.pages.annotation.card_shared import (
        author_initials as shim_initials,
    )
    from promptgrimoire.pages.annotation.items_serialise import (
        serialise_items as shim_serialise,
    )
    from promptgrimoire.pages.annotation.tags import (
        TagInfo as shim_taginfo,
    )
    from promptgrimoire.pages.annotation.tags import (
        workspace_tags_from_crdt as shim_tags_from_crdt,
    )

    assert shim_initials is author_initials
    assert shim_serialise is serialise_items
    assert shim_taginfo is TagInfo
    assert shim_tags_from_crdt is workspace_tags_from_crdt
    assert callable(group_highlights_by_tag)


def test_group_highlights_by_tag_groups_and_defaults() -> None:
    """Grouping matches the shape applyHighlights() consumes."""
    from promptgrimoire.annotation_core import group_highlights_by_tag

    highlights = [
        {"id": "h1", "tag": "t1", "start_char": 0, "end_char": 5},
        {"id": "h2", "tag": "t1", "start_char": 10, "end_char": 15},
        {"id": "h3", "tag": "t2", "start_char": 20, "end_char": 25},
        {"id": "h4", "start_char": 30, "end_char": 35},  # missing tag
    ]
    grouped = group_highlights_by_tag(highlights)
    assert set(grouped) == {"t1", "t2", "highlight"}
    assert [h["id"] for h in grouped["t1"]] == ["h1", "h2"]
    assert grouped["t2"] == [{"start_char": 20, "end_char": 25, "id": "h3"}]
    assert grouped["highlight"][0]["start_char"] == 30
