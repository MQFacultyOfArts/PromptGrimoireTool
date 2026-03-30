"""Lag-based admission gate: AIMD cap, FIFO queue, and entry tickets.

Pure state module — no NiceGUI imports. The diagnostic loop and
page_route (later phases) call into this module.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

if TYPE_CHECKING:
    from promptgrimoire.config import AdmissionConfig


@dataclass
class AdmissionState:
    """Mutable admission gate state (AIMD algorithm)."""

    cap: int
    initial_cap: int
    batch_size: int
    lag_increase_ms: int
    lag_decrease_ms: int
    queue_timeout_seconds: int
    ticket_validity_seconds: int

    _queue: deque[UUID] = field(default_factory=deque)
    _enqueue_times: dict[UUID, float] = field(default_factory=dict)
    _tokens: dict[str, UUID] = field(default_factory=dict)
    _user_tokens: dict[UUID, str] = field(default_factory=dict)
    _tickets: dict[UUID, float] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Public read-only accessors
    # ------------------------------------------------------------------
    @property
    def queue_depth(self) -> int:
        """Number of users currently waiting in the admission queue."""
        return len(self._queue)

    @property
    def ticket_count(self) -> int:
        """Number of outstanding (not yet consumed) entry tickets."""
        return len(self._tickets)

    # ------------------------------------------------------------------
    # AIMD cap adjustment
    # ------------------------------------------------------------------
    def update_cap(
        self,
        lag_ms: float,
        admitted_count: int,
    ) -> None:
        """Adjust cap using AIMD based on event-loop lag."""
        if lag_ms > self.lag_decrease_ms:
            self.cap = max(self.cap // 2, self.initial_cap)
        elif (
            lag_ms < self.lag_increase_ms
            and admitted_count >= self.cap - self.batch_size
        ):
            self.cap += self.batch_size

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------
    def enqueue(self, user_id: UUID) -> str:
        """Add user to FIFO queue; returns opaque queue token.

        Idempotent: re-enqueuing the same user_id returns the
        existing token without changing queue position.
        """
        if user_id in self._user_tokens:
            return self._user_tokens[user_id]

        token = uuid4().hex
        self._queue.append(user_id)
        self._enqueue_times[user_id] = time.monotonic()
        self._tokens[token] = user_id
        self._user_tokens[user_id] = token
        return token

    def admit_batch(self, admitted_count: int) -> list[UUID]:
        """Pop queued users up to available capacity, granting tickets.

        Returns list of newly admitted user_ids.
        """
        available = self.cap - admitted_count
        if available <= 0 or not self._queue:
            return []

        admitted: list[UUID] = []
        for _ in range(min(available, len(self._queue))):
            user_id = self._queue.popleft()
            self._tickets[user_id] = time.monotonic() + self.ticket_validity_seconds
            self._enqueue_times.pop(user_id, None)
            admitted.append(user_id)
        return admitted

    def try_enter(self, user_id: UUID) -> bool:
        """Consume an entry ticket. Returns True if valid and consumed."""
        if user_id not in self._tickets:
            return False
        if self._tickets[user_id] < time.monotonic():
            # Expired — clean up
            del self._tickets[user_id]
            self._cleanup_token_maps(user_id)
            return False
        # Consume ticket
        del self._tickets[user_id]
        self._cleanup_token_maps(user_id)
        return True

    def get_queue_status(self, token: str) -> dict[str, object]:
        """Return queue position / admission status for a token."""
        if token not in self._tokens:
            return self._expired_status()

        user_id = self._tokens[token]

        # Admitted but not yet entered?
        if user_id in self._tickets:
            if self._tickets[user_id] < time.monotonic():
                del self._tickets[user_id]
                self._cleanup_token_maps(user_id)
                return self._expired_status()
            return {
                "position": 0,
                "total": len(self._queue),
                "admitted": True,
                "expired": False,
            }

        # Still in queue?
        if user_id in self._enqueue_times:
            pos = self._find_queue_position(user_id)
            if pos == -1:
                structlog.get_logger().warning(
                    "admission_queue_desync",
                    user_id=str(user_id),
                    enqueue_times_size=len(self._enqueue_times),
                    queue_size=len(self._queue),
                )
                self._enqueue_times.pop(user_id, None)
                self._cleanup_token_maps(user_id)
                return self._expired_status(position=-1, total=len(self._queue))
            return {
                "position": pos,
                "total": len(self._queue),
                "admitted": False,
                "expired": False,
            }

        # Stale token
        self._cleanup_token_maps(user_id)
        return self._expired_status()

    # ------------------------------------------------------------------
    # Expiry sweep
    # ------------------------------------------------------------------
    def sweep_expired(self) -> None:
        """Remove expired queue entries and expired tickets."""
        now = time.monotonic()

        # Expired queue entries
        expired_queue = [
            uid
            for uid, t in self._enqueue_times.items()
            if now - t > self.queue_timeout_seconds
        ]
        if expired_queue:
            expired_set = set(expired_queue)
            for uid in expired_queue:
                del self._enqueue_times[uid]
                self._cleanup_token_maps(uid)
            self._queue = deque(uid for uid in self._queue if uid not in expired_set)

        # Expired tickets
        expired_tickets = [uid for uid, exp in self._tickets.items() if exp < now]
        for uid in expired_tickets:
            del self._tickets[uid]
            self._cleanup_token_maps(uid)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _expired_status(*, position: int = 0, total: int = 0) -> dict[str, object]:
        """Return a standard expired/stale status dict."""
        return {
            "position": position,
            "total": total,
            "admitted": False,
            "expired": True,
        }

    def _find_queue_position(self, user_id: UUID) -> int:
        """Return 1-based queue position, or -1 if not found."""
        for i, uid in enumerate(self._queue):
            if uid == user_id:
                return i + 1
        return -1

    def _cleanup_token_maps(self, user_id: UUID) -> None:
        """Remove a user from the token lookup maps."""
        token = self._user_tokens.pop(user_id, None)
        if token is not None:
            self._tokens.pop(token, None)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_state: AdmissionState | None = None


def init_admission(config: AdmissionConfig) -> None:
    """Initialise the module-level admission state from config."""
    global _state  # noqa: PLW0603
    _state = AdmissionState(
        cap=config.initial_cap,
        initial_cap=config.initial_cap,
        batch_size=config.batch_size,
        lag_increase_ms=config.lag_increase_ms,
        lag_decrease_ms=config.lag_decrease_ms,
        queue_timeout_seconds=config.queue_timeout_seconds,
        ticket_validity_seconds=config.ticket_validity_seconds,
    )


def get_admission_state() -> AdmissionState:
    """Return the module-level admission state.

    Raises RuntimeError if init_admission() has not been called.
    """
    if _state is None:
        msg = "Admission state not initialised. Call init_admission() first."
        raise RuntimeError(msg)
    return _state
