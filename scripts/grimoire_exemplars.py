#!/usr/bin/env python3
"""Find thoughtful annotation exemplars per unit -> assessment, for a demo.

Companion to ``scripts/grimoire_usage_snapshot.sql``.  Where that query counts
*how much* happened, this one surfaces *good examples* of student annotation
work so they can be opened as browser tabs and spoken to in a faculty-exec
demo.

Why a script and not pure SQL
-----------------------------
The signals that distinguish a thoughtful workspace -- highlight count, comment
count, distinct tags used, whether the student worked in the Organise ("second")
tab and reordered cards, whether they wrote a Respond draft -- all live inside
``workspace.crdt_state`` (a pycrdt binary blob), not in queryable columns.  The
only SQL-visible proxy is ``length(search_text)``, which mashes draft prose and
annotations together and cannot separate count from comments.  So this tool
pulls candidate workspaces via SQL, deserialises each CRDT blob with the app's
own ``AnnotationDocument``, and computes real per-workspace metrics.

What "good" means here (per Brian, 2026-06-04)
----------------------------------------------
Richness AND thoughtfulness -- explicitly NOT the "p100 over-highlighter" who
highlighted everything.  Operationalised as a thoughtfulness score, not a raw
count:

* count terms **saturate** (``x/(x+k)``) -- going from 30 to 150 highlights
  barely moves the score, so maximal-count students do not dominate;
* **comments** are rewarded (commented, not just highlighted), both in absolute
  count and as a ratio of highlights that carry a comment;
* **tag diversity** is rewarded (discriminating use, not one-tag-everything);
* **Organise-tab engagement** (any tag has a non-empty ordered highlight list --
  only the Organise drag writes that) and a **Respond draft** are bonuses;
* a **coverage penalty** (highlighted_chars / source_chars above a threshold)
  actively demotes the "highlighted everything" student.  This is the term that
  answers "no p100 overachievers" structurally, rather than via an arbitrary cap.

Eligibility: a workspace must clear a highlight floor AND have >= 1 comment to
be an "example".  If an assessment has no eligible workspace, the tool falls
back to its top-scored workspaces regardless of comments and flags the section
``fallback`` so the gap is visible rather than silently hidden.

Run on prod (you run it; this dev box has no prod data)
-------------------------------------------------------
    ssh grimoire.drbbs.org
    cd /path/to/PromptGrimoireTool && git pull
    sudo -u promptgrimoire env "$(grep -v '^#' .env | xargs)" \\
        uv run python scripts/grimoire_exemplars.py \\
        --out /tmp/exemplars.html --json-out /tmp/exemplars.json
    # Output goes to files, not stdout (the app logs to stdout).  Copy
    # /tmp/exemplars.html back and open it; every link is target=_blank, so
    # "open all in tabs" from the browser gives you one tab per example.

The weights are tunable from the CLI -- expect to adjust them once against the
real cohort (this dev box only has sparse seed data).
"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import typer
from sqlalchemy import text as sql_text

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.db.engine import get_session

# --------------------------------------------------------------------------- #
# Pure core: metrics + scoring (unit-tested in tests/unit/test_grimoire_       #
# exemplars.py).  No I/O here.                                                 #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class WorkspaceMetrics:
    """Per-workspace annotation metrics extracted from a CRDT document."""

    highlight_count: int
    comment_count: int
    highlights_with_comments: int
    distinct_tags: int
    highlighted_chars: int
    source_chars: int
    coverage_ratio: float
    organise_engaged: bool
    respond_words: int
    notes_words: int


@dataclass(frozen=True, slots=True)
class Weights:
    """Tunable weights for :func:`thoughtfulness_score`.

    Defaults are a starting point chosen so the positive terms each contribute
    roughly comparable magnitude and the coverage penalty can dominate a
    "highlighted everything" workspace.  Tune against real data.
    """

    hl_weight: float = 1.0
    hl_saturation: float = 12.0
    comment_weight: float = 1.0
    comment_saturation: float = 6.0
    comment_ratio_weight: float = 0.6
    tag_weight: float = 0.5
    tag_saturation: float = 4.0
    organise_bonus: float = 0.4
    respond_bonus: float = 0.4
    coverage_penalty_weight: float = 1.5
    coverage_threshold: float = 0.5


DEFAULT_WEIGHTS = Weights()


def _saturate(x: float, k: float) -> float:
    """Diminishing-returns transform ``x / (x + k)`` in ``[0, 1)``.

    ``k`` is the half-saturation point: ``_saturate(k, k) == 0.5``.  This is
    what stops a maximal raw count from dominating the score.
    """
    if x <= 0:
        return 0.0
    return x / (x + k)


def compute_metrics(doc: AnnotationDocument, source_chars: int) -> WorkspaceMetrics:
    """Extract annotation metrics from a deserialised CRDT document.

    Parameters
    ----------
    doc : AnnotationDocument
        A document with the workspace's CRDT state already applied.
    source_chars : int
        Approximate visible character count of the workspace's source
        documents (HTML stripped).  Denominator for ``coverage_ratio``.
    """
    highlights = doc.get_all_highlights()
    comment_count = 0
    highlights_with_comments = 0
    highlighted_chars = 0
    tags_used: set[str] = set()

    for h in highlights:
        comments = h.get("comments") or []
        n = len(comments)
        comment_count += n
        if n:
            highlights_with_comments += 1
        span = (h.get("end_char") or 0) - (h.get("start_char") or 0)
        if span > 0:
            highlighted_chars += span
        if tag := (h.get("tag") or ""):
            tags_used.add(tag)

    # Only Organise-tab drags populate a tag's ordered highlight list; plain
    # annotation (Annotate tab) never does.  So a non-empty list == the student
    # worked in the second tab.
    organise_engaged = any(
        len(t.get("highlights") or []) > 0 for t in doc.list_tags().values()
    )

    coverage_ratio = highlighted_chars / source_chars if source_chars > 0 else 0.0

    return WorkspaceMetrics(
        highlight_count=len(highlights),
        comment_count=comment_count,
        highlights_with_comments=highlights_with_comments,
        distinct_tags=len(tags_used),
        highlighted_chars=highlighted_chars,
        source_chars=source_chars,
        coverage_ratio=coverage_ratio,
        organise_engaged=organise_engaged,
        respond_words=len(doc.get_response_draft_markdown().split()),
        notes_words=len(doc.get_general_notes().split()),
    )


def thoughtfulness_score(m: WorkspaceMetrics, w: Weights) -> float:
    """Score a workspace's annotation thoughtfulness (higher is better)."""
    score = w.hl_weight * _saturate(m.highlight_count, w.hl_saturation)
    score += w.comment_weight * _saturate(m.comment_count, w.comment_saturation)
    if m.highlight_count > 0:
        score += w.comment_ratio_weight * (
            m.highlights_with_comments / m.highlight_count
        )
    score += w.tag_weight * _saturate(m.distinct_tags, w.tag_saturation)
    if m.organise_engaged:
        score += w.organise_bonus
    if m.respond_words > 0:
        score += w.respond_bonus

    # Coverage penalty: ramps from 0 at the threshold to the full weight at
    # 100% coverage.  Demotes the "highlighted everything" workspace.
    capped = min(m.coverage_ratio, 1.0)
    if capped > w.coverage_threshold < 1.0:
        excess = (capped - w.coverage_threshold) / (1.0 - w.coverage_threshold)
        score -= w.coverage_penalty_weight * excess

    return score


