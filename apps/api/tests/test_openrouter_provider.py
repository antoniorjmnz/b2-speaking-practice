from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.evaluation_schemas import EvaluationPayload
from app.gemini_evaluation import GeminiEvaluationDraft
from app.providers.base import TranscribedSegment
from app.providers.mock import not_evaluable_payload
from app.providers.openai_provider import (
    OpenAIDiarizationProvider,
    OpenAIEvaluationProvider,
    OpenAIPartnerProvider,
    OpenAIPronunciationProvider,
    OpenAITranscriptionProvider,
    _strict_provider_schema,
)
from app.schemas import PartnerTurn


def openrouter_settings() -> Settings:
    return Settings(
        _env_file=None,
        ai_mode="real",
        ai_provider="openrouter",
        openrouter_api_key="test-key-not-a-real-secret",
    )


def evaluable_payload(*, speaking_part: int = 2) -> EvaluationPayload:
    base_payload = not_evaluable_payload(
        status="insufficient",
        reason_es="No hay suficiente evidencia.",
        confidence=0.1,
        speaking_part=speaking_part,
    )
    criterion = base_payload.grammar_vocabulary.model_copy(
        update={
            "summary_es": "Hay evidencia lingüística suficiente para la práctica.",
            "practice_band": 2.0,
            "confidence": 0.75,
        }
    )
    return base_payload.model_copy(
        update={
            "evaluation_status": "evaluated",
            "status_reason_es": "Hay evidencia suficiente.",
            "grammar_vocabulary": criterion,
            "discourse_management": criterion.model_copy(),
            "overall_confidence": 0.75,
        }
    )


def gemini_evaluable_draft(*, speaking_part: int = 2) -> GeminiEvaluationDraft:
    return GeminiEvaluationDraft(
        speaking_part=speaking_part,
        evaluation_status="evaluated",
        status_reason_es="Hay evidencia suficiente.",
        grammar_summary_es="La evidencia gramatical es suficiente.",
        grammar_band=2.0,
        grammar_confidence=0.75,
        discourse_summary_es="La evidencia discursiva es suficiente.",
        discourse_band=2.0,
        discourse_confidence=0.75,
        interactive_summary_es="La evidencia interactiva es suficiente.",
        interactive_band=2.0,
        interactive_confidence=0.75,
        strengths=[],
        priority_improvements=[],
        criterion_observations=[],
        task_checks=[],
        suggested_exercises=[],
        overall_confidence=0.75,
    )


@pytest.mark.asyncio
async def test_openrouter_transcription_uses_dedicated_audio_endpoint() -> None:
    provider = OpenAITranscriptionProvider(openrouter_settings())
    create = AsyncMock(
        return_value=SimpleNamespace(
            text="Both photographs show people learning.",
            language="en",
            segments=[
                SimpleNamespace(
                    start=0.2,
                    end=3.4,
                    text="Both photographs show people learning.",
                )
            ],
        )
    )
    provider.client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )

    result = await provider.transcribe(b"audio", "answer.webm", "audio/webm", 4_000)

    assert result.provider_name == "openrouter"
    assert result.model_name == "openai/whisper-large-v3"
    assert result.detected_language == "en"
    assert result.segments[0].start_ms == 200
    assert create.await_args.kwargs["response_format"] == "verbose_json"
    assert create.await_args.kwargs["timestamp_granularities"] == ["segment"]


@pytest.mark.asyncio
async def test_part3_diarization_uses_two_known_voice_references() -> None:
    settings = openrouter_settings().model_copy(
        update={"openai_diarization_api_key": "test-direct-openai-key"}
    )
    provider = OpenAIDiarizationProvider(settings)
    create = AsyncMock(
        return_value=SimpleNamespace(
            segments=[
                SimpleNamespace(
                    speaker="candidate_a", start=0.2, end=3.1, text="I agree with that idea."
                ),
                SimpleNamespace(
                    speaker="candidate_b", start=3.2, end=6.4, text="Maybe parks are better."
                ),
            ]
        )
    )
    provider.client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )

    result = await provider.transcribe_pair(
        content=b"pair-audio",
        filename="pair.webm",
        mime_type="audio/webm",
        candidate_a_reference=b"voice-a",
        candidate_a_reference_mime="audio/webm",
        candidate_b_reference=b"voice-b",
        candidate_b_reference_mime="audio/webm",
    )

    assert [segment.speaker for segment in result.segments] == ["A", "B"]
    request = create.await_args.kwargs
    assert request["model"] == "gpt-4o-transcribe-diarize"
    assert request["response_format"] == "diarized_json"
    assert request["chunking_strategy"] == "auto"
    assert request["extra_body"]["known_speaker_names"] == [
        "candidate_a",
        "candidate_b",
    ]


