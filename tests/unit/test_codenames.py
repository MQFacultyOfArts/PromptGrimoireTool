"""Unit tests for wargame codename generation."""

from __future__ import annotations

import pytest


class TestGenerateCodename:
    """Tests for generate_codename."""

    def test_returns_uppercase_slug_from_patched_generator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC1.1: Returned codenames are normalized to uppercase."""
        from promptgrimoire.wargame import generate_codename

        monkeypatch.setattr(
            "promptgrimoire.wargame.codenames.generate_slug",
            lambda _words: "bold-griffin",
        )

        result = generate_codename(existing=set())

        assert result == "BOLD-GRIFFIN"

    def test_retries_until_it_finds_a_unique_slug(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC1.2: Collisions retry until a unique codename is found."""
        from promptgrimoire.wargame import generate_codename

        generated = iter(["bold-griffin", "calm-otter"])
        call_count = 0

        def _fake_generate_slug(_words: int) -> str:
            nonlocal call_count
            call_count += 1
            return next(generated)

        monkeypatch.setattr(
            "promptgrimoire.wargame.codenames.generate_slug",
            _fake_generate_slug,
        )

        result = generate_codename(existing={"BOLD-GRIFFIN"})

        assert result == "CALM-OTTER"
        assert call_count == 2

    def test_raises_after_max_attempts_when_all_candidates_collide(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC1.3: Exhausting the retry cap raises a RuntimeError."""
        from promptgrimoire.wargame import generate_codename

        monkeypatch.setattr(
            "promptgrimoire.wargame.codenames.generate_slug",
            lambda _words: "bold-griffin",
        )

        with pytest.raises(RuntimeError, match="3"):
            generate_codename(existing={"BOLD-GRIFFIN"}, max_attempts=3)