def is_eligible(m: WorkspaceMetrics, min_highlights: int) -> bool:
    """A workspace is an "example" if it clears the floor and has a comment."""
    return m.highlight_count >= min_highlights and m.comment_count >= 1


# --------------------------------------------------------------------------- #
# Imperative shell: query, deserialise, group, render.                        #
# --------------------------------------------------------------------------- #

_CANDIDATE_SQL = """
SELECT
    c.id                AS course_id,
    c.code              AS course_code,
    c.name              AS course_name,
    c.semester          AS semester,
    c.is_archived       AS is_archived,
    wk.week_number      AS week_number,
    wk.title            AS week_title,
    a.id                AS activity_id,
    a.title             AS activity_title,
    w.id                AS workspace_id,
    w.title             AS workspace_title,
    w.crdt_state        AS crdt_state,
    (SELECT u.email FROM acl_entry ae JOIN "user" u ON u.id = ae.user_id
       WHERE ae.workspace_id = w.id AND ae.permission = 'owner'
       ORDER BY ae.created_at LIMIT 1)        AS owner_email,
    (SELECT u.display_name FROM acl_entry ae JOIN "user" u ON u.id = ae.user_id
       WHERE ae.workspace_id = w.id AND ae.permission = 'owner'
       ORDER BY ae.created_at LIMIT 1)        AS owner_name,
    COALESCE((
        SELECT SUM(char_length(regexp_replace(wd.content, '<[^>]+>', ' ', 'g')))
        FROM workspace_document wd
        WHERE wd.workspace_id = w.id AND wd.type = 'source'
    ), 0)                                     AS source_chars
FROM workspace w
JOIN activity a  ON a.id = w.activity_id AND a.type = 'annotation'
JOIN week wk     ON wk.id = a.week_id
JOIN course c    ON c.id = wk.course_id
WHERE w.activity_id IS NOT NULL
  AND (a.template_workspace_id IS NULL OR w.id <> a.template_workspace_id)
  AND w.crdt_state IS NOT NULL
ORDER BY c.is_archived, c.semester DESC, c.code, wk.week_number, a.title
"""


