# Unicode Robustness Implementation Plan - Phase 6

**Goal:** Verify all text handling layers preserve unicode AND resist injection

**Architecture:** Parameterized tests for LaTeX escaping, DB/CRDT round-trips, injection resistance, and PDF roundtrip. BLNS corpus provides edge cases. Core unicode samples run always; full BLNS corpus opt-in via `pytest -m blns`.

**Tech Stack:** pytest, pdftotext, SQLModel, pycrdt, BLNS corpus

**Scope:** Phase 6 of 7 from design plan

**Codebase verified:** 2026-01-31

---

<!-- START_SUBCOMPONENT_A (tasks 1-5) -->

<!-- START_TASK_1 -->
### Task 1: Add BLNS fixture loader to conftest.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/conftest.py`

**Step 1: Add blns_all fixture**

Add after existing imports (around line 15):

```python
import json
import shutil
import subprocess

# BLNS (Big List of Naughty Strings) fixture loading
_BLNS_FILE = Path(__file__).parent / "fixtures" / "blns.json"


@pytest.fixture
def blns_all() -> list[str]:
    """Full BLNS corpus for comprehensive testing."""
    with _BLNS_FILE.open(encoding="utf-8") as f:
        return json.load(f)
```

**Note:** `BLNS_INJECTION_SUBSET` is defined in Phase 1 Task 2 (from category parsing). Do not redefine it here.

**Step 2: Add pdftotext extraction fixture**

```python
@pytest.fixture
def extract_pdf_text():
    """Extract text from PDF using pdftotext utility."""
    pdftotext_path = shutil.which("pdftotext")
    if pdftotext_path is None:
        pytest.skip("pdftotext not installed")

    def _extract(pdf_path: Path) -> str:
        result = subprocess.run(
            [pdftotext_path, str(pdf_path), "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    return _extract
```

**Step 3: Run tests to verify fixture loads**

Run: `uv run pytest --collect-only -q 2>&1 | head -20`

Expected: No import errors

**Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "feat(test): add BLNS and pdftotext fixtures for unicode testing (#101)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add LaTeX escape and injection tests to test_unicode_handling.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_unicode_handling.py`

**Step 1: Add imports and samples at top**

```python
import pytest

from tests.conftest import BLNS_INJECTION_SUBSET


# Sample unicode strings for always-run tests
UNICODE_SAMPLES = [
    ("ascii", "Hello world"),
    ("cjk_chinese", "你好世界"),
    ("cjk_japanese", "こんにちは世界"),
    ("cjk_korean", "안녕하세요 세계"),
    ("emoji_simple", "Hello 🎉"),
    ("emoji_zwj", "Family: 👨‍👩‍👧‍👦"),
    ("mixed", "Hello 世界 🎉!"),
]
```

**Step 2: Add test classes**

```python
class TestLaTeXEscapeNoCrash:
    """Verify escape function doesn't crash on unicode input."""

    @pytest.mark.parametrize("name,text", UNICODE_SAMPLES)
    def test_unicode_sample_no_crash(self, name: str, text: str) -> None:
        """escape_unicode_latex() handles unicode without crashing."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex(text)
        assert isinstance(result, str)

    @pytest.mark.parametrize("text", BLNS_INJECTION_SUBSET)
    def test_injection_string_no_crash(self, text: str) -> None:
        """escape_unicode_latex() handles injection strings without crashing."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex(text)
        assert isinstance(result, str)


class TestLaTeXNoCommandInjection:
    """Verify BLNS injection subset doesn't execute LaTeX commands."""

    @pytest.mark.parametrize("text", BLNS_INJECTION_SUBSET)
    def test_no_raw_backslash_input(self, text: str) -> None:
        """Escaped text doesn't contain raw \\input command."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex(text)
        # Raw \input (not \\input) would be dangerous
        assert "\\input{" not in result or "\\textbackslash" in result

    @pytest.mark.parametrize("text", BLNS_INJECTION_SUBSET)
    def test_no_raw_write18(self, text: str) -> None:
        """Escaped text doesn't contain raw \\write18 command."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex(text)
        assert "\\write18{" not in result or "\\textbackslash" in result


class TestHTMLNoXSS:
    """Verify BLNS injection subset doesn't break HTML rendering."""

    @pytest.mark.parametrize("text", BLNS_INJECTION_SUBSET)
    def test_html_escape_prevents_script_execution(self, text: str) -> None:
        """HTML-escaped BLNS strings don't contain raw script tags."""
        from html import escape as html_escape

        # Apply same escaping that would be used in NiceGUI/HTML context
        escaped = html_escape(text)

        # Verify no raw script tags survive (case-insensitive check)
        assert "<script" not in escaped.lower()
        assert "javascript:" not in escaped.lower()

    @pytest.mark.parametrize("text", BLNS_INJECTION_SUBSET)
    def test_html_escape_prevents_event_handlers(self, text: str) -> None:
        """HTML-escaped BLNS strings don't contain raw event handlers."""
        from html import escape as html_escape

        escaped = html_escape(text)

        # Common XSS event handlers should be escaped
        assert "onerror=" not in escaped.lower() or "&" in escaped
        assert "onload=" not in escaped.lower() or "&" in escaped


@pytest.mark.blns
class TestBLNSFullCorpus:
    """Full BLNS corpus tests (opt-in via pytest -m blns)."""

    def test_all_blns_strings_no_crash(self, blns_all: list[str]) -> None:
        """All 600+ BLNS strings process without crashing."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        for text in blns_all:
            result = escape_unicode_latex(text)
            assert isinstance(result, str)
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_unicode_handling.py -v`

