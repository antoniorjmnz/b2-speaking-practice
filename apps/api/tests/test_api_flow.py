from __future__ import annotations

import hashlib
import json
import sqlite3
import time

import pytest
from conftest import create_authorized_session, upload_and_complete, wait_for_report
from fastapi.testclient import TestClient

from app.config import Settings
from app.providers.mock import MockEvaluationProvider, not_evaluable_payload
from app.sample_data import PART_1_TASK_IDS, PART_3_TASK_IDS


@pytest.mark.parametrize(
    ("task_id", "question_fragment"),
    [
        ("99999999-9999-4999-8999-999999999999", "learning in these ways"),
        ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "exercise in these ways"),
        ("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "social occasions"),
        ("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "working in these places"),
    ],
)
def test_curated_academy_tasks_are_published(
    client: TestClient, task_id: str, question_fragment: str
) -> None:
    response = client.get(f"/v1/tasks/{task_id}")

    assert response.status_code == 200
    task = response.json()
    assert question_fragment in task["question"]
    assert task["examiner_audio_path"].endswith("-sonia.mp3")
    assert "/practice-assets/original/academy-part2/" in task["image_one_path"]
    assert "/practice-assets/original/academy-part2/" in task["image_two_path"]
    assert "Tarea original" in task["content_notice"]


def test_complete_demo_slice_never_fabricates_feedback(
    client: TestClient, wav_bytes: bytes
) -> None:
    task = client.get("/v1/tasks/99999999-9999-4999-8999-999999999999")
    assert task.status_code == 200
    assert task.json()["part"] == 2
    assert task.json()["evaluation_available"] is False

    session = create_authorized_session(client)
    grant = upload_and_complete(client, session, wav_bytes)
    report = wait_for_report(client, session)

    assert report["evaluation_status"] == "demo"
    assert report["evaluation_status_reason_es"].startswith("Modo demostración")
    assert report["disclaimer_es"] == (
        "Intento guardado sin evaluación. Este resultado no contiene feedback sobre tu nivel."
    )
    assert report["task_performance"] == []
    assert report["transcript"] == []
    assert report["strengths"] == []
    assert report["priority_improvements"] == []
    assert report["suggested_exercises"] == []
    assert report["overall_confidence"] == 0
    assert "practice_band" not in str(report)
    assert report["pronunciation"]["available"] is False
    assert "experimental_practice_band" not in str(report)
    assert "global_achievement" not in report
    assert "interactive_communication" not in report
    assert report["expires_at"].endswith("Z")
    assert report["audio_playback_url"].startswith("http://testserver/v1/playback/")

    playback = client.get(report["audio_playback_url"])
    assert playback.status_code == 200
    assert playback.content == wav_bytes
    assert playback.headers["cache-control"] == "private, no-store"
    assert grant["storage_path"].startswith(f"sessions/{session['session_id']}/")


def test_part1_task_exposes_three_questions_and_creates_individual_session(
    client: TestClient,
) -> None:
    response = client.get(f"/v1/tasks/{PART_1_TASK_IDS[0]}")

    assert response.status_code == 200
    task = response.json()
    assert task["part"] == 1
    assert len(task["questions"]) == 3
    assert task["image_one_path"] == ""
    assert task["examiner_audio_path"].endswith("examiner-intro-sonia.mp3")

    session = client.post(
        "/v1/practice-sessions",
        json={
            "task_id": PART_1_TASK_IDS[0],
            "recording_consent": True,
            "consent_policy_version": "test-v1",
        },
    )
    assert session.status_code == 201


def test_part3_pair_task_requires_two_voice_references_before_main_recording(
    client: TestClient, wav_bytes: bytes
) -> None:
    task_response = client.get(f"/v1/tasks/{PART_3_TASK_IDS[0]}")
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["part"] == 3
    assert len(task["questions"]) == 5
    assert task["decision_question"]
    assert task["diarization_available"] is False

    session = client.post(
        "/v1/practice-sessions",
        json={
            "task_id": PART_3_TASK_IDS[0],
            "recording_consent": True,
            "consent_policy_version": "test-v1",
        },
    ).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}

    def upload_kind(kind: str, duration_ms: int) -> dict[str, object]:
        grant_response = client.post(
            f"/v1/practice-sessions/{session['session_id']}/upload-url",
            headers=headers,
            json={
                "mime_type": "audio/wav",
                "extension": "wav",
                "recording_kind": kind,
            },
        )
        assert grant_response.status_code == 200
        grant = grant_response.json()
        assert (
            client.put(
                f"/v1/uploads/{grant['recording_id']}",
                headers={
                    "X-Upload-Token": grant["upload_token"],
                    "Content-Type": "audio/wav",
                },
                content=wav_bytes,
            ).status_code
            == 204
        )
        completion = client.post(
            f"/v1/practice-sessions/{session['session_id']}/recording-complete",
            headers=headers,
            json={
                "recording_id": grant["recording_id"],
                "mime_type": "audio/wav",
                "size_bytes": len(wav_bytes),
                "duration_ms": duration_ms,
                "sha256": hashlib.sha256(wav_bytes).hexdigest(),
                "response_started_at": "2026-07-17T10:00:00Z",
                "response_ended_at": "2026-07-17T10:03:00Z",
            },
        )
        assert completion.status_code == 202
        return completion.json()

    first = upload_kind("candidate_a_reference", 8_000)
    second = upload_kind("candidate_b_reference", 8_000)
    assert first["processing_stage"] == "voice_calibration"
    assert second["processing_stage"] == "voice_calibration"

    events = client.post(
        f"/v1/practice-sessions/{session['session_id']}/part3-events",
        headers=headers,
        json={
            "events": [
                {
                    "sequence": 0,
                    "phase": "discussion",
                    "speaker": "examiner",
                    "started_at_ms": 0,
                    "ended_at_ms": 0,
                    "text": "Start the discussion.",
                }
            ]
        },
    )
    assert events.status_code == 200

    queued = upload_kind("pair_response", 180_000)
    assert queued["processing_stage"] == "queued"


