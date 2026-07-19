from __future__ import annotations

import re
import unicodedata

from app.evaluation_schemas import (
    EvaluationPayload,
    TaskCheckKey,
    TaskPerformanceCheck,
)

_OPTION_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "for",
    "from",
    "in",
    "more",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def _normalise_words(value: str) -> list[str]:
    ascii_value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    return re.findall(r"[a-z0-9]+", ascii_value)


def _option_token(value: str) -> str:
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith("ing") and len(value) > 6:
        return value[:-3]
    if value.endswith("s") and not value.endswith("ss") and len(value) > 4:
        return value[:-1]
    return value


def _option_is_mentioned(prompt: str, utterances: list[str]) -> bool:
    prompt_words = _normalise_words(prompt)
    if not prompt_words:
        return False
    normalised_prompt = " ".join(prompt_words)
    prompt_terms = {_option_token(word) for word in prompt_words if word not in _OPTION_STOP_WORDS}
    if not prompt_terms:
        return False

    for utterance in utterances:
        utterance_words = _normalise_words(utterance)
        if normalised_prompt in " ".join(utterance_words):
            return True
        utterance_terms = {_option_token(word) for word in utterance_words}
        overlap = len(prompt_terms & utterance_terms)
        required = max(2, (len(prompt_terms) + 1) // 2)
        if len(prompt_terms) >= 2 and overlap >= required:
            return True
    return False


def detect_part3_option_coverage(metrics: dict[str, object]) -> dict[str, list[str]]:
    """Return only high-confidence task-option mentions from calibrated speaker turns.

    The detector is deliberately conservative. It can confirm explicit or near-explicit
    mentions but never treats a missing lexical match as proof that an option was ignored;
    the language model remains responsible for paraphrases that are not confidently matched.
    """

    prompts = [str(item).strip() for item in metrics.get("task_prompts", []) if str(item).strip()]
    context = metrics.get("conversation_context", [])
    if not isinstance(context, list):
        context = []
    candidate = str(metrics.get("evaluation_candidate", "")).strip()
    conversation_utterances = [
        str(item.get("text", ""))
        for item in context
        if isinstance(item, dict) and str(item.get("text", "")).strip()
    ]
    candidate_utterances = [
        str(item.get("text", ""))
        for item in context
        if isinstance(item, dict)
        and str(item.get("speaker", "")).strip() == candidate
        and str(item.get("text", "")).strip()
    ]
    return {
        "candidate": [
            prompt for prompt in prompts if _option_is_mentioned(prompt, candidate_utterances)
        ],
        "conversation": [
            prompt for prompt in prompts if _option_is_mentioned(prompt, conversation_utterances)
        ],
    }


def _objective_check(
    key: TaskCheckKey,
    status: str,
    explanation: str,
    confidence: float,
) -> TaskPerformanceCheck:
    return TaskPerformanceCheck(
        key=key,
        status=status,
        evidence_source="objective_metrics",
        evidence="",
        start_ms=None,
        end_ms=None,
        explanation_es=explanation,
        confidence=confidence,
    )


def apply_objective_task_checks(
    evaluation: EvaluationPayload, metrics: dict[str, object]
) -> EvaluationPayload:
    if evaluation.evaluation_status != "evaluated":
        checks = [
            check.model_copy(
                update={
                    "status": "no_evaluable",
                    "evidence_source": "none",
                    "evidence": "",
                    "start_ms": None,
                    "end_ms": None,
                    "explanation_es": evaluation.status_reason_es,
                    "confidence": min(evaluation.overall_confidence, 0.25),
                }
            )
            for check in evaluation.task_performance
        ]
        return evaluation.model_copy(update={"task_performance": checks})

    duration = int(metrics["recorded_duration_ms"])
    speech = int(metrics["detected_speech_duration_ms"])
    silence = int(metrics["silence_duration_ms"])
    if evaluation.speaking_part == 1:
        replacements = {
            TaskCheckKey.RESPONSE_LENGTH_APPROPRIATE: _objective_check(
                TaskCheckKey.RESPONSE_LENGTH_APPROPRIATE,
                "logrado" if speech >= 32_000 else "parcial" if speech >= 18_000 else "no_logrado",
                (
                    f"En las tres respuestas se detectaron {speech / 1000:.1f} segundos "
                    f"de habla dentro de {duration / 1000:.1f} segundos grabados."
                ),
                0.96,
            ),
            TaskCheckKey.EXCESSIVE_SILENCE: _objective_check(
                TaskCheckKey.EXCESSIVE_SILENCE,
                "no_logrado" if silence > 30_000 else "logrado",
                f"Se detectaron aproximadamente {silence / 1000:.1f} segundos de silencio.",
                0.9,
            ),
        }
        return evaluation.model_copy(
            update={
                "task_performance": [
                    replacements.get(check.key, check) for check in evaluation.task_performance
                ]
            }
        )

    if evaluation.speaking_part == 3:
        student_talk = int(metrics.get("candidate_talk_ms", 0))
        partner_talk = int(metrics.get("partner_talk_ms", 0))
        total_talk = max(1, student_talk + partner_talk)
        share = student_talk / total_talk
        turn_count = int(metrics.get("candidate_turn_count", 0))
        balanced = 0.3 <= share <= 0.7 and turn_count >= 3
        coverage = detect_part3_option_coverage(metrics)
        candidate_options = coverage["candidate"]
        conversation_options = coverage["conversation"]
        replacements = {
            TaskCheckKey.BALANCES_PARTICIPATION: _objective_check(
                TaskCheckKey.BALANCES_PARTICIPATION,
                "logrado" if balanced else "parcial" if turn_count >= 2 else "no_logrado",
                (
                    f"El candidato realizo {turn_count} turnos y ocupo aproximadamente "
                    f"el {share * 100:.0f}% del habla atribuida a los dos candidatos."
                ),
                0.9,
            ),
            TaskCheckKey.EXCESSIVE_SILENCE: _objective_check(
                TaskCheckKey.EXCESSIVE_SILENCE,
                "logrado" if student_talk >= 25_000 and turn_count >= 3 else "no_logrado",
                (
                    f"La diarizacion atribuyo {student_talk / 1000:.1f} segundos de habla "
                    f"repartidos en {turn_count} turnos."
                ),
                0.88,
            ),
        }
        if len(candidate_options) >= 2:
            replacements[TaskCheckKey.COVERS_OPTIONS] = _objective_check(
                TaskCheckKey.COVERS_OPTIONS,
                "logrado",
                (
                    "Se detectaron referencias claras del candidato a varias opciones: "
                    + ", ".join(candidate_options)
                    + ". No es necesario mencionar las cinco para explorar varias con sentido."
                ),
                0.96,
            )
            replacements[TaskCheckKey.RELEVANT] = _objective_check(
                TaskCheckKey.RELEVANT,
                "logrado",
                (
                    "Las intervenciones del candidato contienen referencias claras a opciones "
                    "de la tarea: " + ", ".join(candidate_options) + "."
                ),
                0.94,
            )
        elif len(candidate_options) == 1 and len(conversation_options) >= 2:
            replacements[TaskCheckKey.COVERS_OPTIONS] = _objective_check(
                TaskCheckKey.COVERS_OPTIONS,
                "parcial",
                (
                    f"El candidato menciono claramente {candidate_options[0]}; en la "
                    f"conversacion se detectaron {len(conversation_options)} opciones distintas."
                ),
                0.88,
            )
        return evaluation.model_copy(
            update={
                "task_performance": [
                    replacements.get(check.key, check) for check in evaluation.task_performance
                ]
            }
        )

    both = bool(metrics["both_photographs_mentioned"])
    checks_by_key = {check.key: check for check in evaluation.task_performance}
    answers_question = checks_by_key[TaskCheckKey.ANSWERS_QUESTION]
    replacements = {
        TaskCheckKey.DISCUSSES_BOTH: _objective_check(
            TaskCheckKey.DISCUSSES_BOTH,
            "logrado" if both else "no_logrado",
            "La comprobación léxica de la tarea detecta referencias a ambas fotografías."
            if both
            else "La comprobación léxica no detecta referencias claras a las dos fotografías.",
            0.82,
        ),
        TaskCheckKey.USES_MINUTE: _objective_check(
            TaskCheckKey.USES_MINUTE,
            "logrado" if duration >= 55_000 and speech >= 35_000 else "parcial",
            f"Se registraron {duration / 1000:.1f} segundos, con {speech / 1000:.1f} segundos de habla detectada.",
            0.98,
        ),
        TaskCheckKey.FINISHES_EARLY: _objective_check(
            TaskCheckKey.FINISHES_EARLY,
            "no_logrado" if speech < 25_000 else "logrado",
            "La duración de habla detectada indica que la respuesta termina extremadamente pronto."
            if speech < 25_000
            else "La respuesta no termina extremadamente pronto.",
            0.97,
        ),
        TaskCheckKey.EXCESSIVE_SILENCE: _objective_check(
            TaskCheckKey.EXCESSIVE_SILENCE,
            "no_logrado" if silence > 24_000 else "logrado",
            f"Se detectaron aproximadamente {silence / 1000:.1f} segundos de silencio.",
            0.9,
        ),
    }
    if both and answers_question.status in {"logrado", "parcial"}:
        replacements[TaskCheckKey.RELEVANT] = _objective_check(
            TaskCheckKey.RELEVANT,
            "logrado" if answers_question.status == "logrado" else "parcial",
            "La respuesta contiene referencias verificadas a ambas fotografías y aborda la pregunta de la tarea.",
            min(answers_question.confidence, 0.9),
        )
    checks = [replacements.get(check.key, check) for check in evaluation.task_performance]
    return evaluation.model_copy(update={"task_performance": checks})


def withheld_pronunciation(reason: str, metrics: dict[str, object]) -> dict[str, object]:
    quality = metrics.get("audio_quality", {})
    return {
        "available": False,
        "withheld_reason_es": reason,
        "confidence": 0.0,
        "experimental_practice_band": None,
        "pronunciation_summary_es": "Análisis retirado por falta de confianza.",
        "pronunciation_observations": [],
        "fluency_note_es": "La fluidez no se ha utilizado como sustituto de la pronunciación.",
        "pause_note_es": "Las pausas permanecen en las métricas objetivas y no se han tratado como errores de pronunciación.",
        "technical_quality_note_es": "Calidad técnica: " + str(quality),
    }
