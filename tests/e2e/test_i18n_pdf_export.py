"""E2E tests for multilingual PDF export (Issue #101).

These tests verify that Vanessa's i18n fixtures can be pasted into
new documents and exported to PDF through the full UI workflow.

Output saved to: output/test_output/e2e_i18n_exports/

To skip these tests (e.g., in CI without LaTeX):
    pytest -m "not latex"

Traceability:
- Issue: #101 (CJK/BLNS support)
- Fixtures: tests/fixtures/conversations/ (Vanessa's translations)

SKIPPED: Pending #106 HTML input redesign. Reimplement after #106.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "conversations"

# Output directory for test artifacts (matches PDF_TEST_OUTPUT_DIR pattern)
E2E_OUTPUT_DIR = Path("output/test_output/e2e_i18n_exports")

# Skip all tests in this module pending #106 HTML input redesign
pytestmark = pytest.mark.skip(reason="Pending #106 HTML input redesign")

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


# Helper to check latexmk availability
def _has_latexmk() -> bool:
    """Check if latexmk is available."""
    tinytex_path = Path.home() / ".TinyTeX/bin"
    if tinytex_path.exists():
        for arch_dir in tinytex_path.iterdir():
            if (arch_dir / "latexmk").exists():
                return True
    return bool(os.environ.get("LATEXMK_PATH"))


@pytest.mark.latex
@pytest.mark.e2e
class TestI18nPdfExportE2E:
    """E2E tests for multilingual PDF export through UI.

    These tests paste fixture content into documents via the UI,
    then export to PDF and verify the results.

    These tests FAIL (not skip) when LaTeX dependencies are missing.
    To exclude: pytest -m "not latex"

    Output saved to: output/test_output/e2e_i18n_exports/
    """

    @pytest.fixture(autouse=True)
    def _check_latexmk(self) -> None:
        """Fail if latexmk is not installed."""
        if not _has_latexmk():
            pytest.fail(
                "latexmk not installed. Run: uv run python scripts/setup_latex.py\n"
                "To skip LaTeX tests: pytest -m 'not latex'"
            )

    # Expected characters per fixture (for TEX content verification)
    _EXPECTED_CHARS: ClassVar[dict[str, list[str]]] = {
        "chinese_wikipedia": ["维基百科", "示例内容"],  # from clean fixture
        "translation_japanese_sample": ["家庭法令", "離婚判決謄本", "オーストラリア"],
        "translation_korean_sample": ["법은", "차이를", "조정하는"],
        "translation_spanish_sample": ["vehículo", "búsqueda"],
    }

    @staticmethod
    def _load_fixture_text(fixture_name: str) -> str:
        """Load fixture and extract text content preserving paragraph breaks.

        Extracts body content and converts paragraphs to newline-separated text.
        This preserves document structure for proper PDF rendering.
        """
        fixture_path = FIXTURES_DIR / f"{fixture_name}.html"
        if not fixture_path.exists():
            pytest.skip(f"Fixture {fixture_name}.html not found")

        html_content = fixture_path.read_text(encoding="utf-8")

        # Extract body content if present
        body_match = re.search(r"<body[^>]*>(.*?)</body>", html_content, re.DOTALL)
        if body_match:
            html_content = body_match.group(1)

        # Remove script/style tags and their content
        html_content = re.sub(
            r"<(script|style)[^>]*>.*?</\1>", "", html_content, flags=re.DOTALL
        )

        # Convert block elements to newlines for paragraph preservation
        # Add newline after closing tags of block elements
        for tag in ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br"]:
            html_content = re.sub(rf"</{tag}>", "\n", html_content, flags=re.IGNORECASE)
            html_content = re.sub(
                rf"<{tag}[^>]*/?>", "\n", html_content, flags=re.IGNORECASE
            )

        # Strip remaining HTML tags
        text_content = re.sub(r"<[^>]+>", " ", html_content)

        # Clean up whitespace while preserving newlines
        # Replace multiple spaces with single space (not newlines)
        text_content = re.sub(r"[^\S\n]+", " ", text_content)
        # Replace multiple newlines with double newline
        text_content = re.sub(r"\n\s*\n+", "\n\n", text_content)
        return text_content.strip()

    @staticmethod
    def _check_pdf_valid(pdf_path: Path) -> bool:
        """Check if file is a valid PDF."""
        if not pdf_path.exists():
            return False
        if pdf_path.stat().st_size == 0:
            return False
        with pdf_path.open("rb") as f:
            header = f.read(4)
        return header == b"%PDF"

    @pytestmark_db
    @pytest.mark.parametrize(
        "fixture_name",
        [
            "chinese_wikipedia",
            "translation_japanese_sample",
            "translation_korean_sample",
            "translation_spanish_sample",
        ],
    )
    def test_paste_and_export_i18n_fixture(
        self, authenticated_page: Page, app_server: str, fixture_name: str
    ) -> None:
        """Paste i18n fixture content and export to PDF.

        Full E2E workflow:
        1. Navigate to /annotation
        2. Create workspace
        3. Paste fixture content (plain text)
        4. Click Export PDF button
        5. Verify PDF is downloaded and valid
        6. Verify TEX contains expected i18n characters
        """
        page = authenticated_page

        # Load fixture content
        content = self._load_fixture_text(fixture_name)

        # 1. Navigate to /annotation
        page.goto(f"{app_server}/annotation")

        # 2. Create workspace
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        # 3. Paste fixture content
        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill(content)
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-char-index]")
        page.wait_for_timeout(300)  # Let UI settle

        # 4. Create output directory
        output_dir = E2E_OUTPUT_DIR / fixture_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # 5. Click Export PDF and intercept download
        export_button = page.get_by_role(
            "button", name=re.compile("export|pdf", re.IGNORECASE)
        )
        expect(export_button).to_be_visible()

        # Start waiting for download BEFORE clicking
        with page.expect_download(timeout=120000) as download_info:
            export_button.click()

        download = download_info.value

        # Save to our output directory
        pdf_path = output_dir / f"{fixture_name}.pdf"
        download.save_as(pdf_path)

        # 6. Verify PDF is valid
        assert self._check_pdf_valid(pdf_path), f"Invalid PDF for {fixture_name}"

        # Note: TEX file verification would require server-side access
        # For E2E, we verify the PDF was created successfully
        # Full TEX verification is in tests/integration/test_pdf_export.py

    @pytestmark_db
    def test_paste_and_export_cjk_mixed(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Paste mixed CJK content and export to PDF.

        Tests Chinese, Japanese, and Korean in a single document.
        """
        page = authenticated_page

        # Mixed CJK content
        content = "这是中文测试。日本語テスト。한국어 테스트。"

        # Navigate and create workspace
        page.goto(f"{app_server}/annotation")
        page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
        page.wait_for_url(re.compile(r"workspace_id="))

        # Paste content
        content_input = page.get_by_placeholder(
            re.compile("paste|content", re.IGNORECASE)
        )
        content_input.fill(content)
        page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
        page.wait_for_selector("[data-char-index]")
        page.wait_for_timeout(300)

        # Create output directory
        output_dir = E2E_OUTPUT_DIR / "cjk_mixed"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Export PDF
        export_button = page.get_by_role(
            "button", name=re.compile("export|pdf", re.IGNORECASE)
        )
        expect(export_button).to_be_visible()

        with page.expect_download(timeout=120000) as download_info:
            export_button.click()

        download = download_info.value
        pdf_path = output_dir / "cjk_mixed.pdf"
        download.save_as(pdf_path)

        assert self._check_pdf_valid(pdf_path), "Invalid PDF for CJK mixed content"
