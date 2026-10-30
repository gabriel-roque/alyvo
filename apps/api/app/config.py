from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_secret: str = "alyvo-local-only"
    database_url: str = "sqlite:///./alyvo.db"
    database_admin_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "alyvo-demo"
    minio_endpoint: str = "localhost:9000"
    minio_public_endpoint: str = "localhost:9000"
    minio_access_key: str = "alyvo"
    minio_secret_key: str = "alyvo-demo"
    minio_bucket: str = "alyvo-documents"
    minio_secure: bool = False
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: float = 10
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3-8b"
    allow_external_providers: bool = False
    embedding_provider: str = "bge-m3"
    ocr_provider: str = "paddle"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "alyvo@local.test"
    public_web_url: str = "http://localhost:3000"
    upload_max_bytes: int = 10 * 1024 * 1024
    retention_days: int = 90
    rate_limit_per_minute: int = 60
    validation_mode: bool = False
    demo_otp: str = "123456"
    demo_tenant: str = "clinic-alyvo"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

