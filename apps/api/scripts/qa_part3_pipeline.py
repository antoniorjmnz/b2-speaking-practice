from __future__ import annotations

import argparse
import hashlib
import json
import time
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from supabase import create_client

from app.config import Settings

PART3_TASK_ID = "e5555555-5555-4555-8555-555555555555"


def require_ok(response: httpx.Response, step: str) -> dict[str, Any]:
    if response.is_error:
        raise RuntimeError(f"{step}: HTTP {response.status_code}: {response.text[:1_000]}")
    return response.json() if response.content else {}


def wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as audio:
        return round(audio.getnframes() / audio.getframerate() * 1_000)


def upload_recording(
    *,
    client: httpx.Client,
    storage: Any,
    session_id: str,
    auth: dict[str, str],
    path: Path,
    recording_kind: str,
) -> None:
    content = path.read_bytes()
    grant = require_ok(
        client.post(
            f"/v1/practice-sessions/{session_id}/upload-url",
            headers=auth,
            json={
                "mime_type": "audio/wav",
                "extension": "wav",
                "recording_kind": recording_kind,
            },
        ),
        f"authorize {recording_kind}",
    )
    if grant["provider"] == "local":
        response = httpx.put(
            grant["upload_url"],
            headers={
                "X-Upload-Token": grant["upload_token"],
                "Content-Type": "audio/wav",
            },
            content=content,
            timeout=120,
        )
        if response.is_error:
            raise RuntimeError(
                f"upload {recording_kind}: HTTP {response.status_code}: {response.text[:500]}"
            )
    else:
        if not grant.get("bucket"):
            raise RuntimeError(f"upload {recording_kind}: missing Supabase bucket")
        if storage is None:
            raise RuntimeError(
                f"upload {recording_kind}: Supabase credentials are unavailable for QA"
            )
        storage.from_(grant["bucket"]).upload_to_signed_url(
            grant["storage_path"],
            grant["upload_token"],
            content,
            {"content-type": "audio/wav"},
        )

    duration_ms = wav_duration_ms(path)
    ended_at = datetime.now(UTC)
    started_at = ended_at - timedelta(milliseconds=duration_ms)
    require_ok(
        client.post(
            f"/v1/practice-sessions/{session_id}/recording-complete",
            headers=auth,
            json={
                "recording_id": grant["recording_id"],
                "mime_type": "audio/wav",
                "size_bytes": len(content),
                "duration_ms": duration_ms,
                "sha256": hashlib.sha256(content).hexdigest(),
                "response_started_at": started_at.isoformat(),
                "response_ended_at": ended_at.isoformat(),
            },
        ),
        f"complete {recording_kind}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real public Part 3 pair pipeline.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
    )
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=Path("../../experiments/whisperx/sample"),
    )
    parser.add_argument("--timeout", type=float, default=720)
    args = parser.parse_args()

    settings = Settings()
    storage = (
        create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        ).storage
        if settings.supabase_url and settings.supabase_service_role_key
        else None
    )

    reference_a = args.sample_dir / "candidate-a-reference.wav"
    reference_b = args.sample_dir / "candidate-b-reference.wav"
    pair_audio = args.sample_dir / "two-speaker-part3.wav"
    for path in (reference_a, reference_b, pair_audio):
        if not path.is_file():
            raise SystemExit(f"Missing QA audio: {path}")

    session: dict[str, Any] | None = None
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        try:
            task = require_ok(client.get(f"/v1/tasks/{PART3_TASK_ID}"), "fetch task")
            if not task.get("diarization_available"):
                raise RuntimeError("The public API reports diarization unavailable")
            session = require_ok(
                client.post(
                    "/v1/practice-sessions",
                    json={
                        "task_id": PART3_TASK_ID,
                        "recording_consent": True,
                        "consent_policy_version": "qa-part3-v1",
                    },
                ),
                "create session",
            )
            session_id = session["session_id"]
            auth = {"Authorization": f"Bearer {session['session_token']}"}

            upload_recording(
                client=client,
                storage=storage,
                session_id=session_id,
                auth=auth,
                path=reference_a,
                recording_kind="candidate_a_reference",
            )
            upload_recording(
                client=client,
                storage=storage,
                session_id=session_id,
                auth=auth,
                path=reference_b,
                recording_kind="candidate_b_reference",
            )
            require_ok(
                client.post(
                    f"/v1/practice-sessions/{session_id}/part3-events",
                    headers=auth,
                    json={
                        "events": [
                            {
                                "sequence": 0,
                                "phase": "discussion",
                                "speaker": "examiner",
                                "started_at_ms": 0,
                                "ended_at_ms": 0,
                                "text": task["examiner_instruction"],
                                "move": "opens_discussion",
                            },
                            {
                                "sequence": 1,
                                "phase": "decision",
                                "speaker": "examiner",
                                "started_at_ms": 90_000,
                                "ended_at_ms": 90_000,
                                "text": task["decision_question"],
                                "move": "opens_decision",
                            },
                        ]
                    },
                ),
                "save examiner events",
            )
            upload_recording(
                client=client,
                storage=storage,
                session_id=session_id,
                auth=auth,
                path=pair_audio,
                recording_kind="pair_response",
            )

            deadline = time.monotonic() + args.timeout
            last_stage = ""
            status: dict[str, Any] = {}
            while time.monotonic() < deadline:
                status = require_ok(
                    client.get(f"/v1/practice-sessions/{session_id}", headers=auth),
                    "poll session",
                )
                stage = str(status["processing_stage"])
                if stage != last_stage:
                    print(f"stage={stage}", flush=True)
                    last_stage = stage
                if status["status"] in {"completed", "failed"}:
                    break
                time.sleep(2)
            else:
                raise TimeoutError(f"Part 3 processing exceeded {args.timeout:.0f} seconds")
            if status["status"] != "completed":
                raise RuntimeError(
                    f"Part 3 failed at {status['processing_stage']}: "
                    f"{status.get('error_message_es')}"
                )

            reports = {
                candidate: require_ok(
                    client.get(
                        f"/v1/practice-sessions/{session_id}/report",
                        headers=auth,
                        params={"candidate": candidate},
                    ),
                    f"fetch candidate {candidate} report",
                )
                for candidate in ("A", "B")
            }
            transcript_text = {
                candidate: " ".join(segment["text"] for segment in report["transcript"]).strip()
                for candidate, report in reports.items()
            }
            if not transcript_text["A"] or not transcript_text["B"]:
                raise RuntimeError("One candidate received an empty transcript")
            if transcript_text["A"] == transcript_text["B"]:
                raise RuntimeError("Candidate reports contain the same transcript")
            result = {
                "result": "completed",
                "diarization_available": task["diarization_available"],
                "distinct_transcripts": True,
                "candidates": {
                    candidate: {
                        "evaluation_status": report["evaluation_status"],
                        "transcript_segments": len(report["transcript"]),
                        "transcript_words": len(transcript_text[candidate].split()),
                        "transcript_fingerprint": hashlib.sha256(
                            transcript_text[candidate].encode("utf-8")
                        ).hexdigest()[:12],
                        "overall_confidence": report["overall_confidence"],
                        "interactive_band": (report.get("interactive_communication") or {}).get(
                            "practice_band"
                        ),
                    }
                    for candidate, report in reports.items()
                },
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        finally:
            if session is not None:
                client.delete(
                    f"/v1/practice-sessions/{session['session_id']}",
                    headers={"Authorization": f"Bearer {session['session_token']}"},
                )


if __name__ == "__main__":
    raise SystemExit(main())
