"""Chat server settings, loadable from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatSettings(BaseSettings):
    """Runtime configuration for the indexio chat server.

    All settings can be overridden via environment variables prefixed with
    ``INDEXIO_CHAT_``.  For example::

        INDEXIO_CHAT_PORT=8080
        INDEXIO_CHAT_LLM_MODEL=mistral
    """

    # Server
    host: str = "0.0.0.0"
    port: int = 9100

    # CORS — comma-separated origins are split automatically
    cors_origins: list[str] = ["*"]

    # indexio config
    config_path: str = ".projio/indexio/config.yaml"
    root: str = "."
    store: str | None = None
    corpus: str | None = None
    k: int = 6

    # LLM
    llm_backend: str = "ollama"
    llm_model: str = "llama3"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""

    # Widget
    title: str = "Docs Assistant"

    model_config = SettingsConfigDict(
        env_prefix="INDEXIO_CHAT_",
        env_nested_delimiter="__",
    )


@lru_cache(maxsize=1)
def get_settings() -> ChatSettings:
    """Return a cached instance of chat settings."""
    return ChatSettings()
