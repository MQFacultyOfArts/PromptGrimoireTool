"""Deterministic anonymisation utility for annotation authors.

Provides adjective-animal pseudonyms derived from user IDs via SHA-256
hashing. Labels are stable across sessions and page reloads.
"""

from __future__ import annotations

import hashlib
import struct

# 50 positive/neutral adjectives -- audited for appropriateness
ADJECTIVES: tuple[str, ...] = (
    "Bright",
    "Calm",
    "Clever",
    "Coral",
    "Crisp",
    "Daring",
    "Eager",
    "Fair",
    "Gentle",
    "Golden",
    "Happy",
    "Honest",
    "Jolly",
    "Keen",
    "Kind",
    "Lively",
    "Lucky",
    "Mellow",
    "Merry",
    "Mighty",
    "Noble",
    "Olive",
    "Peaceful",
    "Plucky",
    "Polite",
    "Proud",
    "Quick",
    "Quiet",
    "Radiant",
    "Rosy",
    "Sandy",
    "Silver",
    "Sleek",
    "Snowy",
    "Spruce",
    "Steady",
    "Sunny",
    "Swift",
    "Tawny",
    "Tender",
    "Tidy",
    "Topaz",
    "Valiant",
    "Verdant",
    "Vivid",
    "Warm",
    "Witty",
    "Zany",
    "Zesty",
    "Azure",
)

# 50 animals -- audited for appropriateness
ANIMALS: tuple[str, ...] = (
    "Badger",
    "Bear",
    "Bison",
    "Crane",
    "Deer",
    "Dolphin",
    "Eagle",
    "Falcon",
    "Finch",
    "Fox",
    "Gecko",
    "Hare",
    "Hawk",
    "Heron",
    "Horse",
    "Ibis",
    "Jaguar",
    "Jay",
    "Koala",
    "Lark",
    "Lemur",
    "Llama",
    "Lynx",
    "Marten",
    "Moth",
    "Newt",
    "Okapi",
    "Otter",
    "Owl",
    "Panda",
    "Parrot",
    "Pelican",
    "Puffin",
    "Quail",
    "Raven",
    "Robin",
    "Seal",
    "Shrike",
    "Sloth",
    "Sparrow",
    "Stork",
    "Swan",
    "Tern",
    "Tiger",
    "Toucan",
    "Turtle",
    "Viper",
    "Whale",
    "Wren",
    "Zebra",
)


def _adjective_animal_label(user_id: str) -> str:
    """Derive a deterministic adjective-animal label from a user_id.

    Uses SHA-256 hash: first 4 bytes select the adjective,
    next 4 bytes select the animal.
    """
    digest = hashlib.sha256(user_id.encode()).digest()
    adj_idx = struct.unpack_from(">I", digest, 0)[0] % len(ADJECTIVES)
    animal_idx = struct.unpack_from(">I", digest, 4)[0] % len(ANIMALS)
    return f"{ADJECTIVES[adj_idx]} {ANIMALS[animal_idx]}"


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
