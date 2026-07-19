from __future__ import annotations

from app.config import Settings
from app.providers.base import (
    EvaluationProvider,
    PartnerProvider,
    PronunciationProvider,
    SpeakerDiarizationProvider,
    TranscriptionProvider,
)
from app.providers.mock import (
    MockEvaluationProvider,
    MockPronunciationProvider,
    MockTranscriptionProvider,
    PreparedPartnerProvider,
)
from app.providers.modal_provider import ModalDiarizationProvider
from app.providers.openai_provider import (
    OpenAIDiarizationProvider,
    OpenAIEvaluationProvider,
    OpenAIPartnerProvider,
    OpenAIPronunciationProvider,
    OpenAITranscriptionProvider,
)
from app.providers.whisperx_provider import WhisperXDiarizationProvider


def create_diarization_provider(settings: Settings) -> SpeakerDiarizationProvider:
    if settings.diarization_provider == "modal":
        return ModalDiarizationProvider(settings)
    if settings.diarization_provider == "whisperx":
        return WhisperXDiarizationProvider(settings)
    return OpenAIDiarizationProvider(settings)


def create_providers(
    settings: Settings,
) -> tuple[TranscriptionProvider, EvaluationProvider, PronunciationProvider]:
    if settings.ai_mode == "real":
        return (
            OpenAITranscriptionProvider(settings),
            OpenAIEvaluationProvider(settings),
            OpenAIPronunciationProvider(settings),
        )
    return MockTranscriptionProvider(), MockEvaluationProvider(), MockPronunciationProvider()


def create_partner_provider(settings: Settings) -> tuple[PartnerProvider, str]:
    if settings.ai_mode == "real":
        return OpenAIPartnerProvider(settings), "ai"
    return PreparedPartnerProvider(), "prepared"