def test_part3_rejects_a_standard_single_candidate_recording_kind(
    client: TestClient,
) -> None:
    session = client.post(
        "/v1/practice-sessions",
        json={
            "task_id": PART_3_TASK_IDS[0],
            "recording_consent": True,
            "consent_policy_version": "test-v1",
        },
    ).json()
    response = client.post(
        f"/v1/practice-sessions/{session['session_id']}/upload-url",
        headers={"Authorization": f"Bearer {session['session_token']}"},
        json={
            "mime_type": "audio/wav",
            "extension": "wav",
            "recording_kind": "candidate_response",
        },
    )
    assert response.status_code == 422


def test_session_capability_is_required(client: TestClient) -> None:
    session = create_authorized_session(client)
    missing = client.get(f"/v1/practice-sessions/{session['session_id']}")
    wrong = client.get(
        f"/v1/practice-sessions/{session['session_id']}",
        headers={"Authorization": "Bearer definitely-wrong"},
    )
    assert missing.status_code == 401
    assert wrong.status_code == 403


def test_ai_partner_turn_is_scoped_to_session_and_labelled_as_prepared_in_demo(
    client: TestClient,
) -> None:
    session = create_authorized_session(client)
    path = f"/v1/practice-sessions/{session['session_id']}/ai-partner-turn"

    assert client.post(path).status_code == 401
    response = client.post(
        path,
        headers={"Authorization": f"Bearer {session['session_token']}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "prepared"
    assert payload["follow_up_question"].startswith("Which way of learning")
    assert 4 <= payload["estimated_seconds"] <= 15
    assert "no ha sido generada por IA en vivo" in payload["disclaimer_es"]
    assert "evaluation" not in str(payload).lower()


def test_invalid_audio_is_rejected(client: TestClient) -> None:
    session = create_authorized_session(client)
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    grant = client.post(
        f"/v1/practice-sessions/{session['session_id']}/upload-url",
        headers=headers,
        json={"mime_type": "audio/wav", "extension": "wav"},
    ).json()
    response = client.put(
        f"/v1/uploads/{grant['recording_id']}",
        headers={"X-Upload-Token": grant["upload_token"], "Content-Type": "audio/wav"},
        content=b"not audio at all",
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid audio content"}


def test_teacher_view_contains_internal_pronunciation_band_data(
    client: TestClient, wav_bytes: bytes
) -> None:
    session = create_authorized_session(client)
    upload_and_complete(client, session, wav_bytes)
    wait_for_report(client, session)
    response = client.get(
        f"/v1/internal/practice-sessions/{session['session_id']}/validation",
        headers={"Authorization": "Bearer teacher-test-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["evaluation"]["evaluation_status"] == "demo"
    assert payload["pronunciation"]["available"] is False
    assert payload["evaluation"]["grammar_vocabulary"]["practice_band"] is None


def test_teacher_view_can_inspect_each_part3_candidate(
    client: TestClient, settings: Settings
) -> None:
    created = client.post(
        "/v1/practice-sessions",
        json={
            "task_id": PART_3_TASK_IDS[0],
            "recording_consent": True,
            "consent_policy_version": "test-v1",
        },
    )
    assert created.status_code == 201
    session_id = created.json()["session_id"]
    transcript = [
        {
            "id": f"{session_id}-A-0",
            "position": 0,
            "start_ms": 1_000,
            "end_ms": 4_000,
            "text": "Flexible working hours could help employees.",
            "confidence": 0.93,
        }
    ]
    evaluation = not_evaluable_payload(
        status="insufficient",
        reason_es="Datos de prueba para validacion docente.",
        speaking_part=3,
    ).model_dump(mode="json")
    database_path = settings.database_url.removeprefix("sqlite+aiosqlite:///")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO part3_candidate_results (
                id, session_id, candidate_label, transcript, evaluation, pronunciation,
                objective_metrics, model_snapshot, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
                session_id,
                "A",
                json.dumps(transcript),
                json.dumps(evaluation),
                None,
                json.dumps({"candidate_option_mentions": ["flexible working hours"]}),
                json.dumps({"diarization": "test", "evaluation": "test"}),
                "2026-07-19 08:00:00",
            ),
        )

    missing_candidate = client.get(
        f"/v1/internal/practice-sessions/{session_id}/validation",
        headers={"Authorization": "Bearer teacher-test-token"},
    )
    response = client.get(
        f"/v1/internal/practice-sessions/{session_id}/validation?candidate_label=A",
        headers={"Authorization": "Bearer teacher-test-token"},
    )

    assert missing_candidate.status_code == 422
    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"][0]["text"].startswith("Flexible working hours")
    assert payload["objective_metrics"]["candidate_option_mentions"] == ["flexible working hours"]


def test_delete_removes_anonymous_session_and_derived_data(
    client: TestClient, wav_bytes: bytes, settings: Settings
) -> None:
    session = create_authorized_session(client)
    upload_and_complete(client, session, wav_bytes)
    wait_for_report(client, session)
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    deleted = client.delete(f"/v1/practice-sessions/{session['session_id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert (
        client.get(f"/v1/practice-sessions/{session['session_id']}", headers=headers).status_code
        == 404
    )
    database_path = settings.database_url.removeprefix("sqlite+aiosqlite:///")
    with sqlite3.connect(database_path) as connection:
        for table in (
            "recordings",
            "processing_jobs",
            "transcript_segments",
            "evaluations",
            "teacher_reviews",
        ):
            count = connection.execute(
                f"SELECT count(*) FROM {table} WHERE session_id = ?",  # noqa: S608
                (session["session_id"],),
            ).fetchone()[0]
            assert count == 0, table


def test_delete_keeps_reference_when_storage_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = create_authorized_session(client)
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    grant = client.post(
        f"/v1/practice-sessions/{session['session_id']}/upload-url",
        headers=headers,
        json={"mime_type": "audio/wav", "extension": "wav"},
    )
    assert grant.status_code == 200

    async def fail_delete(storage_path: str) -> None:
        raise RuntimeError(f"simulated storage outage for {storage_path}")

    monkeypatch.setattr(client.app.state.storage, "delete", fail_delete)
    # TestClient is intentionally configured to re-raise server exceptions.
    # Production ASGI clients receive the generic 500 response from the app handler.
    with pytest.raises(RuntimeError, match="simulated storage outage"):
        client.delete(f"/v1/practice-sessions/{session['session_id']}", headers=headers)

    # The capability still resolves because the recording reference was not
    # discarded. A later deletion attempt can therefore retry Storage.
    still_present = client.get(f"/v1/practice-sessions/{session['session_id']}", headers=headers)
    assert still_present.status_code == 200


def test_duplicate_recording_confirmation_is_idempotent(
    client: TestClient, wav_bytes: bytes
) -> None:
    session = create_authorized_session(client)
    grant = upload_and_complete(client, session, wav_bytes)
    report = wait_for_report(client, session)
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    duplicate = client.post(
        f"/v1/practice-sessions/{session['session_id']}/recording-complete",
        headers=headers,
        json={
            "recording_id": grant["recording_id"],
            "mime_type": "audio/wav",
            "size_bytes": len(wav_bytes),
            "duration_ms": 60_000,
            "sha256": hashlib.sha256(wav_bytes).hexdigest(),
            "response_started_at": "2026-07-14T10:00:00Z",
            "response_ended_at": "2026-07-14T10:01:00Z",
        },
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["status"] == "completed"
    still_available = client.get(
        f"/v1/practice-sessions/{session['session_id']}/report", headers=headers
    )
    assert still_available.status_code == 200
    assert still_available.json()["session_id"] == report["session_id"]


def test_failed_processing_can_retry_without_recording_again(
    client: TestClient, wav_bytes: bytes
) -> None:
    processor = client.app.state.processor
    delegate = MockEvaluationProvider()

    class FailOnceEvaluationProvider:
        calls = 0

        async def evaluate(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("simulated provider outage")
            return await delegate.evaluate(**kwargs)

    processor.evaluator = FailOnceEvaluationProvider()
    session = create_authorized_session(client)
    upload_and_complete(client, session, wav_bytes)
    headers = {"Authorization": f"Bearer {session['session_token']}"}

    deadline = time.monotonic() + 5
    failed = None
    while time.monotonic() < deadline:
        status = client.get(
            f"/v1/practice-sessions/{session['session_id']}", headers=headers
        ).json()
        if status["status"] == "failed":
            failed = status
            break
        time.sleep(0.025)
    assert failed is not None
    assert failed["can_retry"] is True

    retried = client.post(f"/v1/practice-sessions/{session['session_id']}/retry", headers=headers)
    assert retried.status_code == 200
    report = wait_for_report(client, session)
    assert report["session_id"] == session["session_id"]

    already_completed = client.post(
        f"/v1/practice-sessions/{session['session_id']}/retry", headers=headers
    )
    assert already_completed.status_code == 200
    assert already_completed.json()["status"] == "completed"
