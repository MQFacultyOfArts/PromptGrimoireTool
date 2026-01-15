"""PromptGrimoire - A collaborative tool for prompt iteration and annotation.

A classroom grimoire for prompt iteration, annotation, and sharing
in educational contexts.
"""

import os

__version__ = "0.1.0"


def main() -> None:
    """Entry point for the PromptGrimoire application."""
    from dotenv import load_dotenv
    from nicegui import ui

    load_dotenv()

    import promptgrimoire.pages  # noqa: F401 - registers routes

    port = int(os.environ.get("PROMPTGRIMOIRE_PORT", "8080"))
    storage_secret = os.environ.get("STORAGE_SECRET", "dev-secret-change-me")

    print(f"PromptGrimoire v{__version__}")
    print(f"Starting application on http://localhost:{port}")

    ui.run(port=port, reload=False, storage_secret=storage_secret)


if __name__ == "__main__":
    main()