@pytest.mark.asyncio
async def test_openrouter_evaluation_requires_json_schema_capable_route() -> None:
    provider = OpenAIEvaluationProvider(openrouter_settings())
    base_payload = not_evaluable_payload(
        status="insufficient",
        reason_es="No hay suficiente evidencia.",
        confidence=0.1,
    )
    criterion = base_payload.grammar_vocabulary.model_copy(
        update={
            "summary_es": "Respuesta breve pero evaluable.",
            "practice_band": 1.5,
            "confidence": 0.8,
        }
    )
    payload = base_payload.model_copy(
        update={
            "evaluation_status": "evaluated",
            "status_reason_es": "Hay evidencia suficiente para una revisión formativa.",
            "grammar_vocabulary": criterion,
            "discourse_management": criterion.model_copy(),
            "overall_confidence": 0.8,
        }
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=payload.model_dump_json()))]
        )
    )
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    result, model = await provider.evaluate(
        question="Why might these people need help?",
        transcript=[TranscribedSegment(0, 1_000, "I do not know.")],
        objective_metrics={"word_count": 4},
    )

    assert result.evaluation_status == "evaluated"
    assert model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert create.await_count == 2
    request = create.await_args_list[0].kwargs
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["extra_body"] == {
        "provider": {"require_parameters": True},
        "reasoning": {"effort": "none", "exclude": True},
    }
    review_request = create.await_args_list[1].kwargs
    assert review_request["response_format"] == request["response_format"]
    assert "segundo revisor independiente" in review_request["messages"][0]["content"]
    assert "BORRADOR A AUDITAR" in review_request["messages"][1]["content"]


@pytest.mark.asyncio
async def test_gemini_evaluation_uses_native_parse_without_prompt_schema() -> None:
    settings = openrouter_settings().model_copy(
        update={
            "gemini_api_key": "test-gemini-key-not-a-real-secret",
            "gemini_evaluation_model": "gemini-3.5-flash",
        }
    )
    provider = OpenAIEvaluationProvider(settings)
    draft = gemini_evaluable_draft()
    gemini_parse = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=draft))]
        )
    )
    openrouter_create = AsyncMock()
    provider.gemini_client = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=gemini_parse)))
    )
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=openrouter_create))
    )

    result, model = await provider.evaluate(
        question="Why might these people need help?",
        transcript=[
            TranscribedSegment(
                0,
                4_000,
                "The people may need help because both situations look difficult.",
                confidence=0.81,
            )
        ],
        objective_metrics={"word_count": 10},
    )

    assert result.evaluation_status == "evaluated"
    assert model == "gemini-3.5-flash"
    assert gemini_parse.await_count == 2
    openrouter_create.assert_not_awaited()
    for call in gemini_parse.await_args_list:
        request = call.kwargs
        assert request["model"] == "gemini-3.5-flash"
        assert request["response_format"] is GeminiEvaluationDraft
        assert request["reasoning_effort"] == "low"
        assert "extra_body" not in request
        combined_prompt = " ".join(
            str(message.get("content", "")) for message in request["messages"]
        )
        assert "ESQUEMA JSON OBLIGATORIO" not in combined_prompt
    assert "confianza ASR 0.81" in gemini_parse.await_args_list[0].kwargs["messages"][1]["content"]


@pytest.mark.asyncio
async def test_invalid_gemini_json_falls_back_to_openrouter_with_the_same_schema() -> None:
    settings = openrouter_settings().model_copy(
        update={
            "gemini_api_key": "test-gemini-key-not-a-real-secret",
            "gemini_evaluation_model": "gemini-3.5-flash",
        }
    )
    provider = OpenAIEvaluationProvider(settings)
    payload = evaluable_payload()
    valid_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload.model_dump_json()))]
    )
    gemini_parse = AsyncMock(side_effect=ValueError("Gemini returned unstructured output"))
    openrouter_create = AsyncMock(return_value=valid_response)
    provider.gemini_client = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=gemini_parse)))
    )
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=openrouter_create))
    )

    result, model = await provider.evaluate(
        question="Why might these people need help?",
        transcript=[TranscribedSegment(0, 4_000, "I think they need help with the problem.")],
        objective_metrics={"word_count": 9},
    )

    assert result.evaluation_status == "evaluated"
    assert model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert gemini_parse.await_count == 2
    assert openrouter_create.await_count == 2
    for call in openrouter_create.await_args_list:
        request = call.kwargs
        assert request["response_format"]["type"] == "json_schema"
        assert request["response_format"]["json_schema"]["strict"] is True
        assert request["extra_body"] == {
            "provider": {"require_parameters": True},
            "reasoning": {"effort": "none", "exclude": True},
        }


