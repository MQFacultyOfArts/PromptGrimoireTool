"""Shared pytest fixtures for PromptGrimoire tests."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import emoji as emoji_lib
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from promptgrimoire.db import run_alembic_upgrade
from promptgrimoire.export.pdf import get_latexmk_path

load_dotenv()


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Ensure clean database state before xdist workers spawn.

    Runs once in the main process at pytest startup:
    1. Run Alembic migrations to ensure schema is correct
    2. Truncate all tables to remove leftover data from previous runs

    This runs BEFORE xdist spawns workers, so no race conditions.
    """
    from sqlalchemy import create_engine, text

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return  # Skip if no database configured (non-DB tests)

    # Run migrations to ensure schema is up to date
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd="/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool",
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.exit(f"Alembic migration failed: {result.stderr}", returncode=1)

    # Convert async URL to sync for this one-time operation
    # Use psycopg (v3) driver which is installed
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")

    engine = create_engine(sync_url)
    with engine.begin() as conn:
        # Get all table names from public schema (except alembic_version)
        result = conn.execute(
            text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename != 'alembic_version'
            """)
        )
        tables = [row[0] for row in result.fetchall()]

        if tables:
            # Truncate all tables with CASCADE to handle foreign keys
            # Quote table names to handle reserved keywords like "user"
            quoted_tables = ", ".join(f'"{t}"' for t in tables)
            conn.execute(text(f"TRUNCATE {quoted_tables} RESTART IDENTITY CASCADE"))

    engine.dispose()


# Canary UUID for database rebuild detection
# If this row disappears during a test run, the database was rebuilt
_DB_CANARY_ID = uuid4()

# =============================================================================
# BLNS Corpus Parsing
# =============================================================================

type BLNSCorpus = dict[str, list[str]]


def _parse_blns_by_category(blns_path: Path) -> BLNSCorpus:
    """Parse blns.txt into {category: [strings]}.

    Category headers are lines starting with '#\t' followed by title-case text
    after a blank line. Explanatory comments (containing 'which') are skipped.
    """
    categories: BLNSCorpus = {}
    current_category = "Uncategorized"
    prev_blank = True

    for line in blns_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        # Track blank lines
        if not stripped:
            prev_blank = True
            continue

        # Check for category header: #\t followed by title-case, after blank
        if line.startswith("#\t") and prev_blank:
            header_text = line[2:].strip()
            # Category names are Title Case, not explanations
            if (
                header_text
                and header_text[0].isupper()
                and "which" not in header_text.lower()
            ):
                current_category = header_text
                categories.setdefault(current_category, [])
        elif not line.startswith("#"):
            # Non-comment line is a test string
            categories.setdefault(current_category, []).append(line)

        prev_blank = False

    return categories


# Load BLNS corpus at module level (once per test session)
_FIXTURES_DIR = Path(__file__).parent / "fixtures"
BLNS_BY_CATEGORY: BLNSCorpus = _parse_blns_by_category(_FIXTURES_DIR / "blns.txt")

# Injection-related categories for always-run subset
INJECTION_CATEGORIES = [
    "Script Injection",
    "SQL Injection",
    "Server Code Injection",
    "Command Injection (Unix)",
    "Command Injection (Windows)",
    "Command Injection (Ruby)",
    "XXE Injection (XML)",
    "Unwanted Interpolation",
    "File Inclusion",
    "jinja2 injection",
]

BLNS_INJECTION_SUBSET: list[str] = [
    s for cat in INJECTION_CATEGORIES for s in BLNS_BY_CATEGORY.get(cat, [])
]

# =============================================================================
# Unicode Test Fixtures (derived from BLNS corpus)
# =============================================================================


def _is_cjk_codepoint(cp: int) -> bool:
    """Check if codepoint is in a CJK range."""
    return (
        # CJK Unified Ideographs
        (0x4E00 <= cp <= 0x9FFF)
        # Hiragana
        or (0x3040 <= cp <= 0x309F)
        # Katakana
        or (0x30A0 <= cp <= 0x30FF)
        # Hangul Syllables
        or (0xAC00 <= cp <= 0xD7AF)
        # CJK Unified Ideographs Extension A
        or (0x3400 <= cp <= 0x4DBF)
    )


def _extract_cjk_chars_from_blns() -> list[str]:
    """Extract individual CJK characters from BLNS Two-Byte Characters category.

    Returns unique CJK characters for parameterized testing.
    """
    cjk_chars: set[str] = set()
    for s in BLNS_BY_CATEGORY.get("Two-Byte Characters", []):
        for char in s:
            if _is_cjk_codepoint(ord(char)):
                cjk_chars.add(char)
    return sorted(cjk_chars)


def _extract_emoji_from_blns() -> list[str]:
    """Extract individual emoji from BLNS Emoji category.

    Returns unique emoji strings (including ZWJ sequences) for parameterized testing.
    """
    emoji_set: set[str] = set()
    for s in BLNS_BY_CATEGORY.get("Emoji", []):
        # Use emoji library to find all emoji in the string
        for match in emoji_lib.emoji_list(s):
            emoji_set.add(match["emoji"])
    return sorted(emoji_set)


# Extracted test data from BLNS corpus
CJK_TEST_CHARS: list[str] = _extract_cjk_chars_from_blns()
EMOJI_TEST_STRINGS: list[str] = _extract_emoji_from_blns()

# ASCII strings for negative testing (from BLNS Reserved Strings)
ASCII_TEST_STRINGS: list[str] = [
    s
    for s in BLNS_BY_CATEGORY.get("Reserved Strings", [])
    if s.isascii() and len(s) > 0
][:10]  # Take first 10

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Generator

    from playwright.sync_api import Browser, BrowserContext


# =============================================================================
# LaTeX/PDF Testing Utilities
# =============================================================================


def _has_latexmk() -> bool:
    """Check if latexmk is available via TinyTeX."""
    try:
        get_latexmk_path()
        return True
    except FileNotFoundError:
        return False


# Decorator that FAILS (not skips) when latexmk is missing
# Use pytest -m "not latex" to exclude these tests
def requires_latexmk(func_or_class):
    """Decorator that fails tests if latexmk is not installed.

    Unlike skipif, this makes missing dependencies visible as failures.
    To exclude LaTeX tests entirely: pytest -m "not latex"
    """
    import functools
    import inspect

    if isinstance(func_or_class, type):
        # Class decorator
        for name, method in list(vars(func_or_class).items()):
            if name.startswith("test_") and callable(method):
                setattr(func_or_class, name, requires_latexmk(method))
        return pytest.mark.latex(func_or_class)
    elif inspect.iscoroutinefunction(func_or_class):
        # Async function decorator
        @functools.wraps(func_or_class)
        async def async_wrapper(*args, **kwargs):
            if not _has_latexmk():
                pytest.fail(
                    "latexmk not installed. Run: uv run python scripts/setup_latex.py\n"
                    "To skip LaTeX tests: pytest -m 'not latex'"
                )
            return await func_or_class(*args, **kwargs)

        return pytest.mark.latex(async_wrapper)
    else:
        # Sync function decorator
        @functools.wraps(func_or_class)
        def wrapper(*args, **kwargs):
            if not _has_latexmk():
                pytest.fail(
                    "latexmk not installed. Run: uv run python scripts/setup_latex.py\n"
                    "To skip LaTeX tests: pytest -m 'not latex'"
                )
            return func_or_class(*args, **kwargs)

        return pytest.mark.latex(wrapper)


# =============================================================================
# Fixture File Loading (supports .html and .html.gz)
# =============================================================================

CONVERSATIONS_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "conversations"


def load_conversation_fixture(name: str) -> str:
    """Load a conversation fixture, supporting both .html and .html.gz.

    Args:
        name: Fixture name with or without extension (e.g., "claude_cooking" or
              "claude_cooking.html")

    Returns:
        HTML content as string.
    """
    import gzip

    # Normalize: strip extension if provided
    base_name = name.removesuffix(".html.gz").removesuffix(".html")

    # Try gzipped first (preferred for storage)
    gz_path = CONVERSATIONS_FIXTURES_DIR / f"{base_name}.html.gz"
    if gz_path.exists():
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            return f.read()

    # Fall back to plain HTML
    html_path = CONVERSATIONS_FIXTURES_DIR / f"{base_name}.html"
    if html_path.exists():
        return html_path.read_text()

    msg = f"Fixture not found: {base_name} (tried .html.gz and .html)"
    raise FileNotFoundError(msg)


# =============================================================================
# PDF Export Test Fixtures
# =============================================================================

# Standard tag colours used across the application
TAG_COLOURS: dict[str, str] = {
    "jurisdiction": "#1f77b4",
    "procedural_history": "#ff7f0e",
    "legally_relevant_facts": "#2ca02c",
    "legal_issues": "#d62728",
    "reasons": "#9467bd",
    "courts_reasoning": "#8c564b",
    "decision": "#e377c2",
    "order": "#7f7f7f",
    "domestic_sources": "#bcbd22",
    "reflection": "#17becf",
}

# Shared output directory for test artifacts (gitignored)
PDF_TEST_OUTPUT_DIR = Path("output/test_output")


@dataclass
class PdfExportResult:
    """Result from PDF export containing paths for inspection."""

    pdf_path: Path
    tex_path: Path
    output_dir: Path


@pytest.fixture
def pdf_exporter() -> Callable[..., PdfExportResult]:
    """Factory fixture for exporting PDFs using the production pipeline.

    Uses export_annotation_pdf which goes through the full workflow:
    - HTML normalisation
    - Pandoc with libreoffice.lua filter
    - Full preamble with proper settings
    - LuaLaTeX compilation via latexmk

    Usage:
        def test_something(pdf_exporter, parsed_rtf):
            result = pdf_exporter(
                html=parsed_rtf.html,
                highlights=[...],
                test_name="my_test",
            )
            assert result.pdf_path.exists()
    """
    from promptgrimoire.export.pdf_export import export_annotation_pdf

    def _export(
        html: str,
        highlights: list[dict[str, Any]],
        test_name: str,
        general_notes: str = "",
        acceptance_criteria: str = "",
    ) -> PdfExportResult:
        """Export PDF using production pipeline.

        Args:
            html: HTML content to convert.
            highlights: List of highlight dicts.
            test_name: Name for output files (e.g., "cross_env_test").
            general_notes: Optional HTML content for general notes section.
            acceptance_criteria: Optional text prepended to general notes
                describing what the test validates.

        Returns:
            PdfExportResult with paths to generated files.
        """
        # Combine acceptance criteria with general notes
        if acceptance_criteria:
            notes_content = (
                f"<p><b>TEST ACCEPTANCE CRITERIA</b></p><p>{acceptance_criteria}</p>"
            )
            if general_notes:
                notes_content += general_notes
        else:
            notes_content = general_notes

        # Create output directory (purge first for clean state)
        output_dir = PDF_TEST_OUTPUT_DIR / test_name
        if output_dir.exists():
            import shutil

            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run the async export in a new event loop
        pdf_path = asyncio.run(
            export_annotation_pdf(
                html_content=html,
                highlights=highlights,
                tag_colours=TAG_COLOURS,
                general_notes=notes_content,
                output_dir=output_dir,
                filename=test_name,
            )
        )

        tex_path = output_dir / f"{test_name}.tex"

        return PdfExportResult(
            pdf_path=pdf_path,
            tex_path=tex_path,
            output_dir=output_dir,
        )

    return _export


TEST_STORAGE_SECRET = "test-secret-for-e2e"


@pytest.fixture(scope="session")
def db_schema_guard() -> Generator[None]:
    """Set up database schema once at session start.

    This fixture:
    1. Sets DATABASE_URL from TEST_DATABASE_URL for test isolation
    2. Runs Alembic migrations to ensure schema exists

    The database engine is initialized lazily on first use within each
    test's event loop context. Tests use UUID-based isolation so they
    don't interfere with each other.

    Note: Not autouse - only tests that need the DB should depend on this
    (typically via their db_engine fixture).
    """
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.fail(
            "TEST_DATABASE_URL environment variable is required for tests. "
            "Set it to point to a test database (not production!)."
        )
        return  # Unreachable, but helps type checker

    # Set DATABASE_URL from TEST_DATABASE_URL for test isolation
    os.environ["DATABASE_URL"] = test_url

    # Run migrations (sync - Alembic uses subprocess)
    try:
        run_alembic_upgrade()
    except RuntimeError as e:
        pytest.fail(str(e))

    yield


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_canary(db_schema_guard: None) -> AsyncIterator[str]:  # noqa: ARG001
    """Insert canary row at session start. If DB rebuilds, canary disappears.

    This fixture:
    1. Creates a fresh NullPool engine
    2. Inserts a User with known UUID and email
    3. Returns the canary email for verification

    The canary check in db_session verifies ~1ms PK lookup.
    """
    from promptgrimoire.db import User

    canary_email = f"canary-{_DB_CANARY_ID}@test.local"

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        canary_user = User(email=canary_email, display_name="DB Canary")
        session.add(canary_user)
        await session.commit()

    await engine.dispose()
    yield canary_email

    # Cleanup: remove canary row after session ends
    from sqlmodel import delete

    cleanup_engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    cleanup_factory = async_sessionmaker(
        cleanup_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with cleanup_factory() as session:
        # ty doesn't understand SQLModel column comparison returns expression, not bool
        await session.execute(delete(User).where(User.email == canary_email))  # type: ignore[arg-type]
        await session.commit()

    await cleanup_engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_canary: str) -> AsyncIterator[AsyncSession]:
    """Database session with NullPool - safe for xdist parallelism.

    Each test gets a fresh TCP connection to PostgreSQL.
    Connection closes when test ends. No pooling, no event loop binding.

    Verifies canary row exists - fails fast if database was rebuilt.
    Canary check uses email lookup (indexed column, ~1ms).
    Note: Email lookup is safer than UUID because User.id is auto-generated.
    """
    from sqlmodel import select

    from promptgrimoire.db import User

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        # Verify canary exists - fails if DB was rebuilt
        result = await session.execute(select(User).where(User.email == db_canary))
        canary = result.scalar_one_or_none()
        if canary is None:
            pytest.fail(
                f"DATABASE WAS REBUILT - canary row missing (email: {db_canary})"
            )

        yield session

    await engine.dispose()


@pytest.fixture
async def mock_stytch_client():
    """Create a mocked Stytch B2BClient for unit tests.

    Patches the B2BClient constructor to return a mock, allowing
    tests to set up expected responses without making real API calls.

    Made async to ensure proper event loop handling with pytest-asyncio.
    """
    with patch("promptgrimoire.auth.client.B2BClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client


def _find_free_port() -> int:
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# Script to run NiceGUI server
# Note: We clear PYTEST env vars to prevent NiceGUI from entering test mode
_SERVER_SCRIPT = f"""
import os
import sys

# Clear pytest-related environment variables that NiceGUI checks
for key in list(os.environ.keys()):
    if 'PYTEST' in key or 'NICEGUI' in key:
        del os.environ[key]

# Enable mock auth for E2E tests
os.environ['AUTH_MOCK'] = 'true'
os.environ['STORAGE_SECRET'] = '{TEST_STORAGE_SECRET}'

# Set mock SSO config values so SSO flow can be tested
# Without these, the SSO code returns early before generating a redirect URL
os.environ.setdefault('STYTCH_SSO_CONNECTION_ID', 'test-sso-connection-id')
os.environ.setdefault('STYTCH_PUBLIC_TOKEN', 'test-public-token')

port = int(sys.argv[1])

from nicegui import ui
import promptgrimoire.pages  # noqa: F401 - registers routes

ui.run(port=port, reload=False, show=False, storage_secret='{TEST_STORAGE_SECRET}')
"""


@pytest.fixture(scope="session")
def app_server() -> Generator[str]:
    """Start the NiceGUI app server for E2E tests.

    Returns the base URL of the running server.
    Automatically starts before tests and stops after.

    Note: NiceGUI detects pytest and enters test mode, expecting special
    environment variables. We clear these in the subprocess to run normally.
    """
    port = _find_free_port()
    url = f"http://localhost:{port}"

    # Create clean environment without pytest variables
    clean_env = {
        k: v for k, v in os.environ.items() if "PYTEST" not in k and "NICEGUI" not in k
    }

    # Start server as subprocess with clean environment
    process = subprocess.Popen(
        [sys.executable, "-c", _SERVER_SCRIPT, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=clean_env,
    )

    # Wait for server to be ready
    max_wait = 15  # seconds
    start_time = time.time()
    while time.time() - start_time < max_wait:
        # Check if process died
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(
                f"Server process died. Exit code: {process.returncode}\n"
                f"stdout: {stdout.decode()}\n"
                f"stderr: {stderr.decode()}"
            )
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                break
        except OSError:
            time.sleep(0.1)
    else:
        process.terminate()
        pytest.fail(f"Server failed to start within {max_wait} seconds")

    yield url

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
def crdt_sync_url(app_server: str) -> str:
    """URL for the CRDT sync demo page."""
    return f"{app_server}/demo/crdt-sync"


@pytest.fixture
def text_selection_url(app_server: str) -> str:
    """URL for the text selection demo page."""
    return f"{app_server}/demo/text-selection"


@pytest.fixture
def reset_crdt_state(app_server: str) -> Generator[None]:
    """Reset CRDT state before each test.

    This ensures each E2E test starts with a clean CRDT document state.
    Function-scoped (default) so it runs before every test that uses it.
    """
    import urllib.request

    reset_url = f"{app_server}/api/test/reset-crdt"
    try:
        with urllib.request.urlopen(reset_url, timeout=5) as resp:
            if resp.status != 200:
                pytest.fail(f"Failed to reset CRDT state: {resp.status}")
    except Exception as e:
        pytest.fail(f"Failed to reset CRDT state: {e}")

    yield


@pytest.fixture
def new_context(browser: Browser) -> Generator[Callable[[], BrowserContext]]:
    """Factory fixture for creating new browser contexts.

    Creates isolated browser contexts for multi-user E2E testing.
    All contexts are automatically cleaned up after the test.

    Usage:
        def test_two_users(page: Page, new_context):
            context2 = new_context()
            page2 = context2.new_page()
            # page and page2 are now independent browser sessions
    """
    contexts: list[BrowserContext] = []

    def _new_context() -> BrowserContext:
        ctx = browser.new_context()
        contexts.append(ctx)
        return ctx

    yield _new_context

    # Cleanup all created contexts
    for ctx in contexts:
        ctx.close()


@pytest.fixture
def sample_claude_conversation() -> str:
    """A sample Claude conversation for testing parsers."""
    return (
        "Human: What is the capital of France?\n\n"
        "Assistant: The capital of France is Paris.\n\n"
        "Human: What about Germany?\n\n"
        "Assistant: The capital of Germany is Berlin."
    )


@pytest.fixture
def sample_chatgpt_conversation() -> str:
    """A sample ChatGPT conversation for testing parsers."""
    return (
        "User: What is the capital of France?\n\n"
        "ChatGPT: The capital of France is Paris.\n\n"
        "User: What about Germany?\n\n"
        "ChatGPT: The capital of Germany is Berlin."
    )