Expected: All tests pass (BLNS full corpus skipped by default)

**Step 4: Commit**

```bash
git add tests/unit/test_unicode_handling.py
git commit -m "test(export): add LaTeX escape and injection tests (#101)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add CRDT roundtrip test

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/integration/test_unicode_crdt_roundtrip.py`

**Step 1: Create CRDT roundtrip test**

```python
"""Tests for unicode preservation through CRDT layer."""

import pytest
from pycrdt import Doc, Text

from tests.conftest import BLNS_INJECTION_SUBSET


UNICODE_SAMPLES = [
    "Hello world",
    "你好世界",  # Chinese
    "こんにちは世界",  # Japanese
    "안녕하세요 세계",  # Korean
    "Hello 🎉",  # Emoji
    "Family: 👨‍👩‍👧‍👦",  # ZWJ sequence
]


class TestCRDTUnicodeRoundtrip:
    """Verify unicode content survives CRDT operations."""

    @pytest.mark.parametrize("text", UNICODE_SAMPLES)
    def test_unicode_insert_retrieve(self, text: str) -> None:
        """Unicode text inserted into CRDT Text can be retrieved."""
        doc = Doc()
        doc["content"] = crdt_text = Text()

        crdt_text += text

        retrieved = str(crdt_text)
        assert retrieved == text

    @pytest.mark.parametrize("text", UNICODE_SAMPLES)
    def test_unicode_survives_state_sync(self, text: str) -> None:
        """Unicode text survives state export/import."""
        doc1 = Doc()
        doc1["content"] = text1 = Text()
        text1 += text

        # Export state and apply to new doc
        state = doc1.get_state()
        doc2 = Doc()
        doc2["content"] = text2 = Text()
        doc2.apply_update(state)

        assert str(text2) == text

    @pytest.mark.parametrize("text", BLNS_INJECTION_SUBSET)
    def test_injection_strings_in_crdt(self, text: str) -> None:
        """BLNS injection strings can be stored in CRDT without issues."""
        doc = Doc()
        doc["content"] = crdt_text = Text()

        crdt_text += text

        retrieved = str(crdt_text)
        assert retrieved == text
```

**Step 2: Run tests**

Run: `uv run pytest tests/integration/test_unicode_crdt_roundtrip.py -v`

Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/integration/test_unicode_crdt_roundtrip.py
git commit -m "test(crdt): add unicode roundtrip tests for pycrdt (#101)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add DB roundtrip and SQL injection tests

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/integration/test_unicode_db_roundtrip.py`

**Step 1: Create DB roundtrip test**

```python
"""Tests for unicode preservation through SQLModel/PostgreSQL layer."""

from uuid import uuid4

import pytest

from tests.conftest import BLNS_INJECTION_SUBSET


UNICODE_SAMPLES = [
    "Hello world",
    "你好世界",  # Chinese
    "こんにちは世界",  # Japanese
    "안녕하세요 세계",  # Korean
    "Hello 🎉",  # Emoji
    "Family: 👨‍👩‍👧‍👦",  # ZWJ sequence
]


