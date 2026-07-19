from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ObservationCategory(StrEnum):
    GRAMMAR_VOCABULARY = "grammar_vocabulary"
    DISCOURSE_MANAGEMENT = "discourse_management"
    INTERACTIVE_COMMUNICATION = "interactive_communication"
    TASK_PERFORMANCE = "task_performance"
    STRENGTH = "strength"
    PRIORITY_IMPROVEMENT = "priority_improvement"


class Observation(StrictModel):
    category: ObservationCategory
    evidence: str = Field(min_length=1, max_length=500)
    start_ms: int = Field(ge=0, le=210_000)
    end_ms: int = Field(ge=0, le=210_000)
    explanation_es: str = Field(min_length=1, max_length=1_200)
    suggestion_es: str = Field(min_length=1, max_length=1_200)
    severity: Literal["leve", "importante"]
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_time_range(self) -> Observation:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must not precede start_ms")
        return self


class CriterionAnalysis(StrictModel):
    summary_es: str = Field(min_length=1, max_length=1_500)
    practice_band: float | None = Field(default=None, ge=0, le=5)
    confidence: float = Field(ge=0, le=1)
    observations: list[Observation] = Field(max_length=12)


class TaskCheckKey(StrEnum):
    ANSWERS_QUESTIONS = "answers_questions"
    DEVELOPS_ANSWERS = "develops_answers"
    GIVES_REASONS_EXAMPLES = "gives_reasons_examples"
    RESPONSE_LENGTH_APPROPRIATE = "response_length_appropriate"
    COMPARES_PHOTOS = "compares_photos"
    DISCUSSES_BOTH = "discusses_both"
    ANSWERS_QUESTION = "answers_question"
    SIMILARITIES_DIFFERENCES = "similarities_differences"
    SPECULATES = "speculates"
    JUSTIFIES_OPINIONS = "justifies_opinions"
    RELEVANT = "relevant"
    DEVELOPS_IDEAS = "develops_ideas"
    USES_MINUTE = "uses_minute"
    FINISHES_EARLY = "finishes_early"
    EXCESSIVE_SILENCE = "excessive_silence"
    RESPONDS_TO_PARTNER = "responds_to_partner"
    LINKS_CONTRIBUTIONS = "links_contributions"
    INVITES_PARTNER = "invites_partner"
    NEGOTIATES = "negotiates"
    MOVES_TOWARDS_DECISION = "moves_towards_decision"
    COVERS_OPTIONS = "covers_options"
    BALANCES_PARTICIPATION = "balances_participation"


PART_1_TASK_CHECK_KEYS = (
    TaskCheckKey.ANSWERS_QUESTIONS,
    TaskCheckKey.DEVELOPS_ANSWERS,
    TaskCheckKey.GIVES_REASONS_EXAMPLES,
    TaskCheckKey.RESPONSE_LENGTH_APPROPRIATE,
    TaskCheckKey.RELEVANT,
    TaskCheckKey.EXCESSIVE_SILENCE,
)

PART_2_TASK_CHECK_KEYS = (
    TaskCheckKey.COMPARES_PHOTOS,
    TaskCheckKey.DISCUSSES_BOTH,
    TaskCheckKey.ANSWERS_QUESTION,
    TaskCheckKey.SIMILARITIES_DIFFERENCES,
    TaskCheckKey.SPECULATES,
    TaskCheckKey.JUSTIFIES_OPINIONS,
    TaskCheckKey.RELEVANT,
    TaskCheckKey.DEVELOPS_IDEAS,
    TaskCheckKey.USES_MINUTE,
    TaskCheckKey.FINISHES_EARLY,
    TaskCheckKey.EXCESSIVE_SILENCE,
)

PART_3_TASK_CHECK_KEYS = (
    TaskCheckKey.RESPONDS_TO_PARTNER,
    TaskCheckKey.LINKS_CONTRIBUTIONS,
    TaskCheckKey.INVITES_PARTNER,
    TaskCheckKey.NEGOTIATES,
    TaskCheckKey.MOVES_TOWARDS_DECISION,
    TaskCheckKey.COVERS_OPTIONS,
    TaskCheckKey.JUSTIFIES_OPINIONS,
    TaskCheckKey.BALANCES_PARTICIPATION,
    TaskCheckKey.RELEVANT,
    TaskCheckKey.EXCESSIVE_SILENCE,
)


