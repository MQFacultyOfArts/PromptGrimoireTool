"""Per-lane partitioning of `grimoire test run` arguments.

Regression guard for the mixed-lane silent-drop bug: the old first-match-wins
classifier routed a mixed invocation down one lane and that lane's runner
silently discarded the foreign paths (false-green, hit independently by two
agents on 2026-08-17). Paths must be classified individually, and option
values (`-k foo`) must stay with the flags rather than being mistaken for
paths.
"""

from promptgrimoire.cli.testing import _partition_test_args


class TestPartitionTestArgs:
    def test_mixed_invocation_splits_per_lane(self) -> None:
        lanes, flags = _partition_test_args(
            [
                "tests/integration/test_a.py",
                "tests/integration/test_page_load_query_count.py",
                "tests/e2e/test_b.py",
                "-x",
            ]
        )
        assert lanes["unit"] == ["tests/integration/test_a.py"]
        assert lanes["nicegui"] == ["tests/integration/test_page_load_query_count.py"]
        assert lanes["e2e"] == ["tests/e2e/test_b.py"]
        assert flags == ["-x"]

    def test_option_values_stay_with_flags_in_order(self) -> None:
        _, flags = _partition_test_args(["-k", "foo", "-m", "blns"])
        assert flags == ["-k", "foo", "-m", "blns"]

    def test_node_ids_and_directories_are_paths(self) -> None:
        lanes, _ = _partition_test_args(
            ["tests/unit/test_x.py::TestC::test_m", "tests/integration/"]
        )
        assert lanes["unit"] == [
            "tests/unit/test_x.py::TestC::test_m",
            "tests/integration/",
        ]

    def test_bare_invocation_yields_empty_lanes(self) -> None:
        lanes, flags = _partition_test_args([])
        assert lanes == {"e2e": [], "nicegui": [], "unit": []}
        assert flags == []
