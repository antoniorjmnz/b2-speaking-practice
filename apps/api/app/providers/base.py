from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.evaluation_schemas import EvaluationPayload, PronunciationResult
from app.schemas import PartnerTurn

ProgressCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class TranscribedSegment:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    speaker: str | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    segments: list[TranscribedSegment]
    provider_name: str
    model_name: str
    detected_language: str | None = None


class TranscriptionProvider(Protocol):
    async def transcribe(
        self, content: bytes, filename: str, mime_type: str, duration_ms: int
    ) -> TranscriptionResult: ...


class SpeakerDiarizationProvider(Protocol):
    async def transcribe_pair(
        self,
        *,
        content: bytes,
        filename: str,
        mime_type: str,
        candidate_a_reference: bytes,
        candidate_a_reference_mime: str,
        candidate_b_reference: bytes,
        candidate_b_reference_mime: str,
        content_url: str | None = None,
        candidate_a_reference_url: str | None = None,
        candidate_b_reference_url: str | None = None,
    ) -> TranscriptionResult: ...


class EvaluationProvider(Protocol):
    async def evaluate(
        self,
        *,
        question: str,
        transcript: list[TranscribedSegment],
        objective_metrics: dict[str, object],
        speaking_part: int = 2,
        questions: list[str] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[EvaluationPayload, str]: ...


class PronunciationProvider(Protocol):
    async def analyse(
        self, *, wav_content: bytes, objective_metrics: dict[str, object]
    ) -> tuple[PronunciationResult, str]: ...


class PartnerProvider(Protocol):
    async def respond(
        self, *, task_question: str, follow_up_question: str
    ) -> tuple[PartnerTurn, str]: ...
