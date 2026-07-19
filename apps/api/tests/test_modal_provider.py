from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import Settings
from app.providers.factory import create_diarization_provider
from app.providers.modal_provider import ModalDiarizationProvider


def modal_settings() -> Settings:
    return Settings(
        _env_file=None,
        diarization_provider="modal",
        modal_token_id="test-token-id",  # noqa: S106 - deliberately fake test credential
        modal_token_secret="test-token-secret",  # noqa: S106
    )


def test_modal_configuration_is_available_with_service_credentials() -> None:
    settings = modal_settings()
    assert settings.diarization_available is True
    assert isinstance(create_diarization_provider(settings), ModalDiarizationProvider)


@pytest.mark.asyncio
async def test_modal_provider_prefers_signed_urls_over_audio_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    payload = {
        "provider_name": "modal-whisperx-pyannote",
        "model_name": "whisperx:small.en+pyannote:community-1",
        "detected_language": "en",
        "segments": [
            {
                "start_ms": 100,
                "end_ms": 2200,
                "text": "I think this option is useful.",
                "confidence": 0.9,
                "speaker": "A",
            },
            {
                "start_ms": 2300,
                "end_ms": 4400,
                "text": "I agree, but what about the cost?",
                "confidence": 0.88,
                "speaker": "B",
            },
        ],
    }

    class RemoteMethod:
        def __init__(self, name: str) -> None:
            self.name = name

        def remote(self, *args: object) -> dict[str, Any]:
            captured["method"] = self.name
            captured["args"] = args
            return payload

    worker = SimpleNamespace(
        transcribe_pair_urls=RemoteMethod("urls"),
        transcribe_pair=RemoteMethod("bytes"),
    )

    class RemoteClass:
        def __call__(self) -> object:
            return worker

    monkeypatch.setattr(
        "app.providers.modal_provider.modal.Cls.from_name",
        lambda *args, **kwargs: RemoteClass(),
    )
    provider = ModalDiarizationProvider(modal_settings())
    result = await provider.transcribe_pair(
        content=b"pair-audio",
        filename="pair.webm",
        mime_type="audio/webm",
        candidate_a_reference=b"reference-a",
        candidate_a_reference_mime="audio/webm",
        candidate_b_reference=b"reference-b",
        candidate_b_reference_mime="audio/webm",
        content_url="https://storage.example/pair",
        candidate_a_reference_url="https://storage.example/a",
        candidate_b_reference_url="https://storage.example/b",
    )

    assert captured == {
        "method": "urls",
        "args": (
            "https://storage.example/pair",
            "https://storage.example/a",
            "https://storage.example/b",
        ),
    }
    assert [segment.speaker for segment in result.segments] == ["A", "B"]


def test_production_modal_configuration_requires_service_credentials() -> None:
    with pytest.raises(ValueError, match="MODAL_TOKEN_ID"):
        Settings(
            _env_file=None,
            environment="production",
            session_token_pepper="s" * 40,
            upload_signing_secret="u" * 40,
            diarization_provider="modal",
        )


@pytest.mark.parametrize(
    ("token_id", "token_secret"),
    [
        ("test-token-id", None),
        (None, "test-token-secret"),
        (None, None),
    ],
)
def test_modal_is_unavailable_with_incomplete_service_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    token_id: str | None,
    token_secret: str | None,
) -> None:
    monkeypatch.setattr("app.config.Path.home", lambda: tmp_path)
    settings = Settings(
        _env_file=None,
        diarization_provider="modal",
        modal_token_id=token_id,
        modal_token_secret=token_secret,
    )

    assert settings.diarization_available is False


@pytest.mark.parametrize(
    ("token_id", "token_secret"),
    [
        ("test-token-id", None),
        (None, "test-token-secret"),
    ],
)
def test_production_rejects_each_incomplete_modal_credential_pair(
    token_id: str | None,
    token_secret: str | None,
) -> None:
    with pytest.raises(ValueError, match="MODAL_TOKEN_ID.*MODAL_TOKEN_SECRET"):
        Settings(
            _env_file=None,
            environment="production",
            session_token_pepper="s" * 40,
            upload_signing_secret="u" * 40,
            diarization_provider="modal",
            modal_token_id=token_id,
            modal_token_secret=token_secret,
        )
