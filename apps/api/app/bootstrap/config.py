from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_secret: str = "alyvo-local-only"
    database_url: str = "sqlite:///./alyvo.db"
    database_admin_url: str | None = None
    langgraph_database_url: str | None = None
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
    llm_primary_provider: str = "openrouter"
    llm_fallback_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: float = 30
    ollama_connect_timeout_seconds: float = 3
    ollama_context_length: int = 4096
    ollama_keep_alive: str = "-1"
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3-8b"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 12
    openrouter_max_retries: int = 1
    allow_external_providers: bool = True
    llm_routing_enabled: bool = False
    llm_response_enabled: bool = True
    llm_response_max_tokens: int = 260
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "alyvo"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_sampling_rate: float = 1.0
    embedding_provider: str = "bge-m3"
    embedding_model: str = "BAAI/bge-m3"
    knowledge_index_version: str = "structural-bge-m3-v1"
    knowledge_vector_min_score: float = 0.76
    chunk_parser_version: str = "structural-v1"
    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    ocr_provider: str = "paddle"
    public_web_url: str = "http://localhost:3000"
    upload_max_bytes: int = 10 * 1024 * 1024
    rate_limit_per_minute: int = 60
    validation_mode: bool = False
    api_docs_enabled: bool | None = None
    clinic_name: str = "Clínica Alyvo"
    clinic_timezone: str = "America/Sao_Paulo"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def set_environment_defaults(self) -> "Settings":
        if self.api_docs_enabled is None:
            self.api_docs_enabled = self.app_env != "production"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
