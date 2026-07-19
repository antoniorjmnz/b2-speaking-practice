from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.sample_data import SAMPLE_TASK_ID


def require_ok(response: httpx.Response, step: str) -> dict[str, Any]:
    if response.is_error:
        detail = response.text[:1_000]
        raise RuntimeError(f"{step}: HTTP {response.status_code}: {detail}")
    if not response.content:
        return {}
    return response.json()


def run_case(
    client: httpx.Client,
    settings: Settings,
    name: str,
    path: Path,
    duration_ms: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    session: dict[str, Any] | None = None
    try:
        session = require_ok(
            client.post(
                "/v1/practice-sessions",
                json={
                    "task_id": SAMPLE_TASK_ID,
                    "recording_consent": True,
                    "consent_policy_version": "qa-real-v1",
                },
            ),
            "create session",
        )
        session_id = session["session_id"]
        auth = {"Authorization": f"Bearer {session['session_token']}"}
        grant = require_ok(
            client.post(
                f"/v1/practice-sessions/{session_id}/upload-url",
                headers=auth,
                json={"mime_type": "audio/wav", "extension": "wav"},
            ),
            "authorize upload",
        )
        content = path.read_bytes()
        require_ok(
            client.put(
                grant["upload_url"],
                headers={
                    "X-Upload-Token": grant["upload_token"],
                    "Content-Type": "audio/wav",
                },
                content=content,
            ),
            "upload recording",
        )
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
            "complete recording",
        )

        deadline = time.monotonic() + timeout_seconds
        status: dict[str, Any] = {}
        while time.monotonic() < deadline:
            status = require_ok(
                client.get(f"/v1/practice-sessions/{session_id}", headers=auth),
                "poll session",
            )
            if status["status"] in {"completed", "failed"}:
                break
            time.sleep(1)
        else:
            raise TimeoutError(f"processing exceeded {timeout_seconds:.0f} seconds")
        if status["status"] != "completed":
            raise RuntimeError(
                f"processing failed at {status['processing_stage']}: "
                f"{status.get('error_message_es')}"
            )

        report = require_ok(
            client.get(f"/v1/practice-sessions/{session_id}/report", headers=auth),
            "fetch student report",
        )
        validation = require_ok(
            client.get(
                f"/v1/internal/practice-sessions/{session_id}/validation",
                headers={"Authorization": f"Bearer {settings.teacher_validation_token}"},
            ),
            "fetch teacher validation",
        )
        checks = {item["key"]: item["status"] for item in report["task_performance"]}
        transcript = " ".join(segment["text"] for segment in report["transcript"])
        return {
            "case": name,
            "result": "completed",
            "duration_ms": duration_ms,
            "evaluation_status": report["evaluation_status"],
            "overall_confidence": report["overall_confidence"],
            "transcript_words": len(transcript.split()),
            "transcript_preview": transcript[:300],
            "strengths": len(report["strengths"]),
            "priority_improvements": len(report["priority_improvements"]),
            "task_checks": checks,
            "pronunciation_available": report["pronunciation"]["available"],
            "pronunciation_reason": report["pronunciation"]["withheld_reason_es"],
            "models": validation["model_snapshot"],
            "objective_metrics": validation["objective_metrics"],
        }
    except Exception as exc:  # noqa: BLE001 - QA harness must report every case
        return {"case": name, "result": "failed", "error": str(exc)}
    finally:
        if session is not None:
            client.delete(
                f"/v1/practice-sessions/{session['session_id']}",
                headers={"Authorization": f"Bearer {session['session_token']}"},
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise the real AI pipeline safely.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--audio-dir", type=Path, default=Path("work/qa"))
    parser.add_argument("--output", type=Path, default=Path("work/qa/real-pipeline-results.json"))
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument(
        "--case",
        action="append",
        choices=["good", "bad_off_topic", "too_short", "silence"],
        help="Run only the selected case; repeat the option to select several.",
    )
    args = parser.parse_args()

    settings = Settings()
    if settings.ai_mode != "real" or not settings.teacher_validation_token:
        raise SystemExit("The API must be configured in real mode with a teacher token.")
    cases = [
        ("good", args.audio_dir / "good.wav", 57_540),
        ("bad_off_topic", args.audio_dir / "bad.wav", 26_610),
        ("too_short", args.audio_dir / "short.wav", 4_510),
        ("silence", args.audio_dir / "silence.wav", 8_000),
    ]
    if args.case:
        cases = [case for case in cases if case[0] in args.case]
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        results = [
            run_case(client, settings, name, path, duration, args.timeout)
            for name, path, duration in cases
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result["result"] == "completed" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
