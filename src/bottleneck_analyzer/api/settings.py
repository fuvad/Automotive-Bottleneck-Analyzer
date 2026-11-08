"""Transport limits, separate from Stage 6 execution settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="API_", env_file=".env", extra="ignore")

    admission_timeout_seconds: float = Field(default=10, gt=0, le=60)
    maximum_body_bytes: int = Field(default=32768, ge=1024, le=65536)
    submission_history_limit: int = Field(default=100, ge=10, le=1000)
