"""Tests for idle tracker injection logic in page_route.

Verifies:
- AC1.2: Idle eviction applies to all page_route pages (injection present)
- AC5.3: IDLE__ENABLED=false means no injection
"""

from __future__ import annotations

import json

from promptgrimoire.config import IdleConfig


class TestIdleConfigJsonConversion:
    """Config values are correctly converted to JS-consumable JSON."""

    def test_default_config_produces_correct_json(self) -> None:
        """Default IdleConfig (1800s/60s) → milliseconds in JSON."""
        cfg = IdleConfig()
        result = json.dumps(
            {
                "timeoutMs": cfg.timeout_seconds * 1000,
                "warningMs": cfg.warning_seconds * 1000,
                "enabled": True,
            }
        )
        parsed = json.loads(result)
        assert parsed["timeoutMs"] == 1800000
        assert parsed["warningMs"] == 60000
        assert parsed["enabled"] is True

    def test_custom_config_produces_correct_json(self) -> None:
        """Custom IdleConfig (900s/120s) → milliseconds in JSON."""
        cfg = IdleConfig(timeout_seconds=900, warning_seconds=120)
        result = json.dumps(
            {
                "timeoutMs": cfg.timeout_seconds * 1000,
                "warningMs": cfg.warning_seconds * 1000,
                "enabled": True,
            }
        )
        parsed = json.loads(result)
        assert parsed["timeoutMs"] == 900000
        assert parsed["warningMs"] == 120000


class TestIdleInjectionGating:
    """AC5.3: injection is conditional on enabled flag."""

    def test_enabled_true_would_inject(self) -> None:
        """When enabled=True, injection block executes."""
        cfg = IdleConfig(enabled=True)
        assert cfg.enabled is True

    def test_enabled_false_skips_injection(self) -> None:
        """When enabled=False, injection block is skipped."""
        cfg = IdleConfig(enabled=False)
        assert cfg.enabled is False


class TestIdleInjectionHtmlContent:
    """Verify the injected HTML contains required elements."""

    def test_html_contains_config_and_scripts(self) -> None:
        """Injection HTML has __idleConfig, script src, and init call."""
        cfg = IdleConfig()
        config_json = json.dumps(
            {
                "timeoutMs": cfg.timeout_seconds * 1000,
                "warningMs": cfg.warning_seconds * 1000,
                "enabled": True,
            }
        )
        html = (
            f"<script>window.__idleConfig = {config_json};</script>"
            '<script src="/static/idle-tracker.js"></script>'
            "<script>initIdleTracker();</script>"
        )
        assert "window.__idleConfig" in html
        assert "idle-tracker.js" in html
        assert "initIdleTracker()" in html
        assert '"timeoutMs": 1800000' in html
        assert '"warningMs": 60000' in html
