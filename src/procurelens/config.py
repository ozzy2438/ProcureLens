"""Central application settings, loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg2://procurelens:procurelens@localhost:5432/procurelens"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    mlflow_tracking_uri: str = "http://127.0.0.1:5000"
    amendment_feature_table: str = "analytics_marts.fct_contracts"
    audit_log_path: str = "logs/audit.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
