"""
Application configuration via environment variables (Pydantic Settings).
"""

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

_DEVELOPMENT_SECRET = "development-only-secret-change-before-production"


class Settings(BaseSettings):
    # Environment
    ENV: Literal["dev", "prod"] = "dev"

    # Database
    DATABASE_URL: str = "mysql+pymysql://localhost/digital_twin?charset=utf8mb4"

    # JWT
    SECRET_KEY: str | None = None
    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    JWT_EXPIRATION_MINUTES: int = Field(default=60, gt=0)

    # Redis
    REDIS_URL: str | None = None

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Simulator
    SIMULATOR_ENABLED: bool = False
    SIMULATOR_INTERVAL_SECONDS: int = 10

    # Timezone for campus-local time (data generators, timetable matching)
    CAMPUS_TIMEZONE: str = "Asia/Kolkata"

    model_config = {"env_file": ".env", "env_ignore_empty": True, "extra": "ignore"}

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        secret = (self.SECRET_KEY or "").strip()
        if not secret:
            if self.ENV == "prod":
                raise ValueError("Production requires a non-empty SECRET_KEY")
            self.SECRET_KEY = _DEVELOPMENT_SECRET
            secret = self.SECRET_KEY

        if self.ENV == "prod":
            if (
                len(secret) < 32
                or len(set(secret)) < 16
                or secret == _DEVELOPMENT_SECRET
                or "change-me" in secret.lower()
                or "replace-with" in secret.lower()
                or "development-only" in secret.lower()
            ):
                raise ValueError("Production requires a unique SECRET_KEY of at least 32 characters")

        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        if not origins or "*" in origins:
            if self.ENV == "prod":
                raise ValueError("Production requires explicit CORS_ORIGINS; wildcard origins are forbidden")
            self.CORS_ORIGINS = ",".join(origins) if origins else "http://localhost:3000"

        return self


settings = Settings()
