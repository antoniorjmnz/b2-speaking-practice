from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.evaluation_schemas import (
    PART_1_TASK_CHECK_KEYS,
    PART_2_TASK_CHECK_KEYS,
    PART_3_TASK_CHECK_KEYS,
    CriterionAnalysis,
    EvaluationPayload,
    Observation,
    ObservationCategory,
    TaskCheckKey,
    TaskPerformanceCheck,
)
from app.evidence import verify_evaluation_evidence
from app.objective_checks import (
    apply_objective_task_checks,
    detect_part3_option_coverage,
    withheld_pronunciation,
)
from app.processor import (
    _audio_evaluation_block_reason,
    _transcript_evaluation_block_reason,
)
from app.providers.base import TranscribedSegment, TranscriptionResult
from app.providers.mock import (
    DEMO_REASON_ES,
    MOCK_SEGMENTS,
    MockEvaluationProvider,
    not_evaluable_payload,
)
from app.providers.openai_provider import (
    EVALUATION_REVIEW_SYSTEM_PROMPT,
    EVALUATION_SYSTEM_PROMPT,
    PART1_EVALUATION_SYSTEM_PROMPT,
    PART1_REVIEW_SYSTEM_PROMPT,
    PART3_EVALUATION_SYSTEM_PROMPT,
    PART3_REVIEW_SYSTEM_PROMPT,
)
from app.security import generate_session_token, hash_session_token, verify_session_token

TRANSCRIPT = [
    TranscribedSegment(
        start_ms=1_000,
        end_ms=5_000,
        text="Both photographs show people learning in different places.",
        confidence=0.95,
    )
]


def evaluated_payload() -> EvaluationPayload:
    observation = Observation(
        category=ObservationCategory.STRENGTH,
        evidence=TRANSCRIPT[0].text,
        start_ms=1_000,
        end_ms=5_000,
        explanation_es="Compara las dos fotografías de forma explícita.",
        suggestion_es="Desarrolla la comparación con una razón.",
        severity="leve",
        confidence=0.9,
    )
    criterion = CriterionAnalysis(
        summary_es="Hay evidencia lingüística limitada pero evaluable.",
        practice_band=2.0,
        confidence=0.8,
        observations=[observation],
    )
    return EvaluationPayload(
        evaluation_status="evaluated",
        status_reason_es="La respuesta contiene evidencia suficiente para una evaluación.",
        strengths=[observation],
        priority_improvements=[],
        grammar_vocabulary=criterion,
        discourse_management=criterion.model_copy(),
        task_performance=[
            TaskPerformanceCheck(
                key=key,
                status="no_evaluable",
                evidence_source="none",
                evidence="",
                explanation_es="Pendiente de comprobación objetiva.",
                confidence=0.5,
            )
            for key in PART_2_TASK_CHECK_KEYS
        ],
        suggested_exercises=[],
        overall_confidence=0.8,
    )


def evaluated_part3_payload() -> EvaluationPayload:
    base = evaluated_payload()
    return EvaluationPayload(
        speaking_part=3,
        evaluation_status="evaluated",
        status_reason_es="La conversacion contiene evidencia suficiente.",
        strengths=[],
        priority_improvements=[],
        grammar_vocabulary=base.grammar_vocabulary,
        discourse_management=base.discourse_management,
        interactive_communication=base.grammar_vocabulary.model_copy(),
        task_performance=[
            TaskPerformanceCheck(
                key=key,
                status="no_evaluable",
                evidence_source="none",
                evidence="",
                explanation_es="Pendiente de comprobacion.",
                confidence=0.4,
            )
            for key in PART_3_TASK_CHECK_KEYS
        ],
        suggested_exercises=[],
        overall_confidence=0.8,
    )


def demo_evaluation() -> EvaluationPayload:
    provider = MockEvaluationProvider()
    result, _ = asyncio.run(
        provider.evaluate(
            question="What might be difficult?",
            transcript=MOCK_SEGMENTS,
            objective_metrics={},
        )
    )
    return result


def test_schema_requires_each_task_check_once() -> None:
    payload = demo_evaluation().model_dump()
    payload["task_performance"] = payload["task_performance"][:-1]
    with pytest.raises(ValidationError):
        EvaluationPayload.model_validate(payload)


