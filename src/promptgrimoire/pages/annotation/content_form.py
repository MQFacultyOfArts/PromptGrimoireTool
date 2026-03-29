"""Content paste/upload form for the annotation page.

Thin orchestration layer that wires the paste interception script,
document submission handler, and file upload widget into the page.

Implementation details live in:
- ``upload_handler``: file type detection, preview, upload processing
- ``paste_handler``: client-side JS paste interception, submission logic
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from promptgrimoire.config import get_settings
from promptgrimoire.pages.annotation.paste_handler import (
    handle_add_document_submission,
)
from promptgrimoire.pages.annotation.paste_script import _build_paste_intercept_script
from promptgrimoire.pages.annotation.upload_handler import _handle_file_upload

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from nicegui.events import GenericEventArguments


def _render_add_content_form(
    workspace_id: UUID,
    on_document_added: Callable[[], object],
) -> None:
    """Render the add content form with editor and file upload.

    Extracted from _render_workspace_view to reduce function complexity.

    Args:
        workspace_id: The workspace to add documents to.
        on_document_added: Callback invoked after a document is successfully
            added (upload or paste).  Typically ``document_container.refresh``
            so the document area re-renders in-place without a page reload.
    """
    ui.label("Add content to annotate:").classes("mt-4 font-semibold")

    # HTML-aware editor for paste support (Quasar QEditor)
    content_input = (
        ui.editor(placeholder="Paste HTML content or type plain text here...")
        .classes("w-full min-h-32")
        .props('toolbar=[] data-testid="content-editor"')
    )  # Hide toolbar for minimal UI

    # Intercept paste, strip CSS client-side, store cleaned HTML.
    # Browsers include computed CSS (2.7MB for 32KB text). Strip it here.
    paste_var, platform_var = (
        f"_pastedHtml_{content_input.id}",
        f"_platformHint_{content_input.id}",
    )
    # NOTE: ui.add_body_html('<script>...') does NOT execute inline
    # scripts when delivered via WebSocket (insertAdjacentHTML ignores
    # <script> tags).  In the deferred-load path the socket is already
    # connected, so we must use ui.run_javascript() instead.
    # _build_paste_intercept_script returns a <script>…</script> block;
    # we strip the wrapper and eval the JS directly.
    raw_script = _build_paste_intercept_script(
        paste_var, platform_var, str(content_input.id)
    )
    # Strip <script> and </script> tags to get bare JS
    js_body = raw_script.replace("<script>", "").replace("</script>", "").strip()
    ui.run_javascript(js_body)

    # Wire submit button with JS that captures all three values at click
    # time and emits them as event args, avoiding the stale-value race
    # from python-socketio concurrent task dispatch.
    add_btn = (
        ui.button("Add Document")
        .props('data-testid="add-document-btn"')
        .classes("bg-green-500 text-white mt-2")
    )

    # JS handler: read paste buffer, platform hint, and editor DOM value
    # at click time, emit as a 3-element array.
    editor_hid = content_input.html_id
    js_capture = (
        f"() => {{"
        f"const paste = window.{paste_var} || null;"
        f"const platform = window.{platform_var} || null;"
        f"const edEl = document.getElementById('{editor_hid}');"
        f"const editor = edEl"
        f"  ? (edEl.querySelector('.q-editor__content')"
        f"     || edEl).innerHTML || ''"
        f"  : '';"
        f"emit([paste, platform, editor]);"
        f"}}"
    )

    async def _on_add_document(e: GenericEventArguments) -> None:
        args = e.args if isinstance(e.args, list) else [None, None, ""]
        paste_html: str | None = args[0] if len(args) > 0 else None
        platform_hint_val: str | None = args[1] if len(args) > 1 else None
        editor_val: str = str(args[2]) if len(args) > 2 and args[2] else ""

        await handle_add_document_submission(
            workspace_id=workspace_id,
            paste_html=paste_html,
            platform_hint=platform_hint_val,
            editor_content=editor_val,
            on_document_added=on_document_added,
        )
        # Clear paste buffer after submission (fire-and-forget)
        ui.run_javascript(f"window.{paste_var} = null")
        # Clear editor content
        content_input.value = ""

    add_btn.on("click", _on_add_document, js_handler=js_capture)

    # File upload for HTML, RTF, DOCX, PDF, TXT, Markdown files
    if get_settings().features.enable_file_upload:
        ui.upload(
            label="Or upload a file",
            on_upload=lambda e: _handle_file_upload(workspace_id, e, on_document_added),
            auto_upload=True,
            max_file_size=10 * 1024 * 1024,  # 10 MB limit
        ).props('accept=".html,.htm,.rtf,.docx,.pdf,.txt,.md,.markdown"').classes(
            "w-full"
        )
