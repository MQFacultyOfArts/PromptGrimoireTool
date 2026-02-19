"""Deterministic anonymisation utility for annotation authors.

Provides adjective-animal pseudonyms derived from user IDs via the
``coolname`` library (~328k unique 2-word combinations). Labels are
deterministic per user_id — stable across sessions and page reloads.
"""

from __future__ import annotations

import hashlib
import pathlib
import random

from coolname import RandomGenerator
from coolname.loader import load_config

# Load coolname config once at module level.
_COOLNAME_CONFIG = load_config(
    pathlib.Path(__import__("coolname").__file__).parent / "data"  # type: ignore[arg-type]
)


def _adjective_animal_label(user_id: str) -> str:
    """Derive a deterministic adjective-animal label from a user_id.

    Seeds a ``coolname.RandomGenerator`` with a SHA-256 hash of the
    user_id, producing a stable 2-word title-cased label
    (e.g. "Crystal Peccary").
    """
    seed = int.from_bytes(hashlib.sha256(user_id.encode()).digest()[:8])
    gen = RandomGenerator(_COOLNAME_CONFIG, random.Random(seed))
    slug = gen.generate_slug(2)
    return slug.replace("-", " ").title()


def anonymise_author(
    author: str,
    user_id: str | None,
    viewing_user_id: str | None,
    anonymous_sharing: bool,
    viewer_is_privileged: bool,
    viewer_is_owner: bool,
) -> str:
    """Return the display name for an annotation author.

    Resolution order:
    1. No anonymisation active -> real author
    2. Privileged viewer or workspace owner -> real author
    3. Viewing own annotation -> real author
    4. Legacy data (no user_id) -> "Unknown"
    5. Otherwise -> deterministic adjective-animal label

    Parameters
    ----------
    author:
        The real display name stored with the annotation.
    user_id:
        The Stytch user ID of the annotation creator, or None
        for legacy data.
    viewing_user_id:
        The Stytch user ID of the current viewer, or None if
        unauthenticated.
    anonymous_sharing:
        Whether anonymisation is enabled for this workspace.
    viewer_is_privileged:
        Whether the viewer is an instructor or admin.
    viewer_is_owner:
        Whether the viewer is the workspace owner.

    Returns
    -------
    str
        The name to display for this author.
    """
    if not anonymous_sharing:
        return author
    if viewer_is_privileged or viewer_is_owner:
        return author
    if (
        user_id is not None
        and viewing_user_id is not None
        and user_id == viewing_user_id
    ):
        return author
    if user_id is None:
        return "Unknown"
    return _adjective_animal_label(user_id)


def anonymise_display_name(user_id: str | None) -> str:
    """Return the deterministic adjective-animal label for a user_id.

    Unlike ``anonymise_author``, this does not check permissions or
    viewing context -- it always returns the anonymised label.
    Callers are responsible for gating when to use this vs the real
    name.

    Returns ``"Unknown"`` if *user_id* is ``None``.
    """
    if user_id is None:
        return "Unknown"
    return _adjective_animal_label(user_id)