@dataclass(frozen=True, slots=True)
class Candidate:
    """One scored student workspace, ready to render."""

    workspace_id: str
    owner_email: str
    owner_name: str
    week_number: int
    week_title: str
    score: float
    metrics: WorkspaceMetrics
    teaser: str


def _first_comment_teaser(doc: AnnotationDocument, limit: int = 160) -> str:
    """A short human-readable teaser: the first commented highlight, if any."""
    for h in doc.get_all_highlights():
        comments = h.get("comments") or []
        if comments:
            text = (h.get("text") or "").strip()
            comment = (comments[0].get("text") or "").strip()
            teaser = f"“{text[:80]}” — {comment}" if text else comment
            return teaser[:limit]
    return ""


def _deserialise(crdt_state: bytes | memoryview | None) -> AnnotationDocument | None:
    if crdt_state is None:
        return None
    doc = AnnotationDocument("exemplar-scan")
    doc.apply_update(bytes(crdt_state))
    return doc


def workspace_url(base_url: str, workspace_id: str) -> str:
    """Build the annotation tab URL for a workspace."""
    return f"{base_url.rstrip('/')}/annotation?workspace_id={workspace_id}"


async def _gather_candidates(
    weights: Weights,
) -> dict[tuple[str, str, str, bool], dict[str, list[Candidate]]]:
    """Return units -> assessments -> scored candidates.

    Key is ``(course_code, course_name, semester, is_archived)``; inner key is
    the activity title.  Workspaces whose CRDT blob fails to deserialise are
    skipped with a warning (a single corrupt blob must not kill the run).
    """
    units: dict[tuple[str, str, str, bool], dict[str, list[Candidate]]] = defaultdict(
        lambda: defaultdict(list)
    )
    async with get_session() as session:
        # Raw textual SQL goes through the SQLAlchemy connection, not the
        # SQLModel session.execute() override (which warns, expecting exec()).
        conn = await session.connection()
        result = await conn.execute(sql_text(_CANDIDATE_SQL))
        rows = result.mappings().all()

    for row in rows:
        wid = str(row["workspace_id"])
        try:
            doc = _deserialise(row["crdt_state"])
        except Exception as exc:  # report and skip one bad blob, don't kill the run
            typer.echo(f"warning: skipped workspace {wid}: {exc}", err=True)
            continue
        if doc is None:
            continue

        metrics = compute_metrics(doc, int(row["source_chars"] or 0))
        if metrics.highlight_count == 0:
            continue  # nothing annotated; never an example

        unit_key = (
            row["course_code"],
            row["course_name"],
            row["semester"],
            bool(row["is_archived"]),
        )
        units[unit_key][row["activity_title"]].append(
            Candidate(
                workspace_id=wid,
                owner_email=row["owner_email"] or "(unknown)",
                owner_name=row["owner_name"] or "(unknown)",
                week_number=int(row["week_number"]),
                week_title=row["week_title"],
                score=thoughtfulness_score(metrics, weights),
                metrics=metrics,
                teaser=_first_comment_teaser(doc),
            )
        )
    return units


