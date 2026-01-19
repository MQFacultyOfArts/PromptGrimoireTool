"""NiceGUI pages for PromptGrimoire.

Import this module to register all page routes with NiceGUI.
"""

from promptgrimoire.pages import auth, roleplay, sync_demo, text_selection

__all__ = ["auth", "roleplay", "sync_demo", "text_selection"]

# Touch modules to prevent linter from removing "unused" imports.
# These imports register @ui.page decorators as a side effect.
_PAGES = (auth, roleplay, sync_demo, text_selection)
