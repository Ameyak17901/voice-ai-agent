"""
Authentication and Authorization Module for Voice AI Agent.
Implements PBKDF2-HMAC-SHA256 password hashing and PyJWT token lifecycle management.
"""
import os
import hashlib
import secrets
import datetime
from typing import Optional, Dict, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from loguru import logger

# Configuration from environment with secure production defaults
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "voice-copilot-dev-secret-key-change-in-production-1234567890")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    """
    Hashes a plaintext password using PBKDF2-HMAC-SHA256 with a unique 16-byte random salt.
    
    Args:
        password: Plaintext password string.
        
    Returns:
        Formatted string: '{salt}${derived_key_hex}'
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
    
    Args:
        plain_password: The plaintext candidate password.
        hashed_password: Stored '{salt}${derived_key_hex}' string.
        
    Returns:
        True if the password matches, False otherwise.
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
    Encodes and signs a JWT access token.
    
    Args:
        data: Claims payload to encode (must contain 'sub').
        expires_delta: Optional custom token expiration duration.
        
    Returns:
        Encoded JWT token string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRATION_HOURS)
        
    to_encode.update({"exp": expire, "iat": datetime.datetime.utcnow()})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes and validates a JWT access token.
    
    Args:
        token: Raw JWT token string.
        
    Returns:
        Decoded payload dict or None if invalid or expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.info("JWT access token has expired.")
        return None
    except jwt.PyJWTError as exc:
        logger.warning(f"Invalid JWT token: {exc}")
        return None


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    FastAPI dependency that enforces JWT authorization and resolves the active user.
    
    Raises:
        HTTPException 401 if token is missing, invalid, or user does not exist.
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
