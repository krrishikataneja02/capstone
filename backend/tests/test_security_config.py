from __future__ import annotations

import secrets

import jwt
import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.models import University
from app.security import decode_access_token
from scripts.seed import seed


def test_production_rejects_placeholder_secret_and_wildcard_cors():
    with pytest.raises(ValidationError):
        Settings(ENV="prod", SECRET_KEY="change-me-please-this-is-not-a-secret-1234")
    with pytest.raises(ValidationError):
        Settings(ENV="prod", SECRET_KEY=secrets.token_urlsafe(48), CORS_ORIGINS="*")


def test_production_accepts_unique_key_and_explicit_origins():
    configured = Settings(
        ENV="prod",
        SECRET_KEY=secrets.token_urlsafe(48),
        CORS_ORIGINS="https://campus.example.edu,https://admin.example.edu",
    )
    assert configured.ENV == "prod"


def test_jwt_requires_expiration_and_subject_claims():
    token = jwt.encode({"sub": "1"}, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)


def test_seed_function_skips_existing_upes_university(db_session):
    db_session.add(University(name="UPES Dehradun", code="UPES", address="UPES"))
    db_session.commit()

    seed(db_session)

    assert db_session.query(University).filter(University.code == "UPES").count() == 1
    assert db_session.query(University).count() == 1
