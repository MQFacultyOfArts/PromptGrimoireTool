"""Tests for dialog components.

Note: Full dialog interaction tests require E2E testing with Playwright.
These unit tests verify the module structure and imports.
"""


class TestContentTypeDialog:
    """Tests for show_content_type_dialog module structure."""

    def test_import_function(self) -> None:
        """Function can be imported."""
        from promptgrimoire.pages.dialogs import show_content_type_dialog

        assert callable(show_content_type_dialog)

    def test_import_from_pages(self) -> None:
        """Function can be imported from pages package."""
        from promptgrimoire.pages import show_content_type_dialog

        assert callable(show_content_type_dialog)

    def test_function_is_async(self) -> None:
        """Function is an async function."""
        import inspect

        from promptgrimoire.pages.dialogs import show_content_type_dialog

        assert inspect.iscoroutinefunction(show_content_type_dialog)

    def test_accepts_required_params(self) -> None:
        """Function signature accepts required parameters."""
        import inspect

        from promptgrimoire.pages.dialogs import show_content_type_dialog

        sig = inspect.signature(show_content_type_dialog)
        params = list(sig.parameters.keys())

        assert "detected_type" in params
        assert "preview" in params
        assert "source_numbering_detected" in params

    def test_source_numbering_detected_defaults_false(self) -> None:
        """source_numbering_detected parameter defaults to False."""
        import inspect

        from promptgrimoire.pages.dialogs import show_content_type_dialog

        sig = inspect.signature(show_content_type_dialog)
        param = sig.parameters["source_numbering_detected"]
        assert param.default is False
