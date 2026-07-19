from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.evaluation_schemas import (
    CriterionAnalysis,
    EvaluationPayload,
    Observation,
    ObservationCategory,
    TaskPerformanceCheck,
    task_check_keys_for_part,
)


class GeminiDraftModel(BaseModel):
    """Small structured-output contract accepted by Gemini's compatibility API.

    The public report schema is deliberately not sent to Gemini: it is deeply nested
    enough to be rejected by the provider.  The application expands this compact,
    provider-facing draft into the complete and strictly validated payload below.
    """

    model_config = ConfigDict(extra="forbid")


class GeminiEvidenceDraft(GeminiDraftModel):
    evidence: str
    explanation_es: str
    suggestion_es: str
    severity: Literal["leve", "importante"]
    confidence: float


class GeminiCriterionObservationDraft(GeminiEvidenceDraft):
    criterion: Literal[
        "grammar_vocabulary",
        "discourse_management",
        "interactive_communication",
    ]


class GeminiTaskCheckDraft(GeminiDraftModel):
    key: str
    status: Literal["logrado", "parcial", "no_logrado", "no_evaluable"]
    evidence: str
    explanation_es: str
    confidence: float


class GeminiEvaluationDraft(GeminiDraftModel):
    speaking_part: Literal[1, 2, 3]
    evaluation_status: Literal["evaluated", "insufficient"]
    status_reason_es: str
    grammar_summary_es: str
    grammar_band: float
    grammar_confidence: float
    discourse_summary_es: str
    discourse_band: float
    discourse_confidence: float
    interactive_summary_es: str
    interactive_band: float
    interactive_confidence: float
    strengths: list[GeminiEvidenceDraft]
    priority_improvements: list[GeminiEvidenceDraft]
    criterion_observations: list[GeminiCriterionObservationDraft]
    task_checks: list[GeminiTaskCheckDraft]
    suggested_exercises: list[str]
    overall_confidence: float