@pytest.mark.asyncio
async def test_part1_evaluation_uses_the_interview_rubric_and_questions() -> None:
    provider = OpenAIEvaluationProvider(openrouter_settings())
    base_payload = not_evaluable_payload(
        status="insufficient",
        reason_es="No hay suficiente evidencia.",
        confidence=0.1,
        speaking_part=1,
    )
    criterion = base_payload.grammar_vocabulary.model_copy(
        update={
            "summary_es": "Tres respuestas breves pero evaluables.",
            "practice_band": 2.5,
            "confidence": 0.8,
        }
    )
    payload = base_payload.model_copy(
        update={
            "evaluation_status": "evaluated",
            "status_reason_es": "Hay evidencia suficiente.",
            "grammar_vocabulary": criterion,
            "discourse_management": criterion.model_copy(),
            "overall_confidence": 0.8,
        }
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=payload.model_dump_json()))]
        )
    )
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    questions = [
        "How do you spend your evenings?",
        "How do you celebrate special occasions?",
        "How much TV do you watch?",
    ]

    result, _ = await provider.evaluate(
        question=" / ".join(questions),
        questions=questions,
        speaking_part=1,
        transcript=[TranscribedSegment(0, 1_000, "I usually read because it helps me relax.")],
        objective_metrics={"word_count": 8},
    )

    request = create.await_args_list[0].kwargs
    review_request = create.await_args_list[1].kwargs
    assert result.speaking_part == 1
    assert request["response_format"]["json_schema"]["name"] == "b2_part1_evaluation"
    assert "answers_questions" in request["messages"][0]["content"]
    assert "PREGUNTA 3" in request["messages"][1]["content"]
    assert "Speaking Part 1" in review_request["messages"][0]["content"]


@pytest.mark.asyncio
async def test_evaluation_falls_back_only_after_validating_each_model_response() -> None:
    provider = OpenAIEvaluationProvider(openrouter_settings())
    base_payload = not_evaluable_payload(
        status="insufficient",
        reason_es="No hay suficiente evidencia.",
        confidence=0.1,
    )
    criterion = base_payload.grammar_vocabulary.model_copy(
        update={
            "summary_es": "Respuesta evaluable.",
            "practice_band": 2.0,
            "confidence": 0.75,
        }
    )
    payload = base_payload.model_copy(
        update={
            "evaluation_status": "evaluated",
            "status_reason_es": "Hay evidencia suficiente.",
            "grammar_vocabulary": criterion,
            "discourse_management": criterion.model_copy(),
            "overall_confidence": 0.75,
        }
    )
    invalid = SimpleNamespace(
        model="nvidia/nemotron-3-super-120b-a12b:free",
        choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))],
    )
    valid = SimpleNamespace(
        model="free/model-selected-by-router",
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload.model_dump_json()))],
    )
    create = AsyncMock(side_effect=[invalid, valid, invalid, valid])
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    result, model = await provider.evaluate(
        question="Why might these people need help?",
        transcript=[TranscribedSegment(0, 1_000, "I think they need help today.")],
        objective_metrics={"word_count": 6},
    )

    assert result.evaluation_status == "evaluated"
    assert model == "free/model-selected-by-router"
    assert [call.kwargs["model"] for call in create.await_args_list] == [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "tencent/hy3:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "tencent/hy3:free",
    ]


