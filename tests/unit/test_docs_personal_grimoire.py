"""Tests for the personal_grimoire guide script module.

Verifies:
- personal-grimoire-guide-208.AC1: _SAMPLE_HTML is non-empty and well-formed HTML
- personal-grimoire-guide-208.AC1: GUIDE_OUTPUT_DIR resolves to docs/guides
- personal-grimoire-guide-208.AC2.1: _setup_loose_student issues correct subprocess
  commands
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from promptgrimoire.docs.scripts.personal_grimoire import (
    _SAMPLE_HTML,
    GUIDE_OUTPUT_DIR,
    _setup_loose_student,
)


class TestSampleHTML:
    """Tests for the _SAMPLE_HTML module-level constant."""

    def test_sample_html_is_non_empty(self) -> None:
        """_SAMPLE_HTML must contain content — not an empty string."""
        assert _SAMPLE_HTML

    def test_sample_html_starts_with_div(self) -> None:
        """_SAMPLE_HTML must begin with a <div> tag (well-formed root element)."""
        stripped = _SAMPLE_HTML.strip()
        assert stripped.startswith("<div"), (
            f"Expected _SAMPLE_HTML to start with '<div', got: {stripped[:40]!r}"
        )

    def test_sample_html_ends_with_closing_div(self) -> None:
        """_SAMPLE_HTML must end with a closing </div> tag."""
        stripped = _SAMPLE_HTML.strip()
        assert stripped.endswith("</div>"), (
            f"Expected _SAMPLE_HTML to end with '</div>', got: ...{stripped[-20:]!r}"
        )

    def test_sample_html_contains_user_turn(self) -> None:
        """_SAMPLE_HTML must contain a user/Human turn marker."""
        assert "Human:" in _SAMPLE_HTML

    def test_sample_html_contains_assistant_turn(self) -> None:
        """_SAMPLE_HTML must contain an assistant/AI turn marker."""
        assert "Assistant:" in _SAMPLE_HTML

    def test_sample_html_contains_japanese_legal_content(self) -> None:
        """_SAMPLE_HTML must reference Japanese legal translation content."""
        assert "good faith" in _SAMPLE_HTML


class TestGuideOutputDir:
    """Tests for the GUIDE_OUTPUT_DIR module-level constant."""

    def test_guide_output_dir_is_path_instance(self) -> None:
        """GUIDE_OUTPUT_DIR must be a pathlib.Path instance."""
        assert isinstance(GUIDE_OUTPUT_DIR, Path)

    def test_guide_output_dir_resolves_to_docs_guides(self) -> None:
        """GUIDE_OUTPUT_DIR must be Path('docs/guides')."""
        assert Path("docs/guides") == GUIDE_OUTPUT_DIR

    def test_guide_output_dir_parts(self) -> None:
        """GUIDE_OUTPUT_DIR must have exactly two parts: 'docs' and 'guides'."""
        assert GUIDE_OUTPUT_DIR.parts == ("docs", "guides")


class TestSetupLooseStudent:
    """Tests for the _setup_loose_student setup helper."""

    @pytest.fixture()
    def mock_run(self) -> MagicMock:
        """Patch subprocess.run and invoke _setup_loose_student."""
        with patch("subprocess.run") as patched:
            _setup_loose_student()
        return patched

    def test_calls_create_user(self, mock_run: MagicMock) -> None:
        """_setup_loose_student must invoke manage-users create for the student."""
        create_cmd = mock_run.call_args_list[0][0][0]
        assert create_cmd[:4] == ["uv", "run", "manage-users", "create"]
        assert "loose-student@test.example.edu.au" in create_cmd

    def test_calls_enroll_user(self, mock_run: MagicMock) -> None:
        """_setup_loose_student must invoke manage-users enroll for UNIT1234."""
        enroll_cmd = mock_run.call_args_list[1][0][0]
        assert enroll_cmd[:4] == ["uv", "run", "manage-users", "enroll"]
        assert "loose-student@test.example.edu.au" in enroll_cmd
        assert "UNIT1234" in enroll_cmd

    def test_runs_exactly_two_commands(self, mock_run: MagicMock) -> None:
        """_setup_loose_student must run exactly two subprocess commands."""
        assert mock_run.call_count == 2

    def test_uses_capture_output(self, mock_run: MagicMock) -> None:
        """_setup_loose_student must use capture_output=True to suppress output."""
        for c in mock_run.call_args_list:
            assert c.kwargs.get("capture_output") is True

    def test_uses_check_false(self, mock_run: MagicMock) -> None:
        """_setup_loose_student must use check=False (idempotent: user may exist)."""
        for c in mock_run.call_args_list:
            assert c.kwargs.get("check") is False

    def test_create_includes_name_flag(self, mock_run: MagicMock) -> None:
        """_setup_loose_student create command must pass --name 'Loose Student'."""
        create_cmd = mock_run.call_args_list[0][0][0]
        name_idx = create_cmd.index("--name")
        assert create_cmd[name_idx + 1] == "Loose Student"

    def test_enroll_includes_session(self, mock_run: MagicMock) -> None:
        """_setup_loose_student enroll command must specify session 'S1 2026'."""
        enroll_cmd = mock_run.call_args_list[1][0][0]
        assert "S1 2026" in enroll_cmd
