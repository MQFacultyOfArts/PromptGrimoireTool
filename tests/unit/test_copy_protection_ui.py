"""Tests for copy protection UI mapping functions.

Unit tests for the pure model-to-UI and UI-to-model conversion functions
used in the per-activity copy protection tri-state control.

Verifies AC7.2 (tri-state control), AC7.3 (default to inherit),
AC7.4 (explicit override), AC7.5 (reset to inherit).
"""

from __future__ import annotations

import pytest

from promptgrimoire.pages.courses import (
    _model_to_ui,
    _tri_state_options,
    _ui_to_model,
)


class TestModelToUi:
    """Tests for _model_to_ui: converts model tri-state to UI select value."""

    def test_none_returns_inherit(self) -> None:
        """None (inherit from course) maps to 'inherit'."""
        assert _model_to_ui(None) == "inherit"

    def test_true_returns_on(self) -> None:
        """True (explicitly on) maps to 'on'."""
        assert _model_to_ui(True) == "on"

    def test_false_returns_off(self) -> None:
        """False (explicitly off) maps to 'off'."""
        assert _model_to_ui(False) == "off"


class TestUiToModel:
    """Tests for _ui_to_model: converts UI select value to model tri-state."""

    def test_inherit_returns_none(self) -> None:
        """'inherit' maps to None (clear override, inherit from course)."""
        assert _ui_to_model("inherit") is None

    def test_on_returns_true(self) -> None:
        """'on' maps to True (explicit copy protection on)."""
        assert _ui_to_model("on") is True

    def test_off_returns_false(self) -> None:
        """'off' maps to False (explicit copy protection off)."""
        assert _ui_to_model("off") is False


class TestTriStateOptions:
    """Tests for _tri_state_options factory function."""

    def test_has_three_options(self) -> None:
        """Options dict has exactly three entries."""
        assert len(_tri_state_options()) == 3

    def test_keys_are_inherit_on_off(self) -> None:
        """Option keys are 'inherit', 'on', 'off'."""
        assert set(_tri_state_options().keys()) == {"inherit", "on", "off"}

    def test_inherit_label_mentions_unit(self) -> None:
        """Inherit option label mentions 'unit' for clarity."""
        assert "unit" in _tri_state_options()["inherit"].lower()

    def test_custom_labels(self) -> None:
        """Custom on/off labels are used in the returned dict."""
        opts = _tri_state_options(on_label="Allowed", off_label="Not allowed")
        assert opts["on"] == "Allowed"
        assert opts["off"] == "Not allowed"

    def test_default_labels(self) -> None:
        """Default on/off labels are 'On' and 'Off'."""
        opts = _tri_state_options()
        assert opts["on"] == "On"
        assert opts["off"] == "Off"


class TestRoundTrip:
    """Tests that model->UI->model and UI->model->UI round-trip correctly."""

    @pytest.mark.parametrize(
        "model_value",
        [None, True, False],
        ids=["inherit", "on", "off"],
    )
    def test_model_roundtrip(self, model_value: bool | None) -> None:
        """model -> UI -> model preserves value."""
        assert _ui_to_model(_model_to_ui(model_value)) is model_value

    @pytest.mark.parametrize(
        "ui_value",
        ["inherit", "on", "off"],
    )
    def test_ui_roundtrip(self, ui_value: str) -> None:
        """UI -> model -> UI preserves value."""
        assert _model_to_ui(_ui_to_model(ui_value)) == ui_value
