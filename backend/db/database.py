import os
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from loguru import logger

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "voice_copilot.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"

# Configure SQLite engine with check_same_thread=False for multi-threaded FastAPI workers
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

# Enable SQLite Write-Ahead Logging (WAL) and foreign key constraints
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_schema_migrations():
    """
    Automated schema migration handler for SQLite.
    
    Why this is required:
    SQLAlchemy's `Base.metadata.create_all()` is idempotent only for CREATE TABLE.
    It NEVER executes ALTER TABLE or modifies existing schemas. When new columns
    like `user_id` are added to existing models, this migration runner introspects
    the live SQLite database and safely applies the missing columns without data loss.
    """
    if not DB_PATH.exists():
        return

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # 1. Check and add user_id to call_sessions
        cursor.execute("PRAGMA table_info(call_sessions)")
        call_session_cols = {col[1] for col in cursor.fetchall()}
        if call_session_cols and "user_id" not in call_session_cols:
            logger.info("[DB_MIGRATION] Adding missing column 'user_id' to table 'call_sessions'...")
            cursor.execute("ALTER TABLE call_sessions ADD COLUMN user_id INTEGER REFERENCES users(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_call_sessions_user_id ON call_sessions(user_id)")
            conn.commit()
            logger.info("[DB_MIGRATION] Successfully added 'user_id' to 'call_sessions'.")

        # 2. Check and add user_id to appointments
        cursor.execute("PRAGMA table_info(appointments)")
        appointment_cols = {col[1] for col in cursor.fetchall()}
        if appointment_cols and "user_id" not in appointment_cols:
            logger.info("[DB_MIGRATION] Adding missing column 'user_id' to table 'appointments'...")
            cursor.execute("ALTER TABLE appointments ADD COLUMN user_id INTEGER REFERENCES users(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_appointments_user_id ON appointments(user_id)")
            conn.commit()
            logger.info("[DB_MIGRATION] Successfully added 'user_id' to 'appointments'.")

        # 3. Migrate legacy deprecated models 'gemini-1.5-flash' to 'gemini-3.5-flash'
        cursor.execute("PRAGMA table_info(user_settings)")
        if cursor.fetchall():
            cursor.execute("UPDATE user_settings SET openai_model_name = 'gemini-3.5-flash' WHERE openai_model_name IN ('gemini-1.5-flash', 'gemini-1.5')")
        cursor.execute("PRAGMA table_info(custom_personas)")
        if cursor.fetchall():
            cursor.execute("UPDATE custom_personas SET model_name = 'gemini-3.5-flash' WHERE model_name IN ('gemini-1.5-flash', 'gemini-1.5')")
        conn.commit()

        conn.close()
    except Exception as exc:
        logger.error(f"[DB_MIGRATION] Failed during automatic schema migration: {exc}", exc_info=True)


def init_db():
    """Initialize database tables and synchronize column migrations."""
    from backend.db.models import (  # noqa: F401
        User,
        UserSettings,
        CustomPersona,
        CallSession,
        TranscriptItem,
        Appointment,
        RefreshToken,
    )
    Base.metadata.create_all(bind=engine)
    apply_schema_migrations()