def select_examples(
    candidates: list[Candidate], top: int, min_highlights: int
) -> tuple[list[Candidate], bool]:
    """Pick the top examples for one assessment.

    Returns ``(examples, fallback)``.  Prefers eligible (commented) workspaces;
    if none, falls back to the top-scored regardless of comments and sets
    ``fallback=True``.
    """
    eligible = [c for c in candidates if is_eligible(c.metrics, min_highlights)]
    pool = eligible or candidates
    ranked = sorted(pool, key=lambda c: c.score, reverse=True)
    return ranked[:top], not eligible


@dataclass(frozen=True, slots=True)
class ExampleView:
    """One rendered exemplar (JSON- and HTML-serialisable)."""

    workspace_id: str
    url: str
    owner_email: str
    owner_name: str
    week: str
    score: float
    teaser: str
    metrics: WorkspaceMetrics


@dataclass(frozen=True, slots=True)
class AssessmentBlock:
    """All exemplars chosen for one assessment (activity)."""

    assessment: str
    candidate_workspaces: int
    fallback_no_commented_examples: bool
    examples: list[ExampleView]


@dataclass(frozen=True, slots=True)
class UnitBlock:
    """One unit and its assessments."""

    unit: str
    code: str
    is_archived: bool
    assessments: list[AssessmentBlock]


@dataclass(frozen=True, slots=True)
class Totals:
    """Run-level totals."""

    units: int
    examples: int
    top_per_assessment: int
    min_highlights: int


@dataclass(frozen=True, slots=True)
class Report:
    """The full grouped report."""

    units: list[UnitBlock]
    totals: Totals


def build_report(
    units: dict[tuple[str, str, str, bool], dict[str, list[Candidate]]],
    *,
    top: int,
    min_highlights: int,
    base_url: str,
) -> Report:
    """Assemble the grouped, typed report structure."""
    unit_blocks: list[UnitBlock] = []
    total_examples = 0
    for (code, name, semester, is_archived), assessments in units.items():
        assessment_blocks: list[AssessmentBlock] = []
        for activity_title, cands in assessments.items():
            examples, fallback = select_examples(cands, top, min_highlights)
            total_examples += len(examples)
            assessment_blocks.append(
                AssessmentBlock(
                    assessment=activity_title,
                    candidate_workspaces=len(cands),
                    fallback_no_commented_examples=fallback,
                    examples=[
                        ExampleView(
                            workspace_id=c.workspace_id,
                            url=workspace_url(base_url, c.workspace_id),
                            owner_email=c.owner_email,
                            owner_name=c.owner_name,
                            week=f"W{c.week_number} {c.week_title}",
                            score=round(c.score, 3),
                            teaser=c.teaser,
                            metrics=c.metrics,
                        )
                        for c in examples
                    ],
                )
            )
        unit_blocks.append(
            UnitBlock(
                unit=f"{code} — {name} ({semester})",
                code=code,
                is_archived=is_archived,
                assessments=assessment_blocks,
            )
        )
    return Report(
        units=unit_blocks,
        totals=Totals(
            units=len(unit_blocks),
            examples=total_examples,
            top_per_assessment=top,
            min_highlights=min_highlights,
        ),
    )


_HTML_HEAD = (
    "<!doctype html><html><head><meta charset='utf-8'>\n"
    "<title>Grimoire annotation exemplars</title>\n"
    "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:60rem;"
    "margin:2rem auto;padding:0 1rem}h2{margin-top:2rem;border-bottom:"
    "2px solid #ccc}h3{margin:1.2rem 0 .3rem}li{margin:.35rem 0}"
    ".m{color:#555;font-size:.85em}.fb{color:#b00}.t{color:#333}</style>\n"
    "</head><body>"
)


def _engagement_suffix(m: WorkspaceMetrics) -> str:
    """Trailing ' · organised' / ' · responded' markers for the meta line."""
    suffix = ""
    if m.organise_engaged:
        suffix += " · organised"
    if m.respond_words:
        suffix += " · responded"
    return suffix


def _render_example(ex: ExampleView) -> str:
    """Render one exemplar as an <li> with a target=_blank tab link."""
    esc = html_lib.escape
    m = ex.metrics
    metaline = (
        f"score {ex.score} · {m.highlight_count} highlights · "
        f"{m.comment_count} comments · {m.distinct_tags} tags · "
        f"coverage {m.coverage_ratio:.0%}{_engagement_suffix(m)}"
    )
    teaser = f"<div class='t'>{esc(ex.teaser)}</div>" if ex.teaser else ""
    return (
        f"<li><a href='{esc(ex.url)}' target='_blank' "
        f"rel='noopener'>{esc(ex.owner_name)} "
        f"({esc(ex.owner_email)})</a> "
        f"<span class='m'>{ex.week}</span>"
        f"<div class='m'>{metaline}</div>{teaser}</li>"
    )


