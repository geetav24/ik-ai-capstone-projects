"""
Database access for the MCP server.

Own engine and session — independent of app/db/database.py.
DATABASE_URL env var lets prod point to a real database.
"""
import os

from sqlmodel import Session, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./loanflow.db")
engine = create_engine(DATABASE_URL, echo=False)


def get_session() -> Session:
    return Session(engine)
