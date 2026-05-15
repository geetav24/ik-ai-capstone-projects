"""
SQLite engine and session factory.

FastAPI routes use get_session() as a dependency injection.
Agents do NOT import from here — they use tools instead.
"""
from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = "sqlite:///./loanflow.db"

# echo=True prints SQL — useful for debugging, set to False in prod
engine = create_engine(DATABASE_URL, echo=False)


def create_db_and_tables() -> None:
    """Create all tables. Call once at startup (see main.py lifespan)."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency. Use with: session: Session = Depends(get_session)."""
    with Session(engine) as session:
        yield session


def SessionLocal():
    """Direct session for scripts (seed.py, CLI). Use as: db = SessionLocal()"""
    return Session(engine)
