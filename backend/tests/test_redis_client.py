from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import redis_client


class FakeRedis:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.values: dict[str, str] = {}
        self.unavailable = unavailable
        self.closed = False

    def ping(self) -> bool:
        if self.unavailable:
            raise ConnectionError("Redis unavailable")
        return True

    def get(self, key: str) -> str | None:
        if self.unavailable:
            raise ConnectionError("Redis unavailable")
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        if self.unavailable:
            raise ConnectionError("Redis unavailable")
        self.values[key] = value

    def delete(self, key: str) -> int:
        if self.unavailable:
            raise ConnectionError("Redis unavailable")
        return int(self.values.pop(key, None) is not None)

    def close(self) -> None:
        self.closed = True


class RedisFactory:
    instance: FakeRedis | None = None
    url: str | None = None

    @classmethod
    def from_url(cls, url: str, **kwargs) -> FakeRedis:
        cls.url = url
        cls.instance = FakeRedis()
        return cls.instance


def test_redis_initializes_from_configured_url(monkeypatch):
    monkeypatch.setattr(redis_client.settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(redis_client.redis, "Redis", RedisFactory)

    client = redis_client.init_redis()

    assert client is RedisFactory.instance
    assert RedisFactory.url == redis_client.settings.REDIS_URL
    assert redis_client.redis_health() == {"status": "ok"}


def test_cache_hit_miss_and_write(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(redis_client, "_redis_client", fake)

    assert redis_client.cache_get("missing") is None
    assert redis_client.cache_set("state", {"building": 1}, ttl_seconds=30)
    assert redis_client.cache_get("state") == {"building": 1}
    assert redis_client.cache_delete("state")
    assert redis_client.cache_get("state") is None


def test_redis_failure_degrades_to_noops(monkeypatch):
    monkeypatch.setattr(redis_client, "_redis_client", FakeRedis(unavailable=True))

    assert redis_client.cache_get("key") is None
    assert redis_client.cache_set("key", {"value": 1}) is False
    assert redis_client.cache_delete("key") is False
    assert redis_client.redis_health() == {"status": "unavailable"}


def test_failed_connection_initialization_returns_none(monkeypatch):
    class FailingRedisFactory:
        @staticmethod
        def from_url(url: str, **kwargs) -> FakeRedis:
            return FakeRedis(unavailable=True)

    monkeypatch.setattr(redis_client.redis, "Redis", FailingRedisFactory)

    assert redis_client.init_redis() is None
    assert redis_client.get_redis_client() is None


def test_redis_client_closes_cleanly(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(redis_client, "_redis_client", fake)

    asyncio.run(redis_client.close_redis())

    assert fake.closed
    assert redis_client.get_redis_client() is None


def test_twin_state_endpoint_uses_cache_hit(client, admin_headers, monkeypatch):
    from app.routers import twin

    fake = FakeRedis()
    monkeypatch.setattr(redis_client, "_redis_client", fake)
    original_aggregation = twin.get_twin_state
    aggregation_calls = 0

    def count_aggregation(db):
        nonlocal aggregation_calls
        aggregation_calls += 1
        return original_aggregation(db)

    monkeypatch.setattr(twin, "get_twin_state", count_aggregation)

    first = client.get("/twin/state", headers=admin_headers)
    second = client.get("/twin/state", headers=admin_headers)

    assert first.status_code == second.status_code == 200
    assert aggregation_calls == 1


def test_application_starts_and_health_works_without_redis(db_session, monkeypatch):
    from app.deps import get_db
    from app.main import app

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(redis_client, "init_redis", lambda: None)
    monkeypatch.setattr(redis_client, "close_redis", AsyncMock())
    monkeypatch.setattr(redis_client, "redis_health", lambda: {"status": "unavailable"})

    try:
        with TestClient(app) as test_client:
            response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["redis"] == "unavailable"
    finally:
        app.dependency_overrides.clear()
