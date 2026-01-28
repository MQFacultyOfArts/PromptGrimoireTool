#!/usr/bin/env python
"""Development server with hot reload support."""

import logging

from promptgrimoire import main

if __name__ in {"__main__", "__mp_main__"}:
    # Enable DEBUG logging to console for development
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(name)s: %(message)s",
    )
    # Silence noisy loggers
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    main()
