"""Formative practice score.

Turns the internal 0-5 analytical bands into a student-facing "practice score":
a qualitative tier label (the headline) backed by the per-criterion bands. This
is deliberately orientative and NOT a Cambridge English Scale result.

Design decisions:
- The score is only produced for fully ``evaluated`` responses with enough
  confidence. Weak or ``insufficient`` analyses never show a shiny number.
- Pronunciation is experimental and is intentionally excluded from the global
  band until its reliability improves.
- Part 2 counts Grammar & Vocabulary + Discourse Management. Part 3 also counts
  Interactive Communication when present.
"""

from __future__ import annotations

from dataclasses import dataclass

# Minimum overall confidence required before we surface a numeric score.
MIN_SCORE_CONFIDENCE = 0.45

# Criteria that count towards the global band, per speaking part.
COUNTED_CRITERIA: dict[int, tuple[str, ...]] = {
    1: ("grammar_vocabulary", "discourse_management"),
    2: ("grammar_vocabulary", "discourse_management"),
    3: ("grammar_vocabulary", "discourse_management", "interactive_communication"),
}

# Qualitative tiers, from lowest to highest. Thresholds are the lower bound
# (inclusive) of the global band for that tier.
_TIERS: tuple[tuple[float, str, str, str], ...] = (
    (0.0, "evidencia_limitada", "Evidencia limitada", "muestra todavía limitada"),
    (2.0, "base_en_desarrollo", "Base en desarrollo", "uso todavía irregular"),
    (3.25, "desempeno_consistente", "Desempeño consistente", "evidencia consistente"),
    (
        4.25,
        "desempeno_muy_consistente",
        "Desempeño muy consistente",
        "evidencia interna muy consistente",
    ),
)

TIER_COUNT = len(_TIERS)

SCORE_DISCLAIMER_ES = (
    "Puntuación orientativa y formativa basada en bandas internas de práctica. "
    "No determina tu nivel ni equivale a un aprobado o suspenso. "
    "No es una calificación oficial de Cambridge English."
)


@dataclass(frozen=True)
class PracticeScore:
    global_band: float
    tier_key: str
    tier_label: str
    tier_caption_es: str
    tier_index: int
    tier_count: int
    counted_criteria: list[str]
    confidence: float
    disclaimer_es: str


def _tier_for_band(global_band: float) -> tuple[int, str, str, str]:
    index = 0
    for position, tier in enumerate(_TIERS):
        if global_band >= tier[0]:
            index = position
    _threshold, key, label, caption = _TIERS[index]
    return index, key, label, caption


def compute_practice_score(
    *,
    speaking_part: int,
    evaluation_status: str,
    overall_confidence: float,
    criterion_bands: dict[str, float | None],
    min_confidence: float = MIN_SCORE_CONFIDENCE,
) -> PracticeScore | None:
    """Return a formative score, or ``None`` when a score should not be shown."""
    if evaluation_status != "evaluated":
        return None
    if overall_confidence < min_confidence:
        return None

    counted_keys = COUNTED_CRITERIA.get(speaking_part, COUNTED_CRITERIA[2])
    bands = [
        (key, criterion_bands.get(key))
        for key in counted_keys
        if criterion_bands.get(key) is not None
    ]
    # Require the two core criteria before publishing a global band.
    if not all(criterion_bands.get(key) is not None for key in counted_keys[:2]):
        return None
    if not bands:
        return None

    values = [float(value) for _, value in bands]
    global_band = round(sum(values) / len(values), 1)
    index, key, label, caption = _tier_for_band(global_band)
    return PracticeScore(
        global_band=global_band,
        tier_key=key,
        tier_label=label,
        tier_caption_es=caption,
        tier_index=index,
        tier_count=TIER_COUNT,
        counted_criteria=[name for name, _ in bands],
        confidence=round(float(overall_confidence), 2),
        disclaimer_es=SCORE_DISCLAIMER_ES,
    )
