from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")
    secret_key: str = "change-this-development-secret"
    session_timeout_minutes: int = 60
    max_upload_mb: int = 25
    chunk_size_words: int = 500
    chunk_overlap_words: int = 75
    top_k: int = 5
    contradiction_penalty: float = 0.10
    auto_release_results: bool = False
    ollama_host: str = "http://localhost:11434"

settings = Settings()
