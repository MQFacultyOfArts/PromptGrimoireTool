"""Minimal sd_notify implementation for systemd watchdog integration.

Sends messages to the $NOTIFY_SOCKET Unix socket. Silently no-ops when
not running under systemd (NOTIFY_SOCKET not set).

Protocol reference: https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html
"""

from __future__ import annotations

import os
import socket

import structlog

logger = structlog.get_logger()


def notify(message: str) -> bool:
    """Send a notification to systemd via NOTIFY_SOCKET.

    Parameters
    ----------
    message : str
        The notification message (e.g., "READY=1", "WATCHDOG=1", "STOPPING=1").

    Returns
    -------
    bool
        True if the message was sent, False if NOTIFY_SOCKET is not set.
    """
    socket_path = os.environ.get("NOTIFY_SOCKET")
    if not socket_path:
        return False

    # Abstract socket (starts with @) or filesystem socket
    if socket_path.startswith("@"):
        socket_path = "\0" + socket_path[1:]

    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.sendto(message.encode(), socket_path)

    return True
