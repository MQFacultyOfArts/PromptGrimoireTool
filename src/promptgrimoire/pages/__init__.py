"""NiceGUI pages for PromptGrimoire.

Import this module to register all page routes with NiceGUI.
"""

from promptgrimoire.pages import (
    auth,
    courses,
    index,
    live_annotation_demo,
    logviewer,
    roleplay,
    sync_demo,
    text_selection,
)

__all__ = [
    "auth",
    "courses",
    "index",
    "live_annotation_demo",
    "logviewer",
    "roleplay",
    "sync_demo",
    "text_selection",
]

# Touch modules to prevent linter from removing "unused" imports.
# These imports register @ui.page decorators as a side effect.
_PAGES = (
    auth,
    courses,
    index,
    live_annotation_demo,
    logviewer,
    roleplay,
    sync_demo,
    text_selection,
)
