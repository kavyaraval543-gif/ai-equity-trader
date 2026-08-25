"""Test fixtures. Uses an isolated in-memory SQLite database so tests never
touch the real development Postgres database."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
import app.models  # noqa: F401 — populate Base.metadata


@pytest.fixture()
def db_session():
    # StaticPool: a single shared connection for the whole engine, regardless
    # of which thread requests it. Without this, SQLAlchemy's default pooling
    # for sqlite:///:memory: hands each thread its own (separately empty)
    # in-memory database — which breaks the moment a test drives the app
    # through FastAPI's TestClient, since that executes the endpoint in a
    # worker thread via run_in_threadpool.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session: Session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
