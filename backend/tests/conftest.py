"""
Pytest fixtures for API integration tests.

Uses SQLite in-memory with StaticPool for test isolation (no MySQL needed).
Overrides the DB session dependency to use the test database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, User, UserRole, utcnow
from app.security import create_access_token, hash_password


# Use SQLite in-memory with StaticPool so all threads share one connection
TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


# Enable FK support in SQLite
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create all tables, yield a session, then drop everything."""
    Base.metadata.create_all(bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with the DB dependency overridden."""
    from app.deps import get_db
    from app.main import app
    from app.redis_client import cache_delete
    from app.routers.auth import _login_attempts

    _login_attempts.clear()
    cache_delete("twin:state:v1")

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    cache_delete("twin:state:v1")


@pytest.fixture
def admin_user(db_session) -> User:
    """Create and return an admin user."""
    user = User(
        email="admin@test.com",
        name="Test Admin",
        hashed_password=hash_password("admin123"),
        role=UserRole.admin,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user) -> str:
    """Create a JWT token directly (bypasses login endpoint for reliability)."""
    return create_access_token({"sub": str(admin_user.id), "role": admin_user.role.value})


@pytest.fixture
def admin_headers(admin_token) -> dict:
    """Authorization headers for the admin user."""
    return {"Authorization": f"Bearer {admin_token}"}