def task_check_keys_for_part(speaking_part: int) -> tuple[TaskCheckKey, ...]:
    if speaking_part == 1:
        return PART_1_TASK_CHECK_KEYS
    if speaking_part == 3:
        return PART_3_TASK_CHECK_KEYS
    return PART_2_TASK_CHECK_KEYS


class TaskPerformanceCheck(StrictModel):
    key: TaskCheckKey
    status: Literal["logrado", "parcial", "no_logrado", "no_evaluable"]
    evidence_source: Literal["transcript", "objective_metrics", "none"]
    evidence: str = Field(max_length=500)
    start_ms: int | None = Field(default=None, ge=0, le=210_000)
    end_ms: int | None = Field(default=None, ge=0, le=210_000)
    explanation_es: str = Field(min_length=1, max_length=1_200)
    confidence: float = Field(ge=0, le=1)


class EvaluationPayload(StrictModel):
    speaking_part: Literal[1, 2, 3] = 2
    evaluation_status: Literal["evaluated", "insufficient", "demo"] = "evaluated"
    status_reason_es: str = Field(
        default="La respuesta contiene evidencia suficiente para una evaluación formativa.",
        min_length=1,
        max_length=1_200,
    )
    strengths: list[Observation] = Field(max_length=5)
    priority_improvements: list[Observation] = Field(max_length=4)
    grammar_vocabulary: CriterionAnalysis
    discourse_management: CriterionAnalysis
    interactive_communication: CriterionAnalysis | None = None
    task_performance: list[TaskPerformanceCheck] = Field(min_length=6, max_length=11)
    suggested_exercises: list[str] = Field(max_length=5)
    overall_confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def require_all_task_checks(self) -> EvaluationPayload:
        keys = [check.key for check in self.task_performance]
        expected = set(task_check_keys_for_part(self.speaking_part))
        if len(set(keys)) != len(keys) or set(keys) != expected:
            raise ValueError(
                "task_performance must contain every check for the speaking part exactly once"
            )
        if self.evaluation_status != "evaluated":
            if self.strengths or self.priority_improvements:
                raise ValueError("non-evaluated payloads cannot contain observations")
            if (
                self.grammar_vocabulary.practice_band is not None
                or self.discourse_management.practice_band is not None
                or (
                    self.interactive_communication is not None
                    and self.interactive_communication.practice_band is not None
                )
            ):
                raise ValueError("non-evaluated payloads cannot contain practice bands")
            if self.overall_confidence > 0.25:
                raise ValueError("non-evaluated payloads must have low confidence")
            if any(check.status != "no_evaluable" for check in self.task_performance):
                raise ValueError("non-evaluated payloads must mark every task check no_evaluable")
        if self.speaking_part == 3 and self.evaluation_status == "evaluated":
            if self.interactive_communication is None:
                raise ValueError("Part 3 requires Interactive Communication analysis")
        return self


class PronunciationObservation(StrictModel):
    feature: Literal["sonidos", "acentuacion", "claridad", "entonacion"]
    start_ms: int = Field(ge=0, le=210_000)
    end_ms: int = Field(ge=0, le=210_000)
    explanation_es: str = Field(min_length=1, max_length=1_200)
    suggestion_es: str = Field(min_length=1, max_length=1_200)
    confidence: float = Field(ge=0, le=1)


class PronunciationResult(StrictModel):
    available: bool
    withheld_reason_es: str | None = None
    confidence: float = Field(ge=0, le=1)
    experimental_practice_band: float | None = Field(default=None, ge=0, le=5)
    pronunciation_summary_es: str
    pronunciation_observations: list[PronunciationObservation] = Field(max_length=4)
    fluency_note_es: str
    pause_note_es: str
    technical_quality_note_es: str
