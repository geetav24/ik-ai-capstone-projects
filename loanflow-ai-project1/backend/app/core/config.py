from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app settings loaded from environment variables.

    Keep all provider/model values here so you can switch from mock -> Ollama -> OpenAI
    without touching workflow or API code.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "mock"  # allowed: mock, ollama, openai_later
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma2:2b"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"


settings = Settings()