def _render_assessment(a: AssessmentBlock) -> list[str]:
    """Render one assessment heading plus its exemplar list."""
    esc = html_lib.escape
    fb = (
        " <span class='fb'>(no commented examples — fallback)</span>"
        if a.fallback_no_commented_examples
        else ""
    )
    parts = [
        f"<h3>{esc(a.assessment)}{fb} "
        f"<span class='m'>{a.candidate_workspaces} candidates</span></h3>"
    ]
    if not a.examples:
        parts.append("<p class='m'>no annotated workspaces</p>")
        return parts
    parts.append("<ul>")
    parts.extend(_render_example(ex) for ex in a.examples)
    parts.append("</ul>")
    return parts


def render_html(report: Report, base_url: str) -> str:
    """Render the report as a tab-launcher HTML page (all links target=_blank)."""
    esc = html_lib.escape
    parts: list[str] = [
        _HTML_HEAD,
        f"<h1>Annotation exemplars <span class='m'>({esc(base_url)})</span></h1>",
        "<p class='m'>Each link opens in a new tab. Use your browser's "
        "“open all in tabs” / middle-click to launch a whole assessment.</p>",
    ]
    for unit in report.units:
        archived = " [archived]" if unit.is_archived else ""
        parts.append(f"<h2>{esc(unit.unit)}{archived}</h2>")
        for a in unit.assessments:
            parts.extend(_render_assessment(a))
    parts.append("</body></html>")
    return "\n".join(parts)


# Module singletons: avoid B008 (function call in argument default).
_DEFAULT_OUT = Path("exemplars.html")
_DEFAULT_JSON_OUT = Path("exemplars.json")

app = typer.Typer(add_completion=False, help=__doc__)


@app.command()
def main(
    top: int = typer.Option(3, help="Top examples to show per assessment."),
    min_highlights: int = typer.Option(
        5, help="Minimum highlights for a workspace to qualify as an example."
    ),
    base_url: str = typer.Option(
        "https://grimoire.drbbs.org", help="Base URL for tab links."
    ),
    out: Path = typer.Option(
        _DEFAULT_OUT, help="Path to write the tab-launcher HTML page."
    ),
    json_out: Path = typer.Option(
        _DEFAULT_JSON_OUT, help="Path to write the machine-readable JSON report."
    ),
    hl_saturation: float = typer.Option(
        DEFAULT_WEIGHTS.hl_saturation,
        help="Half-saturation point for highlight count (higher = harder to max).",
    ),
    coverage_threshold: float = typer.Option(
        DEFAULT_WEIGHTS.coverage_threshold,
        help="Coverage ratio above which the over-highlighter penalty starts.",
    ),
    coverage_penalty_weight: float = typer.Option(
        DEFAULT_WEIGHTS.coverage_penalty_weight,
        help="Strength of the 'highlighted everything' demerit.",
    ),
) -> None:
    """Scan all units, rank thoughtful annotation exemplars, emit JSON + HTML.

    Output goes to files (not stdout): the app's structured logging writes to
    stdout, so a stdout-piped JSON would be polluted.  Both ``--out`` (HTML
    tab-launcher) and ``--json-out`` (machine-readable) are written; a one-line
    summary goes to stderr.
    """
    weights = replace(
        DEFAULT_WEIGHTS,
        hl_saturation=hl_saturation,
        coverage_threshold=coverage_threshold,
        coverage_penalty_weight=coverage_penalty_weight,
    )
    units = asyncio.run(_gather_candidates(weights))
    report = build_report(
        units, top=top, min_highlights=min_highlights, base_url=base_url
    )
    out.write_text(render_html(report, base_url), encoding="utf-8")
    json_out.write_text(
        json.dumps(asdict(report), indent=2, default=str), encoding="utf-8"
    )

    typer.echo(
        f"wrote {out} and {json_out} — "
        f"{report.totals.units} units, {report.totals.examples} examples",
        err=True,
    )


if __name__ == "__main__":
    app()