def _bounded(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _text(value: str, fallback: str, *, limit: int = 1_200) -> str:
    cleaned = value.strip()
    return (cleaned or fallback)[:limit]


def _observation(
    draft: GeminiEvidenceDraft,
    category: ObservationCategory,
) -> Observation | None:
    evidence = draft.evidence.strip()
    if not evidence or len(evidence) > 500:
        return None
    explanation = draft.explanation_es.strip()
    suggestion = draft.suggestion_es.strip()
    if not explanation or not suggestion:
        return None
    return Observation(
        category=category,
        evidence=evidence,
        # Evidence verification replaces these placeholders with the exact
        # transcript segment boundaries before the report is persisted.
        start_ms=0,
        end_ms=0,
        explanation_es=explanation[:1_200],
        suggestion_es=suggestion[:1_200],
        severity=draft.severity,
        confidence=_bounded(draft.confidence, 0, 1),
    )


def _criterion(
    *,
    summary: str,
    band: float,
    confidence: float,
    observations: list[Observation],
    evaluated: bool,
) -> CriterionAnalysis:
    return CriterionAnalysis(
        summary_es=_text(summary, "No hay evidencia suficiente para analizar este criterio."),
        practice_band=_bounded(band, 0, 5) if evaluated else None,
        confidence=_bounded(confidence, 0, 1)
        if evaluated
        else min(_bounded(confidence, 0, 1), 0.25),
        observations=observations[:12] if evaluated else [],
    )


def _task_checks(
    draft: GeminiEvaluationDraft,
    speaking_part: int,
    *,
    evaluated: bool,
) -> list[TaskPerformanceCheck]:
    received = {item.key: item for item in draft.task_checks}
    checks: list[TaskPerformanceCheck] = []
    fallback_reason = _text(
        draft.status_reason_es,
        "No hay evidencia suficiente para comprobar este comportamiento.",
    )
    for key in task_check_keys_for_part(speaking_part):
        item = received.get(key.value)
        if not evaluated or item is None:
            checks.append(
                TaskPerformanceCheck(
                    key=key,
                    status="no_evaluable",
                    evidence_source="none",
                    evidence="",
                    start_ms=None,
                    end_ms=None,
                    explanation_es=(
                        fallback_reason
                        if not evaluated
                        else "El análisis no aportó evidencia verificable para este comportamiento."
                    ),
                    confidence=min(_bounded(draft.overall_confidence, 0, 1), 0.25),
                )
            )
            continue
        evidence = item.evidence.strip()
        checks.append(
            TaskPerformanceCheck(
                key=key,
                status=item.status,
                evidence_source="transcript" if evidence else "none",
                evidence=evidence[:500],
                start_ms=0 if evidence else None,
                end_ms=0 if evidence else None,
                explanation_es=_text(
                    item.explanation_es,
                    "El análisis no explicó este comportamiento con suficiente detalle.",
                ),
                confidence=_bounded(item.confidence, 0, 1),
            )
        )
    return checks


def evaluation_payload_from_gemini(
    draft: GeminiEvaluationDraft,
    *,
    speaking_part: int,
) -> EvaluationPayload:
    """Expand a compact Gemini result into the application's strict report contract."""

    if draft.speaking_part != speaking_part:
        raise ValueError("Gemini evaluation returned the wrong speaking part")

    evaluated = draft.evaluation_status == "evaluated"
    grouped: dict[ObservationCategory, list[Observation]] = {
        ObservationCategory.GRAMMAR_VOCABULARY: [],
        ObservationCategory.DISCOURSE_MANAGEMENT: [],
        ObservationCategory.INTERACTIVE_COMMUNICATION: [],
    }
    if evaluated:
        for item in draft.criterion_observations:
            category = ObservationCategory(item.criterion)
            observation = _observation(item, category)
            if observation is not None:
                grouped[category].append(observation)

    strengths = [
        observation
        for item in draft.strengths[:5]
        if (observation := _observation(item, ObservationCategory.STRENGTH)) is not None
    ]
    improvements = [
        observation
        for item in draft.priority_improvements[:4]
        if (observation := _observation(item, ObservationCategory.PRIORITY_IMPROVEMENT)) is not None
    ]

    overall_confidence = _bounded(draft.overall_confidence, 0, 1)
    if not evaluated:
        overall_confidence = min(overall_confidence, 0.25)
        strengths = []
        improvements = []

    grammar = _criterion(
        summary=draft.grammar_summary_es,
        band=draft.grammar_band,
        confidence=draft.grammar_confidence,
        observations=grouped[ObservationCategory.GRAMMAR_VOCABULARY],
        evaluated=evaluated,
    )
    discourse = _criterion(
        summary=draft.discourse_summary_es,
        band=draft.discourse_band,
        confidence=draft.discourse_confidence,
        observations=grouped[ObservationCategory.DISCOURSE_MANAGEMENT],
        evaluated=evaluated,
    )
    interactive = (
        _criterion(
            summary=draft.interactive_summary_es,
            band=draft.interactive_band,
            confidence=draft.interactive_confidence,
            observations=grouped[ObservationCategory.INTERACTIVE_COMMUNICATION],
            evaluated=evaluated,
        )
        if speaking_part == 3
        else None
    )

    return EvaluationPayload(
        speaking_part=speaking_part,
        evaluation_status=draft.evaluation_status,
        status_reason_es=_text(
            draft.status_reason_es,
            (
                "La respuesta contiene evidencia suficiente para un análisis formativo."
                if evaluated
                else "No hay evidencia suficiente para realizar un análisis responsable."
            ),
        ),
        strengths=strengths,
        priority_improvements=improvements,
        grammar_vocabulary=grammar,
        discourse_management=discourse,
        interactive_communication=interactive,
        task_performance=_task_checks(draft, speaking_part, evaluated=evaluated),
        suggested_exercises=[
            item.strip()[:1_200] for item in draft.suggested_exercises[:5] if item.strip()
        ]
        if evaluated
        else [],
        overall_confidence=overall_confidence,
    )
