"""Pure boundary tests for every campaign-capable performance probe."""

from __future__ import annotations


def test_cram_verdicts_clean_degraded_and_systemic_cohorts() -> None:
    """The cram cohort threshold, not pytest exit status, identifies collapse."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from tests.e2e.test_assessment_cram_load import (
        ActionResult,
        CramObservation,
        _cram_gate,
    )

    clean = [
        CramObservation(email=f"clean-{index}", annotation_loaded=True)
        for index in range(25)
    ]
    degraded = [*clean]
    degraded[0] = CramObservation(
        email="degraded",
        annotation_loaded=True,
        actions=[ActionResult(action="highlight", error="one timeout")],
    )
    collapsed = [*clean]
    for index in range(4):
        collapsed[index] = CramObservation(
            email=f"failed-{index}",
            error="page load failed",
        )

    assert _cram_gate(clean).verdict.classification is PerfClassification.PASS
    assert (
        _cram_gate(degraded).verdict.classification
        is PerfClassification.PASS_WITH_DEGRADATION
    )
    assert _cram_gate(collapsed).verdict.classification is PerfClassification.COLLAPSE


def test_soak_verdicts_clean_degraded_and_systemic_cohorts() -> None:
    """Browser degradation stays distinct from a distributed soak boundary."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from tests.e2e.test_soak_full_crud_load import (
        ACTIONS_PER_MIN,
        MIN_ACTION_FRACTION,
        SOAK_MINUTES,
        ActionResult,
        SoakObservation,
        _soak_gate,
    )

    minimum_work = int(ACTIONS_PER_MIN * SOAK_MINUTES * MIN_ACTION_FRACTION) + 1

    def successful_actions() -> list[ActionResult]:
        return [ActionResult(action="highlight_create") for _ in range(minimum_work)]

    clean = [
        SoakObservation(
            email="clean",
            annotation_loaded=True,
            actions=successful_actions(),
        )
    ]
    degraded = [
        SoakObservation(
            email="degraded",
            annotation_loaded=True,
            actions=[
                *successful_actions(),
                ActionResult(
                    action="respond_type",
                    error="browser readiness timeout",
                    degraded=True,
                ),
            ],
        )
    ]
    collapsed = [
        SoakObservation(
            email=f"failed-{index}",
            annotation_loaded=True,
            actions=[
                *successful_actions(),
                ActionResult(action="highlight_create", error="server timeout"),
            ],
        )
        for index in range(3)
    ]

    assert _soak_gate(clean).verdict.classification is PerfClassification.PASS
    assert (
        _soak_gate(degraded).verdict.classification
        is PerfClassification.PASS_WITH_DEGRADATION
    )
    assert _soak_gate(collapsed).verdict.classification is PerfClassification.COLLAPSE


def test_herd_verdicts_clean_degraded_and_systemic_cohorts() -> None:
    """Herd load/action evidence maps to the common typed verdicts."""
    from promptgrimoire.cli.perf.results import PerfClassification
    from tests.e2e.test_thundering_herd import (
        ActionResult,
        CycleResult,
        HerdObservation,
        _herd_verdict,
    )

    clean = [
        HerdObservation(email=f"clean-{index}", annotation_loaded=True)
        for index in range(25)
    ]
    degraded = [*clean]
    degraded[0] = HerdObservation(
        email="degraded",
        annotation_loaded=True,
        cycles=[
            CycleResult(
                actions=[
                    ActionResult(
                        action="respond",
                        error="browser readiness timeout",
                        degraded=True,
                    )
                ]
            )
        ],
    )
    collapsed = [*clean]
    for index in range(4):
        collapsed[index] = HerdObservation(
            email=f"failed-{index}",
            error="annotation load failed",
        )

    assert _herd_verdict(clean).classification is PerfClassification.PASS
    assert (
        _herd_verdict(degraded).classification
        is PerfClassification.PASS_WITH_DEGRADATION
    )
    assert _herd_verdict(collapsed).classification is PerfClassification.COLLAPSE
