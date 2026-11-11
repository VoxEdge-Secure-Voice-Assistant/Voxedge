"""SQLAlchemy database engine, session factory, and base model."""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# ── Engine ─────────────────────────────────────────────────────────────────
# check_same_thread=False is required for SQLite when used with FastAPI
# (multiple threads may access the same connection).
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=settings.debug,
)


# Enable WAL mode and foreign keys for SQLite
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


# ── Session factory ────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Declarative base ──────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ── Dependency for FastAPI routes ──────────────────────────────────────────
def get_db():
    """Yield a database session and ensure it is closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables and perform non-destructive schema migrations."""
    # Ensure all models are imported so Base has their metadata
    from app.models.user import User  # noqa: F401
    from app.models.interaction import Interaction  # noqa: F401
    from app.models.emergency import EmergencyEvent  # noqa: F401
    from app.models.device import Device  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Ensure any new columns exist in existing SQLite databases
    if str(engine.url).startswith("sqlite"):
        with engine.connect() as conn:
            try:
                # 1. emergency_events.category
                res = conn.execute(text("PRAGMA table_info(emergency_events)"))
                cols = [r[1] for r in res.fetchall()]
                if cols and "category" not in cols:
                    conn.execute(text("ALTER TABLE emergency_events ADD COLUMN category VARCHAR(32)"))
                    conn.commit()

                # 2. emergency_events.user_id
                if cols and "user_id" not in cols:
                    conn.execute(text("ALTER TABLE emergency_events ADD COLUMN user_id INTEGER"))
                    conn.commit()

                # 3. interactions.user_id
                res_i = conn.execute(text("PRAGMA table_info(interactions)"))
                cols_i = [r[1] for r in res_i.fetchall()]
                if cols_i and "user_id" not in cols_i:
                    conn.execute(text("ALTER TABLE interactions ADD COLUMN user_id INTEGER"))
                    conn.commit()

            except Exception:
                pass

    # Seed primary user if database has no users yet (preserves existing voice profile & data)
    db = SessionLocal()
    try:
        from app.models.user import User
        from app.services.user_service import UserService

        if db.query(User).count() == 0:
            enrolled_path = settings.get_enrolled_voice_path()
            profile_path_str = str(enrolled_path) if enrolled_path.is_file() else None

            primary_user = UserService.register_user(
                db=db,
                username="user",
                password="voxedge123",
                full_name="Primary User",
            )
            if profile_path_str:
                primary_user.voice_profile_path = profile_path_str
                db.commit()

            # Attach existing unassigned rows to primary user
            with engine.connect() as conn:
                try:
                    conn.execute(text(f"UPDATE interactions SET user_id = {primary_user.id} WHERE user_id IS NULL"))
                    conn.execute(text(f"UPDATE emergency_events SET user_id = {primary_user.id} WHERE user_id IS NULL"))
                    conn.commit()
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        db.close()
