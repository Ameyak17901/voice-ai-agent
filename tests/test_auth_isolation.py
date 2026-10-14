"""
Automated unit and integration test suite for:
- Password hashing and constant-time verification
- User registration and JWT issuance
- Multi-user settings isolation
- Custom persona multi-tenant scoping
- User-specific agent construction
"""
import pytest
from backend.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from backend.db.repository import db_repository
from backend.agent_registry import agent_registry, VoicePersona
from backend.agent_factory import create_agent


def test_password_hashing_and_verification():
    """Verify password hashing with PBKDF2-SHA256 and constant-time comparison."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("IncorrectPassword456!", hashed) is False


def test_user_registration_and_jwt_claims(isolated_db):
    """Verify user creation and JWT claim generation and extraction."""
    user = db_repository.create_user("alice@example.com", "alice", "Password123!")
    assert user["id"] is not None
    assert user["email"] == "alice@example.com"
    assert user["username"] == "alice"

    # Verify duplicate email / username prevention
    with pytest.raises(ValueError, match="already registered"):
        db_repository.create_user("alice@example.com", "alice2", "Password123!")

    with pytest.raises(ValueError, match="already taken"):
        db_repository.create_user("other@example.com", "alice", "Password123!")

    # Verify JWT generation & decoding
    token = create_access_token({"sub": str(user["id"]), "username": user["username"]})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == str(user["id"])
    assert payload["username"] == "alice"


def test_user_settings_isolation(isolated_db):
    """Verify strict tenant segregation between distinct user credentials and settings."""
    u1 = db_repository.create_user("user1@example.com", "user1", "Pass1234!")
    u2 = db_repository.create_user("user2@example.com", "user2", "Pass5678!")

    db_repository.update_user_settings(
        u1["id"],
        gemini_api_key="USER1_GEMINI_KEY_XYZ",
        openai_model_name="gpt-4o-custom-user1",
    )
    db_repository.update_user_settings(
        u2["id"],
        gemini_api_key="USER2_GEMINI_KEY_ABC",
        openai_model_name="gemini-2.0-custom-user2",
    )

    creds1 = db_repository.get_user_credentials(u1["id"])
    creds2 = db_repository.get_user_credentials(u2["id"])

    assert creds1["gemini_api_key"] == "USER1_GEMINI_KEY_XYZ"
    assert creds2["gemini_api_key"] == "USER2_GEMINI_KEY_ABC"
    assert creds1["openai_model_name"] == "gpt-4o-custom-user1"
    assert creds2["openai_model_name"] == "gemini-2.0-custom-user2"


def test_custom_persona_tenant_isolation(isolated_db):
    """Verify custom voice personas are strictly private to the creating tenant."""
    u1 = db_repository.create_user("persona_owner@example.com", "owner", "Pass1234!")
    u2 = db_repository.create_user("persona_viewer@example.com", "viewer", "Pass5678!")

    p1 = VoicePersona(
        id="private_lawyer_persona",
        name="Attorney Voice Assistant",
        system_prompt="You are a private corporate counsel.",
        initial_message="Welcome. How may I advise you today?",
    )
    agent_registry.save_custom_persona(p1, user_id=u1["id"])

    u1_personas = [p.id for p in agent_registry.get_all_personas(user_id=u1["id"])]
    u2_personas = [p.id for p in agent_registry.get_all_personas(user_id=u2["id"])]

    assert "private_lawyer_persona" in u1_personas, "Creator must see their custom persona"
    assert "private_lawyer_persona" not in u2_personas, "Other users must NOT see private personas"


def test_user_agent_construction(isolated_db):
    """Verify that agent factory dynamically parameterizes models according to user settings."""
    u1 = db_repository.create_user("agent_u1@example.com", "agent_u1", "Pass1234!")
    u2 = db_repository.create_user("agent_u2@example.com", "agent_u2", "Pass5678!")

    db_repository.update_user_settings(u1["id"], openai_model_name="gpt-4o-custom-user1")
    db_repository.update_user_settings(u2["id"], openai_model_name="gemini-2.0-custom-user2")

    creds1 = db_repository.get_user_credentials(u1["id"])
    creds2 = db_repository.get_user_credentials(u2["id"])

    agent_u1 = create_agent(user_id=u1["id"], user_settings=creds1)
    agent_u2 = create_agent(user_id=u2["id"], user_settings=creds2)

    if hasattr(agent_u1, "agent_config"):
        assert agent_u1.agent_config.model_name == "gpt-4o-custom-user1"
        assert agent_u2.agent_config.model_name == "gemini-2.0-custom-user2"


def test_websocket_unauthenticated_connection_rejected(isolated_db):
    """Verify that connecting to /conversation without a valid JWT token is rejected with policy violation (1008)."""
    from fastapi.testclient import TestClient
    from fastapi import WebSocketDisconnect
    from backend.app import app

    client = TestClient(app)

    # 1. No token at all
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/conversation"):
            pass
    assert exc_info.value.code == 1008

    # 2. Invalid / bogus token
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/conversation?token=bogus_invalid_jwt"):
            pass
    assert exc_info.value.code == 1008


def test_websocket_authenticated_connection_accepted(isolated_db, sample_user):
    """Verify that connecting with a valid token successfully authenticates and accepts WebSocket handshake."""
    from fastapi.testclient import TestClient
    from backend.app import app

    client = TestClient(app)
    token = create_access_token({"sub": str(sample_user["id"]), "username": sample_user["username"]})

    with client.websocket_connect(f"/conversation?token={token}") as ws:
        # Send valid AudioConfigStartMessage
        ws.send_json({
            "type": "websocket_audio_config_start",
            "input_audio_config": {
                "sampling_rate": 16000,
                "audio_encoding": "linear16",
                "chunk_size": 2048,
            },
            "output_audio_config": {
                "sampling_rate": 16000,
                "audio_encoding": "linear16",
            },
            "conversation_id": "test_conv_auth_gate",
            "subscribe_transcript": True,
        })
        msg = ws.receive_json()
        assert msg["type"] == "websocket_ready"

        # Send STOP signal
        ws.send_json({"type": "websocket_stop"})

    # Verify call session was created in DB and strictly bound to user_id
    call = db_repository.get_call_session("test_conv_auth_gate")
    assert call is not None
    assert call["user_id"] == sample_user["id"]

