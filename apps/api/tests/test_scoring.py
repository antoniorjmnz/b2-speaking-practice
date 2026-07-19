from __future__ import annotations

import re

from app.scoring import compute_practice_score


def test_part2_score_uses_core_criteria_mean() -> None:
    score = compute_practice_score(
        speaking_part=2,
        evaluation_status="evaluated",
        overall_confidence=0.9,
        criterion_bands={"grammar_vocabulary": 3.5, "discourse_management": 3.0},
    )
    assert score is not None
    assert score.global_band == 3.2
    assert score.counted_criteria == ["grammar_vocabulary", "discourse_management"]


def test_high_bands_reach_top_internal_tier_without_claiming_a_cefr_level() -> None:
    score = compute_practice_score(
        speaking_part=2,
        evaluation_status="evaluated",
        overall_confidence=0.8,
        criterion_bands={"grammar_vocabulary": 4.5, "discourse_management": 4.5},
    )
    assert score is not None
    assert score.tier_index == score.tier_count - 1
    student_facing_tier = f"{score.tier_label} {score.tier_caption_es}"
    assert re.search(r"\bB2\b|por encima(?: de B2)?|nivel B2", student_facing_tier, re.I) is None
    assert score.tier_key not in {"solido_b2", "por_encima"}


def test_no_practice_tier_makes_an_unvalidated_cefr_attainment_claim() -> None:
    for band in (0.0, 2.0, 3.25, 4.25, 5.0):
        score = compute_practice_score(
            speaking_part=2,
            evaluation_status="evaluated",
            overall_confidence=0.9,
            criterion_bands={
                "grammar_vocabulary": band,
                "discourse_management": band,
            },
        )
        assert score is not None
        student_facing_tier = f"{score.tier_label} {score.tier_caption_es}"
        assert (
            re.search(r"\bB2\b|por encima(?: de B2)?|nivel B2|equivale", student_facing_tier, re.I)
            is None
        )
        assert "no es una calificación oficial" in score.disclaimer_es.casefold()


def test_insufficient_status_has_no_score() -> None:
    assert (
        compute_practice_score(
            speaking_part=2,
            evaluation_status="insufficient",
            overall_confidence=0.9,
            criterion_bands={"grammar_vocabulary": 3.0, "discourse_management": 3.0},
        )
        is None
    )


def test_low_confidence_has_no_score() -> None:
    assert (
        compute_practice_score(
            speaking_part=2,
            evaluation_status="evaluated",
            overall_confidence=0.2,
            criterion_bands={"grammar_vocabulary": 3.0, "discourse_management": 3.0},
        )
        is None
    )


def test_missing_core_band_has_no_score() -> None:
    assert (
        compute_practice_score(
            speaking_part=2,
            evaluation_status="evaluated",
            overall_confidence=0.9,
            criterion_bands={"grammar_vocabulary": None, "discourse_management": 3.0},
        )
        is None
    )


def test_part3_includes_interactive_communication() -> None:
    score = compute_practice_score(
        speaking_part=3,
        evaluation_status="evaluated",
        overall_confidence=0.8,
        criterion_bands={
            "grammar_vocabulary": 4.0,
            "discourse_management": 4.0,
            "interactive_communication": 4.0,
        },
    )
    assert score is not None
    assert "interactive_communication" in score.counted_criteria
    assert score.global_band == 4.0
