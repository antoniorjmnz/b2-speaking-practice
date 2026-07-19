from __future__ import annotations

import re

from app.evaluation_schemas import EvaluationPayload, Observation, TaskPerformanceCheck
from app.providers.base import TranscribedSegment

SPACE_PATTERN = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return SPACE_PATTERN.sub(" ", value).strip().casefold()


def locate_evidence(evidence: str, segments: list[TranscribedSegment]) -> tuple[int, int] | None:
    needle = normalize_text(evidence)
    if not needle:
        return None
    normalized_segments = [normalize_text(segment.text) for segment in segments]
    for segment, haystack in zip(segments, normalized_segments, strict=True):
        if needle in haystack:
            return segment.start_ms, segment.end_ms

    joined = " ".join(normalized_segments)
    start_index = joined.find(needle)
    if start_index < 0:
        return None
    end_index = start_index + len(needle)
    cursor = 0
    first: TranscribedSegment | None = None
    last: TranscribedSegment | None = None
    for segment, text in zip(segments, normalized_segments, strict=True):
        segment_start = cursor
        segment_end = cursor + len(text)
        if segment_end >= start_index and segment_start <= end_index:
            first = first or segment
            last = segment
        cursor = segment_end + 1
    if first and last:
        return first.start_ms, last.end_ms
    return None


def verify_observation(
    observation: Observation, segments: list[TranscribedSegment]
) -> Observation | None:
    location = locate_evidence(observation.evidence, segments)
    if location is None:
        return None
    return observation.model_copy(update={"start_ms": location[0], "end_ms": location[1]})


def verify_evaluation_evidence(
    evaluation: EvaluationPayload, segments: list[TranscribedSegment]
) -> tuple[EvaluationPayload, int]:
    rejected = 0

    def verified(items: list[Observation]) -> list[Observation]:
        nonlocal rejected
        result: list[Observation] = []
        for item in items:
            accepted = verify_observation(item, segments)
            if accepted is None:
                rejected += 1
            else:
                result.append(accepted)
        return result

    grammar = evaluation.grammar_vocabulary.model_copy(
        update={"observations": verified(evaluation.grammar_vocabulary.observations)}
    )
    discourse = evaluation.discourse_management.model_copy(
        update={"observations": verified(evaluation.discourse_management.observations)}
    )
    interactive = (
        evaluation.interactive_communication.model_copy(
            update={"observations": verified(evaluation.interactive_communication.observations)}
        )
        if evaluation.interactive_communication is not None
        else None
    )
    task_checks: list[TaskPerformanceCheck] = []
    for check in evaluation.task_performance:
        if check.evidence_source != "transcript":
            task_checks.append(check)
            continue
        location = locate_evidence(check.evidence, segments)
        if location is None:
            rejected += 1
            task_checks.append(
                check.model_copy(
                    update={
                        "status": "no_evaluable",
                        "evidence_source": "none",
                        "evidence": "",
                        "start_ms": None,
                        "end_ms": None,
                        "explanation_es": "No se pudo verificar la evidencia de esta observación.",
                        "confidence": 0.0,
                    }
                )
            )
        else:
            task_checks.append(
                check.model_copy(update={"start_ms": location[0], "end_ms": location[1]})
            )

    cleaned = evaluation.model_copy(
        update={
            "strengths": verified(evaluation.strengths),
            "priority_improvements": verified(evaluation.priority_improvements),
            "grammar_vocabulary": grammar,
            "discourse_management": discourse,
            "interactive_communication": interactive,
            "task_performance": task_checks,
        }
    )
    return cleaned, rejected
