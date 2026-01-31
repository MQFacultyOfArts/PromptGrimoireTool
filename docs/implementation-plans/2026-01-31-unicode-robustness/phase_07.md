# Unicode Robustness Implementation Plan - Phase 7

**Goal:** Manual inspection of BLNS/CJK rendering in browser and PDF

**Architecture:** Create `/demo/blns-validation` route using existing demo page pattern. Display CJK samples, emoji samples, and BLNS corpus excerpt for visual validation.

**Tech Stack:** NiceGUI, Python

**Scope:** Phase 7 of 7 from design plan

**Codebase verified:** 2026-01-31

---

<!-- START_SUBCOMPONENT_A (tasks 1) -->

<!-- START_TASK_1 -->
### Task 1: Create blns_validation.py demo page

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/pages/blns_validation.py`

**Step 1: Create demo page with BLNS categories**

```python
"""BLNS Validation Demo - Visual inspection of unicode rendering."""

from __future__ import annotations

import json
from pathlib import Path

from nicegui import ui

from promptgrimoire.pages.layout import require_demo_enabled
from promptgrimoire.pages.registry import page_route

# Load BLNS corpus
_BLNS_FILE = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "blns.json"

# CJK samples for visual validation
CJK_SAMPLES = {
    "Japanese": "日本語のテスト文字列です。ひらがな、カタカナ、漢字を含みます。",
    "Chinese (Simplified)": "这是中文测试字符串。包含简体汉字。",
    "Chinese (Traditional)": "這是中文測試字符串。包含繁體漢字。",
    "Korean": "한국어 테스트 문자열입니다. 한글을 포함합니다.",
    "Mixed CJK": "日本語 中文 한국어 混合テスト",
}

EMOJI_SAMPLES = {
    "Simple emoji": "Hello 🎉 World 🌍",
    "Skin tone modifier": "Thumbs up: 👍🏻 👍🏼 👍🏽 👍🏾 👍🏿",
    "ZWJ family": "Family: 👨‍👩‍👧‍👦",
    "ZWJ profession": "Astronaut: 👩‍🚀 Farmer: 👨‍🌾",
    "Flag sequence": "Flags: 🇺🇸 🇯🇵 🇰🇷 🇨🇳 🇦🇺",
}


def _load_blns_by_category() -> dict[str, list[str]]:
    """Load BLNS corpus, grouped by rough categories."""
    if not _BLNS_FILE.exists():
        return {"Error": ["BLNS file not found"]}

    with _BLNS_FILE.open(encoding="utf-8") as f:
        all_strings = json.load(f)

    # Group into rough categories based on string characteristics
    categories: dict[str, list[str]] = {
        "Empty/Whitespace": [],
        "Unicode": [],
        "Injection": [],
        "Special Characters": [],
        "Other": [],
    }

    for s in all_strings[:100]:  # Limit for demo performance
        if not s or s.isspace():
            categories["Empty/Whitespace"].append(repr(s))
        elif any(ord(c) > 127 for c in s):
            categories["Unicode"].append(s)
        elif any(kw in s.lower() for kw in ["script", "select", "drop", "input"]):
            categories["Injection"].append(s)
        elif any(c in s for c in "&%$#_{}~^\\"):
            categories["Special Characters"].append(s)
        else:
            categories["Other"].append(s)

    return {k: v for k, v in categories.items() if v}


@page_route(
    "/demo/blns-validation",
    title="BLNS Validation",
    icon="translate",
    category="demo",
    requires_demo=True,
    order=40,
)
async def blns_validation_page() -> None:
    """Visual validation page for BLNS and CJK rendering."""
    if not require_demo_enabled():
        return

    ui.label("Unicode Validation Demo").classes("text-h4 q-mb-md")
    ui.label(
        "Visual inspection of BLNS corpus and CJK character rendering"
    ).classes("text-subtitle1 text-grey")

    # CJK Samples Section
    with ui.card().classes("q-mt-md").style("max-width: 800px;"):
        ui.label("CJK Samples").classes("text-h6")
        for name, text in CJK_SAMPLES.items():
            with ui.row().classes("items-center q-my-sm"):
                ui.label(f"{name}:").classes("text-bold").style("min-width: 180px;")
                ui.label(text).classes("font-mono")

    # Emoji Samples Section
    with ui.card().classes("q-mt-md").style("max-width: 800px;"):
        ui.label("Emoji Samples").classes("text-h6")
        for name, text in EMOJI_SAMPLES.items():
            with ui.row().classes("items-center q-my-sm"):
                ui.label(f"{name}:").classes("text-bold").style("min-width: 180px;")
                ui.label(text).style("font-size: 1.2em;")

    # BLNS Categories Section
    with ui.card().classes("q-mt-md").style("max-width: 800px;"):
        ui.label("BLNS Corpus (Sample)").classes("text-h6")
        ui.label("First 100 strings from Big List of Naughty Strings").classes(
            "text-caption text-grey"
        )

        blns_categories = _load_blns_by_category()
        for category, strings in blns_categories.items():
            with ui.expansion(f"{category} ({len(strings)} strings)").classes("q-my-sm"):
                for s in strings[:20]:  # Limit per category
                    ui.label(s).classes("font-mono text-sm q-my-xs").style(
                        "word-break: break-all;"
                    )
                if len(strings) > 20:
                    ui.label(f"... and {len(strings) - 20} more").classes(
                        "text-grey text-caption"
                    )
```

**Step 2: Run app to verify page accessible**

Run: `ENABLE_DEMO_PAGES=true uv run python -m promptgrimoire`

Navigate to: `http://localhost:8080/demo/blns-validation`

Expected: Page displays with CJK samples, emoji samples, and BLNS categories

**Step 3: Commit**

```bash
git add src/promptgrimoire/pages/blns_validation.py
git commit -m "feat(demo): add BLNS validation page for unicode visual inspection (#101)"
```
<!-- END_TASK_1 -->

<!-- END_SUBCOMPONENT_A -->

## Phase 7 Verification

**Done when:**
- [ ] `/demo/blns-validation` route accessible (with `ENABLE_DEMO_PAGES=true`)
- [ ] CJK samples display correctly in browser
- [ ] Emoji samples display correctly in browser
- [ ] BLNS corpus sample loads and displays

**Verification commands:**

```bash
# Start app with demo pages enabled
ENABLE_DEMO_PAGES=true uv run python -m promptgrimoire

# Navigate to http://localhost:8080/demo/blns-validation
# Verify:
# - CJK text renders (Japanese, Chinese, Korean)
# - Emoji renders (including ZWJ sequences)
# - BLNS strings display without crashing
```
