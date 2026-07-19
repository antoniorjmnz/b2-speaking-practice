from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_csv_origin_and_host_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,https://example.test")
    monkeypatch.setenv("TRUSTED_HOSTS", "localhost,api.example.test")
    settings = Settings(_env_file=None)
    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://example.test"]
    assert settings.trusted_hosts == ["localhost", "api.example.test"]


def test_production_rejects_development_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")


def test_safe_demo_and_voice_profile_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.ai_mode == "demo"
    assert settings.ai_provider == "openrouter"
    assert settings.transcription_model == "openai/whisper-large-v3"
    assert settings.evaluation_model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert settings.cors_allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert settings.session_retention_minutes == 60
    assert settings.examiner_voice_locale == "en-GB"
    assert settings.examiner_voice_name == "en-GB-SoniaNeural"
    assert settings.examiner_voice_profile_verified is False
    assert settings.ai_partner_voice_locale == "en-GB"
    assert settings.ai_partner_voice_profile_verified is False
    assert settings.diarization_provider == "openai"
    assert settings.diarization_available is False


def test_legacy_mock_mode_remains_accepted() -> None:
    settings = Settings(_env_file=None, ai_mode="mock")
    assert settings.ai_mode == "mock"


def test_retention_cannot_exceed_one_hour() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, session_retention_minutes=61)


def test_real_openrouter_mode_requires_only_its_server_key() -> None:
    settings = Settings(
        _env_file=None,
        ai_mode="real",
        ai_provider="openrouter",
        openrouter_api_key="test-key-not-a-real-secret",
    )
    assert settings.ai_api_key == "test-key-not-a-real-secret"
    assert settings.ai_base_url == "https://openrouter.ai/api/v1"
    assert settings.ai_default_headers == {
        "HTTP-Referer": "http://localhost:3000",
        "X-OpenRouter-Title": "B2 Speaking Academy",
    }


def test_real_openrouter_mode_rejects_missing_key() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_mode="real", ai_provider="openrouter")


def test_gemini_evaluation_uses_a_pinned_stable_model_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.gemini_evaluation_model == "gemini-3.5-flash"
