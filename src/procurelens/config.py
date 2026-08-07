"""Central application settings, loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    release_version: str = "1.0.0"
    snapshot_version: str = "1.0.0"
    database_url: str = "postgresql+psycopg2://procurelens:procurelens@localhost:5432/procurelens"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    mlflow_tracking_uri: str = "http://127.0.0.1:5050"
    amendment_feature_table: str = "analytics_marts.fct_contracts"
    capability_profile_path: str = "config/capability_profile.yml"
    rag_corpus_path: str = "config/rag_corpus.json"
    audit_log_path: str = "logs/audit.jsonl"
    model_service_url: str = "http://127.0.0.1:8000"
    agent_database_url: str = ""
    agent_sql_schemas: str = "analytics_marts"
    agent_sql_max_rows: int = 200
    agent_sql_timeout_ms: int = 5_000
    langfuse_tracing_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_sample_rate: float = 1.0
    langfuse_release: str = "local"
    llm_input_cost_per_1k: float = 0.0
    llm_output_cost_per_1k: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
