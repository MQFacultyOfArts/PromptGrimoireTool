#!/usr/bin/env python
"""Production server — no hot reload, INFO-level console logging."""

import os

os.environ["PROMPTGRIMOIRE_RELOAD"] = "0"

from promptgrimoire import main

if __name__ in {"__main__", "__mp_main__"}:
    main()
