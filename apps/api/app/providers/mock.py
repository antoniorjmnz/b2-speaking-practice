from __future__ import annotations

from app.evaluation_schemas import (
    CriterionAnalysis,
    EvaluationPayload,
    PronunciationResult,
    TaskPerformanceCheck,
    task_check_keys_for_part,
)
from app.providers.base import TranscribedSegment, TranscriptionResult
from app.schemas import PartnerTurn

# Backwards-compatible name for tests and imports from the original vertical slice.
# An empty list is deliberate: demo mode must never pretend that these words were spoken.
MOCK_SEGMENTS: list[TranscribedSegment] = []

DEMO_REASON_ES = (
    "Modo demostración: la grabación se completó, pero no se ha transcrito ni evaluado."
)


def not_evaluable_payload(
    *,
    status: str,
    reason_es: str,
    confidence: float = 0.0,
    speaking_part: int = 2,
) -> EvaluationPayload:
    if status not in {"demo", "insufficient"}:
        raise ValueError("not_evaluable_payload only accepts demo or insufficient")
    checks = [
        TaskPerformanceCheck(
            key=key,
            status="no_evaluable",
            evidence_source="none",
            evidence="",
            start_ms=None,
            end_ms=None,
            explanation_es=reason_es,
            confidence=confidence,
        )
        for key in task_check_keys_for_part(speaking_part)
    ]
    criterion = CriterionAnalysis(
        summary_es=reason_es,
        practice_band=None,
        confidence=confidence,
        observations=[],
    )
    return EvaluationPayload(
        speaking_part=speaking_part,
        evaluation_status=status,
        status_reason_es=reason_es,
        strengths=[],
        priority_improvements=[],
        grammar_vocabulary=criterion,
        discourse_management=criterion.model_copy(),
        interactive_communication=(criterion.model_copy() if speaking_part == 3 else None),
        task_performance=checks,
        suggested_exercises=[],
        overall_confidence=confidence,
    )


class MockTranscriptionProvider:
    """Legacy class name for an explicit no-evaluation development provider."""

    async def transcribe(
        self, content: bytes, filename: str, mime_type: str, duration_ms: int
    ) -> TranscriptionResult:
        return TranscriptionResult(
            segments=[],
            provider_name="demo-no-transcription",
            model_name="demo-no-transcription-v1",
        )


class MockEvaluationProvider:
    """Legacy class name retained for API compatibility; it performs no evaluation."""

    async def evaluate(
        self,
        *,
        question: str,
        transcript: list[TranscribedSegment],
        objective_metrics: dict[str, object],
        speaking_part: int = 2,
        questions: list[str] | None = None,
        progress_callback=None,
    ) -> tuple[EvaluationPayload, str]:
        if progress_callback:
            await progress_callback("evaluating")
            await progress_callback("reviewing")
        return (
            not_evaluable_payload(
                status="demo", reason_es=DEMO_REASON_ES, speaking_part=speaking_part
            ),
            "demo-no-evaluation-v1",
        )


class MockPronunciationProvider:
    """Legacy class name retained for API compatibility; it performs no analysis."""

    async def analyse(
        self, *, wav_content: bytes, objective_metrics: dict[str, object]
    ) -> tuple[PronunciationResult, str]:
        result = PronunciationResult(
            available=False,
            withheld_reason_es=DEMO_REASON_ES,
            confidence=0.0,
            experimental_practice_band=None,
            pronunciation_summary_es="Análisis no realizado en modo demo.",
            pronunciation_observations=[],
            fluency_note_es="La fluidez no se ha evaluado en modo demo.",
            pause_note_es="Las pausas no se han interpretado como rendimiento lingüístico.",
            technical_quality_note_es="No se ha ejecutado un proveedor de pronunciación.",
        )
        return result, "demo-no-pronunciation-v1"


class PreparedPartnerProvider:
    """A clearly labelled fallback that keeps the practice usable without claiming live AI."""

    async def respond(
        self, *, task_question: str, follow_up_question: str
    ) -> tuple[PartnerTurn, str]:
        del task_question, follow_up_question
        return (
            PartnerTurn(
                spoken_text=(
                    "I think I usually find it easier to ask someone I know well, because "
                    "they understand me and I don't feel embarrassed about the problem."
                ),
                interaction_move="brief_opinion",
                hands_turn_back=True,
                estimated_seconds=11,
                safety_flags=[],
            ),
            "prepared-b2-partner-v1",
        )
