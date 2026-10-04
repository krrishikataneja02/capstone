from __future__ import annotations

import jwt
import pytest

from app.config import Settings
from app.redis_client import cache_get, cache_set, get_redis_client, init_redis, redis_health
from app.security import create_access_token, decode_access_token


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.closed = False

    def ping(self):
        return True

    def setex(self, key, ttl_seconds, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0

    def close(self):
        self.closed = True


def test_settings_reject_insecure_production_secret():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            ENV="prod",
            SECRET_KEY="dev-secret",
            DATABASE_URL="sqlite://",
            CORS_ORIGINS="http://localhost:3000",
        )


def test_decode_access_token_requires_exp_and_sub():
    token = create_access_token({"sub": "42"})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-valid-token")


def test_login_rate_limit(client, admin_user):
    for idx in range(10):
        resp = client.post(
            "/auth/login",
            data={"username": "admin@test.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    resp = client.post(
        "/auth/login",
        data={"username": "admin@test.com", "password": "wrong"},
    )
    assert resp.status_code == 429


def test_redis_cache_fakes_work(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.redis_client._redis_client", fake)
    assert cache_set("demo:key", {"value": 5}, ttl_seconds=60) is True
    assert cache_get("demo:key") == {"value": 5}
    assert redis_health()["status"] == "ok"


def test_redis_init_gracefully_handles_failure(monkeypatch):
    class FailingRedis:
        @staticmethod
        def from_url(*args, **kwargs):
            raise RuntimeError("redis down")

    monkeypatch.setattr("app.redis_client.settings.REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr("app.redis_client.redis.Redis", FailingRedis)
    assert init_redis() is None
    assert get_redis_client() is None
    assert redis_health()["status"] == "unavailable"