@pytest.mark.asyncio
async def test_evaluation_discards_empty_evidence_without_losing_the_report() -> None:
    provider = OpenAIEvaluationProvider(openrouter_settings())
    base_payload = not_evaluable_payload(
        status="insufficient",
        reason_es="No hay suficiente evidencia.",
        confidence=0.1,
    )
    criterion = base_payload.grammar_vocabulary.model_copy(
        update={
            "summary_es": "Respuesta evaluable.",
            "practice_band": 2.0,
            "confidence": 0.8,
        }
    )
    valid_payload = base_payload.model_copy(
        update={
            "evaluation_status": "evaluated",
            "status_reason_es": "Hay evidencia suficiente para una revisión formativa.",
            "grammar_vocabulary": criterion,
            "discourse_management": criterion.model_copy(),
            "overall_confidence": 0.8,
        }
    )
    malformed = valid_payload.model_dump(mode="json")
    malformed["priority_improvements"] = [
        {
            "category": "priority_improvement",
            "evidence": "",
            "start_ms": 0,
            "end_ms": 1_000,
            "explanation_es": "Falta desarrollar la idea.",
            "suggestion_es": "Añade una razón concreta.",
            "severity": "importante",
            "confidence": 0.8,
        }
    ]
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(malformed)))]
    )
    create = AsyncMock(side_effect=[response, response])
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    result, _ = await provider.evaluate(
        question="Why might these people need help?",
        transcript=[TranscribedSegment(0, 1_000, "I do not know.")],
        objective_metrics={"word_count": 4},
    )

    assert result.evaluation_status == "evaluated"
    assert result.priority_improvements == []
    reviewed_draft = create.await_args_list[1].kwargs["messages"][1]["content"]
    assert '"priority_improvements":[]' in reviewed_draft


@pytest.mark.asyncio
async def test_partner_provider_enforces_short_structured_b2_turn() -> None:
    provider = OpenAIPartnerProvider(openrouter_settings())
    payload = PartnerTurn(
        spoken_text=(
            "I'd prefer the second garden because it looks peaceful, and I could spend time "
            "there with my friends without having to do any gardening work."
        ),
        interaction_move="brief_preference",
        hands_turn_back=True,
        estimated_seconds=10,
        safety_flags=[],
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=payload.model_dump_json()))]
        )
    )
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    result, model = await provider.respond(
        task_question="What are the people enjoying about these gardens?",
        follow_up_question="Which garden would you prefer to spend time in? Why?",
    )

    assert result.hands_turn_back is True
    assert 25 <= len(result.spoken_text.split()) <= 45
    assert model == "tencent/hy3:free"
    request = create.await_args.kwargs
    assert request["response_format"]["type"] == "json_schema"
    assert request["extra_body"] == {
        "provider": {"require_parameters": True},
        "reasoning": {"effort": "none", "exclude": True},
    }
    assert "not an examiner" in request["messages"][0]["content"]


def test_strict_provider_schema_requires_nullable_fields_and_removes_constraints() -> None:
    schema = _strict_provider_schema(EvaluationPayload.model_json_schema())

    assert schema["required"] == list(schema["properties"])
    criterion = schema["$defs"]["CriterionAnalysis"]
    assert criterion["required"] == list(criterion["properties"])
    assert "practice_band" in criterion["required"]

    def assert_supported_subset(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                assert_supported_subset(item)
        elif isinstance(node, dict):
            unsupported = {
                "default",
                "maxLength",
                "maximum",
                "minLength",
                "minimum",
                "pattern",
                "title",
            }
            assert not unsupported.intersection(node)
            for value in node.values():
                assert_supported_subset(value)

    assert_supported_subset(schema)


@pytest.mark.asyncio
async def test_pronunciation_limits_and_filters_observations_to_audio_duration() -> None:
    provider = OpenAIPronunciationProvider(openrouter_settings())
    observation = {
        "feature": "claridad",
        "start_ms": 1_000,
        "end_ms": 2_000,
        "explanation_es": "La palabra se entiende.",
        "suggestion_es": "Mantén la claridad.",
        "confidence": 0.7,
    }
    observations = [dict(observation) for _ in range(5)]
    observations[3] = {**observation, "start_ms": 70_000, "end_ms": 71_000}
    payload = {
        "available": True,
        "withheld_reason_es": None,
        "confidence": 0.7,
        "experimental_practice_band": 3.0,
        "pronunciation_summary_es": "Pronunciación comprensible.",
        "pronunciation_observations": observations,
        "fluency_note_es": "La fluidez se analiza por separado.",
        "pause_note_es": "Las pausas se miden por separado.",
        "technical_quality_note_es": "La señal es suficiente.",
    }
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )
    )
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    result, _ = await provider.analyse(
        wav_content=b"RIFF-test",
        objective_metrics={"recorded_duration_ms": 60_000},
    )

    assert len(result.pronunciation_observations) == 3
    request = create.await_args.kwargs
    schema = request["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["pronunciation_observations"]["maxItems"] == 4
