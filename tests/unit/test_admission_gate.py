"""Tests for admission gate check in page_route decorator.

Verifies:
- AC3.1: User already in client_registry passes through freely
- AC3.2: Privileged users bypass gate regardless of cap
- AC3.3: New user redirected to /queue when at capacity
- AC3.5: User with valid entry ticket passes through
- AC3.6: User already in queue gets redirect with existing token
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest


@dataclass
class GateMocks:
    """Collected mocks for _check_admission_gate tests."""

    cr: Any  # client_registry mock
    adm: Any  # admission module mock
    ui: Any  # nicegui ui mock
    state: MagicMock


@pytest.fixture
def user_id() -> UUID:
    return uuid4()


@pytest.fixture
def user_id_str(user_id: UUID) -> str:
    return str(user_id)


@pytest.fixture
def auth_user(user_id_str: str) -> dict[str, object]:
    return {"user_id": user_id_str, "is_admin": False}


@pytest.fixture
def gate_mocks():
    """Patch client_registry, admission, and ui for gate tests."""
    with (
        patch("promptgrimoire.pages.registry.client_registry") as mock_cr,
        patch("promptgrimoire.pages.registry.admission") as mock_adm,
        patch("promptgrimoire.pages.registry.ui") as mock_ui,
    ):
        state = MagicMock(cap=100)
        state.try_enter.return_value = False
        mock_adm.get_admission_state.return_value = state
        mock_cr._registry = {}
        yield GateMocks(cr=mock_cr, adm=mock_adm, ui=mock_ui, state=state)


class TestCheckAdmissionGate:
    """Test _check_admission_gate function in isolation."""

    @pytest.mark.anyio
    async def test_registered_user_passes_through(
        self, user_id: UUID, user_id_str: str, auth_user: dict, gate_mocks: GateMocks
    ) -> None:
        """AC3.1: User already in client_registry passes through freely."""
        from promptgrimoire.pages.registry import _check_admission_gate

        gate_mocks.cr._registry = {user_id: {MagicMock()}}
        result = await _check_admission_gate(user_id_str, auth_user, "/annotation/abc")

        assert result is False
        gate_mocks.adm.get_admission_state.assert_not_called()
        gate_mocks.ui.navigate.to.assert_not_called()

    @pytest.mark.anyio
    async def test_ticket_holder_passes_through(
        self, user_id: UUID, user_id_str: str, auth_user: dict, gate_mocks: GateMocks
    ) -> None:
        """AC3.5: User with valid entry ticket passes through; ticket consumed."""
        from promptgrimoire.pages.registry import _check_admission_gate

        gate_mocks.state.try_enter.return_value = True

        result = await _check_admission_gate(user_id_str, auth_user, "/annotation/abc")

        assert result is False
        gate_mocks.state.try_enter.assert_called_once_with(user_id)
        gate_mocks.ui.navigate.to.assert_not_called()

    @pytest.mark.anyio
    async def test_privileged_user_bypasses_gate(
        self, user_id_str: str, auth_user: dict, gate_mocks: GateMocks
    ) -> None:
        """AC3.2: Privileged users bypass gate regardless of cap."""
        from promptgrimoire.pages.registry import _check_admission_gate

        gate_mocks.state.cap = 0

        with patch(
            "promptgrimoire.pages.registry.is_privileged_user",
            return_value=True,
        ):
            result = await _check_admission_gate(
                user_id_str, auth_user, "/annotation/abc"
            )

        assert result is False
        gate_mocks.ui.navigate.to.assert_not_called()

    @pytest.mark.anyio
    async def test_new_user_under_cap_passes_through(
        self, user_id_str: str, auth_user: dict, gate_mocks: GateMocks
    ) -> None:
        """Under capacity: new user passes through without queuing."""
        from promptgrimoire.pages.registry import _check_admission_gate

        with patch(
            "promptgrimoire.pages.registry.is_privileged_user",
            return_value=False,
        ):
            result = await _check_admission_gate(
                user_id_str, auth_user, "/annotation/abc"
            )

        assert result is False
        gate_mocks.ui.navigate.to.assert_not_called()

    @pytest.mark.anyio
    async def test_new_user_at_cap_redirected_to_queue(
        self, user_id: UUID, user_id_str: str, auth_user: dict, gate_mocks: GateMocks
    ) -> None:
        """AC3.3: New user redirected to /queue when admitted count >= cap."""
        from promptgrimoire.pages.registry import _check_admission_gate

        fake_token = "abc123token"

        # At cap: 5 registered users, cap=5
        gate_mocks.cr._registry = {uuid4(): {MagicMock()} for _ in range(5)}
        gate_mocks.state.cap = 5
        gate_mocks.state.enqueue.return_value = fake_token

        with patch(
            "promptgrimoire.pages.registry.is_privileged_user",
            return_value=False,
        ):
            result = await _check_admission_gate(
                user_id_str, auth_user, "/annotation/abc"
            )

        assert result is True
        gate_mocks.state.enqueue.assert_called_once_with(user_id)
        redirect_url = gate_mocks.ui.navigate.to.call_args[0][0]
        assert redirect_url.startswith("/queue?")
        assert f"t={fake_token}" in redirect_url
        assert "return=%2Fannotation%2Fabc" in redirect_url

    @pytest.mark.anyio
    async def test_user_already_in_queue_gets_existing_token(
        self, user_id: UUID, user_id_str: str, auth_user: dict, gate_mocks: GateMocks
    ) -> None:
        """AC3.6: User already in queue redirected with existing token."""
        from promptgrimoire.pages.registry import _check_admission_gate

        existing_token = "existing789"

        gate_mocks.cr._registry = {uuid4(): {MagicMock()} for _ in range(5)}
        gate_mocks.state.cap = 5
        # User already in queue — enqueue() returns existing token (idempotent)
        gate_mocks.state.enqueue.return_value = existing_token

        with patch(
            "promptgrimoire.pages.registry.is_privileged_user",
            return_value=False,
        ):
            result = await _check_admission_gate(
                user_id_str, auth_user, "/annotation/abc"
            )

        assert result is True
        # enqueue IS called — idempotency guarantees the existing token is returned
        gate_mocks.state.enqueue.assert_called_once_with(user_id)
        redirect_url = gate_mocks.ui.navigate.to.call_args[0][0]
        assert f"t={existing_token}" in redirect_url

    @pytest.mark.anyio
    async def test_startup_race_passes_through(
        self, user_id_str: str, auth_user: dict, gate_mocks: GateMocks
    ) -> None:
        """Startup race: if admission state not initialised, pass through."""
        from promptgrimoire.pages.registry import _check_admission_gate

        gate_mocks.adm.get_admission_state.side_effect = RuntimeError(
            "Admission state not initialised"
        )

        result = await _check_admission_gate(user_id_str, auth_user, "/annotation/abc")

        assert result is False
        gate_mocks.ui.navigate.to.assert_not_called()
