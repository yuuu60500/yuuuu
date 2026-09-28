from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/audiosub.db"

    storage_backend: str = "local"  # local | s3
    local_storage_dir: str = "./data/storage"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    ffmpeg_binary: str = "ffmpeg"

    asr_provider: str = "faster_whisper"  # faster_whisper | openai | mock
    whisper_model: str = "large-v3"
    whisper_device: str = "auto"
    whisper_compute_type: str = "default"
    openai_asr_model: str = "whisper-1"
    openai_api_key: str | None = None

    translation_provider: str = "claude"  # claude | ollama | mock
    translation_model: str = "claude-opus-5"
    # Read from .env here: values in .env are not exported to os.environ, so
    # SDK clients must be given the key explicitly.
    anthropic_api_key: str | None = None
    # Local, offline translation through Ollama (https://ollama.com)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout: float = 900.0
    translation_batch_size: int = 15
    translation_context_size: int = 3

    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 2048

    # When false, pipeline steps run inline in the request (used by tests).
    run_jobs_in_background: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
