"""Read and validate application settings from the environment."""

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Typed runtime settings for the local advisory application."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: int = Field(default=30, ge=1, le=120)
    llm_max_output_tokens: int = Field(default=4000, ge=256, le=16000)
    workflow_max_steps: int = Field(default=10, ge=7, le=20)
    workflow_retrieval_limit: int = Field(default=20, ge=1, le=50)
    simulation_max_days: int = Field(default=30, ge=1, le=366)
    simulation_max_replications: int = Field(default=20, ge=2, le=50)
    simulation_timeout_seconds: int = Field(default=600, ge=1, le=600)
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_api_key: SecretStr | None = None
    embedding_dimensions: int = Field(default=1536, gt=0, le=16000)
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_timeout_seconds: int = Field(default=10, gt=0, le=120)
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "automotive-bottleneck-analyzer"
    design_production_rate_jph: float = 60.0
    illustrative_actual_production_rate_jph: float = 46.0
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_reload: bool = False
    database_connect_timeout_seconds: int = 5

    @field_validator("database_url")
    @classmethod
    def require_postgresql_psycopg(cls, value: str) -> str:
        """Reject accidental configuration of another database or driver."""
        if value and not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize the logging level while rejecting unknown values."""
        normalized = value.upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(valid_levels)}")
        return normalized

    @field_validator("design_production_rate_jph", "illustrative_actual_production_rate_jph")
    @classmethod
    def require_non_negative_rate(cls, value: float) -> float:
        """Ensure production-rate references are usable quantities."""
        if value < 0:
            raise ValueError("production rates cannot be negative")
        return value

    @field_validator("app_port", "database_connect_timeout_seconds")
    @classmethod
    def require_positive_integer(cls, value: int) -> int:
        """Ensure network and database timeout settings are positive."""
        if value <= 0:
            raise ValueError("this setting must be positive")
        return value

    def require_database_url(self) -> str:
        """Return the configured PostgreSQL URL or explain the missing setting."""
        if not self.database_url:
            raise ValueError("DATABASE_URL is required for database operations")
        return self.database_url


def get_settings() -> AppSettings:
    """Construct settings when infrastructure first needs them."""
    return AppSettings()
