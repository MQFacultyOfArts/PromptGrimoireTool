"""NiceGUI pages for PromptGrimoire.

Import this module to register all page routes with NiceGUI.
"""

from promptgrimoire.pages import (
    annotation,
    auth,
    courses,
    index,
    logviewer,
    milkdown_spike,
    roleplay,
    sync_demo,
    text_selection,
)
from promptgrimoire.pages.dialogs import show_content_type_dialog

__all__ = [
    "annotation",
    "auth",
    "courses",
    "index",
    "logviewer",
    "milkdown_spike",
    "roleplay",
    "show_content_type_dialog",
    "sync_demo",
    "text_selection",
]

# Touch modules to prevent linter from removing "unused" imports.
# These imports register @ui.page decorators as a side effect.
_PAGES = (
    annotation,
    auth,
    courses,
    index,
    logviewer,
    milkdown_spike,
    roleplay,
    sync_demo,
    text_selection,
)
