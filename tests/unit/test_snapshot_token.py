"""Snapshot delivery authorization token: mint/verify contract.

The NiceGUI process mints a token only after resolve_annotation_context
succeeds; the snapshot service verifies signature and expiry and nothing
else.  Stateless presigned-URL model, 60-second TTL.
"""

from __future__ import annotations

from uuid import uuid4

from promptgrimoire.snapshot import (
    SnapshotClaims,
    mint_snapshot_token,
    verify_snapshot_token,
)

_SECRET = "test-secret"


def _claims() -> SnapshotClaims:
    return SnapshotClaims(
        workspace_id=str(uuid4()),
        document_id=str(uuid4()),
        user_id=str(uuid4()),
        viewer_is_privileged=False,
        can_annotate=True,
        anonymous_sharing=False,
    )


def test_round_trip_preserves_claims() -> None:
    claims = _claims()
    token = mint_snapshot_token(claims, secret=_SECRET, now=1000.0)
    verified = verify_snapshot_token(token, secret=_SECRET, now=1030.0)
    assert verified == claims


def test_expired_token_rejected() -> None:
    token = mint_snapshot_token(_claims(), secret=_SECRET, now=1000.0)
    assert verify_snapshot_token(token, secret=_SECRET, now=1061.0) is None


def test_tampered_payload_rejected() -> None:
    token = mint_snapshot_token(_claims(), secret=_SECRET, now=1000.0)
    payload_b64, sig = token.rsplit(".", 1)
    # Flip a payload character; signature no longer matches.
    tampered = payload_b64[:-2] + ("A" if payload_b64[-2] != "A" else "B")
    assert (
        verify_snapshot_token(f"{tampered}.{sig}", secret=_SECRET, now=1030.0) is None
    )


def test_wrong_secret_rejected() -> None:
    token = mint_snapshot_token(_claims(), secret=_SECRET, now=1000.0)
    assert verify_snapshot_token(token, secret="other-secret", now=1030.0) is None


def test_malformed_token_rejected() -> None:
    for garbage in ("", "no-dot", "a.b", "!!!.???"):
        assert verify_snapshot_token(garbage, secret=_SECRET, now=1030.0) is None


def test_unauthenticated_viewer_claims_survive_round_trip() -> None:
    claims = SnapshotClaims(
        workspace_id=str(uuid4()),
        document_id=str(uuid4()),
        user_id=None,
        viewer_is_privileged=False,
        can_annotate=False,
        anonymous_sharing=True,
    )
    token = mint_snapshot_token(claims, secret=_SECRET, now=1000.0)
    assert verify_snapshot_token(token, secret=_SECRET, now=1030.0) == claims
