"""
Pytest configuration and global test fixtures.
Provides isolated, zero-pollution SQLite database environments and mock utilities.
"""
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backend.db.database as db_module
import backend.db.repository as repo_module
from backend.db.database import Base
from backend.db.repository import db_repository


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Provisions a fresh, isolated SQLite database file per test function.
    Guarantees zero database pollution against development/production databases.
    """
    db_file = tmp_path / "test_voice_copilot.db"
    test_db_url = f"sqlite:///{db_file}"

    test_engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Initialize all database models and tables
    Base.metadata.create_all(bind=test_engine)

    # Monkeypatch the database engine and sessionmaker instances
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(repo_module, "SessionLocal", TestingSessionLocal)

    # Monkeypatch agent_registry storage path to isolated temp file
    from backend.agent_registry import agent_registry
    temp_registry_json = tmp_path / "test_agent_registry.json"
    monkeypatch.setattr(agent_registry, "storage_path", temp_registry_json)
    monkeypatch.setattr(agent_registry, "_custom_personas", {})

    yield TestingSessionLocal

    # Clean up and dispose engine connections
    test_engine.dispose()


@pytest.fixture
def sample_user(isolated_db):
    """Fixture providing a standard test user in the isolated database."""
    user = db_repository.create_user(
        email="developer@example.com",
        username="dev_user",
        plain_password="SecurePassword123!",
    )
    return user
