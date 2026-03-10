# pattern: Functional Core

"""Pure codename generation helpers for wargame teams."""

from coolname import generate_slug

MAX_CODENAME_ATTEMPTS = 100


def generate_codename(
    existing: set[str], *, max_attempts: int = MAX_CODENAME_ATTEMPTS
) -> str:
    """Generate a unique uppercase codename not present in ``existing``.

    Parameters
    ----------
    existing : set[str]
        Activity-local codename collision set supplied by the caller.
    max_attempts : int, default=MAX_CODENAME_ATTEMPTS
        Maximum number of slug attempts before raising.

    Returns
    -------
    str
        Uppercase two-word slug such as ``BOLD-GRIFFIN``.

    Raises
    ------
    RuntimeError
        If no unique codename is found within ``max_attempts`` attempts.
    """
    for _ in range(max_attempts):
        candidate = generate_slug(2).upper()
        if candidate not in existing:
            return candidate

    msg = f"failed to generate unique codename after {max_attempts} attempts"
    raise RuntimeError(msg)
