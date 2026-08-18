"""Initial annotation snapshot: authorization token and bundle builder.

NiceGUI-free functional core for the standalone snapshot delivery service
(see docs/design-notes/2026-08-16-initial-snapshot-delivery.md).  The
NiceGUI process mints a token after its normal permission resolution; the
service verifies the token and builds one JSON bundle (document HTML,
highlights, tags, sidebar items) from the database and the persisted CRDT
state.  The service never widens access: every permission bit in the
bundle comes from the claims the NiceGUI process signed.

Guard: tests/unit/test_annotation_core.py asserts this module imports
without NiceGUI.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

import structlog

from promptgrimoire.annotation_core import (
    group_highlights_by_tag,
    serialise_items,
    workspace_tags,
)
from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.input_pipeline.paragraph_map import inject_paragraph_attributes

logger = structlog.get_logger()

#: Token lifetime.  Stateless presigned-URL model: replay within the TTL
#: yields the same read the same user is already authorised for.
TOKEN_TTL_SECONDS = 60


@dataclass(frozen=True, slots=True)
class SnapshotClaims:
    """Signed claims carried by a snapshot authorization token.

    Every field is resolved by the NiceGUI process's existing permission
    resolution (resolve_annotation_context) before minting.  The snapshot
    service treats them as authoritative and adds no grants of its own.
    """

    workspace_id: str
    document_id: str
    user_id: str | None
    viewer_is_privileged: bool
    can_annotate: bool
    anonymous_sharing: bool


def _sign(payload_b64: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload_b64, hashlib.sha256).hexdigest()


def mint_snapshot_token(
    claims: SnapshotClaims,
    *,
    secret: str,
    now: float | None = None,
) -> str:
    """Mint a signed, expiring snapshot token: base64url(JSON) + signature."""
    issued = time.time() if now is None else now
    payload = asdict(claims) | {"exp": issued + TOKEN_TTL_SECONDS}
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    return f"{payload_b64.decode()}.{_sign(payload_b64, secret)}"


def verify_snapshot_token(
    token: str,
    *,
    secret: str,
    now: float | None = None,
) -> SnapshotClaims | None:
    """Verify signature and expiry; return the claims or None.

    Returns None for malformed, tampered, wrongly-signed, or expired
    tokens.  No other checks: authorization happened at mint time.
    """
    current = time.time() if now is None else now
    payload_part, sep, signature = token.rpartition(".")
    if not sep or not payload_part:
        return None
    payload_b64 = payload_part.encode()
    if not hmac.compare_digest(signature, _sign(payload_b64, secret)):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = float(payload.pop("exp"))
        claims = SnapshotClaims(**payload)
    except ValueError, TypeError, KeyError, binascii.Error:
        logger.warning("snapshot_token_malformed")
        return None
    if current > exp:
        return None
    return claims


async def build_snapshot_bundle(claims: SnapshotClaims) -> dict[str, Any] | None:
    """Build the initial annotation bundle for verified claims.

    Sources: document and tag metadata from the database (the authority
    that CRDT tag hydration copies from); highlights from the workspace's
    persisted ``crdt_state`` hydrated into a throwaway AnnotationDocument
    (the db/crdt_extraction.py pattern).  Highlights whose tag is missing
    from the DB fall back to the same "recovered" label the page uses.

    Returns None when the workspace or document no longer exists or the
    document does not belong to the workspace.
    """
    # Local import: db pulls SQLModel/engine machinery; keep module import cheap.
    from promptgrimoire.db.acl import (  # noqa: PLC0415
        get_privileged_user_ids_for_workspace,
    )
    from promptgrimoire.db.workspace_documents import get_document  # noqa: PLC0415
    from promptgrimoire.db.workspaces import get_workspace  # noqa: PLC0415

    workspace_id = UUID(claims.workspace_id)
    document_id = UUID(claims.document_id)

    # ponytail: three sequential reads over three sessions; collapse into one
    # session if the snapshot service's own DB profile ever makes it material.
    workspace = await get_workspace(workspace_id)
    if workspace is None:
        return None
    document = await get_document(document_id)
    if document is None or document.workspace_id != workspace_id:
        return None
    tag_infos = await workspace_tags(workspace_id)
    privileged_user_ids = await get_privileged_user_ids_for_workspace(workspace_id)

    crdt_doc = AnnotationDocument(f"snapshot-{workspace_id}")
    if workspace.crdt_state:
        crdt_doc.apply_update(workspace.crdt_state)
    highlights = crdt_doc.get_highlights_for_document(str(document_id))

    tag_info_map = {ti.raw_key: ti for ti in tag_infos}
    tag_colours = {ti.raw_key: ti.colour for ti in tag_infos}

    items = serialise_items(
        highlights=highlights,
        tag_info_map=tag_info_map,
        tag_colours=tag_colours,
        user_id=claims.user_id,
        viewer_is_privileged=claims.viewer_is_privileged,
        privileged_user_ids=privileged_user_ids,
        can_annotate=claims.can_annotate,
        anonymous_sharing=claims.anonymous_sharing,
    )

    document_html = (
        inject_paragraph_attributes(document.content, document.paragraph_map or {})
        if document.content
        else ""
    )

    return {
        "document_html": document_html,
        "highlights": group_highlights_by_tag(highlights),
        "items": items,
        "tag_options": {ti.raw_key: ti.name for ti in tag_infos},
        "permissions": {"can_annotate": claims.can_annotate},
    }