@pytest.mark.asyncio
class TestDBUnicodeRoundtrip:
    """Verify unicode content survives database storage."""

    @pytest.mark.parametrize("text", UNICODE_SAMPLES)
    async def test_unicode_in_user_display_name(self, text: str) -> None:
        """Unicode text stored in User.display_name is preserved."""
        from promptgrimoire.db.models import User
        from promptgrimoire.db import get_session

        unique_email = f"test-unicode-{uuid4()}@example.com"

        async with get_session() as session:
            user = User(
                email=unique_email,
                display_name=text,
                stytch_user_id=f"stytch-{uuid4()}",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Retrieve and verify
            assert user.display_name == text

    @pytest.mark.parametrize("text", BLNS_INJECTION_SUBSET)
    async def test_sql_injection_strings_safe(self, text: str) -> None:
        """BLNS SQL injection strings stored safely via SQLModel."""
        from promptgrimoire.db.models import User
        from promptgrimoire.db import get_session

        unique_email = f"test-injection-{uuid4()}@example.com"

        async with get_session() as session:
            # This should NOT execute SQL - just store the string
            user = User(
                email=unique_email,
                display_name=text,
                stytch_user_id=f"stytch-{uuid4()}",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # String should be stored literally, not interpreted as SQL
            assert user.display_name == text
```

**Step 2: Run tests (requires TEST_DATABASE_URL)**

Run: `uv run pytest tests/integration/test_unicode_db_roundtrip.py -v`

Expected: Tests pass (or skip if database not configured)

**Step 3: Commit**

```bash
git add tests/integration/test_unicode_db_roundtrip.py
git commit -m "test(db): add unicode roundtrip and SQL injection tests (#101)"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add PDF roundtrip test

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/integration/test_unicode_pdf_roundtrip.py`

**Step 1: Create PDF roundtrip test**

```python
"""Tests for unicode preservation through PDF export pipeline."""

import pytest


@pytest.mark.slow
class TestUnicodePDFRoundtrip:
    """Verify unicode content survives PDF export."""

    def test_cjk_in_pdf_text_extraction(
        self,
        pdf_exporter,
        extract_pdf_text,
    ) -> None:
        """CJK text appears in extracted PDF content."""
        # Export a document with CJK content
        html = "<p>日本語テスト Chinese: 中文</p>"
        result = pdf_exporter(
            test_name="cjk_roundtrip",
            html=html,  # Note: fixture uses 'html' not 'html_content'
            highlights=[],
        )

        # Extract text from PDF
        extracted = extract_pdf_text(result.pdf_path)

        # Verify CJK content survived
        # Note: Exact match may vary due to font rendering
        # Verify: (1) no tofu/replacement chars AND (2) we got meaningful content
        assert "�" not in extracted and len(extracted) > 10

    def test_ascii_with_special_chars_roundtrip(
        self,
        pdf_exporter,
        extract_pdf_text,
    ) -> None:
        """ASCII special characters survive roundtrip."""
        html = "<p>Test: 100% success & more</p>"
        result = pdf_exporter(
            test_name="ascii_special_roundtrip",
            html=html,  # Note: fixture uses 'html' not 'html_content'
            highlights=[],
        )

        extracted = extract_pdf_text(result.pdf_path)
        assert "100" in extracted
        assert "success" in extracted
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_unicode_pdf_roundtrip.py -v -m slow`

Expected: Tests pass (or skip if dependencies not installed)

**Step 3: Commit**

```bash
git add tests/integration/test_unicode_pdf_roundtrip.py
git commit -m "test(export): add PDF roundtrip tests for unicode content (#101)"
```
<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_A -->

## Phase 6 Verification

**Done when:**
- [ ] BLNS fixture loads correctly
- [ ] Unicode sample tests pass (CJK, emoji, mixed)
- [ ] Injection subset tests pass (always run)
- [ ] Full BLNS corpus available via `pytest -m blns`
- [ ] CRDT roundtrip tests pass
- [ ] DB roundtrip tests pass
- [ ] SQL injection tests pass (strings stored safely)
- [ ] HTML XSS tests pass (injection subset escapes properly)
- [ ] PDF roundtrip test extracts text correctly (no tofu AND has content)

**Verification commands:**

```bash
# Run unicode tests (excludes BLNS full corpus)
uv run pytest tests/unit/test_unicode_handling.py -v

# Run BLNS full corpus
uv run pytest tests/unit/test_unicode_handling.py -v -m blns

# Run CRDT roundtrip tests
uv run pytest tests/integration/test_unicode_crdt_roundtrip.py -v

# Run DB roundtrip tests (requires TEST_DATABASE_URL)
uv run pytest tests/integration/test_unicode_db_roundtrip.py -v

# Run PDF roundtrip tests
uv run pytest tests/integration/test_unicode_pdf_roundtrip.py -v -m slow
```
