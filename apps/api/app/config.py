from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_secret: str = "alyvo-local-only"
    database_url: str = "sqlite:///./alyvo.db"
    redis_url: str = "redis://localhost:6379/0"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "alyvo-demo"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "alyvo"
    minio_secret_key: str = "alyvo-demo"
    minio_bucket: str = "alyvo-documents"
    llm_provider: str = "mock"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3-8b"
    embedding_provider: str = "mock"
    ocr_provider: str = "mock"
    demo_otp: str = "123456"
    demo_tenant: str = "clinic-alyvo"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

