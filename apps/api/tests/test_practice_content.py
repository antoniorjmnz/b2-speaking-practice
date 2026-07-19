from __future__ import annotations

from pathlib import Path

from app.sample_data import PART_3_TASKS

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PART_3_AUDIO_ROOT = PROJECT_ROOT / "apps" / "web" / "public" / "assets" / "temporary-part3"


def test_backend_part3_tasks_have_exactly_five_unique_prompts() -> None:
    assert len(PART_3_TASKS) == 4

    for task in PART_3_TASKS:
        prompts = [str(prompt).strip().casefold() for prompt in task["questions"]]
        assert len(prompts) == 5, task["id"]
        assert all(prompts), task["id"]
        assert len(set(prompts)) == 5, task["id"]
        assert str(task["question"]).strip()
        assert str(task["decision_question"]).strip()


def test_backend_part3_tasks_reference_complete_nonempty_audio_sequences() -> None:
    for ordinal, task in zip(range(5, 9), PART_3_TASKS, strict=True):
        expected_intro = f"/assets/temporary-part3/examiner-p3-{ordinal:03d}-intro-sonia.mp3"
        assert task["examiner_audio_path"] == expected_intro

        for phase in ("intro", "decision"):
            asset = PART_3_AUDIO_ROOT / f"examiner-p3-{ordinal:03d}-{phase}-sonia.mp3"
            assert asset.is_file(), asset
            assert asset.stat().st_size > 1_000, asset

    closing = PART_3_AUDIO_ROOT / "examiner-closing-sonia.mp3"
    assert closing.is_file()
    assert closing.stat().st_size > 1_000
