"""
Automated unit and security test suite for:
- Initial access and refresh token pair issuance
- Legitimate token rotation (consume single-use token, issue descendant pair)
- Compromised token reuse detection (family-wide invalidation)
- Expired access token rejection
- Explicit token revocation (logout)
"""
import datetime
import pytest
from fastapi import HTTPException
from backend.auth import (
    issue_token_pair,
    rotate_refresh_token,
    revoke_token,
    create_access_token,
    decode_access_token,
    hash_token_string,
)
from backend.db.repository import db_repository


def test_token_pair_issuance(sample_user):
    """Verify issuance of cryptographically signed access and refresh tokens."""
    access_token, refresh_token = issue_token_pair(sample_user["id"], sample_user["username"])
    assert access_token is not None
    assert refresh_token is not None

    payload = decode_access_token(access_token)
    assert payload is not None
    assert payload["sub"] == str(sample_user["id"])
    assert payload["username"] == sample_user["username"]
    assert payload["type"] == "access"


def test_legitimate_token_rotation(sample_user):
    """Verify rotation consumes previous refresh token and issues linked descendant."""
    access_1, refresh_1 = issue_token_pair(sample_user["id"], sample_user["username"])

    access_2, refresh_2, user_meta = rotate_refresh_token(refresh_1)
    assert access_2 != access_1
    assert refresh_2 != refresh_1
    assert user_meta["id"] == sample_user["id"]

    # Verify old refresh token is marked revoked
    hash_1 = hash_token_string(refresh_1)
    record_1 = db_repository.get_refresh_token_by_hash(hash_1)
    assert record_1 is not None
    assert record_1["is_revoked"] is True

    # Verify new refresh token is active and preserves family_id
    hash_2 = hash_token_string(refresh_2)
    record_2 = db_repository.get_refresh_token_by_hash(hash_2)
    assert record_2 is not None
    assert record_2["is_revoked"] is False
    assert record_2["family_id"] == record_1["family_id"]


def test_token_reuse_attack_family_invalidation(sample_user):
    """
    Verify security defense: Replaying an already-consumed refresh token
    triggers reuse detection and invalidates all tokens in the family.
    """
    _, refresh_1 = issue_token_pair(sample_user["id"], sample_user["username"])
    _, refresh_2, _ = rotate_refresh_token(refresh_1)

    # Attacker attempts replay of refresh_1
    with pytest.raises(HTTPException) as exc_info:
        rotate_refresh_token(refresh_1)

    assert exc_info.value.status_code == 401
    assert "reuse detected" in exc_info.value.detail.lower()

    # Crucial security assertion: Legitimate active token refresh_2 must now be revoked
    hash_2 = hash_token_string(refresh_2)
    record_2 = db_repository.get_refresh_token_by_hash(hash_2)
    assert record_2["is_revoked"] is True, "Token family must be terminated upon theft detection"


def test_expired_access_token_rejection(sample_user):
    """Verify expired JWTs fail signature / timestamp validation gracefully."""
    expired_token = create_access_token(
        {"sub": str(sample_user["id"]), "username": sample_user["username"]},
        expires_delta=datetime.timedelta(seconds=-10),
    )
    decoded = decode_access_token(expired_token)
    assert decoded is None, "Expired tokens must evaluate to None"


def test_explicit_token_revocation(sample_user):
    """Verify explicit revocation (logout) marks token revoked in repository."""
    _, refresh_token = issue_token_pair(sample_user["id"], sample_user["username"])
    revoke_token(refresh_token)

    h = hash_token_string(refresh_token)
    record = db_repository.get_refresh_token_by_hash(h)
    assert record["is_revoked"] is True
