from __future__ import annotations

import pytest

from app.evaluation_schemas import PART_2_TASK_CHECK_KEYS, PART_3_TASK_CHECK_KEYS
from app.gemini_evaluation import (
    GeminiCriterionObservationDraft,
    GeminiEvaluationDraft,
    GeminiEvidenceDraft,
    GeminiTaskCheckDraft,
    evaluation_payload_from_gemini,
)


def make_draft(
    *,
    speaking_part: int = 3,
    evaluation_status: str = "evaluated",
) -> GeminiEvaluationDraft:
    return GeminiEvaluationDraft.model_validate(
        {
            "speaking_part": speaking_part,
            "evaluation_status": evaluation_status,
            "status_reason_es": "Hay evidencia suficiente para la práctica.",
            "grammar_summary_es": "El control gramatical es irregular pero evaluable.",
            "grammar_band": 2.5,
            "grammar_confidence": 0.8,
            "discourse_summary_es": "Las ideas se conectan de forma sencilla.",
            "discourse_band": 2.0,
            "discourse_confidence": 0.75,
            "interactive_summary_es": "Responde a la otra candidata.",
            "interactive_band": 2.5,
            "interactive_confidence": 0.7,
            "strengths": [],
            "priority_improvements": [],
            "criterion_observations": [],
            "task_checks": [],
            "suggested_exercises": [],
            "overall_confidence": 0.78,
        }
    )


def test_compact_gemini_draft_expands_to_a_complete_part3_payload() -> None:
    draft = make_draft().model_copy(
        update={
            "grammar_band": 8.0,
            "grammar_confidence": 1.4,
            "strengths": [
                GeminiEvidenceDraft(
                    evidence="I agree with that idea",
                    explanation_es="Responde directamente a la aportación de su compañera.",
                    suggestion_es="Mantén este tipo de enlace.",
                    severity="leve",
                    confidence=1.2,
                )
            ],
            "criterion_observations": [
                GeminiCriterionObservationDraft(
                    criterion="interactive_communication",
                    evidence="I agree with that idea",
                    explanation_es="Enlaza su turno con el anterior.",
                    suggestion_es="Añade una alternativa después de enlazar.",
                    severity="leve",
                    confidence=0.85,
                )
            ],
            "task_checks": [
                GeminiTaskCheckDraft(
                    key="responds_to_partner",
                    status="logrado",
                    evidence="I agree with that idea",
                    explanation_es="La respuesta retoma la propuesta anterior.",
                    confidence=0.9,
                )
            ],
        }
    )

    payload = evaluation_payload_from_gemini(draft, speaking_part=3)

    assert payload.evaluation_status == "evaluated"
    assert payload.grammar_vocabulary.practice_band == 5
    assert payload.grammar_vocabulary.confidence == 1
    assert payload.interactive_communication is not None
    assert len(payload.interactive_communication.observations) == 1
    assert payload.strengths[0].start_ms == 0
    assert payload.strengths[0].end_ms == 0
    assert {check.key for check in payload.task_performance} == set(PART_3_TASK_CHECK_KEYS)
    by_key = {check.key.value: check for check in payload.task_performance}
    assert by_key["responds_to_partner"].status == "logrado"
    assert by_key["responds_to_partner"].evidence_source == "transcript"
    assert by_key["links_contributions"].status == "no_evaluable"
    assert by_key["links_contributions"].evidence_source == "none"
    assert by_key["links_contributions"].confidence <= 0.25


def test_missing_and_unknown_gemini_checks_never_break_the_report_contract() -> None:
    draft = make_draft(speaking_part=2).model_copy(
        update={
            "task_checks": [
                GeminiTaskCheckDraft(
                    key="not_a_real_check",
                    status="logrado",
                    evidence="invented",
                    explanation_es="Este control no pertenece a la parte.",
                    confidence=0.9,
                )
            ]
        }
    )

    payload = evaluation_payload_from_gemini(draft, speaking_part=2)

    assert {check.key for check in payload.task_performance} == set(PART_2_TASK_CHECK_KEYS)
    assert {check.status for check in payload.task_performance} == {"no_evaluable"}
    assert {check.evidence_source for check in payload.task_performance} == {"none"}


def test_insufficient_gemini_draft_cannot_leak_praise_bands_or_high_confidence() -> None:
    draft = make_draft(speaking_part=2, evaluation_status="insufficient").model_copy(
        update={
            "strengths": [
                GeminiEvidenceDraft(
                    evidence="Good answer",
                    explanation_es="Elogio que debe retirarse.",
                    suggestion_es="Ninguna.",
                    severity="leve",
                    confidence=0.95,
                )
            ],
            "priority_improvements": [
                GeminiEvidenceDraft(
                    evidence="One word",
                    explanation_es="Observación que debe retirarse.",
                    suggestion_es="Habla más.",
                    severity="importante",
                    confidence=0.95,
                )
            ],
            "suggested_exercises": ["Practica respuestas largas."],
            "overall_confidence": 0.99,
        }
    )

    payload = evaluation_payload_from_gemini(draft, speaking_part=2)

    assert payload.evaluation_status == "insufficient"
    assert payload.strengths == []
    assert payload.priority_improvements == []
    assert payload.suggested_exercises == []
    assert payload.grammar_vocabulary.practice_band is None
    assert payload.discourse_management.practice_band is None
    assert payload.interactive_communication is None
    assert payload.overall_confidence == 0.25
    assert {check.status for check in payload.task_performance} == {"no_evaluable"}
    assert all(check.confidence <= 0.25 for check in payload.task_performance)


def test_gemini_draft_for_the_wrong_speaking_part_is_rejected() -> None:
    with pytest.raises(ValueError, match="wrong speaking part"):
        evaluation_payload_from_gemini(make_draft(speaking_part=3), speaking_part=2)
