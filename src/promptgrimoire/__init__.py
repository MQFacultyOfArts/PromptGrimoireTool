"""PromptGrimoire - A collaborative tool for prompt iteration and annotation.

A classroom grimoire for prompt iteration, annotation, and sharing
in educational contexts.
"""

import os

__version__ = "0.1.0"


def main() -> None:
    """Entry point for the PromptGrimoire application."""
    # Late imports to avoid circular dependencies and allow module-level usage
    from nicegui import ui  # noqa: PLC0415

    import promptgrimoire.pages.sync_demo  # noqa: PLC0415
    import promptgrimoire.pages.text_selection  # noqa: F401, PLC0415

    port = int(os.environ.get("PROMPTGRIMOIRE_PORT", "8080"))

    print(f"PromptGrimoire v{__version__}")
    print(f"Starting application on http://localhost:{port}")

    ui.run(port=port, reload=False)


if __name__ == "__main__":
    main()
