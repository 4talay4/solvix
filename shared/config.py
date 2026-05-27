import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_alumnos_token: str = ""
    bot_admin_token: str = ""
    bot_soporte_token: str = ""

    admin_telegram_ids: str = ""

    postgres_user: str = "curso"
    postgres_password: str = ""
    postgres_db: str = "curso_ia"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_embed_model: str = "nomic-embed-text"

    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    chroma_collection: str = "curso_docs"

    rag_api_url: str = "http://rag-api:8080"
    similarity_cache_threshold: float = 0.87
    cache_lookup_limit: int = 300
    chunk_size: int = 800
    chunk_overlap: int = 150

    course_data_dir: str = "/app/data/curso"
    tests_data_file: str = "/app/data/tests/preguntas_test.json"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def admin_ids(self) -> list[int]:
        if not self.admin_telegram_ids.strip():
            return []
        return [int(x.strip()) for x in self.admin_telegram_ids.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
