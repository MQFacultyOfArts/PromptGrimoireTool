"""Verify structlog debug output is not suppressed after setLevel removal.

Before #377, per-module setLevel(logging.INFO) calls suppressed debug
output through the structlog-stdlib bridge. This test confirms that
structlog.get_logger().debug() produces output at DEBUG level.
"""

from __future__ import annotations

import structlog
from structlog.testing import capture_logs


def test_debug_messages_appear_in_structlog_output() -> None:
    """structlog.get_logger().debug() produces output at DEBUG level.

    AC4.2: proves setLevel removal was meaningful — debug messages are
    no longer suppressed by stdlib level filtering.
    """
    with capture_logs() as cap:
        log = structlog.get_logger()
        log.debug("test_debug_visible", key="value")

    assert len(cap) == 1
    assert cap[0]["event"] == "test_debug_visible"
    assert cap[0]["key"] == "value"
    assert cap[0]["log_level"] == "debug"
