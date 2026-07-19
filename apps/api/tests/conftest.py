from __future__ import annotations

import hashlib
import io
import time
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sample_data import SAMPLE_TASK_ID


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        ai_mode="demo",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        local_storage_path=tmp_path / "storage",
        session_token_pepper="test-session-pepper-with-more-than-32-characters",  # noqa: S106
        upload_signing_secret="test-upload-signing-secret-with-32-characters",  # noqa: S106
        teacher_validation_token="teacher-test-token",  # noqa: S106
        public_api_url="http://testserver",
        cors_allowed_origins=["http://testserver"],
        trusted_hosts=["testserver"],
        worker_poll_seconds=0.01,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * 16_000)
    return buffer.getvalue()


def create_authorized_session(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/v1/practice-sessions",
        json={
            "task_id": SAMPLE_TASK_ID,
            "recording_consent": True,
            "consent_policy_version": "test-v1",
        },
    )
    assert response.status_code == 201
    return response.json()


def upload_and_complete(
    client: TestClient, session: dict[str, Any], content: bytes
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    grant_response = client.post(
        f"/v1/practice-sessions/{session['session_id']}/upload-url",
        headers=headers,
        json={"mime_type": "audio/wav", "extension": "wav"},
    )
    assert grant_response.status_code == 200
    grant = grant_response.json()
    upload_response = client.put(
        f"/v1/uploads/{grant['recording_id']}",
        headers={"X-Upload-Token": grant["upload_token"], "Content-Type": "audio/wav"},
        content=content,
    )
    assert upload_response.status_code == 204
    completion = client.post(
        f"/v1/practice-sessions/{session['session_id']}/recording-complete",
        headers=headers,
        json={
            "recording_id": grant["recording_id"],
            "mime_type": "audio/wav",
            "size_bytes": len(content),
            "duration_ms": 60_000,
            "sha256": hashlib.sha256(content).hexdigest(),
            "response_started_at": "2026-07-14T10:00:00Z",
            "response_ended_at": "2026-07-14T10:01:00Z",
        },
    )
    assert completion.status_code == 202
    return grant


def wait_for_report(client: TestClient, session: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = client.get(f"/v1/practice-sessions/{session['session_id']}", headers=headers)
        assert status.status_code == 200
        if status.json()["status"] == "completed":
            report = client.get(
                f"/v1/practice-sessions/{session['session_id']}/report",
                headers=headers,
            )
            assert report.status_code == 200
            return report.json()
        time.sleep(0.025)
    pytest.fail("demo processing did not complete")
