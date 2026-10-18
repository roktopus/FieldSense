from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "staging", "production"] = "development"
    dataset_profile: Literal["sample", "test"] = "sample"
    database_url: str = "postgresql+psycopg://fieldsense:fieldsense@localhost:5432/fieldsense"
    source_root: str = "/data/sample-data"
    # sample profile default; test profile uses 2027-01-15 via env
    evaluation_as_of: str = "2026-10-16T00:00:00Z"
    app_timezone: str = "UTC"
    # llm: model plans tool calls and writes the summary. router: optional offline phrase router.
    answer_mode: Literal["llm", "router"] = "llm"
    model_provider: str = "openai_compatible"
    model_base_url: str = ""
    model_api_key: str = ""
    model_name: str = ""
    # Gemini API key for MODEL_PROVIDER=google (Gemma). https://aistudio.google.com/apikey
    gemini_api_key: str = ""
    demo_user_picker_enabled: bool = True
    tool_call_limit: int = 8
    agent_max_result_rows: int = 500
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    session_secret: str = Field(default="fieldsense-dev-secret")
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("session_secret")
    @classmethod
    def _session_secret_strength(cls, v: str) -> str:
        # Validated again at startup for production; keep import-safe here.
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_runtime_settings(settings: Settings | None = None) -> None:
    """Fail fast on unsafe production configuration."""
    s = settings or get_settings()
    if not s.is_production:
        return
    weak = {"", "fieldsense-dev", "fieldsense-dev-secret", "fieldsense-dev-change-me", "change-me-in-real-deployments"}
    if s.session_secret.strip().lower() in weak or len(s.session_secret) < 24:
        raise RuntimeError(
            "APP_ENV=production requires a strong SESSION_SECRET "
            "(>= 24 chars, not a default placeholder)."
        )
    if "*" in s.cors_origin_list:
        raise RuntimeError("APP_ENV=production forbids CORS_ORIGINS=*")
    if s.demo_user_picker_enabled:
        # Allowed for the challenge demo, but warn via log in main.
        pass
