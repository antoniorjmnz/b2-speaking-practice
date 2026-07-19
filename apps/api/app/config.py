from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("apps/api/.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    ai_mode: Literal["demo", "mock", "real"] = "demo"
    database_url: str = "sqlite+aiosqlite:///./apps/api/data/b2_speaking.db"
    auto_create_db: bool = True
    enable_inline_worker: bool = True

    session_token_pepper: str = "development-only-session-pepper-change-me"  # noqa: S105
    upload_signing_secret: str = "development-only-upload-secret-change-me"  # noqa: S105
    teacher_validation_token: str | None = None

    public_api_url: str = "http://localhost:8000"
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    trusted_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    max_audio_bytes: int = 8 * 1024 * 1024
    session_retention_minutes: int = Field(default=60, ge=1, le=60)
    playback_url_ttl_seconds: int = 300

    storage_mode: Literal["local", "supabase"] = "local"
    local_storage_path: Path = Path("./apps/api/data/storage")
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "part2-recordings"

    ai_provider: Literal["openrouter", "openai"] = "openrouter"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_transcription_model: str = "openai/whisper-large-v3"
    openrouter_evaluation_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    openrouter_evaluation_fallback_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "tencent/hy3:free",
            "openrouter/free",
        ]
    )
    openrouter_pronunciation_model: str = "google/gemini-2.5-flash"
    openrouter_pronunciation_fallback_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["openrouter/free"]
    )
    openrouter_partner_model: str = "tencent/hy3:free"
    openrouter_partner_fallback_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "nvidia/nemotron-3-super-120b-a12b:free",
            "openrouter/free",
        ]
    )
    openrouter_model_attempt_timeout_seconds: float = Field(default=45.0, ge=10.0, le=120.0)
    openrouter_completion_budget_seconds: float = Field(default=90.0, ge=20.0, le=300.0)
    openrouter_http_referer: str = "http://localhost:3000"
    openrouter_app_name: str = "B2 Speaking Academy"

    # Google AI Studio (Gemini) free tier as primary evaluation judge. When the
    # key is present, evaluation and review try Gemini first and fall back to
    # the OpenRouter chain automatically.
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # Pin the stable model. The `latest` alias can be hot-swapped and would make
    # teacher calibration and regression comparisons non-reproducible.
    gemini_evaluation_model: str = "gemini-3.5-flash"

    openai_api_key: str | None = None
    openai_diarization_api_key: str | None = None
    openai_diarization_model: str = "gpt-4o-transcribe-diarize"
    diarization_provider: Literal["openai", "whisperx", "modal"] = "openai"
    whisperx_python_path: Path = Path(".whisperx-venv/Scripts/python.exe")
    whisperx_bridge_path: Path = Path("apps/api/scripts/whisperx_diarize.py")
    whisperx_model: str = "small.en"
    whisperx_device: Literal["cuda", "cpu"] = "cuda"
    whisperx_compute_type: str = "float16"
    whisperx_batch_size: int = Field(default=8, ge=1, le=32)
    whisperx_timeout_seconds: float = Field(default=300.0, ge=30.0, le=900.0)
    modal_app_name: str = "b2-speaking-whisperx"
    modal_class_name: str = "WhisperXWorker"
    modal_environment_name: str = "main"
    modal_token_id: str | None = None
    modal_token_secret: str | None = None
    modal_timeout_seconds: float = Field(default=600.0, ge=60.0, le=900.0)
    openai_transcription_model: str | None = None
    openai_evaluation_model: str | None = None
    openai_pronunciation_model: str | None = None
    openai_timeout_seconds: float = 90.0

    # Voice profiles are planning/configuration metadata only. Their presence does not prove
    # that a remote provider, region, model, or voice is available for this deployment.
    examiner_voice_provider: Literal[
        "azure_speech", "openai_tts", "elevenlabs", "local_placeholder"
    ] = "azure_speech"
    examiner_voice_locale: str = "en-GB"
    examiner_voice_name: str = "en-GB-SoniaNeural"
    examiner_voice_profile_verified: bool = False
    ai_partner_voice_provider: Literal["openai_realtime", "azure_voice_live", "elevenlabs"] = (
        "openai_realtime"
    )
    ai_partner_voice_locale: str = "en-GB"
    ai_partner_voice_name: str = "marin"
    ai_partner_voice_profile_verified: bool = False

    worker_poll_seconds: float = 0.5
    worker_heartbeat_seconds: float = Field(default=10.0, ge=2.0, le=30.0)
    stale_job_seconds: float = Field(default=150.0, ge=60.0, le=600.0)
    max_job_attempts: int = 3

    @field_validator(
        "cors_allowed_origins",
        "trusted_hosts",
        "openrouter_evaluation_fallback_models",
        "openrouter_pronunciation_fallback_models",
        "openrouter_partner_fallback_models",
        mode="before",
    )
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def validate_runtime_secrets(self) -> Settings:
        if self.environment == "production":
            weak = ("development-only", "replace-with")
            if any(marker in self.session_token_pepper for marker in weak):
                raise ValueError("SESSION_TOKEN_PEPPER must be replaced in production")
            if any(marker in self.upload_signing_secret for marker in weak):
                raise ValueError("UPLOAD_SIGNING_SECRET must be replaced in production")
            if len(self.session_token_pepper) < 32 or len(self.upload_signing_secret) < 32:
                raise ValueError("Signing secrets must contain at least 32 characters")
        if self.storage_mode == "supabase" and not (
            self.supabase_url and self.supabase_service_role_key
        ):
            raise ValueError("Supabase storage requires SUPABASE_URL and service role key")
        if self.ai_mode == "real":
            if self.ai_provider == "openrouter" and not self.openrouter_api_key:
                raise ValueError("Real OpenRouter mode requires OPENROUTER_API_KEY")
            if self.ai_provider == "openai" and not (
                self.openai_api_key
                and self.openai_transcription_model
                and self.openai_evaluation_model
                and self.openai_pronunciation_model
            ):
                raise ValueError("Real OpenAI mode requires the API key and all model identifiers")
        if (
            self.environment == "production"
            and self.diarization_provider == "modal"
            and not (self.modal_token_id and self.modal_token_secret)
        ):
            raise ValueError("Modal diarization requires MODAL_TOKEN_ID and MODAL_TOKEN_SECRET")
        return self

    @property
    def ai_api_key(self) -> str | None:
        return self.openrouter_api_key if self.ai_provider == "openrouter" else self.openai_api_key

    @property
    def ai_base_url(self) -> str | None:
        return self.openrouter_base_url if self.ai_provider == "openrouter" else None

    @property
    def transcription_model(self) -> str:
        return (
            self.openrouter_transcription_model
            if self.ai_provider == "openrouter"
            else (self.openai_transcription_model or "")
        )

    @property
    def evaluation_model(self) -> str:
        return (
            self.openrouter_evaluation_model
            if self.ai_provider == "openrouter"
            else (self.openai_evaluation_model or "")
        )

    @property
    def evaluation_fallback_models(self) -> list[str]:
        if self.ai_provider != "openrouter":
            return []
        return self.openrouter_evaluation_fallback_models

    @property
    def pronunciation_model(self) -> str:
        return (
            self.openrouter_pronunciation_model
            if self.ai_provider == "openrouter"
            else (self.openai_pronunciation_model or "")
        )

    @property
    def pronunciation_fallback_models(self) -> list[str]:
        if self.ai_provider != "openrouter":
            return []
        return self.openrouter_pronunciation_fallback_models

    @property
    def partner_model(self) -> str:
        return self.openrouter_partner_model

    @property
    def partner_fallback_models(self) -> list[str]:
        if self.ai_provider != "openrouter":
            return []
        return self.openrouter_partner_fallback_models

    @property
    def ai_default_headers(self) -> dict[str, str] | None:
        if self.ai_provider != "openrouter":
            return None
        return {
            "HTTP-Referer": self.openrouter_http_referer,
            "X-OpenRouter-Title": self.openrouter_app_name,
        }

    @property
    def diarization_api_key(self) -> str | None:
        return self.openai_diarization_api_key or (
            self.openai_api_key if self.ai_provider == "openai" else None
        )

    def resolve_project_path(self, value: Path) -> Path:
        if value.is_absolute():
            return value
        project_root = Path(__file__).resolve().parents[3]
        return project_root / value

    @property
    def diarization_available(self) -> bool:
        if self.diarization_provider == "openai":
            return bool(self.diarization_api_key)
        if self.diarization_provider == "modal":
            local_profile = Path.home() / ".modal.toml"
            return bool(
                (self.modal_token_id and self.modal_token_secret) or local_profile.is_file()
            )
        return (
            self.resolve_project_path(self.whisperx_python_path).is_file()
            and self.resolve_project_path(self.whisperx_bridge_path).is_file()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