def test_schema_allows_zero_strengths_for_evaluated_response() -> None:
    payload = evaluated_payload().model_dump()
    payload["strengths"] = []
    assert EvaluationPayload.model_validate(payload).strengths == []


def test_part1_uses_only_interview_specific_checks() -> None:
    payload = not_evaluable_payload(
        status="insufficient",
        reason_es="No hay habla suficiente.",
        speaking_part=1,
    )

    assert payload.speaking_part == 1
    assert tuple(check.key for check in payload.task_performance) == PART_1_TASK_CHECK_KEYS


def test_non_evaluated_payload_rejects_praise_bands_and_high_confidence() -> None:
    payload = demo_evaluation().model_dump()
    payload["strengths"] = [evaluated_payload().strengths[0].model_dump()]
    payload["grammar_vocabulary"]["practice_band"] = 4.0
    payload["overall_confidence"] = 0.9
    with pytest.raises(ValidationError):
        EvaluationPayload.model_validate(payload)


def test_demo_provider_is_explicit_and_fabricates_nothing() -> None:
    result = demo_evaluation()
    assert result.evaluation_status == "demo"
    assert result.status_reason_es == DEMO_REASON_ES
    assert result.strengths == []
    assert result.priority_improvements == []
    assert result.grammar_vocabulary.practice_band is None
    assert result.discourse_management.practice_band is None
    assert result.overall_confidence == 0
    assert {check.status for check in result.task_performance} == {"no_evaluable"}


def test_unverifiable_evidence_is_removed() -> None:
    evaluation = evaluated_payload()
    hallucinated = evaluation.strengths[0].model_copy(
        update={"evidence": "This sentence was never spoken by the candidate."}
    )
    evaluation = evaluation.model_copy(update={"strengths": [hallucinated]})
    cleaned, rejected = verify_evaluation_evidence(evaluation, TRANSCRIPT)
    assert rejected >= 1
    assert cleaned.strengths == []


def test_objective_rules_treat_early_finish_and_silence_as_failures() -> None:
    metrics = {
        "recorded_duration_ms": 60_000,
        "detected_speech_duration_ms": 18_000,
        "silence_duration_ms": 42_000,
        "both_photographs_mentioned": True,
    }
    result = apply_objective_task_checks(evaluated_payload(), metrics)
    by_key = {check.key: check for check in result.task_performance}
    assert by_key[TaskCheckKey.FINISHES_EARLY].status == "no_logrado"
    assert by_key[TaskCheckKey.EXCESSIVE_SILENCE].status == "no_logrado"
    assert by_key[TaskCheckKey.DISCUSSES_BOTH].status == "logrado"


def test_relevance_is_confirmed_when_both_photos_and_question_are_verified() -> None:
    evaluation = evaluated_payload()
    checks = [
        check.model_copy(update={"status": "logrado", "confidence": 0.88})
        if check.key == TaskCheckKey.ANSWERS_QUESTION
        else check
        for check in evaluation.task_performance
    ]
    evaluation = evaluation.model_copy(update={"task_performance": checks})
    result = apply_objective_task_checks(
        evaluation,
        {
            "recorded_duration_ms": 60_000,
            "detected_speech_duration_ms": 45_000,
            "silence_duration_ms": 15_000,
            "both_photographs_mentioned": True,
        },
    )

    by_key = {check.key: check for check in result.task_performance}
    assert by_key[TaskCheckKey.RELEVANT].status == "logrado"
    assert by_key[TaskCheckKey.RELEVANT].evidence_source == "objective_metrics"


def test_non_evaluated_checks_stay_no_evaluable_despite_metrics() -> None:
    metrics = {
        "recorded_duration_ms": 60_000,
        "detected_speech_duration_ms": 60_000,
        "silence_duration_ms": 0,
        "both_photographs_mentioned": True,
    }
    result = apply_objective_task_checks(demo_evaluation(), metrics)
    assert {check.status for check in result.task_performance} == {"no_evaluable"}


