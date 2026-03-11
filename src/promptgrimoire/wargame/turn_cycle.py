"""Pure domain helpers for the wargame turn cycle engine.

All functions are side-effect-free. Database orchestration lives in
``db/wargames.py``; these helpers are called from that imperative shell.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from string.templatelib import Interpolation, Template

import pycrdt

__all__ = [
    "NO_MOVE_SENTINEL",
    "build_summary_prompt",
    "build_turn_prompt",
    "calculate_deadline",
    "expand_bootstrap",
    "extract_move_text",
    "render_prompt",
]

NO_MOVE_SENTINEL = "No move submitted"


def expand_bootstrap(template: str, codename: str) -> str:
    """Expand a scenario bootstrap template with team codename.

    Uses ``str.replace`` rather than ``str.format`` because the template
    is user-authored database content that may contain unrelated braces
    (e.g. JSON examples in scenario text).

    Parameters
    ----------
    template:
        The ``WargameConfig.scenario_bootstrap`` text with ``{codename}``
        placeholder.
    codename:
        The team's codename (e.g. ``BOLD-GRIFFIN``).

    Returns
    -------
    str
        Template with ``{codename}`` replaced by the actual codename.
    """
    return template.replace("{codename}", codename)


def calculate_deadline(
    *,
    publish_time: datetime,
    timer_delta: timedelta | None,
    timer_wall_clock: time | None,
) -> datetime:
    """Calculate the next deadline from publish time and timer config.

    Exactly one of ``timer_delta`` or ``timer_wall_clock`` must be
    provided (enforced by WargameConfig's model validator and CHECK
    constraint).

    Parameters
    ----------
    publish_time:
        When the round was published (timezone-aware).
    timer_delta:
        Relative duration from publish time.
    timer_wall_clock:
        Fixed time of day. Rolls to next day if already past.

    Returns
    -------
    datetime
        Timezone-aware deadline.

    Raises
    ------
    ValueError
        If neither or both timer fields are set.
    """
    if (timer_delta is None) == (timer_wall_clock is None):
        msg = "exactly one of timer_delta or timer_wall_clock must be set"
        raise ValueError(msg)

    if timer_delta is not None:
        return publish_time + timer_delta

    # Wall-clock mode: next occurrence of the given time.
    # timer_wall_clock is guaranteed non-None by the XOR guard above;
    # the explicit check satisfies the type checker.
    if timer_wall_clock is None:  # pragma: no cover — unreachable
        msg = "exactly one of timer_delta or timer_wall_clock must be set"
        raise ValueError(msg)
    wall = timer_wall_clock
    tz = publish_time.tzinfo
    candidate = datetime.combine(publish_time.date(), wall, tzinfo=tz)
    if candidate <= publish_time:
        candidate = datetime.combine(
            publish_time.date() + timedelta(days=1),
            wall,
            tzinfo=tz,
        )
    return candidate


def extract_move_text(move_buffer_crdt: bytes | None) -> str:
    """Extract markdown text from a team's CRDT move buffer.

    Parameters
    ----------
    move_buffer_crdt:
        Raw CRDT bytes from ``WargameTeam.move_buffer_crdt``, or ``None``
        if no buffer exists.

    Returns
    -------
    str
        The extracted markdown, or ``NO_MOVE_SENTINEL`` if the buffer is
        ``None``, empty, or whitespace-only.
    """
    if move_buffer_crdt is None:
        return NO_MOVE_SENTINEL

    doc = pycrdt.Doc()
    doc.apply_update(move_buffer_crdt)
    text = doc.get("content_markdown", type=pycrdt.Text)
    content = str(text).strip()
    if not content:
        return NO_MOVE_SENTINEL
    return content


def render_prompt(template: Template) -> str:
    """Render a t-string template to a plain string.

    Interpolated values are converted to strings. No escaping is applied
    because prompts are not a security-sensitive context (all inputs are
    server-controlled).

    Parameters
    ----------
    template:
        A t-string ``Template`` object.

    Returns
    -------
    str
        The rendered prompt string.
    """
    parts: list[str] = []
    for item in template:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, Interpolation):
            value = item.value
            if item.conversion == "r":
                value = repr(value)
            elif item.conversion == "s":
                value = str(value)
            elif item.conversion == "a":
                value = ascii(value)
            value = format(value, item.format_spec) if item.format_spec else str(value)
            parts.append(value)
    return "".join(parts)


def build_turn_prompt(move_text: str, game_state: str) -> str:
    """Assemble the user prompt for the turn agent.

    Parameters
    ----------
    move_text:
        The team's move text (extracted from CRDT or ``NO_MOVE_SENTINEL``).
    game_state:
        Current game state artifact (GM-only context).

    Returns
    -------
    str
        Assembled prompt for the turn agent.
    """
    return render_prompt(
        t"""<game_state>
{game_state}
</game_state>

<cadet_orders>
{move_text}
</cadet_orders>"""
    )


def build_summary_prompt(response_text: str) -> str:
    """Assemble the user prompt for the summary agent.

    Parameters
    ----------
    response_text:
        The approved assistant response text for the team.

    Returns
    -------
    str
        Assembled prompt for the summary agent.
    """
    return render_prompt(
        t"""Summarise the following response for the student team. \
Include only information that students should see. \
Do not reveal hidden game state or GM-only details.

<response>
{response_text}
</response>"""
    )
