"""Structural guard: to_jsonb-hydrated models must carry no lossy field types.

``to_jsonb(table.*)`` silently corrupts ``bytea`` columns (verified on
``Workspace.crdt_state``; see docs/architecture/raw-sql-convention.md §
"ty gotchas"). ``resolve_annotation_context`` and its siblings in
``db/workspaces.py`` work around this by hydrating ``Workspace`` from its
own unprefixed columns (``w.*`` + ``model_validate(row, from_attributes=True)``)
and reserving ``to_jsonb(...)`` for scalar-only entities (currently
ACLEntry, Activity, Week, Course).

This guard parses ``workspaces.py``'s source to find every
``to_jsonb(alias.*) AS x_json`` result column and the
``Model.model_validate(...)`` call each alias feeds, then asserts the
resolved model has no field typed ``bytes``, ``Decimal``, ``float``, or
``timedelta`` -- the pydantic-level signature of "would silently corrupt
or lose precision under to_jsonb's opaque JSON round-trip". The model
list is derived from the source, not hand-maintained: a hand-maintained
list would be a tautology against exactly the regression this guard
exists to catch. Adding a new to_jsonb column, or a
bytes/Decimal/float/timedelta field to an existing to_jsonb-hydrated
model, must fail this test.
"""

import ast
import re
import types
import typing
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Iterator

_WORKSPACES_PY = (
    Path(__file__).parents[2] / "src" / "promptgrimoire" / "db" / "workspaces.py"
)

_TO_JSONB_ALIAS_RE = re.compile(r"to_jsonb\([\w.]+\*\)\s+AS\s+(\w+)", re.IGNORECASE)

_FORBIDDEN_TYPES: tuple[type, ...] = (bytes, Decimal, float, timedelta)


def _find_to_jsonb_aliases(source: str) -> set[str]:
    """Return every ``to_jsonb(x.*) AS <alias>`` result-column alias in *source*."""
    return set(_TO_JSONB_ALIAS_RE.findall(source))


def _find_model_validate_targets(
    source: str,
    aliases: set[str],
    *,
    filename: str = "<source>",
) -> dict[str, str]:
    """Map each to_jsonb alias to the model class hydrated from it.

    Walks every ``<Model>.model_validate(<expr>.<alias>)`` call in
    *source* and records ``alias -> Model`` for aliases in *aliases*.
    ``ast.walk`` visits every descendant node regardless of whether the
    call sits bare, inside a ternary, or nested some other way, so no
    special-casing of surrounding syntax is needed.
    """
    tree = ast.parse(source, filename=filename)
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "model_validate"):
            continue
        if not (isinstance(func.value, ast.Name) and node.args):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Attribute) and arg.attr in aliases:
            mapping[arg.attr] = func.value.id
    return mapping


def _iter_leaf_types(annotation: object) -> Iterator[object]:
    """Yield the non-None leaf types of *annotation*, unwrapping ``X | None``."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        for arg in typing.get_args(annotation):
            if arg is type(None):
                continue
            yield from _iter_leaf_types(arg)
    else:
        yield annotation


def _forbidden_fields(model: type[BaseModel]) -> list[str]:
    """Return field names on *model* typed bytes/Decimal/float/timedelta."""
    violations: list[str] = []
    for name, field in model.model_fields.items():
        for leaf in _iter_leaf_types(field.annotation):
            if isinstance(leaf, type) and issubclass(leaf, _FORBIDDEN_TYPES):
                violations.append(name)
                break
    return violations


def test_synthetic_alias_and_model_extraction() -> None:
    """The extractor maps a to_jsonb alias to its hydrating model.

    Proves the mechanism independently of the real file: a change that
    breaks alias or model-name extraction fails here directly, rather
    than showing up as a silently-empty scan of workspaces.py that would
    make the main guard test below pass for the wrong reason.
    """
    snippet = (
        "row = await session.execute(\n"
        '    tstring(t"SELECT to_jsonb(x.*) AS thing_json FROM x")\n'
        ")\n"
        "thing = Thing.model_validate(row.thing_json) if row.thing_json else None\n"
    )

    aliases = _find_to_jsonb_aliases(snippet)
    assert aliases == {"thing_json"}

    mapping = _find_model_validate_targets(snippet, aliases)
    assert mapping == {"thing_json": "Thing"}


def test_forbidden_field_type_detection() -> None:
    """The field-type checker flags bytes/Decimal/float/timedelta fields."""

    class _Dirty(BaseModel):
        ok: int
        bad: bytes | None = None

    class _AlsoDirty(BaseModel):
        amount: Decimal
        elapsed: timedelta | None = None
        ratio: float = 0.0

    class _Clean(BaseModel):
        ok: int
        name: str | None = None
        count: int = 0

    assert _forbidden_fields(_Dirty) == ["bad"]
    assert set(_forbidden_fields(_AlsoDirty)) == {"amount", "elapsed", "ratio"}
    assert _forbidden_fields(_Clean) == []


def test_to_jsonb_hydrated_models_have_no_forbidden_field_types() -> None:
    """No model hydrated via to_jsonb in workspaces.py may carry a
    bytes/Decimal/float/timedelta field.

    ``to_jsonb(table.*)`` silently corrupts such columns (bytea observed
    on Workspace.crdt_state; Decimal/float/timedelta share the same
    "opaque JSON round-trip" risk surface). If this fails, either
    hydrate the new field from its real column instead of via to_jsonb
    (see Workspace's ``w.*`` + ``model_validate(row, from_attributes=True)``
    pattern), or keep the to_jsonb entity scalar-only.
    """
    source = _WORKSPACES_PY.read_text()

    aliases = _find_to_jsonb_aliases(source)
    assert aliases, (
        f"No `to_jsonb(...) AS <alias>` found in {_WORKSPACES_PY} -- the "
        "extractor regex may be broken, or the query no longer uses "
        "to_jsonb. Either way this guard is currently checking nothing; "
        "investigate before trusting a green run here."
    )

    alias_to_model = _find_model_validate_targets(
        source, aliases, filename=str(_WORKSPACES_PY)
    )
    unresolved = aliases - alias_to_model.keys()
    assert not unresolved, (
        f"to_jsonb alias(es) {sorted(unresolved)} in {_WORKSPACES_PY} have "
        "no matching `Model.model_validate(row.<alias>)` call this guard "
        "can find -- update the extractor, or hydrate via a traceable "
        "`Model.model_validate(row.<alias>)` call so the model stays "
        "checkable."
    )

    import promptgrimoire.db.models as models_module

    violations: dict[str, list[str]] = {}
    for model_name in set(alias_to_model.values()):
        model = getattr(models_module, model_name)
        bad_fields = _forbidden_fields(model)
        if bad_fields:
            violations[model_name] = bad_fields

    assert not violations, (
        "to_jsonb(...) hydration in workspaces.py would silently corrupt "
        "or lose precision on these fields (see docs/architecture/"
        "raw-sql-convention.md § 'ty gotchas'):\n"
        + "\n".join(f"  {m}: {fs}" for m, fs in violations.items())
    )