def test_part3_confirms_multiple_explicit_options_from_real_conversation() -> None:
    metrics: dict[str, object] = {
        "recorded_duration_ms": 180_000,
        "detected_speech_duration_ms": 150_000,
        "silence_duration_ms": 30_000,
        "candidate_talk_ms": 76_000,
        "partner_talk_ms": 74_000,
        "candidate_turn_count": 6,
        "evaluation_candidate": "A",
        "task_prompts": [
            "flexible working hours",
            "a free gym in the office",
            "more team activities",
            "longer holidays",
            "a quiet room for breaks",
        ],
        "conversation_context": [
            {
                "speaker": "A",
                "text": "Let's start talking about flexible working hours.",
            },
            {
                "speaker": "B",
                "text": "Yes, that would be a good idea.",
            },
            {
                "speaker": "A",
                "text": "What do you think about a free gym in the office?",
            },
            {
                "speaker": "B",
                "text": "It would be beneficial for our health.",
            },
            {
                "speaker": "A",
                "text": "What do you think about longer holidays?",
            },
        ],
    }

    coverage = detect_part3_option_coverage(metrics)
    result = apply_objective_task_checks(evaluated_part3_payload(), metrics)
    by_key = {check.key: check for check in result.task_performance}

    assert coverage["candidate"] == [
        "flexible working hours",
        "a free gym in the office",
        "longer holidays",
    ]
    assert by_key[TaskCheckKey.COVERS_OPTIONS].status == "logrado"
    assert by_key[TaskCheckKey.COVERS_OPTIONS].evidence_source == "objective_metrics"
    assert by_key[TaskCheckKey.RELEVANT].status == "logrado"
    assert by_key[TaskCheckKey.RELEVANT].evidence_source == "objective_metrics"
    assert (
        "No es necesario mencionar las cinco" in by_key[TaskCheckKey.COVERS_OPTIONS].explanation_es
    )


def test_part3_option_detector_confirms_reordered_near_explicit_wording() -> None:
    coverage = detect_part3_option_coverage(
        {
            "evaluation_candidate": "B",
            "task_prompts": [
                "flexible working hours",
                "a free gym in the office",
                "longer holidays",
            ],
            "conversation_context": [
                {"speaker": "B", "text": "Working flexible hours could help."},
                {"speaker": "B", "text": "An office gym is useful for health."},
            ],
        }
    )

    assert coverage["candidate"] == [
        "flexible working hours",
        "a free gym in the office",
    ]


def test_part3_option_detector_does_not_turn_no_match_into_a_failure() -> None:
    metrics: dict[str, object] = {
        "recorded_duration_ms": 180_000,
        "detected_speech_duration_ms": 120_000,
        "silence_duration_ms": 60_000,
        "candidate_talk_ms": 60_000,
        "partner_talk_ms": 60_000,
        "candidate_turn_count": 5,
        "evaluation_candidate": "A",
        "task_prompts": ["flexible working hours", "longer holidays"],
        "conversation_context": [
            {"speaker": "A", "text": "There are some useful ideas here."},
            {"speaker": "B", "text": "I agree with you."},
        ],
    }

    result = apply_objective_task_checks(evaluated_part3_payload(), metrics)
    by_key = {check.key: check for check in result.task_performance}

    assert by_key[TaskCheckKey.COVERS_OPTIONS].status == "no_evaluable"


def test_audio_and_language_preflight_withhold_unreliable_evaluation() -> None:
    silence_reason = _audio_evaluation_block_reason(
        {
            "recorded_duration_ms": 60_000,
            "detected_speech_duration_ms": 0,
            "audio_quality": {},
        }
    )
    language_reason = _transcript_evaluation_block_reason(
        TranscriptionResult(
            segments=TRANSCRIPT,
            provider_name="test",
            model_name="test",
            detected_language="es",
        ),
        {"word_count": 8},
    )
    assert silence_reason is not None and "silencio" in silence_reason
    assert language_reason is not None and "no es inglés" in language_reason


def test_prompt_forbids_automatic_positivity() -> None:
    normalized = EVALUATION_SYSTEM_PROMPT.casefold()
    for required in ("strengths", "silencio", "nonsense", "fuera de tema", "no busques"):
        assert required in normalized


