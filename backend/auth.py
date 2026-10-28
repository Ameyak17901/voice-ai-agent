"""
Authentication and Authorization Module for Voice AI Agent.
Implements PBKDF2-HMAC-SHA256 password hashing, PyJWT access tokens,
and stateful refresh token rotation with reuse detection.
"""
import os
import hashlib
import secrets
import uuid
import datetime
from datetime import timezone as _tz
from typing import Optional, Dict, Any, Tuple

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from loguru import logger

# Configuration from environment with secure production defaults
_DEFAULT_JWT_SECRET = "voice-copilot-dev-secret-key-change-in-production-1234567890"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", _DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"

# CRIT-1: Guard against insecure default secret in non-debug / production environments.
# This prevents silent token forgery if the environment variable is accidentally omitted.
if JWT_SECRET_KEY == _DEFAULT_JWT_SECRET and os.getenv("DEBUG", "true").lower() not in ("true", "1", "yes"):
    raise RuntimeError(
        "FATAL: JWT_SECRET_KEY environment variable is not set. "
        "Generate a cryptographically random secret: "
        "python -c \"import secrets; print(secrets.token_hex(64))\" "
        "and set it before starting the server in production."
    )

# Senior Engineering Architecture:
# Access tokens are short-lived (15 minutes) to minimize exposure windows if intercepted.
# Refresh tokens are long-lived (7 days) and statefully rotated on each use.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    """
    Hashes a plaintext password using PBKDF2-HMAC-SHA256 with a unique 16-byte random salt.
    """
    salt = secrets.token_hex(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100_000,
    ).hex()
    return f"{salt}${derived_key}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against a stored salted hash using constant-time comparison.
    """
    try:
        salt, expected_key = hashed_password.split("$", 1)
        actual_key = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations=100_000,
        ).hex()
        return secrets.compare_digest(actual_key, expected_key)
    except Exception as exc:
        logger.warning(f"Password verification error: {exc}")
        return False


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[datetime.timedelta] = None,
) -> str:
    """
    Encodes and signs a short-lived JWT access token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.now(_tz.utc) + expires_delta
    else:
        expire = datetime.datetime.now(_tz.utc) + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": datetime.datetime.now(_tz.utc),
        "jti": str(uuid.uuid4()),
        "type": "access",
    })
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes and validates a JWT access token.
    Returns payload if valid and unexpired; returns None if expired or invalid.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            logger.warning("Rejected token: Expected type='access'")
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.info("JWT access token has expired.")
        return None
    except jwt.PyJWTError as exc:
        logger.warning(f"Invalid JWT token: {exc}")
        return None


def hash_token_string(raw_token: str) -> str:
    """Hashes a raw refresh token string with SHA-256 for safe database indexing."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_token_pair(
    user_id: int,
    username: str,
    family_id: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Generates a fresh (access_token, refresh_token) pair and persists the stateful
    refresh token in the database.
    
    Args:
        user_id: The ID of the authenticated user.
        username: The username claim to embed in the access token.
        family_id: Existing token family ID during rotation, or None for initial login.
        
    Returns:
        Tuple of (raw_access_token, raw_refresh_token).
    """
    from backend.db.repository import db_repository

    # 1. Create short-lived access token (JWT)
    access_token = create_access_token({"sub": str(user_id), "username": username})

    # 2. Create cryptographically secure opaque refresh token
    raw_refresh_token = secrets.token_urlsafe(48)
    token_hash = hash_token_string(raw_refresh_token)
    fam_id = family_id or str(uuid.uuid4())
    expires_at = datetime.datetime.now(_tz.utc) + datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    # 3. Persist refresh token in database
    db_repository.store_refresh_token(
        user_id=user_id,
        token_hash=token_hash,
        family_id=fam_id,
        expires_at=expires_at,
    )

    return access_token, raw_refresh_token


def rotate_refresh_token(raw_refresh_token: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Rotates a refresh token following the strict OAuth 2.0 Token Exchange with Reuse Detection.
    
    Security Workflow:
    1. Look up token by SHA-256 hash.
    2. If token does not exist: Reject.
    3. If token exists BUT is already marked is_revoked=True:
       -> THEFT / REUSE DETECTED!
       -> Invalidate ENTIRE token family immediately to protect user.
       -> Reject request.
    4. If token is expired:
       -> Reject request.
    5. Token is valid and unused:
       -> Invalidate (revoke) this old token.
       -> Issue new access token + new refresh token under the same family_id.
       -> Return new credentials.
       
    Returns:
        Tuple of (new_access_token, new_refresh_token, user_dict).
        
    Raises:
        HTTPException 401 if invalid, expired, or compromised.
    """
    from backend.db.repository import db_repository

    token_hash = hash_token_string(raw_refresh_token)
    rt_record = db_repository.get_refresh_token_by_hash(token_hash)

    if not rt_record:
        logger.warning("Refresh token rotation attempted with nonexistent token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    family_id = rt_record["family_id"]
    user_id = rt_record["user_id"]

    # Check for Reuse Attack
    if rt_record["is_revoked"]:
        logger.critical(
            f"[SECURITY ALERT] Refresh token reuse detected for user_id={user_id}, "
            f"family_id={family_id}! Invalidation of entire session family triggered."
        )
        db_repository.revoke_token_family(family_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected. All active sessions in this family revoked for security.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check for Expiration (MED-4: ensure timezone-aware comparison)
    raw_exp = rt_record["expires_at"]
    expires_at_dt = datetime.datetime.fromisoformat(raw_exp)
    if expires_at_dt.tzinfo is None:
        expires_at_dt = expires_at_dt.replace(tzinfo=_tz.utc)
    if datetime.datetime.now(_tz.utc) > expires_at_dt:
        logger.info(f"Refresh token expired for user_id={user_id}.")
        db_repository.revoke_refresh_token(token_hash)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch User
    user = db_repository.get_user_by_id(user_id)
    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or deleted",
        )

    # 1. Invalidate current refresh token
    db_repository.revoke_refresh_token(token_hash)

    # 2. Issue new token pair in the same family
    new_access_token, new_refresh_token = issue_token_pair(
        user_id=user["id"],
        username=user["username"],
        family_id=family_id,
    )

    logger.info(f"[AUTH] Successfully rotated refresh token for user '{user['username']}' (family={family_id}).")
    return new_access_token, new_refresh_token, user


def revoke_token(raw_refresh_token: str) -> bool:
    """Revokes a refresh token on explicit user sign-out."""
    from backend.db.repository import db_repository
    token_hash = hash_token_string(raw_refresh_token)
    rt = db_repository.get_refresh_token_by_hash(token_hash)
    if rt:
        db_repository.revoke_token_family(rt["family_id"])
        return True
    return False


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    FastAPI dependency that enforces JWT authorization and resolves the active user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise credentials_exception

    user_id = payload.get("sub")
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        raise credentials_exception

    from backend.db.repository import db_repository
    user = db_repository.get_user_by_id(user_id_int)
    if not user or not user.get("is_active", True):
        raise credentials_exception

    return user


async def get_optional_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency that resolves the user if a valid Bearer token is provided,
    otherwise returns None without raising an exception (supports guest/demo mode).
    """
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    try:
        user_id_int = int(payload.get("sub"))
        from backend.db.repository import db_repository
        user = db_repository.get_user_by_id(user_id_int)
        if user and user.get("is_active", True):
            return user
    except Exception:
        pass
    return None
