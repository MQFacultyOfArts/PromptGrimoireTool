"""Guard: fixture data-annots colour refs must be compilable.

Pre-baked data-annots in HTML fixtures reference colour names like
tag-Jurisdiction-dark. The live app export uses UUID-keyed colours
from state.tag_colours(). If a test compiles a fixture without
providing matching colour definitions, LaTeX fails on undefined
colours — presenting as a 120s Playwright timeout, not an obvious
error.

This guard scans all HTML fixtures with data-annots and verifies
the colour refs are documented or have matching tag_colours dicts
in the test files that use them.
"""

from __future__ import annotations

import re
from pathlib import Path

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures"


def _extract_colour_refs(html: str) -> set[str]:
    """Extract colour names from data-annots attributes.

    Finds patterns like tag-Jurisdiction-dark, tag-Reasons-light
    inside data-annots="..." attribute values.
    """
    colours: set[str] = set()
    # Match data-annots="...\annot{COLOUR}{...}..."
    for annot_match in re.finditer(
        r'data-annots="[^"]*\\annot\{([^}]+)\}',
        html,
    ):
        colours.add(annot_match.group(1))
    # Match data-colors="COLOUR" attributes
    for color_match in re.finditer(r'data-colors="([^"]+)"', html):
        colours.add(color_match.group(1))
    return colours


def _base_tag_names(colour_refs: set[str]) -> set[str]:
    """Extract base tag names from colour refs.

    tag-Jurisdiction-dark -> Jurisdiction
    tag-Jurisdiction-light -> Jurisdiction
    tag-smoke-dark -> smoke
    """
    bases: set[str] = set()
    for ref in colour_refs:
        m = re.match(r"tag-(.+?)-(dark|light)$", ref)
        if m:
            bases.add(m.group(1))
    return bases


class TestFixtureColourGuard:
    """Ensure fixture colour refs are self-consistent."""

    def test_cjk_fixture_colours_match_integration_test(self) -> None:
        """CJK fixture colour refs must have matching tag_colours entries.

        The integration test (test_cjk_annotated_table_export.py) defines
        _TAG_COLOURS with keys that generate_tag_colour_definitions()
        turns into tag-{key}, tag-{key}-light, tag-{key}-dark. These
        must match the fixture's data-annots colour refs.
        """
        fixture_path = FIXTURE_DIR / "workspace_cjk_annotated_table.html"
        if not fixture_path.exists():
            return

        html = fixture_path.read_text()
        colour_refs = _extract_colour_refs(html)

        if not colour_refs:
            return

        base_names = _base_tag_names(colour_refs)

        # These are the tag_colours keys from test_cjk_annotated_table_export.py
        # generate_tag_colour_definitions() creates tag-{key}-dark/light from these
        integration_tag_keys = {"Jurisdiction", "Reasons", "Decision"}

        missing = base_names - integration_tag_keys
        assert not missing, (
            f"Fixture colour refs use base tag names {missing} "
            f"that have no matching _TAG_COLOURS entry in the "
            f"integration test. The preamble won't define these "
            f"colours, causing 'Undefined color' LaTeX errors. "
            f"Either update the fixture or the _TAG_COLOURS dict."
        )

    def test_no_uuid_colour_refs_in_fixtures(self) -> None:
        """Fixture data-annots must not use UUID colour refs.

        UUID-keyed colours (tag-{uuid}-dark) are workspace-specific
        and will never match across test runs. Fixtures must use
        human-readable tag names.
        """
        uuid_pattern = re.compile(
            r"tag-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}",
        )
        for fixture in FIXTURE_DIR.glob("*.html"):
            html = fixture.read_text()
            if "data-annots" not in html:
                continue
            matches = uuid_pattern.findall(html)
            assert not matches, (
                f"{fixture.name} contains UUID colour refs: {matches}. "
                f"Fixtures must use human-readable tag names, not UUIDs."
            )