@pytest.mark.parametrize(
    "prompt",
    [
        EVALUATION_SYSTEM_PROMPT,
        EVALUATION_REVIEW_SYSTEM_PROMPT,
        PART1_EVALUATION_SYSTEM_PROMPT,
        PART1_REVIEW_SYSTEM_PROMPT,
        PART3_EVALUATION_SYSTEM_PROMPT,
        PART3_REVIEW_SYSTEM_PROMPT,
    ],
)
def test_prompts_do_not_force_a_minimum_b2_band_from_intelligibility_alone(
    prompt: str,
) -> None:
    normalized = prompt.casefold()
    forbidden_shortcuts = (
        "la banda mínima defendible es 3",
        "la banda correcta es 4, no 3",
        "rechaza toda banda 2",
        "mínimo defendible es 3",
    )

    for shortcut in forbidden_shortcuts:
        assert shortcut not in normalized


def test_part3_prompts_treat_low_confidence_asr_as_uncertain_evidence() -> None:
    for prompt in (PART3_EVALUATION_SYSTEM_PROMPT, PART3_REVIEW_SYSTEM_PROMPT):
        normalized = " ".join(prompt.casefold().split())
        assert "confianza asr" in normalized
        assert "0.85" in normalized


@pytest.mark.parametrize(
    ("metrics", "reason_fragment"),
    [
        (
            {
                "recorded_duration_ms": 4_999,
                "detected_speech_duration_ms": 4_000,
                "audio_quality": {},
            },
            "demasiado corta",
        ),
        (
            {
                "recorded_duration_ms": 60_000,
                "detected_speech_duration_ms": 2_999,
                "audio_quality": {},
            },
            "menos de tres segundos",
        ),
        (
            {
                "recorded_duration_ms": 60_000,
                "detected_speech_duration_ms": 30_000,
                "audio_quality": {"signal_rms_dbfs": -56},
            },
            "señal",
        ),
        (
            {
                "recorded_duration_ms": 60_000,
                "detected_speech_duration_ms": 30_000,
                "audio_quality": {"estimated_snr_db": 2.9},
            },
            "ruidosa",
        ),
        (
            {
                "recorded_duration_ms": 60_000,
                "detected_speech_duration_ms": 30_000,
                "audio_quality": {"clipping_ratio": 0.21},
            },
            "saturada",
        ),
    ],
)
def test_bad_audio_is_withheld_before_ai_evaluation(
    metrics: dict[str, object], reason_fragment: str
) -> None:
    reason = _audio_evaluation_block_reason(metrics)

    assert reason is not None
    assert "NO EVALUABLE" in reason
    assert reason_fragment in reason.casefold()


@pytest.mark.parametrize(
    ("detected_language", "word_count", "reason_fragment"),
    [
        ("es", 20, "no es inglés"),
        ("en", 2, "menos de tres palabras"),
        (None, 0, "menos de tres palabras"),
    ],
)
def test_bad_or_insufficient_transcripts_are_withheld_before_ai_evaluation(
    detected_language: str | None,
    word_count: int,
    reason_fragment: str,
) -> None:
    transcription = TranscriptionResult(
        segments=TRANSCRIPT,
        provider_name="test",
        model_name="test",
        detected_language=detected_language,
    )

    reason = _transcript_evaluation_block_reason(
        transcription,
        {"word_count": word_count},
    )

    assert reason is not None
    assert "NO EVALUABLE" in reason
    assert reason_fragment in reason.casefold()


def test_pronunciation_withholding_separates_technical_and_fluency_notes() -> None:
    result = withheld_pronunciation(
        "Audio insuficiente.",
        {"audio_quality": {"sufficient_for_pronunciation": False, "clipping_ratio": 0.2}},
    )
    assert result["available"] is False
    assert result["experimental_practice_band"] is None
    assert "fluidez" in str(result["fluency_note_es"]).lower()
    assert "Calidad técnica" in str(result["technical_quality_note_es"])


def test_session_token_is_stored_as_one_way_hash() -> None:
    token = generate_session_token()
    digest = hash_session_token(token, "a-test-pepper")
    assert token not in digest
    assert len(digest) == 64
    assert verify_session_token(token, digest, "a-test-pepper")
    assert not verify_session_token("wrong-token", digest, "a-test-pepper")
